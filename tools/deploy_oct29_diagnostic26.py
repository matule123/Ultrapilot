"""Deploy frozen diagnostic 26 only; never starts applications."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / 'docs/steering-audit/oct25-incident-assembly/daemon26-release'
APP = Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def stopped():
    rows = json.loads(subprocess.check_output(['powershell', '-NoProfile', '-Command', 'Get-CimInstance Win32_Process | Select-Object Name,CommandLine | ConvertTo-Json -Compress'], text=True))
    for row in rows:
        name, cmd = row['Name'].lower(), (row.get('CommandLine') or '').lower()
        if 'eurotrucks' in name or 'ultrapilot' in name or (name.startswith('python') and str(APP).lower() in cmd):
            raise RuntimeError('Application running: ' + name)

def main():
    stopped()
    manifest = json.loads((RELEASE / 'release-manifest.json').read_bytes())
    qualification = json.loads((RELEASE / 'qualification-result.json').read_bytes())
    assert qualification['exit_code'] == 0 and qualification['unchanged']
    assert manifest['release_status'] == 'READY_FOR_CONTROLLED_CAPTURE_AWAITING_APPROVAL'
    archive_names = ['ultrapilot-diagnostic-20261026-26-candidate.zip', 'rollback-installed-base.zip']
    expected = ['b34abd71747a2b71f0ee4ab58e508bc908eb9362952418dd83a3cdc83fdf3291', 'ab7a5cbf3489d9c8633942d23a488fce23d80e7ce409f1fbcc2a3cbe73496339']
    contents = []
    for name, digest in zip(archive_names, expected):
        assert sha((RELEASE / name).read_bytes()) == digest, name
        with zipfile.ZipFile(RELEASE / name) as archive:
            assert archive.testzip() is None
            contents.append({n: archive.read(n) for n in archive.namelist()})
    payload, backup = contents
    receipt_path = APP / 'manual-deployment.json'
    receipt_raw = receipt_path.read_bytes()
    assert sha(receipt_raw) == manifest['base_receipt_sha256'], 'Base receipt drift'
    receipt = json.loads(receipt_raw)
    for entry in receipt['files'] + manifest['required_base']:
        assert sha(Path(entry['target']).read_bytes()) == entry['sha256'].lower(), entry['target']
    assert backup['manual-deployment.json'] == receipt_raw
    originals = {}
    assert len(manifest['files']) == 9
    for entry in manifest['files']:
        rel = entry['path']
        target = (APP / rel).resolve()
        assert target.is_relative_to(APP.resolve())
        raw = payload[rel]
        assert sha(raw) == entry['sha256'] == qualification['runtime_sha256'][rel]
        assert len(raw) == entry['bytes']
        compile(raw, rel, 'exec')
        originals[rel] = target.read_bytes()
        assert sha(originals[rel]) == entry['previous_sha256']
        assert backup[rel] == originals[rel]
    protected = {p: sha((APP / p).read_bytes()) for p in ('settings.json', 'commit.txt') if (APP / p).exists()}
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    transaction = RELEASE / ('deployment-' + stamp)
    transaction.mkdir()
    (transaction / 'rollback-installed-base.zip').write_bytes((RELEASE / archive_names[1]).read_bytes())
    (transaction / 'manual-deployment.before.json').write_bytes(receipt_raw)
    for entry in manifest['files']:
        stage = transaction / 'staging' / entry['path']
        stage.parent.mkdir(parents=True, exist_ok=True)
        stage.write_bytes(payload[entry['path']])
        assert sha(stage.read_bytes()) == entry['sha256']
    stopped()
    try:
        for entry in manifest['files']:
            os.replace(transaction / 'staging' / entry['path'], APP / entry['path'])
        for entry in manifest['files']:
            assert sha((APP / entry['path']).read_bytes()) == entry['sha256']
            target = APP / entry['path']
            item = next((v for v in receipt['files'] if Path(v['target']) == target), None)
            update = dict(relative_path=entry['path'], target=str(target), sha256=entry['sha256'], previous_sha256=entry['previous_sha256'])
            if item is None:
                receipt['files'].append(update)
            else:
                item.update(update)
        for entry in receipt['files']:
            assert sha(Path(entry['target']).read_bytes()) == entry['sha256'].lower(), entry['target']
        assert all(sha((APP / p).read_bytes()) == digest for p, digest in protected.items())
        receipt['diagnostic_deployment'] = dict(build=manifest['build'], deployed_at_utc=stamp, user_authorized=True, candidate_sha256=expected[0], rollback_sha256=expected[1], rollback=str(transaction / archive_names[1]), base_receipt_sha256=sha(receipt_raw), working_tree_uncommitted=True, source_head=manifest.get('source_head'), runtime_files=manifest['files'], game_started=False, game_verified=False)
        raw = (json.dumps(receipt, indent=2) + '\n').encode()
        receipt_path.write_bytes(raw)
        assert receipt_path.read_bytes() == raw
        (transaction / 'manual-deployment.after.json').write_bytes(raw)
    except BaseException:
        for rel, raw in originals.items():
            (APP / rel).write_bytes(raw)
        receipt_path.write_bytes(receipt_raw)
        assert all((APP / rel).read_bytes() == raw for rel, raw in originals.items())
        assert receipt_path.read_bytes() == receipt_raw
        raise
    result = dict(status='DEPLOYED_HASH_VERIFIED', build=manifest['build'], payload_files=9, receipt_files=len(receipt['files']), rollback=str(transaction / archive_names[1]), game_started=False)
    (transaction / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
