"""Freeze an installed-base October 29 patch; never installs or starts games."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
APP=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')
OUT=ROOT/'docs/steering-audit/oct29-transition/release01'
BUILD='UP-OCT29-INCIDENT-01'


def sha(raw):return hashlib.sha256(raw).hexdigest()


def load(path):return json.loads(path.read_text(encoding='utf-8'))


def function(source,name):
    node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name==name)
    return '\n'.join(source.splitlines()[node.lineno-1:node.end_lineno])


def verify(manifest):
    assert sha((APP/'manual-deployment.json').read_bytes())==manifest['base_receipt_sha256']
    for entry in manifest['required_base']:
        assert sha(Path(entry['target']).read_bytes())==entry['sha256'].lower(),entry['target']
    for entry in manifest['files']:
        assert sha((OUT/'verification-runtime'/entry['path']).read_bytes())==entry['sha256']


def prepare():
    assert not OUT.exists(),'Preserve previous frozen candidates'
    receipt_raw=(APP/'manual-deployment.json').read_bytes();receipt=json.loads(receipt_raw)
    for row in receipt['files']:assert sha(Path(row['target']).read_bytes())==row['sha256'].lower()
    base=(APP/'core/longitudinal.py').read_text(encoding='utf-8-sig')
    source=(ROOT/'core/longitudinal.py').read_text(encoding='utf-8-sig')
    patched=base.replace(function(base,'signal_drive_write_guard'),function(source,'signal_drive_write_guard'),1)
    anchor="        result['required_acc_owner_id']=current_acc.get('following_target_id')"
    assert patched.count(anchor)==1
    patched=patched.replace(anchor,anchor+"\n        if isinstance(current_acc.get('following_owner'),dict):\n            result['required_acc_owner']=dict(current_acc['following_owner'])",1)
    payload={'core/longitudinal.py':patched.encode('utf-8')}
    for name in ('core/steering_replay.py','core/navigation/longitudinal_diagnostics.py'):
        payload[name]=(ROOT/name).read_bytes()
    config=(APP/'core/navigation/diagnostic_build_config.py').read_text(encoding='utf-8')
    assert config.count("BUILD = 'UP-DIAGNOSTIC-20261026-26'")==1
    payload['core/navigation/diagnostic_build_config.py']=config.replace(
        "BUILD = 'UP-DIAGNOSTIC-20261026-26'",'BUILD = '+repr(BUILD)).encode('utf-8')
    stage=OUT/'verification-runtime'
    for folder in ('core','plugins','sdk','ui'):
        for path in (APP/folder).rglob('*.py'):
            target=stage/path.relative_to(APP);target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(path.read_bytes())
    for name,raw in payload.items():
        target=stage/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw);compile(raw,name,'exec')
    for folder in [stage/name for name in ('core','plugins','sdk','ui')]+[
            p for p in stage.rglob('*') if p.is_dir() and any(p.glob('*.py'))]:
        marker=folder/'__init__.py'
        if not marker.exists():marker.write_text('# Offline namespace only; not deployed.\n',encoding='utf-8')
    def functions(text):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(text).body if isinstance(n,ast.FunctionDef)}
    a,b=functions(base),functions(patched)
    changed=[n for n in a if a[n]!=b[n]]
    assert changed==['signal_drive_write_guard','_engine_decision'],changed
    manifest=dict(build=BUILD,base_receipt_sha256=sha(receipt_raw),required_base=receipt['files'],
        files=[dict(path=n,sha256=sha(raw),bytes=len(raw),previous_sha256=sha((APP/n).read_bytes())) for n,raw in payload.items()],
        changed_control_functions=changed,unchanged_controls=['core/engine.py','plugins/acc/main.py',
            'plugins/drivepolicy/main.py','plugins/autopilot/main.py','core/service_brake_hold.py'],
        source_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        working_tree_uncommitted=True,plugin_versions_changed=False,dll_changed=False,
        installed_unchanged=True,game_verified=False,deployment_authorized=False)
    for name in manifest['unchanged_controls']:assert (stage/name).read_bytes()==(APP/name).read_bytes()
    (OUT/'candidate-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    targets=load(ROOT/'docs/steering-audit/oct25-incident-assembly/daemon26-release/test-selection.json')['targets']
    targets += ['tests/traffic/test_moving_transition.py','tests/diagnostics/test_late_assembly.py','tests/diagnostics/test_capture_failures.py',
        'tests/traffic/test_native_owner_contract.py','tests/traffic/test_crossing_dev_hud.py','tests/lifecycle/test_stop_completion.py',
        'tests/signals/test_signal_lifecycle.py']
    targets=list(dict.fromkeys(targets))
    selection=dict(targets=targets,test_sha256={p:sha((ROOT/p).read_bytes()) for p in sorted({t.split('::')[0] for t in targets})})
    (OUT/'test-selection.json').write_text(json.dumps(selection,indent=2),encoding='utf-8')
    verify(manifest);print(json.dumps(dict(build=BUILD,files=len(payload),stage=str(stage))))


def qualify():
    manifest=load(OUT/'candidate-manifest.json');verify(manifest)
    selection=load(OUT/'test-selection.json')
    for p,digest in selection['test_sha256'].items():assert sha((ROOT/p).read_bytes())==digest
    log=OUT/'qualification-tests.log';assert not log.exists()
    script=('import sys;sys.path.insert(0,'+repr(str(OUT/'verification-runtime'))+');'
        'import core.engine,core.longitudinal,core.steering_replay,core.navigation.longitudinal_diagnostics,plugins.autopilot.main;'
        'print("FROZEN RUNTIME",core.longitudinal.__file__,flush=True);'
        'import pytest;raise SystemExit(pytest.main('+repr(selection['targets']+['-q'])+'))')
    with log.open('x',encoding='utf-8') as stream:
        result=subprocess.run([sys.executable,'-c',script],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
    verify(manifest)
    (OUT/'qualification-result.json').write_text(json.dumps(dict(exit_code=result.returncode,
        log_sha256=sha(log.read_bytes()),runtime_sha256={r['path']:r['sha256'] for r in manifest['files']},
        test_selection_sha256=sha((OUT/'test-selection.json').read_bytes()),installed_unchanged=True,
        whole_pytest_run=False,game_verified=False),indent=2),encoding='utf-8')
    print(log.read_text(encoding='utf-8')[-3000:]);sys.exit(result.returncode)


def package():
    manifest=load(OUT/'candidate-manifest.json');verify(manifest)
    proof=load(OUT/'qualification-result.json')
    if proof['exit_code']:
        supplement=load(OUT/'qualification-completion.json')
        assert supplement['exit_code']==0 and supplement['runtime_unchanged']
        assert supplement['original_result_sha256']==sha((OUT/'qualification-result.json').read_bytes())
        assert supplement['supplement_log_sha256']==sha((OUT/'contract-compatibility-regressions.log').read_bytes())
        assert supplement['adapted_test_sha256']==sha((ROOT/'tests/traffic/test_crossing_dev_hud.py').read_bytes())
        proof=dict(proof,completion=supplement,exit_code=0)
    assert sha((OUT/'qualification-tests.log').read_bytes())==proof['log_sha256']
    measured=load(OUT/'qualification-measurements.json')
    assert measured['numeric_gates_passed'] and measured['runtime_sha256']==proof['runtime_sha256']
    payload={r['path']:(OUT/'verification-runtime'/r['path']).read_bytes() for r in manifest['files']}
    release=dict(manifest,qualification=proof,measurements=measured,game_verified=False,deployment_authorized=False)
    release['fixture_sha256']={p:sha((ROOT/p).read_bytes()) for p in
        ('tests/fixtures/oct29-motion-transition.json','tests/fixtures/oct29-history-overflow.json')}
    payload['runtime-manifest.json']=json.dumps(release,indent=2).encode('utf-8')
    originals={r['path']:(APP/r['path']).read_bytes() for r in manifest['files']}
    originals['manual-deployment.json']=(APP/'manual-deployment.json').read_bytes()
    output={}
    for name,values in (('ultrapilot-oct29-incident-01-candidate.zip',payload),('rollback-installed-base.zip',originals)):
        path=OUT/name
        with zipfile.ZipFile(path,'x',zipfile.ZIP_DEFLATED) as archive:
            for n,raw in values.items():archive.writestr(n,raw)
        with zipfile.ZipFile(path) as archive:
            assert archive.testzip() is None
            for n,raw in values.items():assert archive.read(n)==raw
        output[name]=dict(sha256=sha(path.read_bytes()),bytes=path.stat().st_size)
    (OUT/'release-receipt.json').write_text(json.dumps(dict(build=BUILD,archives=output,
        deployed=False,game_verified=False),indent=2),encoding='utf-8')
    print(json.dumps(output,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','qualify','package'])
    action=p.parse_args().action
    dict(prepare=prepare,qualify=qualify,package=package)[action]()
