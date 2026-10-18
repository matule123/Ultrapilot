"""Freeze, verify once and prepare a consistent candidate. Never deploys."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile

from tools.prepare_oct17_joint_candidate import RUNTIME

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/steering-audit/oct17-systemic-longitudinal'
INSTALL=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')


def digest(raw):return hashlib.sha256(raw).hexdigest()


def hashes():
    names=set(RUNTIME)
    for directory in ('core','plugins','sdk','ui','tests','tools'):
        names.update(p.relative_to(ROOT).as_posix() for p in (ROOT/directory).rglob('*.py'))
    names.update(p.relative_to(ROOT).as_posix() for p in (ROOT/'tests/fixtures').glob('*.json'))
    return {name:digest((ROOT/name).read_bytes()) for name in sorted(names)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify',action='store_true');parser.add_argument('--package',action='store_true')
    parser.add_argument('--label',default='final',help='Unique record name; never overwrite failed verification')
    args=parser.parse_args()
    if args.verify==args.package:parser.error('Choose exactly one action')
    if not re.fullmatch(r'[a-z0-9-]+',args.label):parser.error('Invalid record label')
    frozen=OUT/(args.label+'-frozen.json');proof=OUT/(args.label+'-verification.json');log=OUT/(args.label+'-full-suite.log')
    if args.verify:
        if any(p.exists() for p in (frozen,proof,log)):raise ValueError('Never repeat or overwrite the frozen run')
        before=hashes()
        frozen.write_text(json.dumps(dict(head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(),
            uncommitted=True,sha256=before),indent=2),encoding='utf-8')
        env=dict(os.environ,PYTHONCASEOK='1');env.pop('UP_OCT18_SYSTEMIC_BASELINE',None)
        with log.open('x',encoding='utf-8') as stream:
            full=subprocess.run([sys.executable,'-m','pytest','tests','-q'],cwd=ROOT,env=env,
                stdout=stream,stderr=subprocess.STDOUT)
        record=dict(exit_code=full.returncode,unchanged=hashes()==before,
            full_log_sha256=digest(log.read_bytes()),sha256=before,
            system_complete=False,historical_inner_delay_resolved=False,game_verified=False,deployed=False)
        proof.write_text(json.dumps(record,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in record.items() if k!='sha256'},indent=2))
        raise SystemExit(0 if full.returncode==0 and record['unchanged'] else 1)
    verified=json.loads(proof.read_text(encoding='utf-8'))
    if verified['exit_code'] or not verified['unchanged'] or verified['sha256']!=hashes():raise ValueError('Matching full PASS required')
    if digest(log.read_bytes())!=verified['full_log_sha256']:raise ValueError('Verification log changed')
    receipt=(INSTALL/'manual-deployment.json').read_bytes();base=json.loads(receipt.decode('utf-8-sig'))
    for item in base['files']:
        if digest(Path(item['target']).read_bytes())!=item['sha256'].lower():raise ValueError('Installed base changed')
    payload={name:(ROOT/name).read_bytes() for name in RUNTIME}
    native=(INSTALL/'assets/ets2la_plugin.dll').read_bytes()
    if digest(native)!='fd06c12985fb67c48a7b9aaf5dd500d81e6ac23b928b79c95997bb8ed5d55d27':raise ValueError('Unexpected native base')
    original={name:(INSTALL/name).read_bytes() for name in RUNTIME}
    manifest=dict(kind='candidate_not_deployment',runtime_authorized=False,game_verified=False,system_complete=False,
        historical_inner_delay_resolved=False,source_head=json.loads(frozen.read_text())['head'],
        working_tree_uncommitted=True,base_receipt_sha256=digest(receipt),required_base_files=base['files'],
        required_native_version='1.59.5-up-parked-records',required_native_sha256=digest(native),native_changed=False,
        verification_sha256=digest(proof.read_bytes()),
        versions={k:base[k] for k in ('acc_version','autopilot_version','map_version','drivepolicy_version','turnsignals_version')},
        files=[dict(path=n,sha256=digest(raw),previous_sha256=digest(original[n]),bytes=len(raw)) for n,raw in sorted(payload.items())],
        blockers=['Historical Engine inner phase causing late traffic remains unrecorded',
            'Significant-event quota still requires separately approved archival/readiness check',
            'Separate deployment approval and game acceptance remain required'],
        supersedes='Oct17 following/hold candidate as a proposed package only; all original proof files retained')
    backup=OUT/'rollback-runtime.zip'
    with zipfile.ZipFile(backup,'x',zipfile.ZIP_DEFLATED) as archive:
        for name,raw in original.items():archive.writestr(name,raw)
        archive.writestr('manual-deployment.json',receipt)
    with zipfile.ZipFile(backup) as archive:
        for name,raw in original.items():assert digest(archive.read(name))==digest(raw)
    manifest['rollback_archive_sha256']=digest(backup.read_bytes())
    payload['candidate-manifest.json']=json.dumps(manifest,indent=2).encode()
    target=OUT/'ultrapilot-oct18-systemic-candidate.zip'
    with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED) as archive:
        for name,raw in payload.items():archive.writestr(name,raw)
    with zipfile.ZipFile(target) as archive:
        for name,raw in payload.items():assert digest(archive.read(name))==digest(raw)
    result=dict(path=str(target),sha256=digest(target.read_bytes()),entries=len(payload),runtime_files=len(RUNTIME),
        rollback_path=str(backup),rollback_sha256=digest(backup.read_bytes()),
        full_suite_verified=True,system_complete=False,game_verified=False,deployed=False)
    (OUT/'candidate-receipt.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    (OUT/'candidate-manifest.json').write_bytes(payload['candidate-manifest.json'])
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
