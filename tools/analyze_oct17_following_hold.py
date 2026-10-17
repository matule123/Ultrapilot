"""Read-only reconstruction of the Oct17 17:17/17:21 deployed incidents."""
import hashlib
import json
from pathlib import Path
import zipfile

from core.steering_replay import inspect_replay

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/steering-audit/oct17-following-hold-signals'
INSTALL=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    digest=lambda b:hashlib.sha256(b).hexdigest()
    from tools.prepare_oct17_joint_candidate import RUNTIME
    names=tuple(dict.fromkeys((*RUNTIME,'plugins/turnsignals/main.py',
        'core/sdk/scs_controller_writer.py','core/navigation/turn_maneuvers.py')))
    receipt_bytes=(INSTALL/'manual-deployment.json').read_bytes()
    receipt=json.loads(receipt_bytes.decode('utf-8-sig'))
    checks=[dict(target=r['target'],match=digest(Path(r['target']).read_bytes())==r['sha256'].lower())
        for r in receipt['files']]
    sources=[dict(path=n,sha256=digest((ROOT/n).read_bytes()),
        normalized_equal=(ROOT/n).read_bytes().replace(b'\r\n',b'\n')==(INSTALL/n).read_bytes().replace(b'\r\n',b'\n')) for n in names]
    snapshot=OUT/'entry-runtime.zip'
    if not snapshot.exists():
        with zipfile.ZipFile(snapshot,'x',zipfile.ZIP_DEFLATED) as archive:
            for n in names:archive.writestr(n,(ROOT/n).read_bytes())
    entry=OUT/'entry-installation.json'
    if not entry.exists():entry.write_text(json.dumps(dict(receipt_sha256=digest(receipt_bytes),
        checks=checks,source=sources),indent=2))
    print('Receipt',len(checks),all(r['match'] for r in checks),'normalized mismatches',
        [r['path'] for r in sources if not r['normalized_equal']])
    summaries=[];rows={};events={}
    for path in sorted((INSTALL/'route-diagnostics').glob('*20261017T15*.json')):
        if path.name.startswith('steering-timing'):continue
        inspected=inspect_replay(path)
        if not inspected['integrity_valid']:raise ValueError((path.name,inspected))
        data=inspected['replay'];block=data.get('longitudinal') or {}
        (OUT/path.name).write_text(json.dumps(data))
        history=block.get('decision_history') or {};identities=history.get('identities') or {}
        entries=history.get('regular_samples',[])+history.get('changes',[])
        for row in entries:
            rows[(row['monotonic_s'],str(row.get('identity_reference')))]=dict(row,
                identity=identities.get(row.get('identity_reference')),export=path.name)
        for event in block.get('events',[]):
            events[(event['call_started_at_s'],event['sequence'])]=dict(event,export=path.name)
        item=dict(file=path.name,sha256=digest(path.read_bytes()),integrity_valid=True,
            kind=data.get('sample_kind'),identity=data.get('identity'),
            rows=len(entries),times=[min(r['monotonic_s'] for r in entries),max(r['monotonic_s'] for r in entries)] if entries else None,
            writes=len(block.get('events',[])),dense=len(data.get('samples',[])),
            first_intervention=block.get('first_intervention'),significant_event=block.get('significant_event'))
        summaries.append(item)
        print(path.name,'history',item['rows'],item['times'],'writes',item['writes'],'dense',item['dense'])
    (OUT/'summary.json').write_text(json.dumps(summaries,indent=2))
    (OUT/'rows.json').write_text(json.dumps(sorted(rows.values(),key=lambda r:r['monotonic_s'])))
    (OUT/'writes.json').write_text(json.dumps(sorted(events.values(),key=lambda e:e['call_started_at_s'])))


if __name__=='__main__':main()
