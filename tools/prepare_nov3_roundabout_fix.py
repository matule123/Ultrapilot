"""Freeze only the actor/near-stop/AP-continuation correction; never deploy."""
from pathlib import Path
import hashlib,json,subprocess,zipfile

ROOT=Path(__file__).resolve().parents[1]
APP=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')
OUT=ROOT/'docs/steering-audit/nov2-roundabout/release19'
BUILD='UP-NOV6-ROUNDABOUT-PERF-01'
RUNTIME=('core/actor_motion.py','core/acc_following.py','core/acc_body_prediction.py','core/steering_replay.py',
    'core/engine.py','plugins/map/main.py','core/navigation/longitudinal_diagnostics.py','core/traffic_dev_hud.py',
    'core/navigation/diagnostic_build_config.py')


def sha(raw):return hashlib.sha256(raw).hexdigest()


def verify_base(files):
    for row in files:
        path = Path(row['target'])
        expected = row['sha256'].lower()
        actual = sha(path.read_bytes())
        if actual != expected:
            raise ValueError(f'Installed base mismatch for {path}: expected {expected}, found {actual}')


def verify():
    m=json.loads((OUT/'candidate-manifest.json').read_bytes())
    assert sha((APP/'manual-deployment.json').read_bytes())==m['base_receipt_sha256']
    verify_base(m['required_base'])
    for row in m['files']:assert sha((OUT/'verification-runtime'/row['path']).read_bytes())==row['sha256']
    return m


def prepare():
    assert not OUT.exists(),'Never overwrite a frozen candidate'
    receipt_raw=(APP/'manual-deployment.json').read_bytes();receipt=json.loads(receipt_raw)
    verify_base(receipt['files'])
    stage=OUT/'verification-runtime'
    for folder in ('core','plugins','sdk','ui'):
        for p in (APP/folder).rglob('*.py'):
            target=stage/p.relative_to(APP);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(p.read_bytes())
    rows=[]
    for name in RUNTIME:
        previous=(APP/name).read_bytes() if (APP/name).exists() else None
        data=(ROOT/name).read_bytes() if name!=RUNTIME[-1] else previous.replace(
            b"BUILD = 'UP-NOV2-PREPARATION-02'",('BUILD = '+repr(BUILD)).encode())
        if name=='core/engine.py':
            # The installed observational build injects capture hooks which
            # intentionally are not present in the working-tree Engine.
            # Apply only this task's selector interface change to that base.
            old=b'selector.prepare(lane[\'points\'], binding, preserve_target=same_dependency)'
            assert previous.count(old)==1
            data=previous.replace(old,b'selector.prepare(lane[\'points\'], binding, preserve_target=same_dependency,\n                    actor_motion=lane.get(\'actor_motion\'))')
        compile(data,name,'exec');(stage/name).write_bytes(data)
        rows.append(dict(path=name,sha256=sha(data),bytes=len(data),
            previous_sha256=sha(previous) if previous is not None else None))
    for p in [stage/f for f in ('core','plugins','sdk','ui')]+[p for p in stage.rglob('*') if p.is_dir() and any(p.glob('*.py'))]:
        if not (p/'__init__.py').exists():(p/'__init__.py').write_text('# Offline namespace only.\n')
    m=dict(build=BUILD,base_receipt_sha256=sha(receipt_raw),required_base=receipt['files'],files=rows,
        source_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        working_tree_uncommitted=True,plugin_versions_changed={'map':'1.1.3 -> 1.1.4'},
        unchanged_plugins={'acc':'1.3.8','autopilot':'1.3.5'},dll_changed=False,deployed=False,game_verified=False)
    (OUT/'candidate-manifest.json').write_text(json.dumps(m,indent=2));verify();print(json.dumps(m,indent=2))


def package():
    m=verify();proof=json.loads((OUT/'qualification-result.json').read_bytes())
    assert proof['all_gates_passed'] and proof['runtime_sha256']=={r['path']:r['sha256'] for r in m['files']}
    payload={n:(OUT/'verification-runtime'/n).read_bytes() for n in RUNTIME}
    payload['runtime-manifest.json']=json.dumps(dict(m,qualification=proof),indent=2).encode()
    rollback={n:(APP/n).read_bytes() for n in RUNTIME if (APP/n).exists()}
    rollback['return-manifest.json']=json.dumps(dict(remove_only_new_files=[n for n in RUNTIME if not (APP/n).exists()],
        files=[dict(path=n,sha256=sha(data)) for n,data in rollback.items()]),indent=2).encode()
    rollback['manual-deployment.json']=(APP/'manual-deployment.json').read_bytes()
    result={}
    for name,entries in (('ultrapilot-nov3-roundabout-01-candidate.zip',payload),('rollback-installed-base.zip',rollback)):
        path=OUT/name
        with zipfile.ZipFile(path,'x',zipfile.ZIP_DEFLATED) as z:
            for n,data in entries.items():z.writestr(n,data)
        with zipfile.ZipFile(path) as z:
            assert z.testzip() is None
            for n,data in entries.items():assert z.read(n)==data
        result[name]=dict(sha256=sha(path.read_bytes()),bytes=path.stat().st_size)
    (OUT/'release-receipt.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','verify','package'])
    dict(prepare=prepare,verify=verify,package=package)[p.parse_args().action]()
