"""Installed-base, diagnostic-only candidate. No deployment or game operations."""
from pathlib import Path
import hashlib,json,subprocess,zipfile

ROOT=Path(__file__).resolve().parents[1]
APP=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')
OUT=ROOT/'docs/steering-audit/oct29-reactivation/release02'
BUILD='UP-OCT29-REACTIVATION-02'
RUNTIME=('core/steering_replay.py','core/navigation/longitudinal_diagnostics.py',
    'core/navigation/diagnostic_build_config.py')


def sha(raw):return hashlib.sha256(raw).hexdigest()


def verify():
    m=json.loads((OUT/'candidate-manifest.json').read_bytes())
    assert sha((APP/'manual-deployment.json').read_bytes())==m['base_receipt_sha256']
    for row in m['required_base']:assert sha(Path(row['target']).read_bytes())==row['sha256'].lower()
    for row in m['files']:assert sha((OUT/'verification-runtime'/row['path']).read_bytes())==row['sha256']
    return m


def prepare():
    assert not OUT.exists(),'Never overwrite a frozen candidate'
    raw=(APP/'manual-deployment.json').read_bytes();receipt=json.loads(raw)
    for row in receipt['files']:assert sha(Path(row['target']).read_bytes())==row['sha256'].lower()
    stage=OUT/'verification-runtime'
    for folder in ('core','plugins','sdk','ui'):
        for p in (APP/folder).rglob('*.py'):
            target=stage/p.relative_to(APP);target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(p.read_bytes())
    for name in RUNTIME:
        data=(ROOT/name).read_bytes() if name!=RUNTIME[-1] else (APP/name).read_bytes().replace(
            b"BUILD = 'UP-OCT29-INCIDENT-01'",('BUILD = '+repr(BUILD)).encode())
        compile(data,name,'exec');(stage/name).write_bytes(data)
    # Namespace markers for isolated qualification only; never deployment payload.
    for p in [stage/f for f in ('core','plugins','sdk','ui')]+[p for p in stage.rglob('*') if p.is_dir() and any(p.glob('*.py'))]:
        if not (p/'__init__.py').exists():(p/'__init__.py').write_text('# Offline namespace only.\n')
    controls=('core/engine.py','core/longitudinal.py','core/acc_following.py','core/service_brake_hold.py',
        'core/ipc/shared_state.py','plugins/autopilot/main.py','plugins/acc/main.py','plugins/drivepolicy/main.py')
    for name in controls:assert (APP/name).read_bytes()==(stage/name).read_bytes()
    m=dict(build=BUILD,base_receipt_sha256=sha(raw),required_base=receipt['files'],
        files=[dict(path=n,sha256=sha((stage/n).read_bytes()),bytes=(stage/n).stat().st_size,
            previous_sha256=sha((APP/n).read_bytes())) for n in RUNTIME],
        unchanged_controls={n:sha((APP/n).read_bytes()) for n in controls},
        source_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        working_tree_uncommitted=True,plugin_versions_changed=False,dll_changed=False,
        deployed=False,game_verified=False)
    (OUT/'candidate-manifest.json').write_text(json.dumps(m,indent=2))
    verify();print(json.dumps(dict(stage=str(stage),build=BUILD)))


def package():
    m=verify();proof=json.loads((OUT/'qualification-result.json').read_bytes())
    assert proof['all_gates_passed'] and proof['runtime_sha256']=={r['path']:r['sha256'] for r in m['files']}
    payload={n:(OUT/'verification-runtime'/n).read_bytes() for n in RUNTIME}
    payload['runtime-manifest.json']=json.dumps(dict(m,qualification=proof),indent=2).encode()
    rollback={n:(APP/n).read_bytes() for n in RUNTIME}
    rollback['manual-deployment.json']=(APP/'manual-deployment.json').read_bytes()
    results={}
    for name,entries in (('ultrapilot-oct29-reactivation-02-candidate.zip',payload),('rollback-installed-base.zip',rollback)):
        path=OUT/name
        with zipfile.ZipFile(path,'x',zipfile.ZIP_DEFLATED) as z:
            for n,data in entries.items():z.writestr(n,data)
        with zipfile.ZipFile(path) as z:
            assert z.testzip() is None
            for n,data in entries.items():assert z.read(n)==data
        results[name]=dict(sha256=sha(path.read_bytes()),bytes=path.stat().st_size)
    (OUT/'release-receipt.json').write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2))


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','verify','package'])
    dict(prepare=prepare,verify=verify,package=package)[p.parse_args().action]()
