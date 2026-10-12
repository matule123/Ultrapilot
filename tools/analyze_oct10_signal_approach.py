"""Read-only integrity/binding audit of the latest Oct 10 approach exports."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.steering_replay import inspect_replay


def history_timeline(history):
    if not history: return []
    rows = sorted(history['regular_samples']+history['changes'], key=lambda r:r['monotonic_s'])
    result=[]; previous=None
    for row in rows:
        key=(row['activation'],row['signal_id'],row['signal_color'],row['hold_phase'])
        if key != previous:
            result.append({k:row.get(k) for k in ('monotonic_s','activation','identity_reference',
                'sdk_frame_us','observation_timestamp','speed_mps','gear','signal_id','signal_color',
                'signal_observed_at','signal_generation','signal_native_state','signal_time_left_s',
                'hold_phase','stop_target','selected_source','reason','written_throttle','written_brake',
                'write_first_sequence','write_last_sequence')})
        previous=key
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    receipt = json.loads((args.root/'manual-deployment.json').read_text(encoding='utf-8-sig'))
    checks = []
    for item in receipt['files']:
        target = Path(item['target']).read_bytes()
        source = Path(item['source']).read_bytes()
        checks.append(dict(path=item.get('relative_path', item['target']),
            receipt_matches=hashlib.sha256(target).hexdigest() == item['sha256'].lower(),
            normalized_matches=source.replace(b'\r\n', b'\n') == target.replace(b'\r\n', b'\n')))
    result = dict(receipt=receipt, checks=checks, exports=[])
    for path in sorted((args.root/'route-diagnostics').glob('*20261010T183*.json')):
        checked = inspect_replay(path)
        if not checked['integrity_valid']:
            raise ValueError((path.name, checked))
        replay = checked.pop('replay')
        block = replay.get('longitudinal') or {}
        signals = []
        def visit(value, location=''):
            if isinstance(value, dict):
                signal = value.get('signal')
                if isinstance(signal, dict) and signal.get('candidate'):
                    signals.append(dict(location=location, signal=signal,
                        frame=value.get('sdk_frame_us'), context=value.get('context')))
                for k, v in value.items():
                    visit(v, location+'/'+k)
            elif isinstance(value, list):
                for i, v in enumerate(value):
                    visit(v, location+'/'+str(i))
        visit(block)
        result['exports'].append(dict(file=path.name, integrity_valid=True,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(), identity=replay.get('identity'),
            sample_count=replay.get('sample_count'), execution_count=replay.get('execution_sample_count'),
            first_intervention=block.get('first_intervention'), history=block.get('decision_history'),
            history_timeline=history_timeline(block.get('decision_history')),
            signals=signals, events=block.get('events', [])))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(receipt_id=receipt.get('deployment_id') or Path(receipt['backup_directory']).name,
        receipt_valid=all(c['receipt_matches'] for c in checks),
        actual_differences=[c['path'] for c in checks if not c['normalized_matches']],
        exports=[dict(file=e['file'], identity={k:v for k,v in e['identity'].items() if k!='control_intervention'}, signals=len(e['signals']),
            sample_count=e['sample_count'], events=len(e['events']),
            history_keys=list((e['history'] or {}).keys()),
            history_timeline=e['history_timeline'],
            first_reason=(e['first_intervention'] or {}).get('reason')
                or (e['identity'].get('control_intervention') or {}).get('reason'))
            for e in result['exports']]), indent=2))


if __name__ == '__main__':
    main()
