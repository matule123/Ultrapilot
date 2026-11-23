"""Closed-app transaction for the exact four-file October 29 incident fix."""
import hashlib
import json
import os
from pathlib import Path
import zipfile
from datetime import datetime, timezone
from deploy_oct29_diagnostic26 import stopped

ROOT=Path(__file__).resolve().parents[1]
RELEASE=ROOT/'docs/steering-audit/oct29-transition/release01'
APP=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')
def sha(raw):return hashlib.sha256(raw).hexdigest()

def main():
    stopped()
    manifest=json.loads((RELEASE/'candidate-manifest.json').read_bytes())
    qualified=json.loads((RELEASE/'qualification-completion.json').read_bytes())
    assert qualified['exit_code']==0 and qualified['runtime_unchanged']
    archives={
        'ultrapilot-oct29-incident-01-candidate.zip':'82c1b3b358ea4bf5cb6b76a4f56dd408570dfbcf12808d8d4dbe1c90284edaf5',
        'rollback-installed-base.zip':'4ac95c96e43146e339f192904ed6d8645902f99d2adf8c582ef956a6a3db0879'}
    data={}
    for name,digest in archives.items():
        raw=(RELEASE/name).read_bytes();assert sha(raw)==digest
        with zipfile.ZipFile(RELEASE/name) as z:
            assert z.testzip() is None
            data[name]={n:z.read(n) for n in z.namelist()}
    payload=data['ultrapilot-oct29-incident-01-candidate.zip']
    backup=data['rollback-installed-base.zip']
    receipt_path=APP/'manual-deployment.json';before=receipt_path.read_bytes()
    assert sha(before)==manifest['base_receipt_sha256'],'Base receipt drift'
    receipt=json.loads(before)
    for entry in receipt['files']+manifest['required_base']:
        assert sha(Path(entry['target']).read_bytes())==entry['sha256'].lower(),entry['target']
    assert backup['manual-deployment.json']==before
    originals={}
    assert len(manifest['files'])==4
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
    for entry in manifest['files']:
        stage=transaction/'staging'/entry['path'];stage.parent.mkdir(parents=True,exist_ok=True)
        stage.write_bytes(payload[entry['path']]);assert sha(stage.read_bytes())==entry['sha256']
    stopped()
    try:
        for entry in manifest['files']:os.replace(transaction/'staging'/entry['path'],APP/entry['path'])
        for entry in manifest['files']:
            target=APP/entry['path'];assert sha(target.read_bytes())==entry['sha256']
            original=next(v for v in receipt['files'] if Path(v['target'])==target)
            original.update(sha256=entry['sha256'],previous_sha256=entry['previous_sha256'])
        for entry in receipt['files']:
            assert sha(Path(entry['target']).read_bytes())==entry['sha256'].lower(),entry['target']
        assert all(sha((APP/p).read_bytes())==digest for p,digest in protected.items())
        receipt['diagnostic_deployment']=dict(build=manifest['build'],deployed_at_utc=stamp,
            user_authorized=True,archives=archives,base_receipt_sha256=sha(before),
            rollback=str(transaction/'rollback-installed-base.zip'),runtime_files=manifest['files'],
            working_tree_uncommitted=True,source_head=manifest.get('source_head'),game_started=False,game_verified=False)
        after=(json.dumps(receipt,indent=2)+'\n').encode();receipt_path.write_bytes(after)
        assert receipt_path.read_bytes()==after
        (transaction/'manual-deployment.after.json').write_bytes(after)
    except BaseException:
        for rel,raw in originals.items():(APP/rel).write_bytes(raw)
        receipt_path.write_bytes(before)
        assert receipt_path.read_bytes()==before
        assert all((APP/rel).read_bytes()==raw for rel,raw in originals.items())
        raise
    result=dict(status='DEPLOYED_HASH_VERIFIED',build=manifest['build'],runtime_files=4,
        receipt_files=len(receipt['files']),backup=str(transaction/'rollback-installed-base.zip'),game_started=False)
    (transaction/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
