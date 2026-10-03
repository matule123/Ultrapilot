"""Same-seed route following comparison; uncalibrated longitudinal plant.

Uses actual raw-buffer decode, cached route selector, existing ACC/PID and
Autopilot pedal stages, paired arbitration and final Engine decision. Full
hotkey/physical-backend writes are exercised by test_acc_following, not this
plant. Exact synthetic poses on the path are NOT measured lane/coverage proof.
"""
import argparse
import ast
from collections import deque
import json
import math
from pathlib import Path
import random
import struct
import subprocess
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.engine import UltraPilotEngine
from core.longitudinal import context, publish, finalize, engine_decision
from core.navigation.traffic_producer import TrafficCapture
from core.sdk.ets2la_data import _TRAFFIC_FMT, _PARKED_FMT
from sdk.plugin_sdk import PluginSDK
from tools.run_longitudinal_comfort_bench import classes, percentile

BASELINE = '9ffd5ac'
CASES = [dict(name='slower_straight', radius=None),
         dict(name='slower_left', radius=60.), dict(name='slower_right', radius=-60.),
         dict(name='roundabout', radius=35.), dict(name='braking_lead', radius=None, braking=True),
         dict(name='cut_in', radius=83., cutin=True),
         dict(name='jitter_noise_heavy', radius=60., jitter=True, noise=.12, load=1.4)]


def point(s, radius):
    if radius is None:
        return [0., 0., -s], 0.
    r = abs(radius)
    direction = 1. if radius > 0 else -1.
    # Half circle, then tangent straight; same XYZ geometry in both runs.
    angle = min(math.pi, s/r)
    x, z = direction*r*(1.-math.cos(angle)), -r*math.sin(angle)
    if s > r*math.pi:
        z += s-r*math.pi
    return [x, 0., z], -direction*angle


def raw_capture(actors, stamp):
    moving = [0.]*1840
    for i, (actor_id, xyz, yaw, speed) in enumerate(actors):
        b = i*46
        moving[b:b+12] = [*xyz, math.cos(yaw/2), 0., math.sin(yaw/2), 0.,
                           2., 2., 4., speed, 0.]
        moving[b+12:b+16] = [0, actor_id, 0, 0]
    for i in range(40):
        b = i*46
        moving[b+12:b+16] = [int(v) for v in moving[b+12:b+16]]
    parked = [0.]*480
    for i in range(40):
        parked[i*12+10:i*12+12] = [0, 0]
    return TrafficCapture('offline', stamp, struct.pack(_TRAFFIC_FMT, *moving),
                          struct.pack(_PARKED_FMT, *parked), True)


def legacy_brake():
    source = subprocess.check_output(['git', 'show', f'{BASELINE}:core/engine.py'], cwd=ROOT).decode('utf-8')
    cls = next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name == 'UltraPilotEngine')
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_lead_brake')
    namespace = {}
    exec(compile(ast.Module(body=[method], type_ignores=[]), '<baseline lead brake>', 'exec'), namespace)
    return namespace['_lead_brake']


