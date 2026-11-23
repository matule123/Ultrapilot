"""Freeze one whole-suite run and prepare/read-back one coordinated package.

Never writes the installation, arms diagnostics or controls the game.
"""
import argparse
import ast
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import zipfile

from tools.prepare_oct17_joint_candidate import RUNTIME as PREVIOUS

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/steering-audit/oct18-joint-handoffs'
INSTALL=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')
RUNTIME=tuple(dict.fromkeys((*PREVIOUS,'bootloader.py','core/ipc/shared_state.py','sdk/plugin_sdk.py')))


def sha(raw):return hashlib.sha256(raw).hexdigest()


def hashes():
    names=set(RUNTIME)
    for directory in ('core','plugins','sdk','ui','tests','tools'):
        names.update(p.relative_to(ROOT).as_posix() for p in (ROOT/directory).rglob('*.py'))
    names.update(p.relative_to(ROOT).as_posix() for p in (ROOT/'tests/fixtures').glob('*.json'))
    return {name:sha((ROOT/name).read_bytes()) for name in sorted(names)}


def versions():
    result={}
    for plugin in ('acc','autopilot','map','drivepolicy','turnsignals'):
        tree=ast.parse((ROOT/f'plugins/{plugin}/main.py').read_text(encoding='utf-8-sig'))
        for node in ast.walk(tree):
            if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='VERSION' for t in node.targets):
                result[plugin]=ast.literal_eval(node.value)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify',action='store_true');parser.add_argument('--package',action='store_true')
    parser.add_argument('--label',default='final',help='New immutable verification name; earlier failed evidence is retained')
    args=parser.parse_args()
    if args.verify==args.package:parser.error('Choose one action')
    if not re.fullmatch(r'[a-z0-9-]+',args.label):parser.error('Invalid label')
    frozen=OUT/(args.label+'-frozen.json');proof=OUT/(args.label+'-verification.json');log=OUT/(args.label+'-full-suite.log')
    if args.verify:
        if any(p.exists() for p in (frozen,proof,log)):raise ValueError('One final run; preserve earlier evidence')
        before=hashes()
        frozen.write_text(json.dumps(dict(head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(),
            uncommitted=True,versions=versions(),sha256=before),indent=2),encoding='utf-8')
        env=dict(os.environ,PYTHONCASEOK='1')
        for name in ('UP_OCT18_SYSTEMIC_BASELINE','UP_OCT17_FOLLOW_BASELINE','ULTRAPILOT_OCT14_BASELINE'):
            env.pop(name,None)
        with log.open('x',encoding='utf-8') as stream:
            full=subprocess.run([sys.executable,'-m','pytest','tests','-q'],cwd=ROOT,env=env,
                stdout=stream,stderr=subprocess.STDOUT)
        result=dict(exit_code=full.returncode,unchanged=before==hashes(),sha256=before,
            log_sha256=sha(log.read_bytes()),system_complete=False,game_verified=False,deployed=False)
        proof.write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in result.items() if k!='sha256'},indent=2))
        raise SystemExit(0 if not full.returncode and result['unchanged'] else 1)
    result=json.loads(proof.read_text(encoding='utf-8'))
    if result['exit_code'] or not result['unchanged'] or result['sha256']!=hashes():raise ValueError('Matching frozen PASS required')
    if sha(log.read_bytes())!=result['log_sha256']:raise ValueError('Verification log changed')
    receipt=(INSTALL/'manual-deployment.json').read_bytes();deployed=json.loads(receipt.decode('utf-8-sig'))
    for row in deployed['files']:
        if sha(Path(row['target']).read_bytes())!=row['sha256'].lower():raise ValueError('Installed base changed')
    payload={name:(ROOT/name).read_bytes() for name in RUNTIME}
    originals={name:(INSTALL/name).read_bytes() for name in RUNTIME}
    rollback=OUT/'rollback-runtime.zip';target=OUT/'ultrapilot-oct18-joint-handoffs-candidate.zip'
    with zipfile.ZipFile(rollback,'x',zipfile.ZIP_DEFLATED) as archive:
        for name,raw in originals.items():archive.writestr(name,raw)
        archive.writestr('manual-deployment.json',receipt)
    with zipfile.ZipFile(rollback) as archive:
        for name,raw in originals.items():assert sha(archive.read(name))==sha(raw)
    manifest=dict(kind='coordinated_candidate_not_deployment',source_head=json.loads(frozen.read_text())['head'],
        working_tree_uncommitted=True,runtime_authorized=False,game_verified=False,system_complete=False,
        versions=versions(),base_receipt_sha256=sha(receipt),required_base_files=deployed['files'],
        required_native_sha256=sha((INSTALL/'assets/ets2la_plugin.dll').read_bytes()),native_changed=False,
        verification_sha256=sha(proof.read_bytes()),rollback_sha256=sha(rollback.read_bytes()),
        files=[dict(path=n,sha256=sha(raw),previous_sha256=sha(originals[n]),bytes=len(raw)) for n,raw in sorted(payload.items())],
        known_limits=['Exact final historical traffic producer phase after 20469.5671095 is missing',
            'Original complete actor geometry for owner 78 at first fault was not preserved',
            'No ETS2 verification of these repairs; backend return is not game consumption'],
        supersedes='Earlier Oct18 systemic candidate as a package proposal only; preserve its original evidence',
        install_gate='User whole-suite acceptance and separate explicit deployment approval; application/game stopped')
    payload['candidate-manifest.json']=json.dumps(manifest,indent=2).encode('utf-8')
    with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED) as archive:
        for name,raw in payload.items():archive.writestr(name,raw)
    with zipfile.ZipFile(target) as archive:
        for name,raw in payload.items():assert sha(archive.read(name))==sha(raw)
    assert result['sha256']==hashes()
    saved=dict(path=str(target),sha256=sha(target.read_bytes()),runtime_files=len(RUNTIME),
        rollback=str(rollback),rollback_sha256=sha(rollback.read_bytes()),
        integrity_valid=True,game_verified=False,deployed=False,system_complete=False)
    (OUT/'candidate-manifest.json').write_bytes(payload['candidate-manifest.json'])
    (OUT/'candidate-receipt.json').write_text(json.dumps(saved,indent=2),encoding='utf-8')
    print(json.dumps(saved,indent=2))


if __name__=='__main__':main()
