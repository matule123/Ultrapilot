"""Paired 8/5 m SDK-reference convention on a real placed PPD passage.

Explicit uncalibrated closed plant, not bumper/painted-line metrology. The
existing production reader, selector, Policy, ACC, Autopilot, Engine and SCS
Controller are exercised with chronological physical test-backend writes.
Only the planned front allowance is substituted; gains and lifecycle stay
identical. Original exports and installations are never changed.
"""
import argparse
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from core.navigation import prefab_signals
from tools.audit_oct11_stop_geometry import model_case
from tools.run_oct11_terminal_stop_bench import metrics


def compare(directory, *, speed=35., mode=0, curvature=0., plant=None,
            program=None, other_stop=False):
    results = {}
    for name, front in (('before', 6.), ('after', 3.)):
        with patch.object(prefab_signals, 'FRONT_ALLOWANCE_M', front):
            result = model_case(directory, speed=speed, mode=mode,
                approach_curvature=curvature, plant_options=plant,
                program=program, other_stop=other_stop)
        value = metrics(result)
        stop = result['stop']
        value.update(reference_offset_m=stop['reference_offset_m'] if stop else front+2.,
            sdk_reference_to_authored_entry_m=(stop['reference_gap_to_target_m']
                + stop['reference_offset_m']) if stop else None,
            physical_bumper_to_painted_line_m=None,
            game_verified=False)
        results[name] = value
    return results


def summarize(cases):
    values = list(cases.values())
    if not values:
        raise ValueError('no completed pairs')
    failures = []
    for label,pair in cases.items():
        for side,value in pair.items():
            if value['gap_m'] is None or value['gap_m'] < 0.:
                failures.append((label,side,'missing stop or target overrun'))
            for key in ('red_target_overruns','red_entry_overrun_samples',
                        'hold_zero_writes','red_standstill_drive_writes',
                        'positive_pedal_overlap','parking_writes','far_low_speed_s'):
                if value[key] != 0:
                    failures.append((label,side,key))
            if not value['active'] or not value['resumed_without_n']:
                failures.append((label,side,'authority/green resume'))
    keys = ('gap_m','sdk_reference_to_authored_entry_m','maximum_deceleration_mps2',
            'maximum_abs_model_jerk_mps3','below_5_kmh_moving_s','pedal_transitions')
    return dict(pairs=len(values), failures=failures,
        samples={side:sum(v[side]['samples'] for v in values) for side in ('before','after')},
        ranges={key:{side:[min(v[side][key] for v in values),max(v[side][key] for v in values)]
            for side in ('before','after')} for key in keys},
        model_front_sensitivity_m={str(front):[
            min(v['after']['sdk_reference_to_authored_entry_m']-front for v in values),
            max(v['after']['sdk_reference_to_authored_entry_m']-front for v in values)]
            for front in (3.,4.,6.)},
        physical_line_gap_verified=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if not args.output.resolve().is_relative_to(root/'docs/steering-audit'):
        raise ValueError('output must remain in workspace steering-audit')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    results = dict(criteria=dict(
        reference_offset_m=5., reference_target_overrun_samples=0,
        model_front_extent_m=4., physical_line_gap_verified=False,
        positive_pedal_overlap=0, hold_zero_writes=0, parking_writes=0,
        green_resume_without_n=True,
        far_creep_definition='speed < 5 km/h and distance to derived target > 10 m'),
        source_sha256=hashlib.sha256(Path(prefab_signals.__file__).read_bytes()).hexdigest(),
        cases={})
    plants = dict(normal={}, quick=dict(brake_response_s=.2,input_delay_s=.05),
        slow_loaded=dict(brake_response_s=.6,input_delay_s=.22,mass_ratio=1.8))
    for name, plant in plants.items():
        for curvature in (0., 1./60., -1./60.):
            for speed in (20.,35.,50.):
                for mode in (0,3):
                    label = f'{name}/{curvature:.6f}/{speed:g}/{mode}'
                    pair = compare(args.output.parent, speed=speed, mode=mode,
                        curvature=curvature, plant=plant)
                    results['cases'][label] = pair
                    args.output.write_text(json.dumps(results, indent=2)+'\n', encoding='utf-8')
                    a,b = pair['before'],pair['after']
                    print(label,'entry gap',a['sdk_reference_to_authored_entry_m'],
                        '->',b['sdk_reference_to_authored_entry_m'],flush=True)
    results['summary'] = summarize(results['cases'])
    results['complete'] = len(results['cases']) == 54 and not results['summary']['failures']
    args.output.write_text(json.dumps(results, indent=2)+'\n', encoding='utf-8')
    if not results['complete']:
        raise AssertionError(results['summary'])


if __name__ == '__main__':
    main()