def simulate(case, *, baseline=False):
    ACC, AP = classes(BASELINE if baseline else None)
    clock, rng = [1000.], random.Random(7301)
    points = [point(float(s), case['radius'])[0] for s in range(1801)]
    identity = dict(source_game_session_id='offline', source_map_key='offline',
        source_dataset_fingerprint='offline', navigation_intent_id='intent', revision=1, route_build_id='build')
    values = dict(longitudinal_control_schema=1, telemetry_control_schema=1,
        autopilot_active=True, autopilot_failure_epoch=1, game_session_id='offline',
        active_map_key='offline', active_dataset_fingerprint='offline',
        navigation_intent_id='intent', lane_trajectory_revision=1,
        lane_trajectory=dict(identity, valid=True, points=points),
        lane_trajectory_identity=identity, lane_trajectory_publication_token='geometry',
        system_state='CRUISE', acc_target_speed=70., acc_obey_limit=False)
    acc, ap = ACC(PluginSDK(values, 'acc')), AP(PluginSDK(values, 'autopilot'))
    engine = UltraPilotEngine.__new__(UltraPilotEngine)
    engine.shared_state = acc.sdk.shared_state
    brake_law = legacy_brake() if baseline else None
    speed, progress, lead_progress, lead_speed = 15., 0., 55., 10.
    actuator_drive = actuator_brake = drive = brake = 0.
    queue, rows = deque(), []
    last_id, switches = None, 0
    t, cut_progress, frame = 0., None, 10000
    with patch('time.monotonic', side_effect=lambda: clock[0]):
        acc.on_start()
        ap.on_start()
        while t < 70.:
            dt = rng.choice([.02, .05, .08, .12]) if case.get('jitter') else .05
            lead_speed = max(5., 10.-max(0., t-20.)*1.5) if case.get('braking') else 10.
            steps = math.ceil(dt/.01)
            for j in range(steps):
                h = dt/steps
                at = t+j*h
                while queue and queue[0][0] <= at:
                    _, drive, brake = queue.popleft()
                alpha = 1.-math.exp(-h/.35)
                actuator_drive += alpha*(drive-actuator_drive)
                actuator_brake += alpha*(brake-actuator_brake)
                a = (2.2*actuator_drive-4.*actuator_brake)/case.get('load', 1.)-.12-.004*speed*speed
                speed = max(0., speed+a*h)
                progress += speed*h
                lead_progress += lead_speed*h
                if cut_progress is not None:
                    cut_progress += 6.*h
            t += dt
            clock[0] += dt
            frame += round(dt*1e6)
            if case.get('cutin') and t >= 15. and cut_progress is None:
                cut_progress = progress+25.
            ego_xyz, heading = point(progress, case['radius'])
            lead_xyz, lead_yaw = point(lead_progress, case['radius'])
            actors = [(7, lead_xyz, lead_yaw, lead_speed)]
            if cut_progress is not None:
                cut_xyz, cut_yaw = point(cut_progress, case['radius'])
                actors.append((8, cut_xyz, cut_yaw, 6.))
            observed_speed = max(0., speed+rng.gauss(0., case.get('noise', 0.)/3.6))
            truck = dict(speed=observed_speed, speedLimit=0., gear=8, parkBrake=False,
                x=ego_xyz[0], y=ego_xyz[1], z=ego_xyz[2], rotation=heading,
                sdkFrameTimeUs=frame, _control_observation=dict(schema_version=1, valid=True,
                    sdk_frame_us=frame, observed_at=clock[0]))
            values['telemetry'] = {'truck': truck}
            values['nav_steering_debug'] = dict(authority_valid=True, trajectory_identity=identity,
                observation_timestamp=clock[0], tracking_progress_m=progress)
            raw = raw_capture(actors, clock[0])
            if baseline:
                display = [dict(id=i, x=p[0], y=p[1], z=p[2], yaw=h, speed=v,
                                width=2., length=4.) for i, p, h, v in actors]
                traffic_brake = brake_law(engine, display, (truck['x'], truck['z']), heading, observed_speed)
                following = None
                target_id = None
                distance = values.get('lead_distance')
                for i, p, _, _ in actors:
                    ahead = -(p[0]-truck['x'])*math.sin(heading)-(p[2]-truck['z'])*math.cos(heading)
                    if distance is not None and abs(ahead-distance) < 1e-5:
                        target_id = str(i)
            else:
                following = engine._route_lead_observation(raw, truck, context(engine.shared_state))
                assert following['status'] == 'candidate', (case, t, following)
                traffic_brake = 1. if following['emergency'] else 0.
                target_id = following['target_id']
            if last_id is not None and target_id != last_id:
                switches += 1
            last_id = target_id
            publish(engine.shared_state, truck, 'traffic', traffic_brake=traffic_brake,
                    light_brake=0., light=None, following=following)
            acc.on_tick(dt)
            request = values['longitudinal_acc']
            emergency = request.get('emergency') or traffic_brake > .7
            demand = max(request['brake'], traffic_brake)
            ap._longitudinal_decision = dict(source='acc', reason='following model', emergency=emergency)
            ap._set_brake(1. if emergency else demand, min(dt, .1))
            ap._apply_throttle(request['throttle'] if demand == 0 else 0., min(dt, .1))
            finalize(engine.shared_state, truck, ap._last_throttle, ap._last_brake,
                     ap._longitudinal_decision, context(engine.shared_state))
            output, reason = engine_decision(engine.shared_state, truck)
            assert not reason, (case['name'], t, reason)
            queue.append((t+.12, output['throttle'], output['brake']))
            gap = min(lead_progress-progress, cut_progress-progress if cut_progress is not None else math.inf)
            reference_speed = 6. if cut_progress is not None else lead_speed
            rows.append(dict(t=t, dt=dt, gap=gap, headway=gap/speed if speed > .1 else None,
                             error=(speed-reference_speed)*3.6, throttle=output['throttle'],
                             brake=output['brake'], selected=target_id, emergency=bool(emergency)))
            if gap <= 0:
                break
    steady = [r for r in rows if r['t'] >= 50.]
    gaps = [r['gap'] for r in rows]
    return dict(samples=len(rows), duration_s=rows[-1]['t'], min_reference_gap_m=min(gaps),
        final_gap_m=gaps[-1], min_time_headway_s=min(r['headway'] for r in rows if r['headway'] is not None),
        speed_error_rms_kmh=math.sqrt(sum(r['error']**2 for r in rows)/len(rows)),
        steady_speed_error_rms_kmh=(math.sqrt(sum(r['error']**2 for r in steady)/len(steady)) if steady else None),
        target_switches=switches, target_absent_samples=sum(r['selected'] is None for r in rows),
        reference_collision=min(gaps) <= 0, emergency_samples=sum(r['emergency'] for r in rows),
        emergency_engine_reaction_s=0. if any(r['emergency'] and r['brake'] == 1. for r in rows) else None,
        backend_queue_delay_s=.12, max_observation_age_s=0.)


def costs():
    from core.acc_following import observation, RouteLeadSelector
    from time import perf_counter
    points = [point(float(s), 60.)[0] for s in range(1801)]
    selector = RouteLeadSelector()
    start = perf_counter()
    selector.prepare(points, ('offline',))
    preparation = perf_counter()-start
    actors = [(i, *point(float(10+i*2), 60.), 8.) for i in range(40)]
    capture = raw_capture(actors, time.monotonic())
    times = []
    for _ in range(100):
        start = perf_counter()
        capture = TrafficCapture(capture.session, start, capture.moving, capture.parked, True)
        decoded = observation(capture, start)
        selector.select(decoded['actors'], dict(x=0., y=0., z=0., rotation=0., speed=12.), 0.)
        times.append((perf_counter()-start)*1000.)
    return dict(route_points=len(points), route_prepare_ms=preparation*1000,
        actors=40, samples=len(times), receiver_decode_and_selection_median_ms=percentile(times, .5),
        p95_ms=percentile(times, .95), max_ms=max(times),
        limitation='in-process operation costs, not Engine cadence, game freshness or live IPC')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT):
        parser.error('output must stay in workspace')
    result = dict(baseline=BASELINE, seed=7301,
        limitation='Uncalibrated longitudinal model; perfect synthetic path pose, no body/coverage proof.',
        cases={c['name']: dict(before=simulate(c, baseline=True), after=simulate(c)) for c in CASES},
        costs=costs())
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
