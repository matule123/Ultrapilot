"""Read-only evening Oct 10 signal flow using the existing immutable codec."""
import json
import hashlib
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.steering_replay import inspect_replay

def main():
    root=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')
    out=Path('docs/steering-audit/oct10-signal');out.mkdir(parents=True,exist_ok=True)
    receipt=json.loads((root/'manual-deployment.json').read_text(encoding='utf-8-sig'))
    checks=[]
    for entry in receipt['files']:
        raw=Path(entry['target']).read_bytes();src=Path(entry['source'])
        checks.append(dict(target=entry['target'],receipt_matches=hashlib.sha256(raw).hexdigest()==entry['sha256'].lower(),
            source_matches=src.is_file() and src.read_bytes().replace(b'\r\n',b'\n')==raw.replace(b'\r\n',b'\n')))
    result=dict(receipt=receipt,receipt_checks=checks,exports=[])
    for path in sorted((root/'route-diagnostics').glob('*20261010T1641*.json')):
        inspected=inspect_replay(path);replay=inspected.pop('replay',{})
        (out/(path.stem+'-decoded.json')).write_text(json.dumps(replay,indent=2),encoding='utf-8')
        block=replay.get('longitudinal') or {}; fault=block.get('first_intervention')
        signals=[];seen=set()
        def visit(x,path=''):
            if isinstance(x,dict):
                if 'signal' in x and isinstance(x['signal'],dict) and x['signal'].get('coverage'):
                    value=x['signal'];token=json.dumps(value,sort_keys=True)
                    if token not in seen:
                        seen.add(token);signals.append(dict(path=path,signal=value,sdk_frame=x.get('sdk_frame_us'),
                            observation_timestamp=x.get('observation_timestamp'),computed_at=x.get('computed_at'),
                            context=x.get('context')))
                for k,v in x.items():visit(v,path+'/'+k)
            elif isinstance(x,list):
                for i,v in enumerate(x):visit(v,path+'/'+str(i))
        visit(block)
        result['exports'].append(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),**inspected,
            sample_count=replay.get('sample_count'),executions=replay.get('execution_sample_count'),
            identity=replay.get('identity'),first_intervention=fault,signals=signals,
            samples_near_fault=[r for r in replay.get('samples',[]) if 1167.7<=r.get('application_monotonic_s',0)<=1168.1],
            pedal_events=block.get('events',[])))
    (out/'summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(receipt_verified=all(c['receipt_matches'] for c in checks),
        runtime_source_matches=all(c['source_matches'] for c in checks if c['target'].endswith('.py')),
        exports=[dict(path=e['path'],integrity_valid=e['integrity_valid'],samples=e['sample_count'],
            executions=e['executions'],signals=len(e['signals']),first_fault=e['first_intervention']) for e in result['exports']]),indent=2))
    for e in result['exports']:
        selected=[s for s in e['signals'] if (s['signal'].get('coverage') or {}).get('requires_takeover')]
        print('required inputs',json.dumps(selected[:2],indent=2))

if __name__=='__main__':main()
