"""Compare the Oct 8 installed core against the candidate, without game I/O.

The two real map placements are frozen source subsets, not fabricated heads.
Supplied SDK scenarios measure software writes. Closed-loop profiles use the
existing explicit, uncalibrated prefab plant, not ETS2 physics.
"""
import argparse
from contextlib import ExitStack
import hashlib
import json
import logging
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.engine import UltraPilotEngine
from core import longitudinal, service_brake_hold
from core.sdk.signal_snapshot import RouteSignalSelector
from tests.test_activation_observation_binding import flow
from tests.signals.test_stop_lifecycle import directed_stop
from tests.signals.test_signal_approach_consistency import actual_passage
from tests.test_roundabout_intervention_reporting import pedal
from tools.run_oct8_stop_lifecycle_bench import load
from tools.run_prefab_signal_bench import run as stop_model


def scenarios(directory, mode):
    gen = flow.__wrapped__(); harness = next(gen)
    try:
        values, step = directed_stop(harness, mode)
        state, truck, engine, ap, tick, n, clock, writes, collector = values
        lane = state.get('lane_trajectory')
        lane['points'] = [[0., 10., 100.], [0., 10., -50.]]
        lane['signal_passages']['passages'][0]['entry_progress_m'] = 110.
        truck['z'] = 100.; state.set('lane_trajectory', lane)
        state.set('lane_trajectory_publication_token', 'far')
        state.set('acc_target_speed', 10.)
        step(4, 10., color=2)  # ordinary ACC overspeed, red still beyond braking point
        start = len(writes); rows = []
        for _ in range(120):
            step(4, .97222, color=2)
            rows.append(dict(at=clock[0], throttle=pedal(engine, 'aforward'),
                brake=pedal(engine, 'abackward'), active=state.get('autopilot_active'),
                hold=(state.get('simple_auto_service_hold') or {}).get('phase')))
        pair = dict(aforward=0., abackward=0.); overlap = 0
        for _, channel, value, _ in writes[start:]:
            if channel in pair:
                pair[channel] = value
                overlap += pair['aforward'] > 0 and pair['abackward'] > 0
        far = dict(samples=len(rows), duration_s=rows[-1]['at']-rows[0]['at'],
            supplied_speed_mps=.97222, distance_not_simulated=True,
            positive_drive_ticks=sum(r['throttle'] > 0 for r in rows),
            positive_brake_ticks=sum(r['brake'] > 0 for r in rows),
            final_hold=rows[-1]['hold'], simultaneous_physical_pairs=overlap,
            final_active=rows[-1]['active'])
    finally: gen.close()
    gen = flow.__wrapped__(); harness = next(gen)
    try:
        values, step = directed_stop(harness, mode)
        state, truck, engine, ap, tick, n, clock, writes, collector = values
        step(4, 2., color=2); initial = pedal(engine, 'abackward')
        for speed in (.7, .2, .06, .01, 0.):
            step(4 if speed > .05 or mode == 3 else 0, speed, color=2)
        hold = dict(initial_decelerating_write=initial, holding_write=pedal(engine, 'abackward'),
            phase=(state.get('simple_auto_service_hold') or {}).get('phase'),
            active=state.get('autopilot_active'))
    finally: gen.close()
    admissions = []
    for placement in (0, 1):
        net, path, plan = actual_passage(directory, placement)
        p = path.points[0]
        result = RouteSignalSelector().select(
            dict(valid=True, lifecycle=1, generation=1, frame_us=1, observed_at=100., lights=[]),
            [[p.x, p.y, p.z] for p in path.points], 'p', ('a',),
            dict(x=p.x, y=p.y, z=p.z, rotation=p.heading), 0., plan)
        admissions.append(dict(placement=placement, map_semaphore_id=plan['passages'][0]['semaphore_id'],
            has_required_stop=bool(result.get('prefab_required')),
            reason=result.get('reason'), entry_xyz=plan['passages'][0]['entry_xyz']))
    return dict(far_profile=far, hold=hold, real_map_admissions=admissions)


def run(baseline, directory):
    paths = ('core/engine.py', 'core/longitudinal.py', 'core/service_brake_hold.py',
             'core/sdk/signal_snapshot.py')
    old = {p: load(baseline/p, 'oct8_common_baseline_'+str(i)) for i,p in enumerate(paths)}
    result = dict(baseline_root=str(baseline),
        baseline_hashes={p:hashlib.sha256((baseline/p).read_bytes()).hexdigest() for p in paths},
        candidate_hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},
        limitations='Supplied SDK speeds are inputs, not a closed-loop vehicle. Separate stop profiles '
                     'use the existing uncalibrated transport/actuator plant; writes are not ETS2 consumption.',
        cases={}, closed_loop={})
    for before in (True, False):
        with ExitStack() as stack:
            if before:
                for method in ('_flush_controls_unlocked', '_autopilot_activation_rejection_reason'):
                    stack.enter_context(patch.object(UltraPilotEngine, method,
                        getattr(old['core/engine.py'].UltraPilotEngine, method)))
                for method in ('select', '_prefab_candidate'):
                    stack.enter_context(patch.object(RouteSignalSelector, method,
                        getattr(old['core/sdk/signal_snapshot.py'].RouteSignalSelector, method)))
                stack.enter_context(patch.object(longitudinal, '_engine_decision', old['core/longitudinal.py']._engine_decision))
                stack.enter_context(patch.object(longitudinal, 'signal_stop_brake_request',
                    old['core/longitudinal.py'].signal_stop_brake_request))
                for method in ('planned_stop', 'after_write', 'fresh_moving_stop_request'):
                    stack.enter_context(patch.object(service_brake_hold, method,
                        getattr(old['core/service_brake_hold.py'], method)))
            for mode in (0, 3):
                label = 'before' if before else 'after'
                result['cases'][f'{mode}/{label}'] = scenarios(directory, mode)
                for speed in (20., 35., 50.):
                    profile = stop_model(directory, mode=mode, speed_kmh=speed, jitter=True,
                                         allow_rejection=True)
                    rows = profile['rows']
                    crawl = [(a,b) for a,b in zip(rows, rows[1:])
                             if .3 <= a['speed_mps'] <= 1.2 and a['red'] and b['red']]
                    profile['crawl_time_s'] = sum(b['t']-a['t'] for a,b in crawl)
                    profile['crawl_distance_m'] = sum(b['s']-a['s'] for a,b in crawl)
                    # Keep moving deceleration separate from numerical jerk
                    # around low-speed clamping/holding and subsequent launch.
                    moving = [abs((b['acceleration_mps2']-a['acceleration_mps2'])/b['dt'])
                        for a,b in zip(rows,rows[1:])
                        if a['red'] and b['red'] and min(a['speed_mps'],b['speed_mps'])>.5]
                    profile['maximum_abs_model_jerk_above_half_mps'] = max(moving, default=None)
                    result['closed_loop'][f'{mode}/{speed:g}/{label}'] = {
                        k:v for k,v in profile.items() if k not in ('rows','writes','captures')}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workdir', type=Path, required=True)
    args = parser.parse_args()
    for path in (args.output, args.workdir):
        if not path.resolve().is_relative_to(ROOT): parser.error('Outputs must remain in the workspace')
    args.workdir.mkdir(parents=True, exist_ok=False)
    logging.disable(logging.CRITICAL)
    result = run(args.baseline_runtime, args.workdir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__': main()
