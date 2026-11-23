"""Apply only the audited, recoverable one-replay archival plan."""
import hashlib
import json
from pathlib import Path
import sys
from deploy_oct29_diagnostic26 import stopped
from deploy_nov2_preparation02 import APP, RELEASE

sys.path.insert(0, str(APP))
from core.steering_replay import _archive_incidents, _diagnostic_disk_lock
sys.path.insert(1, str(Path(__file__).resolve().parents[1]))
from tools.preflight_nov2_capture import preflight


def main():
    stopped()
    root = APP / 'route-diagnostics'
    name = 'steering-replay-20261029T130506.578600Z-manual_disable-devinputs.json'
    digest = '32b1d34106c428996ef19c404689230ebb1457b086546d268ddb905fb5be8955'
    source = root / name
    destination = root / 'archive' / ('standalone-' + digest) / name
    with _diagnostic_disk_lock(root):
        before = preflight(root)
        plan = before['proposed_standalone_archive']
        assert before['possible_after_verified_archive']
        assert len(plan) == 1 and plan[0]['path'] == str(source)
        assert plan[0]['sha256'] == digest and plan[0]['destination'] == str(destination)
        assert source.resolve().is_relative_to(root.resolve())
        assert destination.resolve().is_relative_to((root / 'archive').resolve())
        assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
        inventory = {str(p.relative_to(root)): p.stat().st_size for p in root.rglob('*') if p.is_file()}
        stopped()
        _archive_incidents(root, reserve_bytes=32 * 1024 * 1024)
        assert not source.exists()
        assert hashlib.sha256(destination.read_bytes()).hexdigest() == digest
        after = preflight(root)
        assert after['ready_without_archival']
        actual = {str(p.relative_to(root)): p.stat().st_size for p in root.rglob('*') if p.is_file()}
        expected = dict(inventory)
        expected[str(destination.relative_to(root))] = expected.pop(name)
        assert actual == expected, 'Unexpected evidence inventory change'
    result = dict(status='READY_FOR_CONTROLLED_CAPTURE', before=before, after=after,
                  moved_from=str(source), preserved_at=str(destination), sha256=digest,
                  original_bytes_preserved=True, files_deleted=0, game_started=False)
    transaction = max(RELEASE.glob('deployment-*'), key=lambda p: p.name)
    (transaction / 'capture-preflight.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
