"""Read-only Oct 10 traffic rejection; existing immutable replay codec."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.steering_replay import inspect_replay

def analyze(root, output):
    receipt = json.loads((root/'manual-deployment.json').read_text(encoding='utf-8-sig'))
    installed = []
    for row in receipt['files']:
        target = Path(row['target'])
        raw = target.read_bytes()
        source = Path(row['source'])
        installed.append(dict(target=str(target), receipt_matches=hashlib.sha256(raw).hexdigest()==row['sha256'].lower(),
            source_matches=source.is_file() and source.read_bytes().replace(b'\r\n',b'\n')==raw.replace(b'\r\n',b'\n')))
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for path in sorted((root/'route-diagnostics').glob('*20261010T0635*.json')):
        checked = inspect_replay(path)
        replay = checked.pop('replay', {})
        row = dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(), **checked,
            reason=replay.get('reason'), identity=replay.get('identity'),
            samples=len(replay.get('samples',[])), execution_samples=len(replay.get('execution_samples',[])))
        block = replay.get('longitudinal') or {}
        row.update(first_intervention=block.get('first_intervention'),
            first_events=block.get('events',[])[:8], last_events=block.get('events',[])[-8:])
        first=block.get('first_intervention') or {}
        if first:
            fault_time=first['observed_at']
            events=block.get('events',[])
            before=[e for e in events if e['call_started_at_s']<fault_time]
            after=[e for e in events if e['call_started_at_s']>=fault_time]
            def write(e):
                s=e.get('source') or {}
                return dict(sequence=e['sequence'],channel=e['channel'],requested=e['requested_value'],
                    backend=e['backend'],call_started_at=e['call_started_at_s'],
                    call_returned_at=e['call_returned_at_s'],context=s.get('context'),
                    sdk_frame=s.get('sdk_frame_us'),original_sdk_time=s.get('observation_timestamp'),
                    gear=s.get('observed_gear'),speed_mps=s.get('actual_speed_mps'),
                    selected=s.get('selected'),input_rejections=s.get('input_rejections'))
            row['fault_timeline']=dict(first_fault=first,
                last_bound_write_before_fault=write(before[-1]) if before else None,
                first_writes_after_fault=[write(e) for e in after[:2]],
                detail_evidence=block.get('detail_evidence'))
        histories=block.get('decision_history') or {}
        row['history_tail'] = sorted(histories.get('regular_samples',[])+histories.get('changes',[]),
            key=lambda r:r['monotonic_s'])[-5:]
        (output/(path.stem+'-decoded.json')).write_text(json.dumps(replay,indent=2),encoding='utf-8')
        records.append(row)
    result=dict(receipt=receipt, installed=installed, records=records)
    (output/'incident-summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(installed_receipt_ok=all(r['receipt_matches'] for r in installed),
        installed_source_ok=all(r['source_matches'] for r in installed if r['target'].endswith('.py')),
        records=[dict(path=r['path'],integrity_valid=r.get('integrity_valid'),reason=r['reason'],
            samples=r['samples'],execution_samples=r['execution_samples'],
            first_intervention=r['first_intervention']) for r in records]),indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot'))
    parser.add_argument('--output',type=Path,default=Path('docs/steering-audit/oct10-traffic'))
    args=parser.parse_args();analyze(args.root,args.output)
