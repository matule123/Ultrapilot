"""Uncalibrated delayed along-route plant through actual Map and physical writer.

GPS distance is to the modeled truck reference, not a bumper/painted stop line.
Native zero/removal never means successful arrival. No game mapping is opened.
"""
import argparse
import ast
from contextlib import ExitStack, contextmanager
from collections import deque
import json
import math
from pathlib import Path
from unittest.mock import patch

from tests.test_activation_observation_binding import flow
from tests.test_rolling_longitudinal_authority import rolling
from tests.test_longitudinal_arbitration import strict_flow
from core import engine as engine_module, service_brake_hold, longitudinal
from plugins.acc import main as acc_module
from plugins.drivepolicy import main as policy_module
from plugins.autopilot import main as ap_module


def baseline(stack):
    root = Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')
    for relative, module, owner, names in (
        ('core/engine.py', engine_module, engine_module.UltraPilotEngine, ('_flush_controls_unlocked',)),
        ('core/longitudinal.py', longitudinal, longitudinal, ('_engine_decision', 'planned_braking_input')),
        ('core/service_brake_hold.py', service_brake_hold, service_brake_hold,
            ('planned_stop', 'after_write', 'profile_approach_allowed')),
        ('plugins/acc/main.py', acc_module, acc_module.Plugin, ('on_tick',)),
        ('plugins/drivepolicy/main.py', policy_module, policy_module.Plugin, ('on_tick', '_compute_planned_speed')),
        ('plugins/autopilot/main.py', ap_module, ap_module.Plugin, ('on_tick',))):
        source = (root/relative).read_text(encoding='utf-8-sig')
        nodes = {n.name:n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.FunctionDef)}
        for name in names:
            namespace = {}
            exec(compile(ast.Module(body=[nodes[name]], type_ignores=[]), str(root/relative), 'exec'),
                 vars(module), namespace)
            stack.enter_context(patch.object(owner, name, namespace[name]))


def run(speed, mode, *, before=False):
    with ExitStack() as stack:
        if before: baseline(stack)
        raw = stack.enter_context(contextmanager(flow.__wrapped__)())
        stack.enter_context(patch('tests.test_rolling_longitudinal_authority.strict_flow',
            side_effect=lambda value: strict_flow(value, mode=mode)))
        state, engine, ap, acc, policy, tick, observe, n, physical, writes, clock = \
            stack.enter_context(contextmanager(rolling.__wrapped__)(raw))
        assert engine._active_transmission_mode == mode
        truck = raw[1]
        # The live validated Map route is 280 m; the explicit modeled GPS goal
        # is 240 m. No local corridor end is substituted for GPS destination.
        goal, s, v, t = 240., 20., speed/3.6, 0.
        state.set('game_gps_navigation_active', True)
        state.set('acc_target_speed', speed)
        applied_t = applied_b = held_t = held_b = 0.
        delayed = deque(); rows = []
        for i in range(1800):
            dt = 1/30
            old_v = v
            for j in range(4):
                h = dt/4
                while delayed and delayed[0][0] <= t+j*h:
                    _, held_t, held_b = delayed.popleft()
                alpha = 1.-math.exp(-h/.35)
                applied_t += alpha*(held_t-applied_t)
                applied_b += alpha*(held_b-applied_b)
                a = (2.2*applied_t-4.*applied_b)/1.4-.12-.004*v*v
                v = max(0., v+a*h); s += v*h
            t += dt
            truck['routeDistance'] = max(0., goal-s)
            state.set('navigation_arrival_pending', 0.<goal-s<=35.)
            tick(gear=0 if mode==0 and v<.05 else 8, speed=v, z=s)
            # Same-controller source/output order; fixed 30 Hz model, not a
            # claim about live scheduler latency. Map is the actual producer.
            engine._flush_controls()
            throttle, brake = physical('aforward'), physical('abackward')
            delayed.append((t+.12, throttle, brake))
            rows.append(dict(t=t, dt=dt, distance_m=goal-s, speed_kmh=v*3.6,
                target_kmh=(state.get('longitudinal_acc') or {}).get('constrained_speed_kmh'),
                throttle=throttle, brake=brake, acceleration=(v-old_v)/dt,
                hold=(state.get('simple_auto_service_hold') or {}).get('phase'),
                state=state.get('autopilot_control_state')))
            if not state.get('autopilot_active') or s>=goal:
                break
        active_modes = ['brake' if r['brake']>0 else 'drive' for r in rows
                        if r['brake']>0 or r['throttle']>0]
        return dict(speed=speed, mode=mode, samples=len(rows), duration_s=t,
            final_reference_gap_m=goal-s, final_speed_kmh=v*3.6,
            state=state.get('autopilot_control_state'), reason=state.get('autopilot_disable_reason'),
            brake_onset_distance_m=next((r['distance_m'] for r in rows if r['brake']>.02),None),
            maximum_deceleration_mps2=max(-r['acceleration'] for r in rows),
            maximum_jerk_mps3=max(abs((b['acceleration']-a['acceleration'])/b['dt'])
                                  for a,b in zip(rows,rows[1:])),
            low_speed_far_s=sum(r['dt'] for r in rows if r['distance_m']>10. and r['speed_kmh']<5.),
            pedal_changes=sum(a!=b for a,b in zip(active_modes,active_modes[1:])),
            positive_overlap=sum(r['throttle']>0 and r['brake']>0 for r in rows),
            rows=rows, writes=writes)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--before', action='store_true')
    args=parser.parse_args(); result={}
    args.output.mkdir(parents=True,exist_ok=True)
    for speed in (20.,35.,50.):
        for mode in (0,3):
            case=run(speed,mode,before=args.before)
            name=f'{speed:g}-{mode}'
            (args.output/(name+'.json')).write_text(json.dumps(case)+'\n')
            result[name]={k:v for k,v in case.items() if k not in ('rows','writes')}
            print(name,json.dumps(result[name]),flush=True)
    (args.output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
