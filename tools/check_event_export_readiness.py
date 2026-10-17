"""Read-only readiness and hash inventory for the EXISTING event export quota.

Never arms, archives, removes evidence, edits settings or grants runtime authority.
Ready means a file slot and some bytes are free, not that an unknown next
payload is guaranteed to fit. Run before a future evidence drive.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.steering_replay import significant_event_export_budget


def inventory(directory):
    root = Path(directory).resolve()
    if not root.is_dir():
        raise ValueError('DIAGNOSTIC_DIRECTORY_NOT_FOUND')
    status = significant_event_export_budget(root)
    for row in status['files']:
        path = root / row['name']
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        row['sha256'] = digest.hexdigest()
    status.update(directory=str(root), read_only=True,
                  runtime_authorized=False, game_verified=False,
                  action='NONE' if status['ready'] else 'ARCHIVE_EXISTING_EVENTS_WITH_USER_APPROVAL',
                  scope='significant_event files only; not all replay/export types')
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', required=True)
    args = parser.parse_args()
    result = inventory(args.directory)
    print(json.dumps(result, indent=2))
    return 0 if result['ready'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
