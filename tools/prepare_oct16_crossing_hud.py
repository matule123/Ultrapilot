"""Hash-bound complete verification/candidate preparation. Never deploys."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.prepare_oct14_runtime import RUNTIME as BASE_RUNTIME

RUNTIME=BASE_RUNTIME+('core/hud.py','core/traffic_dev_hud.py','ui/visualization.py')


def sha(value):return hashlib.sha256(value).hexdigest()


def hashes():return {name:sha((ROOT/name).read_bytes()) for name in RUNTIME}


def verify(log):
    log=log.resolve()
    if not log.is_relative_to(ROOT/'docs/steering-audit') or log.exists():
        raise ValueError('Use a new workspace audit log, preserving previous evidence')
    before=hashes()
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()
    with log.open('x',encoding='utf-8') as out:
        result=subprocess.run([sys.executable,'-m','pytest','tests','-q'],cwd=ROOT,
            env=dict(os.environ,PYTHONCASEOK='1'),stdout=out,stderr=subprocess.STDOUT)
    after=hashes()
    if after!=before:raise ValueError('Candidate runtime changed during complete verification')
    record=dict(exit_code=result.returncode,runtime_sha256=after,log_sha256=sha(log.read_bytes()),
        source_head=head,game_verified=False)
    log.with_suffix('.verified.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    print('\n'.join(log.read_text(errors='replace').splitlines()[-40:]),flush=True)
    return result.returncode


def prepare(log,output):
    if not output.resolve().is_relative_to(ROOT/'docs/steering-audit') or output.exists():
        raise ValueError('Use a new candidate path in workspace audit directory')
    verification=json.loads(log.with_suffix('.verified.json').read_text())
    if verification['exit_code']!=0 or verification['log_sha256']!=sha(log.read_bytes()):
        raise ValueError('Successful complete-suite receipt required')
    if verification['runtime_sha256']!=hashes():
        raise ValueError('Runtime changed after complete verification')
    install=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')
    receipt_bytes=(install/'manual-deployment.json').read_bytes()
    receipt=json.loads(receipt_bytes.decode('utf-8-sig'))
    for row in receipt['files']:
        if sha(Path(row['target']).read_bytes())!=row['sha256'].lower():
            raise ValueError('Installed base changed: '+row['target'])
    from core.app_release import plugin_versions
    versions=plugin_versions(ROOT)
    payload={'runtime/'+name:(ROOT/name).read_bytes() for name in RUNTIME}
    delta=[name for name in RUNTIME if not (install/name).exists() or
        (install/name).read_bytes().replace(b'\r\n',b'\n')!=payload['runtime/'+name].replace(b'\r\n',b'\n')]
    manifest=dict(schema=1,kind='candidate_not_deployment',runtime_authorized=False,
        scope='oct16-crossing-qualification-continuity-and-classic-3d-dev-hud',
        source_head=verification['source_head'],working_tree_uncommitted=True,game_verified=False,
        supersedes_candidate='oct15-refresh-protocol-v1 for future deployment; historical originals retained',
        required_base_receipt_sha256=sha(receipt_bytes),required_base_files=receipt['files'],
        native_changed=False,versions={k:versions[k] for k in ('acc','drivepolicy','autopilot','map','hud','turnsignals')},
        required_native_version=receipt['dll_version'],changed_content_vs_installation=delta,
        full_verification=verification,
        files=[dict(path=k,bytes=len(v),sha256=sha(v)) for k,v in payload.items()],
        requirements=['Separate user approval and whole-set rollback backup before any installation',
            'Recheck base hashes; apply every payload as one set and verify SHA-256',
            'Keep existing native DLLs, settings/cache, commit marker and original diagnostics unchanged'],
        limitations=['Historical exact ACC invalid branch/full actor scene were not retained',
            'Constant-motion prediction is not a lane or actor-intent certificate',
            'Unmatched/old geometry is explicitly unverified; no fabricated trajectory or clearance',
            'No deployment or ETS2 verification'])
    with zipfile.ZipFile(output,'x',zipfile.ZIP_DEFLATED) as archive:
        for name,data in payload.items():archive.writestr(name,data)
        archive.writestr('candidate-manifest.json',json.dumps(manifest,indent=2))
    with zipfile.ZipFile(output) as archive:
        for row in manifest['files']:assert sha(archive.read(row['path']))==row['sha256']
    output.with_suffix('.manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps(dict(path=str(output),sha256=sha(output.read_bytes()),bytes=output.stat().st_size,
        payloads=len(payload),changed=delta,installed=False),indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log',type=Path,required=True)
    parser.add_argument('--verify',action='store_true')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.verify:raise SystemExit(verify(args.log))
    if not args.output:parser.error('--output is required when preparing a candidate')
    prepare(args.log,args.output)
