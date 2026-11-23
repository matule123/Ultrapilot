"""Compare Oct 8 stop-source gaps through actual offline producers/SCS writes.

Baseline methods are loaded read-only from an explicitly supplied runtime.
SDK speeds are supplied incident-shaped inputs, not closed-loop game physics.
The separate prefab stop benchmark covers closed-loop deceleration/jerk.
"""
import argparse
from contextlib import ExitStack
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.engine import UltraPilotEngine
from core import service_brake_hold
from core.sdk.signal_snapshot import RouteSignalSelector
from tests.test_activation_observation_binding import flow
from tests.signals.test_stop_lifecycle import directed_stop
from tests.test_roundabout_intervention_reporting import pedal


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def scenario(mode):
    generator = flow.__wrapped__()
    harness = next(generator)
    try:
        values, step = directed_stop(harness, mode)
        state, truck, engine, ap, tick, n, clock, writes, collected = values
        rows = []
        # A qualified authored entry remains in the same route. Its live head
        # is absent; source demand briefly drops despite no green clearance.
        for index in range(48):
            speed = 2.9 - index * .01
            step(4, speed, missing=True, no_demand=index % 6 >= 3)
            rows.append(dict(t=clock[0], speed_mps=speed, gear=4,
                throttle=pedal(engine, 'aforward'), brake=pedal(engine, 'abackward'),
                hold=(state.get('simple_auto_service_hold') or {}).get('phase'),
                active=state.get('autopilot_active')))
        for speed in (.683, .194, .04, 0.):
            gear = 0 if speed < .05 and mode == 0 else 4
            step(gear, speed, missing=True, no_demand=True)
            rows.append(dict(t=clock[0], speed_mps=speed, gear=gear,
                throttle=pedal(engine, 'aforward'), brake=pedal(engine, 'abackward'),
                hold=(state.get('simple_auto_service_hold') or {}).get('phase'),
                active=state.get('autopilot_active')))
        modes = ['brake' if row['brake'] > 0 else 'drive' if row['throttle'] > 0 else 'coast'
                 for row in rows]
        nonzero = [mode for mode in modes if mode != 'coast']
        result = dict(samples=len(rows), duration_s=rows[-1]['t']-rows[0]['t'],
            supplied_observation_model=True,
            drive_brake_transitions=sum(a != b for a, b in zip(nonzero, nonzero[1:])),
            coast_ticks=modes.count('coast'), propulsion_without_clearance=modes.count('drive'),
            simultaneous_pedals=sum(r['throttle'] > 0 and r['brake'] > 0 for r in rows),
            final_active=rows[-1]['active'], final_hold=rows[-1]['hold'],
            final_reason=state.get('autopilot_disable_reason'),
            backend_calls=len(writes), rows=rows)
        return result
    finally:
        generator.close()


def run(baseline, directory):
    paths = ('core/engine.py', 'core/service_brake_hold.py', 'core/sdk/signal_snapshot.py')
    originals = {p: load(baseline / p, 'oct8_baseline_' + str(i)) for i, p in enumerate(paths)}
    output = dict(baseline_root=str(baseline), baseline_hashes={
        p: hashlib.sha256((baseline / p).read_bytes()).hexdigest() for p in paths},
        current_hashes={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths},
        limitation='Supplied SDK speeds, real production producers and Controller BytesIO writes; '
                   'not ETS2 or proof of game consumption. Closed-loop cases use the '
                   'existing explicit prefab benchmark plant.', cases={}, closed_loop={})
    for before in (True, False):
        with ExitStack() as stack:
            if before:
                for name in ('_light_brake', '_flush_controls_unlocked'):
                    stack.enter_context(patch.object(UltraPilotEngine, name,
                        getattr(originals['core/engine.py'].UltraPilotEngine, name)))
                for name in ('after_write', 'fresh_moving_stop_request'):
                    stack.enter_context(patch.object(service_brake_hold, name,
                        getattr(originals['core/service_brake_hold.py'], name)))
                stack.enter_context(patch.object(RouteSignalSelector, 'select',
                    originals['core/sdk/signal_snapshot.py'].RouteSignalSelector.select))
            for mode in (0, 3):
                output['cases'][f'{mode}/{"before" if before else "after"}'] = scenario(mode)
                from tools.run_prefab_signal_bench import run as stop_model
                for missing in (False, True):
                    result = stop_model(directory, mode=mode, speed_kmh=35., jitter=True,
                        head_missing_during_approach=missing, allow_rejection=True)
                    name = f'{mode}/{"missing" if missing else "red"}/{"before" if before else "after"}'
                    output['closed_loop'][name] = {k: v for k, v in result.items()
                                                   if k not in ('rows', 'writes', 'captures')}
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workdir', type=Path, required=True)
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT):
        parser.error('Output must remain inside the workspace')
    if not args.workdir.resolve().is_relative_to(ROOT):
        parser.error('Workdir must remain inside the workspace')
    args.workdir.mkdir(parents=True, exist_ok=False)
    result = run(args.baseline_runtime, args.workdir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(cases={name: {k: v for k, v in case.items() if k != 'rows'}
                      for name, case in result['cases'].items()}, closed_loop=result['closed_loop']), indent=2))


if __name__ == '__main__':
    main()
