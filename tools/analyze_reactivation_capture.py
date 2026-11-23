"""Read-only October 29 evening evidence: exact streams, never nearby actors."""
from pathlib import Path
import json
import hashlib
from collections import Counter
from core.steering_replay import inspect_replay, inspect_incident

APP=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')
OUT=Path(__file__).resolve().parents[1]/'docs/steering-audit/oct29-reactivation'


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    receipt=json.loads((APP/'manual-deployment.json').read_bytes())
    assert all(sha(Path(r['target']))==r['sha256'].lower() for r in receipt['files'])
    root=APP/'route-diagnostics';originals=[];results=[];selected=[]
    for path in sorted(root.rglob('incident-def0be9809114e53a55e959d11361ae9-*.json')):
        checked=inspect_incident(path)
        originals.append(dict(path=str(path),sha256=sha(path)))
        item=dict(name=path.name,integrity_valid=checked['integrity_valid'],reason=checked.get('reason'))
        if checked['integrity_valid']:
            dossier=checked['dossier'];replay=checked['replay'];window=replay['longitudinal']['diagnostic_incident']
            streams={}
            for r in window['records']:streams.setdefault(r['kind'],[]).append(r)
            item.update(range=window['range_s'],episode=dossier.get('episode'),incomplete=checked['incomplete'],
                components=dossier['component_completeness'],counts={k:len(v) for k,v in streams.items()},
                gaps={k:[dict(start_s=a['at_s'],end_s=b['at_s'],seconds=b['at_s']-a['at_s'],
                    first_sequence=a['sequence'],last_sequence=b['sequence'])
                    for a,b in zip(v,v[1:]) if b['at_s']-a['at_s']>.5] for k,v in streams.items()
                    if k in ('traffic','ego','output_summary')},subevents=dossier['subevents'])
            for row in window['records']:
                if 37410<row['at_s']<37495 and row['kind'] in ('traffic','consumer_acc','consumer_traffic','output_summary','pedal_binding'):
                    v=row['value'];packet=v.get('packet') or {}
                    following=packet.get('following') or {}
                    if (packet.get('following_target_id')=='85' or following.get('target_id')=='85'
                            or row['kind']=='traffic' or row['kind']=='output_summary'):
                        selected.append(row)
        results.append(item)
    def safe(v):
        if isinstance(v,bytes):return dict(raw_hex=v.hex(),sha256=hashlib.sha256(v).hexdigest())
        if isinstance(v,dict):return {k:safe(c) for k,c in v.items()}
        if isinstance(v,(list,tuple)):return [safe(c) for c in v]
        return v
    (OUT/'stream-audit.json').write_text(json.dumps(safe(dict(receipt_sha256=sha(APP/'manual-deployment.json'),
        installed_files_verified=len(receipt['files']),originals=originals,incidents=results)),indent=2),encoding='utf-8')
    import pickle
    # Trusted local analysis-only cache, not an external runtime/evidence format.
    (OUT/'exact-rows.bin').write_bytes(pickle.dumps(selected,protocol=5))
    auto=root/'steering-replay-20261029T171114.244598Z-automatic_disable.json'
    replay=inspect_replay(auto);assert replay['integrity_valid']
    (OUT/'automatic-disable-expanded.json').write_text(json.dumps(safe(replay['replay']),indent=2),encoding='utf-8')
    print(json.dumps(dict(incidents=len(results),installed_files=len(receipt['files']),
        main=[x for x in results if '43934' in x['name']],automatic_valid=replay['integrity_valid']),default=str)[:4500])


if __name__=='__main__':main()
