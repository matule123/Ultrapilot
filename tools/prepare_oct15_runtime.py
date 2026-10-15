"""Hash-bound Oct 15 core candidate; no installation or native replacement."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.prepare_oct14_runtime import RUNTIME


def prepare(output, log):
    output, log = output.resolve(), log.resolve()
    if not output.is_relative_to(ROOT / 'docs/steering-audit') or output.exists():
        raise ValueError('Use a new workspace candidate; preserve previous evidence')
    sha = lambda b: hashlib.sha256(b).hexdigest()
    checked = json.loads(log.with_suffix('.verified.json').read_text())
    if checked['exit_code'] != 0 or sha(log.read_bytes()) != checked['log_sha256']:
        raise ValueError('Full suite verification receipt mismatch')
    payload = {}
    for name in RUNTIME:
        content = (ROOT / name).read_bytes()
        if sha(content) != checked['runtime_sha256'][name]:
            raise ValueError('Runtime changed after full verification: ' + name)
        payload['runtime/' + name] = content
    install = Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')
    receipt_bytes = (install / 'manual-deployment.json').read_bytes()
    receipt = json.loads(receipt_bytes.decode('utf-8-sig'))
    for row in receipt['files']:
        if sha(Path(row['target']).read_bytes()) != row['sha256'].lower():
            raise ValueError('Installed base differs from deployment receipt: ' + row['target'])
    base = ROOT / 'docs/steering-audit/oct14-roundabout/ultrapilot-oct14-roundabout-candidate-v5.zip'
    with zipfile.ZipFile(base) as archive:
        previous = json.loads(archive.read('candidate-manifest.json'))
        for row in previous['files']:
            if sha(archive.read(row['path'])) != row['sha256']:
                raise ValueError('Preserved v5 ZIP integrity failure')
    delta = [name for name in RUNTIME if (install / name).read_bytes().replace(b'\r\n', b'\n')
             != (ROOT / name).read_bytes().replace(b'\r\n', b'\n')]
    from core.app_release import plugin_versions
    versions = plugin_versions(ROOT)
    manifest = dict(schema=1, kind='candidate_not_deployment', runtime_authorized=False,
        scope='oct15-longitudinal-traffic-lease-handoff', source_head=checked['source_head'],
        working_tree_uncommitted=True, game_verified=False,
        supersedes_candidate='oct14-roundabout-v5 (candidate only; original retained)',
        versions={**{k: versions[k] for k in ('acc', 'drivepolicy', 'autopilot', 'map', 'turnsignals')},
                  'native': receipt['dll_version']},
        plugin_implementation_changed=False, native_changed=False,
        verified_base_receipt_sha256=sha(receipt_bytes),
        verified_base_v5_zip_sha256=sha(base.read_bytes()),
        required_base_files=receipt['files'], changed_content_vs_installation=delta,
        full_verification=checked,
        files=[dict(path=k, size=len(v), sha256=sha(v)) for k, v in payload.items()],
        deployment_requirements=[
            'Separate approval, both applications off, whole-set rollback backup',
            'Recheck all required base hashes before applying the complete runtime payload',
            'Retain the existing native DLL at both receipt paths; no DLL is included or replaced',
            'Preserve settings/cache/diagnostic originals and commit marker; verify every copied SHA-256'],
        limits=[
            'Exact historic traffic first delivery and initiating scheduling delay are not retained',
            'A newer qualified dependency permits zero-drive handoff, not use of the old pedals',
            'No new game verification; true evidence loss/identity/R/backend faults remain protected',
            'Significant-event quota is full; originals need separately approved archival, fault export remains available'])
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'x', zipfile.ZIP_DEFLATED) as archive:
        for name, content in payload.items():
            archive.writestr(name, content)
        archive.writestr('candidate-manifest.json', json.dumps(manifest, indent=2) + '\n')
    with zipfile.ZipFile(output) as archive:
        for row in manifest['files']:
            if sha(archive.read(row['path'])) != row['sha256']:
                raise ValueError('Candidate ZIP readback failed')
    output.with_suffix('.manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(path=str(output), sha256=sha(output.read_bytes()),
        files=len(payload), changed_content=delta, installed=False), indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--verification-log', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    prepare(args.output, args.verification_log)
