"""Read original diagnostic26 evidence without modifying the installation."""
import hashlib
import json
from pathlib import Path
from collections import Counter
from core.steering_replay import inspect_replay, inspect_incident

APP = Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')
OUT = Path(__file__).resolve().parents[1] / 'docs/steering-audit/oct29-transition'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    receipt_path = APP / 'manual-deployment.json'
    receipt = json.loads(receipt_path.read_bytes())
    installed = []
    for entry in receipt['files']:
        path = Path(entry['target'])
        installed.append(dict(path=str(path), matches=hashlib.sha256(path.read_bytes()).hexdigest() == entry['sha256'].lower()))
    assert all(r['matches'] for r in installed)
    root = APP / 'route-diagnostics'
    names = ['incident-d8f8382277da40c398b28c5fcf315a11-14102.json',
        'steering-replay-20261029T130620.051281Z-diagnostic_incident.json',
        'ap-inputs-d8f8382277da40c398b28c5fcf315a11-14102.json']
    checked = inspect_incident(root/names[0])
    engine = inspect_replay(root/names[1]); ap = inspect_replay(root/names[2])
    assert checked['integrity_valid'] and engine['integrity_valid'] and ap['integrity_valid']
    rows = engine['replay']['longitudinal']['diagnostic_incident']['records']
    native_rows=[r for r in rows if r['kind'] in ('traffic','ego') and 22764<r['at_s']<22772]
    import pickle
    # LOCAL analysis-only primitive cache. Never loaded by external inspector
    # or runtime. Exact bytes stay bytes, rather than a nearby HUD header.
    (OUT/'native-analysis-cache.bin').write_bytes(pickle.dumps(native_rows,protocol=5))
    # JSON primitive fixture preserves the exact original producer packets; native
    # byte buffers are already in the original replay, not coerced to strings.
    selected = [r for r in rows if r['sequence'] in (16993,16994,17004)
        or r['kind'] in ('consumed_decision','pedal_binding') and 22771.60<r['at_s']<22771.79]
    def native(item):
        if isinstance(item,bytes):
            return dict(raw_hex=item.hex(),sha256=hashlib.sha256(item).hexdigest())
        if isinstance(item,dict): return {k:native(v) for k,v in item.items()}
        if isinstance(item,(list,tuple)):return [native(v) for v in item]
        return item
    (OUT/'exact-transition.json').write_text(json.dumps(native(selected),indent=2),encoding='utf-8')
    traffic=[]
    for row in rows:
        if row['kind']!='consumer_traffic' or not 22763<row['at_s']<22772:continue
        packet=row['value'].get('packet') or {}
        following=packet.get('following') or {}
        if row['sequence'] in (16993,17004) or packet.get('traffic_brake',0)>0 or packet.get('motion_constraint'):
            traffic.append(dict(sequence=row['sequence'],at_s=row['at_s'],packet=packet))
    (OUT/'crossing-inputs.json').write_text(json.dumps(native(traffic),indent=2),encoding='utf-8')
    ap_data=ap['replay'].get('diagnostic_consumed_inputs') or {}
    (OUT/'ap-analysis-cache.bin').write_bytes(pickle.dumps(ap_data,protocol=5))
    (OUT/'engine-analysis-cache.bin').write_bytes(pickle.dumps(engine['replay']['longitudinal'],protocol=5))
    ap_bad=[r for r in ap_data.get('records',[]) if (r.get('value') or {}).get('capture_failures')]
    history=engine['replay']['longitudinal'].get('decision_history') or {}
    bad_summaries=[r for kind in ('regular_samples','changes') for r in history.get(kind,[]) if r.get('capture_incomplete')]
    summary=dict(installed=installed,receipt_sha256=hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
        originals=[dict(name=n,sha256=hashlib.sha256((root/n).read_bytes()).hexdigest(),
            mtime_utc=(root/n).stat().st_mtime) for n in names],
        incident={k:v for k,v in checked.items() if k not in ('replay','dossier')},
        manifest=checked['dossier'],engine_keys=list(engine['replay']),ap_keys=list(ap['replay']),
        ap_metadata={k:v for k,v in ap_data.items() if k!='records'},
        ap_failure_rows=ap_bad,history={k:v for k,v in history.items() if k not in ('regular_samples','changes')},
        incomplete_summaries=bad_summaries,kinds=dict(Counter(r['kind'] for r in rows)))
    (OUT/'audit.json').write_text(json.dumps(native(summary),indent=2),encoding='utf-8')
    from core.navigation.longitudinal_diagnostics import _decision_summary, _DecisionHistory
    replayed = _DecisionHistory(); history_errors=[]
    for row in rows:
        if row['kind'] not in ('consumed_decision','pedal_binding'):continue
        try:
            small, identity = _decision_summary(row['value'])
            count = replayed.failures
            replayed.observe(row['at_s'], small, identity)
            if replayed.failures != count:
                history_errors.append(dict(sequence=row['sequence'],at_s=row['at_s'],reason='summary incomplete/budget',summary=small))
        except Exception as error:
            history_errors.append(dict(sequence=row['sequence'],at_s=row['at_s'],error=type(error).__name__,detail=str(error)))
    requests=[]; previous=None
    for row in ap_data.get('records',[]):
        v=row.get('value') or {}
        for inp in v.get('inputs',[]):
            packet=(inp.get('value') or {}).get('packet') or {}
            request=packet.get('diagnostic_part_request')
            if request and request!=previous:
                requests.append(dict(at_s=row['at_s'],request=request));previous=request
    (OUT/'failure-reconstruction.json').write_text(json.dumps(native(dict(
        history_errors=history_errors,ap_requests=requests,
        ap_transactions_with_failure=ap_bad))),encoding='utf-8')
    print(json.dumps(dict(installed=len(installed),incident_valid=checked['integrity_valid'],
        selected=[(r['sequence'],r['kind']) for r in selected],traffic_rows=len(traffic),
        ap_failure_rows=len(ap_bad),incomplete_summaries=len(bad_summaries),output=str(OUT))))


if __name__=='__main__':main()
