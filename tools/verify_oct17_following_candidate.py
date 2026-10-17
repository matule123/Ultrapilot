"""Freeze/test/package the Oct17 following/hold candidate. Never installs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

from tools.prepare_oct17_joint_candidate import RUNTIME

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/steering-audit/oct17-following-hold-signals'
INSTALL=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')
TARGETED=('tests/test_oct17_following_hold_signals.py','tests/test_oct17_signal_completion.py',
    'tests/test_oct16_joint_traffic_regressions.py','tests/test_oct14_completion.py',
    'tests/test_oct10_signal_timing.py','tests/test_signal_stop_resume.py',
    'tests/test_continuous_service_stop.py','tests/test_significant_longitudinal_events.py',
    'tests/test_event_archive_preparation.py','tests/test_oct17_evidence_quota.py')


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
    args=parser.parse_args()
    if args.verify==args.package:parser.error('Choose exactly one action')
    frozen=OUT/'frozen.json';proof=OUT/'verification.json';log=OUT/'full-suite.log'
    if args.verify:
        if any(p.exists() for p in (frozen,proof,log)):raise ValueError('Never overwrite verification')
        before=hashes()
        frozen.write_text(json.dumps(dict(head=subprocess.check_output(['git','rev-parse','HEAD']).decode().strip(),
            uncommitted=True,sha256=before),indent=2))
        env=dict(os.environ,PYTHONCASEOK='1');env.pop('UP_OCT17_FOLLOW_BASELINE',None)
        targeted=OUT/'frozen-targeted.log'
        with targeted.open('x') as stream:
            first=subprocess.run([sys.executable,'-m','pytest',*TARGETED,'-q'],cwd=ROOT,env=env,
                stdout=stream,stderr=subprocess.STDOUT)
        if first.returncode or hashes()!=before:raise ValueError('Frozen targeted verification failed; no full run started')
        with log.open('x') as stream:
            full=subprocess.run([sys.executable,'-m','pytest','tests','-q'],cwd=ROOT,env=env,
                stdout=stream,stderr=subprocess.STDOUT)
        record=dict(exit_code=full.returncode,unchanged=hashes()==before,
            targeted_sha256=digest(targeted.read_bytes()),full_log_sha256=digest(log.read_bytes()),
            sha256=before,game_verified=False,deployed=False)
        proof.write_text(json.dumps(record,indent=2))
        print(json.dumps({k:v for k,v in record.items() if k!='sha256'},indent=2))
        raise SystemExit(0 if full.returncode==0 and record['unchanged'] else 1)
    verified=json.loads(proof.read_text())
    if verified['exit_code'] or not verified['unchanged'] or verified['sha256']!=hashes():raise ValueError('Matching full PASS required')
    if digest(log.read_bytes())!=verified['full_log_sha256']:raise ValueError('Verification log changed')
    receipt=(INSTALL/'manual-deployment.json').read_bytes();base=json.loads(receipt.decode('utf-8-sig'))
    for item in base['files']:
        if digest(Path(item['target']).read_bytes())!=item['sha256'].lower():raise ValueError('Installed base changed')
    payload={name:(ROOT/name).read_bytes() for name in RUNTIME}
    native=(INSTALL/'assets/ets2la_plugin.dll').read_bytes()
    if digest(native)!='fd06c12985fb67c48a7b9aaf5dd500d81e6ac23b928b79c95997bb8ed5d55d27':raise ValueError('Unexpected native base')
    # DLL is UNCHANGED: bind its required hash; do not include/install a duplicate.
    manifest=dict(kind='candidate_not_deployment',runtime_authorized=False,game_verified=False,
        source_head=json.loads(frozen.read_text())['head'],working_tree_uncommitted=True,
        base_receipt_sha256=digest(receipt),required_base_files=base['files'],
        required_native_version='1.59.5-up-parked-records',required_native_sha256=digest(native),native_changed=False,
        verification_sha256=digest(proof.read_bytes()),
        versions={k:base[k] for k in ('acc_version','autopilot_version','map_version','drivepolicy_version','turnsignals_version')},
        files=[dict(path=n,sha256=digest(data),bytes=len(data)) for n,data in sorted(payload.items())],
        blockers=['Separate approval before installation','Existing event quota requires prepared archival before a future evidence collection',
            'Historical full actor/route observations and game consumption not certified'],
        supersedes='oct17-signal-completion candidate as a future proposal; original evidence preserved')
    payload['candidate-manifest.json']=json.dumps(manifest,indent=2).encode()
    target=OUT/'ultrapilot-oct17-following-hold-candidate.zip'
    with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED) as archive:
        for name,raw in payload.items():archive.writestr(name,raw)
    with zipfile.ZipFile(target) as archive:
        for name,raw in payload.items():assert archive.read(name)==raw
    result=dict(path=str(target),sha256=digest(target.read_bytes()),entries=len(payload),
        full_suite_verified=True,game_verified=False,deployed=False)
    (OUT/'candidate-receipt.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))


if __name__=='__main__':main()
