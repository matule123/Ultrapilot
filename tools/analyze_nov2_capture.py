"""Read-only incident audit; derived outputs stay in this checkout."""
from pathlib import Path
import hashlib
import json
from collections import Counter
from core.steering_replay import inspect_replay, inspect_autopilot_part, incident_diagnostic_budget

APP = Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')
OUT = Path(__file__).resolve().parents[1] / 'docs/steering-audit/nov2-sdk-preparation'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def safe(value):
    if isinstance(value, bytes):
        return dict(raw_bytes=len(value), sha256=hashlib.sha256(value).hexdigest())
    if isinstance(value, dict):
        return {str(k): safe(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [safe(v) for v in value]
    return value

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    receipt = json.loads((APP/'manual-deployment.json').read_bytes())
    mismatches = [r['target'] for r in receipt['files'] if sha(Path(r['target'])) != r['sha256'].lower()]
    root = APP/'route-diagnostics'
    inventory = [dict(path=p.relative_to(root).as_posix(), bytes=p.stat().st_size)
        for p in sorted(root.rglob('*')) if p.is_file()]
    sources = []
    results = []
    for name in ('steering-replay-20261102T145830.244312Z-automatic_disable.json',
                 'steering-replay-20261102T145714.339237Z-manual_disable-devinputs.json',
                 'steering-timing-20261102T145951.569694Z-plugin_stop.json',
                 'ap-inputs-55bfc3027cad4dfd90fd37d7a4164c84-15672.json',
                 'incident-failure-55bfc3027cad4dfd90fd37d7a4164c84-18550.txt'):
        p=root/name
        sources.append(dict(path=str(p), sha256=sha(p), bytes=p.stat().st_size))
        value=json.loads(p.read_bytes())
        item=dict(name=name, keys=list(value))
        if name.startswith('steering-replay'):
            checked=inspect_replay(p)
            item.update(integrity_valid=checked['integrity_valid'], reason=checked.get('reason'))
            if checked['integrity_valid']:
                expanded=checked['replay']
                (OUT/(name+'.expanded.json')).write_text(json.dumps(safe(expanded)),encoding='utf-8')
                item.update(samples=len(expanded['samples']), executions=len(expanded['execution_samples']),
                    longitudinal_keys=list((expanded.get('longitudinal') or {})))
        elif name.startswith('ap-inputs'):
            expanded=inspect_replay(p)
            request=expanded['replay']['identity']['part_request']
            checked=inspect_autopilot_part(p,request)
            item.update({k:v for k,v in checked.items() if k not in ('part','records')})
            item['request']=request
            records=expanded['replay']['diagnostic_consumed_inputs'].get('records') or []
            item['capture_failure_rows']=[dict(at_s=r['at_s'],sequence=r['sequence'],
                failures=r['value'].get('capture_failures'),sources=[i.get('source') for i in r['value'].get('inputs',[])])
                for r in records if r['value'].get('capture_failures')]
        else:item['value']=value if name.endswith('.txt') else {k:v for k,v in value.items() if k not in ('samples','records')}
        results.append(item)
    result=dict(receipt_sha256=sha(APP/'manual-deployment.json'), deployment=receipt.get('diagnostic_deployment'),
        installed_count=len(receipt['files']), installed_mismatches=mismatches,
        budget=incident_diagnostic_budget(root), inventory=inventory, originals=sources, results=results)
    (OUT/'audit.json').write_text(json.dumps(safe(result),indent=2),encoding='utf-8')
    print(json.dumps(safe({k:v for k,v in result.items() if k not in ('inventory','deployment','results')}),indent=2))
    print(json.dumps([dict(name=r['name'],integrity_valid=r.get('integrity_valid'),reason=r.get('reason')) for r in results]))

if __name__=='__main__':main()
