"""Freeze, verify ONCE and package the Oct17 signal-completion candidate.

No install, game control, settings change or authority. Preserve the preceding
partial package/proofs; original signal reproductions now belong to tests/.
"""
import ast
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile

from tools.prepare_oct16_signal_handoff_runtime import base

ROOT=base.ROOT
OUT=ROOT/'docs/steering-audit/oct17-joint-lifecycle'
NATIVE=OUT/'native-candidate-b'
RUNTIME=tuple(dict.fromkeys((*base.RUNTIME,'plugins/autopilot/main.py',
    'plugins/map/main.py','core/sdk/signal_snapshot.py')))


def digest(data):return hashlib.sha256(data).hexdigest()


def hashes():
    names=set(RUNTIME)
    for folder in ('core','plugins','sdk','ui','tests','tools'):
        names.update(str(p.relative_to(ROOT)).replace('\\','/') for p in (ROOT/folder).rglob('*.py'))
    names.add(str((NATIVE/'ets2la_plugin.dll').relative_to(ROOT)).replace('\\','/'))
    names.add(str((NATIVE/'build-receipt.json').relative_to(ROOT)).replace('\\','/'))
    native=json.loads((NATIVE/'build-receipt.json').read_text())
    for relative in native['files']:
        names.add(str((NATIVE/relative).relative_to(ROOT)).replace('\\','/'))
    names.add('tests/fixtures/oct17-signal-profile-original.json')
    return {n:digest((ROOT/n).read_bytes()) for n in sorted(names)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify',action='store_true');parser.add_argument('--package',action='store_true')
    parser.add_argument('--label',default='completion-final',
        help='New verification record prefix; failed earlier records are never overwritten')
    args=parser.parse_args()
    if args.verify==args.package:parser.error('Choose exactly one action')
    if not re.fullmatch(r'[a-z0-9-]+',args.label):parser.error('Invalid verification label')
    frozen=OUT/f'{args.label}-frozen.json';verified=OUT/f'{args.label}-verification.json';log=OUT/f'full-{args.label}.log'
    if args.verify:
        if any(p.exists() for p in (frozen,verified,log)):raise ValueError('Do not repeat or overwrite the final run')
        before=hashes()
        frozen.write_text(json.dumps(dict(source_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(),
            working_tree_uncommitted=True,sha256=before,task_complete=False,game_verified=False),indent=2),encoding='utf-8')
        env=dict(os.environ,PYTHONCASEOK='1')
        with log.open('x',encoding='utf-8') as stream:
            result=subprocess.run([sys.executable,'-m','pytest','tests','-q'],cwd=ROOT,env=env,
                stdout=stream,stderr=subprocess.STDOUT)
        after=hashes()
        record=dict(full_suite_passed=result.returncode==0 and before==after,exit_code=result.returncode,
            unchanged=before==after,sha256=before,log_sha256=digest(log.read_bytes()),
            original_signal_reproduction='Both unchanged assertions collected by tests/signals/test_signal_completion.py',
            task_complete=False,game_verified=False,runtime_authorized=False)
        verified.write_text(json.dumps(record,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in record.items() if k!='sha256'},indent=2))
        raise SystemExit(0 if record['full_suite_passed'] else 1)
    proof=json.loads(verified.read_text())
    if not proof['full_suite_passed'] or proof['sha256']!=hashes() or proof['log_sha256']!=digest(log.read_bytes()):
        raise ValueError('Final source/verification does not match')
    target=OUT/'ultrapilot-oct17-signal-completion-candidate.zip'
    if target.exists():raise ValueError('Never overwrite a candidate')
    native=json.loads((NATIVE/'build-receipt.json').read_text())
    for name,expected in native['files'].items():
        if digest((NATIVE/name).read_bytes())!=expected:raise ValueError('Native build/source mismatch: '+name)
    deployed_bytes=(Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')/'manual-deployment.json').read_bytes()
    deployed=json.loads(deployed_bytes.decode('utf-8-sig'))
    for row in deployed['files']:
        if digest(Path(row['target']).read_bytes())!=row['sha256'].lower():
            raise ValueError('Installed base changed: '+row['target'])
    payload={name:(ROOT/name).read_bytes() for name in RUNTIME}
    payload['assets/ets2la_plugin.dll']=(NATIVE/'ets2la_plugin.dll').read_bytes()
    for source,name in ((NATIVE/'LICENSE.md','third-party/ets2la_plugin.LICENSE'),(NATIVE/'FMT_LICENSE','third-party/fmt.LICENSE')):
        payload[name]=source.read_bytes()
    versions={}
    for plugin in ('acc','autopilot','drivepolicy','map'):
        cls=next(n for n in ast.parse((ROOT/f'plugins/{plugin}/main.py').read_text(encoding='utf-8-sig')).body
            if isinstance(n,ast.ClassDef) and n.name=='Plugin')
        versions[plugin]=next(ast.literal_eval(n.value) for n in cls.body if isinstance(n,ast.Assign)
            and any(isinstance(t,ast.Name) and t.id=='VERSION' for t in n.targets))
    manifest=dict(scope='Spatial signal reference, signed existing PID, continuous approach receipt at zero ratio; preserved native records fix',
        source_head=json.loads(frozen.read_text())['source_head'],working_tree_uncommitted=True,
        files=[dict(path=n,sha256=digest(data),bytes=len(data)) for n,data in sorted(payload.items())],
        full_suite_verified=True,verification_sha256=digest(verified.read_bytes()),
        required_base_receipt_sha256=digest(deployed_bytes),required_base_files=deployed['files'],
        task_complete=False,game_verified=False,runtime_authorized=False,
        native_version=native['version'],plugin_versions=versions,
        offline_signal_cases_verified=True,game_acceptance_pending=True,
        dll_targets=['UltraPilot/assets/ets2la_plugin.dll','ETS2/bin/win_x64/plugins/ets2la_plugin.dll'],
        open=['Actual still-red slowdown under positive game drive lacks original engine/RPM/clutch/input-owner proof; no retrospective attribution',
            'Exact contacting car/acquisition absent; coverage and safe autonomous roundabout entry are not certified'],
        supersedes='ultrapilot-oct17-native-records-PARTIAL-candidate.zip and rejected profile trials as proposals only; originals retained',
        install_gate='Separate explicit approval; package preparation is not authorization')
    payload['native-build-receipt.json']=(NATIVE/'build-receipt.json').read_bytes()
    payload['candidate-manifest.json']=json.dumps(manifest,indent=2).encode('utf-8')
    with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED) as archive:
        for name,data in payload.items():archive.writestr(name,data)
    with zipfile.ZipFile(target) as archive:
        for name,data in payload.items():assert digest(archive.read(name))==digest(data)
    receipt=dict(path=str(target),sha256=digest(target.read_bytes()),entries=len(payload),
        runtime_dependencies=len(RUNTIME),offline_signal_cases_verified=True,
        task_complete=False,game_verified=False,deployed=False)
    (OUT/f'{args.label}-candidate-receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':main()
