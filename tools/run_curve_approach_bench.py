"""Reproduce the R19 preview/commit fix using production pedal operations.

Explicit along-path plant, NOT an ETS2 measurement or a lateral simulation.
Real Policy, ACC, Autopilot, Engine, Controller and SCS float mapping writes;
only the SDK/steering-authority harness is isolated. No game/device is opened.
"""
import argparse
from collections import deque
import json
import math
from pathlib import Path
import random
import struct
import subprocess
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.engine import UltraPilotEngine
from core.longitudinal import curve_preview_horizon_m
from core.navigation.route import Route
from sdk.plugin_sdk import PluginSDK
from tests.test_activation_observation_binding import flow
from tests.test_longitudinal_arbitration import strict_flow
from tests.test_longitudinal_evidence_diagnostics import memory_controller


def module_at(ref, path):
    name = 'curve_bench_' + path.replace('/', '_').replace('.', '_')
    module = types.ModuleType(name)
    module.__file__ = str(ROOT / path)
    sys.modules[name] = module
    source = subprocess.check_output(['git', 'show', f'{ref}:{path}'], cwd=ROOT).decode('utf-8')
    exec(compile(source, f'{ref}/{path}', 'exec'), module.__dict__)
    return module


def run(*, baseline=False, direction=1, load=1.4, jitter=False,
        baseline_ref='b9fb484', radius=19., roundabout=False,
        custom_points=None, entry_points=()):
    if baseline:
        Policy = module_at(baseline_ref, 'plugins/drivepolicy/main.py').Plugin
        ACC = module_at(baseline_ref, 'plugins/acc/main.py').Plugin
        AP = module_at(baseline_ref, 'plugins/autopilot/main.py').Plugin
        Engine = module_at(baseline_ref, 'core/engine.py').UltraPilotEngine
        Map = module_at(baseline_ref, 'plugins/map/main.py').Plugin
        # Bind the old producer functions to their actual old longitudinal
        # implementation, rather than inadvertently importing the candidate.
        old_core = module_at(baseline_ref, 'core/longitudinal.py')
        for cls in (Policy, ACC, AP):
            namespace = sys.modules[cls.__module__].__dict__
            for name in tuple(namespace):
                if callable(namespace[name]) and getattr(namespace[name], '__module__', '') == 'core.longitudinal':
                    if hasattr(old_core, name):
                        namespace[name] = getattr(old_core, name)
    else:
        from plugins.drivepolicy.main import Plugin as Policy
        from plugins.acc.main import Plugin as ACC
        from plugins.autopilot.main import Plugin as AP
        from plugins.map.main import Plugin as Map
        Engine = UltraPilotEngine
    points = [(0., float(z)) for z in range(201)]
    points += [(direction*radius*(1.-math.cos(i*math.pi/240.)),
                200.+radius*math.sin(i*math.pi/240.)) for i in range(1, 121)]
    points += [(direction*(radius+i), 200.+radius) for i in range(1, 91)]
    if custom_points is not None:
        points = custom_points
    route = Route(points)
    generator = flow.__wrapped__()
    harness = next(generator)
    state, truck, engine, _, update, n, clock, _ = strict_flow(harness, mode=3)
    engine.__class__ = Engine
    engine.controller = memory_controller()
    ap, acc = AP(PluginSDK(state.values, 'autopilot')), ACC(PluginSDK(state.values, 'acc'))
    policy = Policy(PluginSDK(state.values, 'drivepolicy'))
    ap.on_start(); acc.on_start(); policy.on_start()
    state.set('acc_target_speed', 50.)
    v, s, t = 50./3.6, 0., 0.
    actuator_t = actuator_b = held_t = held_b = 0.
    queue = deque()
    rng = random.Random(7103)
    records = []
    def pedal(channel):
        return struct.unpack_from('f', engine.controller.scs._buf.getvalue(),
                                  engine.controller.scs._offsets[channel])[0]
    try:
        update(8, v)
        n()
        while s < (max(entry_points)+10. if entry_points else 220.) and t < 100.:
            dt = rng.choice([.025, .04, .05, .08]) if jitter else .05
            previous_v = v
            steps = math.ceil(dt/.01)
            for j in range(steps):
                h = dt/steps
                while queue and queue[0][0] <= t+j*h:
                    _, held_t, held_b = queue.popleft()
                alpha = 1.-math.exp(-h/.35)
                actuator_t += alpha*(held_t-actuator_t)
                actuator_b += alpha*(held_b-actuator_b)
                a = (2.2*actuator_t-4.*actuator_b)/load - .12 - .004*v*v
                v = max(0., v+a*h)
                s += v*h
            t += dt
            update(8, v, dt=dt)
            position = route._point_at_progress(s)
            ahead = route._point_at_progress(s+.1)
            heading = math.atan2(-(ahead[0]-position[0]), -(ahead[1]-position[1]))
            horizon = 60. if baseline and baseline_ref == 'b9fb484' else curve_preview_horizon_m(v, 50.)
            curve = (route.curve_profile_ahead(position, heading, horizon) if baseline else
                     route.curve_profile_ahead(position, heading, horizon, speed_ms=v))
            packet = state.get('nav_steering_debug')
            lane = state.get('lane_trajectory')
            if roundabout:
                lane['turn_events'] = [dict(kind='roundabout', start_s_m=200.,
                                          end_s_m=200.+radius*math.pi/2.)]
                operation = getattr(Map, '_roundabout_speed_profile', None)
                if operation:
                    curve = operation(lane, curve, route.tracking_progress(position, heading))
            packet.update(trajectory_identity={k: lane[k] for k in (
                'navigation_intent_id', 'revision', 'route_build_id',
                'source_game_session_id', 'source_map_key', 'source_dataset_fingerprint')},
                longitudinal_curve_profile=curve)
            state.set('nav_steering_debug', packet)
            policy.on_tick(dt); acc.on_tick(dt); ap.on_tick(dt)
            engine._flush_controls()
            if state.get('autopilot_control_state') == 'controlled_stop' or not state.get('autopilot_active'):
                raise AssertionError(state.get('automatic_safety_stop_reason') or state.get('autopilot_disable_reason'))
            throttle, brake = pedal('aforward'), pedal('abackward')
            assert throttle == 0 or brake == 0
            queue.append((t+.12, throttle, brake))
            records.append(dict(t=t, s=s, speed_kmh=v*3.6, throttle=throttle, brake=brake,
                acceleration_mps2=(v-previous_v)/dt, dt=dt, curve=curve,
                target_kmh=state.get('longitudinal_acc')['constrained_speed_kmh']))
    finally:
        generator.close()
    braking = next((r for r in records if r['brake'] > .02), None)
    entry = next((r for r in records if r['s'] >= 200.), None)
    jerks = [(b['acceleration_mps2']-a['acceleration_mps2'])/b['dt']
             for a,b in zip(records, records[1:])]
    return dict(samples=len(records), duration_s=t, direction=direction, load=load, jitter=jitter,
        entry_samples={str(entry): next((dict(s=r['s'], speed_kmh=r['speed_kmh'],
            throttle=r['throttle'], brake=r['brake'], target_kmh=r['target_kmh'])
            for r in records if r['s'] >= entry), None) for entry in entry_points},
        brake_start_distance_to_entry_m=200.-braking['s'] if braking else None,
        entry_speed_kmh=entry['speed_kmh'] if entry else None,
        entry_overspeed_kmh=max(0.,entry['speed_kmh']-min(35. if roundabout else float('inf'), math.sqrt(1.8*radius)*3.6)) if entry else None,
        first_35_distance_to_entry_m=next((200.-r['s'] for r in records if r['speed_kmh'] <= 35.), None),
        maximum_deceleration_mps2=max(-r['acceleration_mps2'] for r in records),
        maximum_abs_model_jerk_mps3=max(map(abs, jerks)),
        simultaneous_positive_pedals=sum(r['throttle']>0 and r['brake']>0 for r in records))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ref', default='b9fb484')
    parser.add_argument('--roundabout', action='store_true')
    parser.add_argument('--two-bends', action='store_true',
                        help='200 m approach, R40/30 m, 70 m gap, R15/25 m; not a measured roundabout')
    args = parser.parse_args()
    if args.roundabout and args.two_bends:
        parser.error('choose tagged roundabout or the untagged two-bend scenario')
    cases = [(d,l,j) for d in (-1,1) for l in (1.,1.4) for j in (False,True)]
    def points(direction):
        x = z = 0.
        heading = math.pi
        result = [(x, z)]
        for curvature, length in [(0.,200), (direction/40.,30), (0.,70), (direction/15.,25), (0.,30)]:
            for _ in range(length):
                heading -= curvature
                x -= math.sin(heading); z -= math.cos(heading)
                result.append((x,z))
        return result
    result = {str(case): {name: run(baseline=old, direction=case[0], load=case[1], jitter=case[2],
                                  baseline_ref=args.ref, radius=80. if args.roundabout else (40. if args.two_bends else 19.),
                                  roundabout=args.roundabout,
                                  custom_points=points(case[0]) if args.two_bends else None,
                                  entry_points=(200.,300.) if args.two_bends else ())
                         for name,old in [('baseline',True),('candidate',False)]} for case in cases}
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
