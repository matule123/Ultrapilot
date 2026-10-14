"""Same current traffic selector/plant, committed vs candidate ACC/AP.

No game or physical device; production Controller is tested separately. Current
selector has no diff from entry HEAD. TTC is between model reference points,
never an inferred bumper/body safety certificate.
"""
import argparse
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import run_acc_following_bench as following
from tools.run_longitudinal_comfort_bench import classes


def run(case, ref=None):
    original = following.engine_decision
    ttcs = []
    def decision(state, truck, *args, **kwargs):
        result = original(state, truck, *args, **kwargs)
        lead = (state.get('longitudinal_traffic') or {}).get('following') or {}
        if result[0] is not None and lead.get('status') == 'candidate':
            closing = truck['speed'] - lead['speed_mps']
            if closing > 0:
                ttcs.append(lead['gap_m']/closing)
        return result
    with patch.object(following, 'engine_decision', decision):
        if ref:
            with patch.object(following, 'classes', lambda unused=None: classes(ref)):
                result = following.simulate(case)
        else:
            result = following.simulate(case)
    return dict(result, minimum_model_reference_ttc_s=min(ttcs) if ttcs else None)


def paired_cost(ref, samples):
    from tools.run_longitudinal_handoff_bench import version
    from tools.benchmark_oct10_traffic_contract import run as pipeline
    rows = []
    for _ in range(3):
        with version(ref):
            before = pipeline(samples)
        after = pipeline(samples)
        keys = set(before['reads']) | set(after['reads'])
        rows.append(dict(before_ms=before['cost'], after_ms=after['cost'],
            backend_mappings_identical=before['mapped'] == after['mapped'],
            additional_reads={k: after['reads'].get(k, 0)-before['reads'].get(k, 0)
                for k in sorted(keys) if after['reads'].get(k, 0) != before['reads'].get(k, 0)},
            retained_before=before['retained'], retained_after=after['retained']))
    return dict(source_ref=ref, samples_per_run=samples, runs=rows,
        limitation='40 decoded traffic actors; actual Policy/ACC/AP/Engine/Controller/SCS BytesIO. '
        'Copied in-process IPC wall operation cost; not live scheduling or game consumption. '
        'Test assertion histories are cleared and excluded from runtime memory.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ref', default='b3d82bb')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cost-samples', type=int, default=0,
                        help='Instead of the numerical plant, run 3 paired whole-pipeline cost samples')
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT/'docs/steering-audit'):
        parser.error('Output must stay in the workspace audit directory')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.cost_samples:
        if not 10 <= args.cost_samples <= 1200:
            parser.error('Use 10..1200 cost samples')
        result = paired_cost(args.ref, args.cost_samples)
        args.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(result, indent=2))
        raise SystemExit(0 if all(r['backend_mappings_identical'] for r in result['runs']) else 1)
    results = {case['name']: dict(before=run(case, args.ref), after=run(case))
               for case in following.CASES}
    args.output.write_text(json.dumps(dict(source_ref=args.ref, seed=7301,
        limitation=__doc__, cases=results), indent=2, allow_nan=False)+'\n', encoding='utf-8')
    for name, row in results.items():
        print(name, 'min gap', row['before']['min_reference_gap_m'], '->',
              row['after']['min_reference_gap_m'], 'TTC', row['before']['minimum_model_reference_ttc_s'],
              '->', row['after']['minimum_model_reference_ttc_s'], flush=True)
