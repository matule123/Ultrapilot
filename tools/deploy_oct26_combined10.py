"""Deploy only the user-approved frozen combined10 payload, with rollback."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / 'docs/steering-audit/oct25-incident-assembly/combined10-release'
APP = Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def stopped():
    command = "Get-CimInstance Win32_Process | Select-Object Name,CommandLine | ConvertTo-Json -Compress"
    rows = json.loads(subprocess.check_output(['powershell', '-NoProfile', '-Command', command], text=True))
    for row in rows:
        name = row['Name'].lower()
        cmd = (row.get('CommandLine') or '').lower()
        if 'eurotrucks2' in name or 'ultrapilot' in name or (name.startswith('python') and str(APP).lower() in cmd):
            raise RuntimeError('Application still running: ' + name)

def main():
    stopped()
    manifest = json.loads((RELEASE / 'release-manifest.json').read_text())
    archives = {}
    for name, expected in (
        ('ultrapilot-diagnostic-20261026-10-candidate.zip', '1a22bb40ca93fb21cada9fd0db25cb90d91f0dabf98b9245c448ecf3de41428e'),
        ('rollback-installed-base.zip', '511ce34ee1803957d72bf2a050ba6dd5de415eb83cc85c9a05aae48cee189e3d')):
        path = RELEASE / name
        assert sha(path.read_bytes()) == expected, name
        with zipfile.ZipFile(path) as archive:
            assert archive.testzip() is None
            archives[name] = {n: archive.read(n) for n in archive.namelist()}
    payload = archives['ultrapilot-diagnostic-20261026-10-candidate.zip']
    receipt_path = APP / 'manual-deployment.json'
    receipt_raw = receipt_path.read_bytes()
    assert sha(receipt_raw) == manifest['base_receipt_sha256'], 'Receipt drift'
    receipt = json.loads(receipt_raw)
    for entry in receipt['files']:
        assert sha(Path(entry['target']).read_bytes()) == entry['sha256'].lower(), entry['target']
    for entry in manifest['required_base']:
        assert sha(Path(entry['target']).read_bytes()) == entry['sha256'].lower(), entry['target']
    originals = {}
    for entry in manifest['files']:
        rel = entry['path']
        target = (APP / rel).resolve()
        assert target.is_relative_to(APP.resolve())
        raw = payload[rel]
        assert sha(raw) == entry['sha256'] and len(raw) == entry['bytes'], rel
        compile(raw, rel, 'exec')
        original = target.read_bytes() if target.exists() else None
        assert (sha(original) if original is not None else None) == entry['previous_sha256'], rel
        originals[rel] = original
    backup_payload = archives['rollback-installed-base.zip']
    for rel, raw in originals.items():
        if raw is not None:
            assert backup_payload[rel] == raw, 'Backup mismatch: ' + rel
    assert backup_payload['manual-deployment.json'] == receipt_raw
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    transaction = RELEASE / ('deployment-' + stamp)
    transaction.mkdir()
    (transaction / 'manual-deployment.before.json').write_bytes(receipt_raw)
    # Preserve a second independent copy of the verified return archive.
    (transaction / 'rollback-installed-base.zip').write_bytes((RELEASE / 'rollback-installed-base.zip').read_bytes())
    for entry in manifest['files']:
        stage = transaction / 'staging' / entry['path']
        stage.parent.mkdir(parents=True, exist_ok=True)
        stage.write_bytes(payload[entry['path']])
    stopped()
    try:
        for entry in manifest['files']:
            rel = entry['path']
            os.replace(transaction / 'staging' / rel, APP / rel)
        for entry in manifest['files']:
            assert sha((APP / entry['path']).read_bytes()) == entry['sha256']
        for entry in manifest['files']:
            target = str(APP / entry['path'])
            existing = next((v for v in receipt['files'] if Path(v['target']) == Path(target)), None)
            update = dict(relative_path=entry['path'], target=target, sha256=entry['sha256'], previous_sha256=entry['previous_sha256'])
            if existing is None:
                receipt['files'].append(update)
            else:
                existing.update(update)
        receipt['diagnostic_deployment'] = dict(build=manifest['build'], deployed_at_utc=stamp, user_authorized=True, game_started=False, game_verified=False, source_head=manifest['source_head'], working_tree_uncommitted=True, base_receipt_sha256=sha(receipt_raw), candidate_sha256=sha((RELEASE / 'ultrapilot-diagnostic-20261026-10-candidate.zip').read_bytes()), rollback=str(transaction / 'rollback-installed-base.zip'), runtime_files=manifest['files'])
        receipt_stage = transaction / 'manual-deployment.after.json'
        receipt_stage.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
        receipt_path.write_bytes(receipt_stage.read_bytes())
        for entry in receipt['files']:
            assert sha(Path(entry['target']).read_bytes()) == entry['sha256'].lower(), entry['target']
    except BaseException:
        for rel, raw in originals.items():
            target = APP / rel
            if raw is not None:
                target.write_bytes(raw)
            elif target.exists():
                assert sha(target.read_bytes()) == next(v['sha256'] for v in manifest['files'] if v['path'] == rel)
                target.unlink()
        receipt_path.write_bytes(receipt_raw)
        raise
    result = dict(status='DEPLOYED_HASH_VERIFIED', build=manifest['build'], runtime_files=7, receipt_files=len(receipt['files']), backup=str(transaction / 'rollback-installed-base.zip'), game_started=False)
    (transaction / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
