"""Build one hash-bound renewal candidate; no deployment and no DLL payload."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.prepare_oct14_runtime import RUNTIME
from core.app_release import plugin_versions


def prepare(output, log):
    output, log = output.resolve(), log.resolve()
    if not output.is_relative_to(ROOT/'docs/steering-audit') or output.exists():
        raise ValueError('Preserve all prior candidates; use a new workspace ZIP')
    sha = lambda b: hashlib.sha256(b).hexdigest()
    verification = json.loads(log.with_suffix('.verified.json').read_text())
    if verification['exit_code'] != 0 or sha(log.read_bytes()) != verification['log_sha256']:
        raise ValueError('Successful complete test receipt required')
    payload = {'runtime/'+p:(ROOT/p).read_bytes() for p in RUNTIME}
    for p in RUNTIME:
        if verification['runtime_sha256'][p] != sha(payload['runtime/'+p]):
            raise ValueError('Runtime changed after verification: '+p)
    install = Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')
    receipt_bytes = (install/'manual-deployment.json').read_bytes()
    receipt = json.loads(receipt_bytes.decode('utf-8-sig'))
    for row in receipt['files']:
        if sha(Path(row['target']).read_bytes()) != row['sha256'].lower():
            raise ValueError('Installed base changed: '+row['target'])
    base = ROOT/'docs/steering-audit/oct15-traffic-lease/ultrapilot-oct15-traffic-lease-candidate-v1.zip'
    with zipfile.ZipFile(base) as archive:
        previous = json.loads(archive.read('candidate-manifest.json'))
        for row in previous['files']:
            if sha(archive.read(row['path'])) != row['sha256']:
                raise ValueError('Prior candidate integrity failure')
    delta = [p for p in RUNTIME if (install/p).read_bytes().replace(b'\r\n',b'\n') !=
             payload['runtime/'+p].replace(b'\r\n',b'\n')]
    versions = plugin_versions(ROOT)
    manifest = dict(schema=1, kind='candidate_not_deployment', runtime_authorized=False,
        scope='oct15-bounded-refresh-response-protocol', source_head=verification['source_head'],
        working_tree_uncommitted=True, game_verified=False,
        supersedes_candidate='oct15-traffic-lease-v1; retained as historical deployed evidence',
        plugin_implementation_changed=False, native_changed=False,
        versions={**{k:versions[k] for k in ('acc','drivepolicy','autopilot','map','turnsignals')},
                  'native':receipt['dll_version']},
        verified_base_receipt_sha256=sha(receipt_bytes), verified_previous_candidate_sha256=sha(base.read_bytes()),
        required_base_files=receipt['files'], changed_content_vs_installation=delta,
        full_verification=verification,
        files=[dict(path=k,size=len(v),sha256=sha(v)) for k,v in payload.items()],
        deployment_requirements=[
            'Separate user approval; both applications off; whole-set rollback backup',
            'Recheck every required base hash, apply complete runtime payload, verify every SHA-256',
            'Keep receipt-identified native DLLs, settings/cache/original evidence and commit marker unchanged'],
        limits=['Historical complete AP response availability and the 457 ms completion gap remain unproven',
                'A missing/late complete decision correctly still causes a safety stop',
                'Existing significant-event quota remains full; no originals removed',
                'Offline models do not prove ETS2 consumption, comfort or universal reliability'])
    with zipfile.ZipFile(output,'x',zipfile.ZIP_DEFLATED) as archive:
        for name, content in payload.items():
            archive.writestr(name,content)
        archive.writestr('candidate-manifest.json',json.dumps(manifest,indent=2)+'\n')
    with zipfile.ZipFile(output) as archive:
        for row in manifest['files']:
            if sha(archive.read(row['path'])) != row['sha256']:
                raise ValueError('Candidate readback mismatch')
    output.with_suffix('.manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(path=str(output),sha256=sha(output.read_bytes()),files=len(payload),
                         changed_content=delta,installed=False),indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verification-log',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    prepare(args.output,args.verification_log)
