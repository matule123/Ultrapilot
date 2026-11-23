"""Install only approved release02 frozen bytes, with complete rollback."""
import hashlib
import json
import os
from pathlib import Path
import zipfile
from datetime import datetime, timezone
from deploy_oct29_diagnostic26 import stopped

ROOT=Path(__file__).resolve().parents[1]
RELEASE=ROOT/'docs/steering-audit/oct29-reactivation/release02'
APP=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')
def sha(raw):return hashlib.sha256(raw).hexdigest()

def main():
    stopped()
    manifest=json.loads((RELEASE/'candidate-manifest.json').read_bytes())
    qualified=json.loads((RELEASE/'qualification-result.json').read_bytes())
    assert qualified['all_gates_passed'] is True and not qualified['failures']
    assert qualified['build']==manifest['build']=='UP-OCT29-REACTIVATION-02'
    archives={
        'ultrapilot-oct29-reactivation-02-candidate.zip':'f42e507655fb85ed3dcd46265a332cf6d978a1419e6264b4467c701122f1cc54',
        'rollback-installed-base.zip':'6ff55fa8f2a91fbab5c25baceeb587ea6088fd184b0fcb23f9a3b68555101d41'}
    contents={}
    for name,digest in archives.items():
        assert sha((RELEASE/name).read_bytes())==digest
        with zipfile.ZipFile(RELEASE/name) as archive:
            assert archive.testzip() is None
            contents[name]={n:archive.read(n) for n in archive.namelist()}
    payload=contents['ultrapilot-oct29-reactivation-02-candidate.zip']
    backup=contents['rollback-installed-base.zip']
    receipt_path=APP/'manual-deployment.json';before=receipt_path.read_bytes()
    assert sha(before)==manifest['base_receipt_sha256'],'Base receipt drift'
    receipt=json.loads(before)
    for entry in receipt['files']+manifest['required_base']:
        assert sha(Path(entry['target']).read_bytes())==entry['sha256'].lower(),entry['target']
    for rel,digest in manifest['unchanged_controls'].items():
        assert sha((APP/rel).read_bytes())==digest,rel
    assert backup['manual-deployment.json']==before
    assert {e['path'] for e in manifest['files']}=={
        'core/steering_replay.py','core/navigation/longitudinal_diagnostics.py',
        'core/navigation/diagnostic_build_config.py'}
    originals={}
    for entry in manifest['files']:
        rel=entry['path'];target=(APP/rel).resolve()
        assert target.is_relative_to(APP.resolve())
        assert sha(payload[rel])==entry['sha256']==qualified['runtime_sha256'][rel]
        assert len(payload[rel])==entry['bytes'];compile(payload[rel],rel,'exec')
        originals[rel]=target.read_bytes()
        assert sha(originals[rel])==entry['previous_sha256'] and backup[rel]==originals[rel]
    protected={p:sha((APP/p).read_bytes()) for p in ('settings.json','commit.txt') if (APP/p).exists()}
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    transaction=RELEASE/('deployment-'+stamp);transaction.mkdir()
    (transaction/'manual-deployment.before.json').write_bytes(before)
    (transaction/'rollback-installed-base.zip').write_bytes((RELEASE/'rollback-installed-base.zip').read_bytes())
    assert sha((transaction/'rollback-installed-base.zip').read_bytes())==archives['rollback-installed-base.zip']
    for entry in manifest['files']:
        stage=transaction/'staging'/entry['path'];stage.parent.mkdir(parents=True,exist_ok=True)
        stage.write_bytes(payload[entry['path']]);assert sha(stage.read_bytes())==entry['sha256']
    stopped()
    try:
        for entry in manifest['files']:os.replace(transaction/'staging'/entry['path'],APP/entry['path'])
        for entry in manifest['files']:
            target=APP/entry['path'];assert sha(target.read_bytes())==entry['sha256']
            row=next(v for v in receipt['files'] if Path(v['target'])==target)
            row.update(sha256=entry['sha256'],previous_sha256=entry['previous_sha256'])
        for entry in receipt['files']:
            assert sha(Path(entry['target']).read_bytes())==entry['sha256'].lower(),entry['target']
        assert all(sha((APP/p).read_bytes())==digest for p,digest in protected.items())
        receipt['diagnostic_deployment']=dict(build=manifest['build'],deployed_at_utc=stamp,
            user_authorized=True,archives=archives,base_receipt_sha256=sha(before),
            rollback=str(transaction/'rollback-installed-base.zip'),runtime_files=manifest['files'],
            working_tree_uncommitted=True,source_head=manifest['source_head'],game_started=False,game_verified=False)
        after=(json.dumps(receipt,indent=2)+'\n').encode();receipt_path.write_bytes(after)
        assert receipt_path.read_bytes()==after
        (transaction/'manual-deployment.after.json').write_bytes(after)
    except BaseException:
        for rel,raw in originals.items():(APP/rel).write_bytes(raw)
        receipt_path.write_bytes(before)
        assert receipt_path.read_bytes()==before
        assert all((APP/rel).read_bytes()==raw for rel,raw in originals.items())
        raise
    result=dict(status='DEPLOYED_HASH_VERIFIED',build=manifest['build'],runtime_files=3,
        receipt_files=len(receipt['files']),backup=str(transaction/'rollback-installed-base.zip'),game_started=False)
    (transaction/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
