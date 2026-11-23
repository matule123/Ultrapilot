"""Recoverably retire only older generated diagnostic captures, never runtime."""
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
import zipfile
from deploy_oct29_diagnostic26 import stopped

ROOT = Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot\route-diagnostics').resolve()
REPO = Path(__file__).resolve().parents[1]
SESSION = 'acc09d754db347859ee0a83944db6d9a'
CUTOFF = datetime(2026, 11, 2, 19, 54, 28, tzinfo=timezone.utc).timestamp()


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def main():
    stopped()
    assert ROOT == Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot\route-diagnostics').resolve()
    old = []
    protected = []
    for path in sorted(ROOT.rglob('*')):
        if not path.is_file():
            continue
        assert path.resolve().is_relative_to(ROOT)
        assert not path.is_symlink() and not path.is_junction()
        rel = str(path.relative_to(ROOT))
        generated = path.name.startswith(('steering-replay-', 'steering-timing-', 'incident-', 'incident-failure-', 'ap-inputs-'))
        row = dict(path=rel, bytes=path.stat().st_size, sha256=digest(path))
        if generated and path.stat().st_mtime < CUTOFF and SESSION not in path.name:
            old.append(row)
        else:
            protected.append(row)
    assert old and protected
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    target = REPO / 'docs/cleanup-archives' / ('old-replays-' + stamp)
    target.mkdir(parents=True)
    archive_path = target / 'older-diagnostic-replays.zip'
    manifest = dict(source=str(ROOT), current_session_preserved=SESSION,
                    files=old, protected=protected, originals_removed=False)
    manifest_path = target / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    with zipfile.ZipFile(archive_path, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as archive:
        for row in old:
            path = ROOT / row['path']
            assert digest(path) == row['sha256']
            archive.write(path, row['path'].replace('\\', '/'))
        archive.writestr('RESTORE-MANIFEST.json', json.dumps(manifest, indent=2))
    with zipfile.ZipFile(archive_path) as archive:
        for row in old:
            h = hashlib.sha256()
            with archive.open(row['path'].replace('\\', '/')) as stream:
                while chunk := stream.read(1024 * 1024):
                    h.update(chunk)
            assert h.hexdigest() == row['sha256']
    manifest.update(archive_sha256=digest(archive_path), archive_bytes=archive_path.stat().st_size, archive_verified=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    stopped()
    for row in old:
        path = (ROOT / row['path']).resolve()
        assert path.is_relative_to(ROOT) and path != ROOT
        assert digest(path) == row['sha256']
    for row in old:
        (ROOT / row['path']).unlink()
    for row in protected:
        assert digest(ROOT / row['path']) == row['sha256']
    manifest['originals_removed'] = True
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps(dict(removed_old_files=len(old), preserved_files=len(protected),
        retired_bytes=sum(r['bytes'] for r in old), recovery_archive=str(archive_path),
        archive_bytes=archive_path.stat().st_size, current_session_preserved=True), indent=2))


if __name__ == '__main__':
    main()
