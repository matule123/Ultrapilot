"""Read-only incident analysis using the existing immutable replay codec."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.steering_replay import inspect_replay


def analyze(installation, output):
    output.mkdir(parents=True, exist_ok=True)
    receipt = json.loads((installation/'manual-deployment.json').read_text(encoding='utf-8-sig'))
    sha = lambda b: hashlib.sha256(b).hexdigest()
    installed = []
    for row in receipt['files']:
        target = Path(row['target'])
        content = target.read_bytes()
        name = row.get('relative_path') or str(target.relative_to(installation)) if target.is_relative_to(installation) else 'game-plugin/ets2la_plugin.dll'
        source = ROOT/name
        installed.append(dict(path=str(target), relative_path=name,
            receipt_matches=sha(content)==row['sha256'].lower(),
            source_normalized_matches=(source.read_bytes().replace(b'\r\n',b'\n')==content.replace(b'\r\n',b'\n')) if source.is_file() else None))
    package = ROOT/'docs/steering-audit/oct14-completion/ultrapilot-oct14-candidate-v4.zip'
    package_checks = []
    with zipfile.ZipFile(package) as archive:
        manifest = json.loads(archive.read('candidate-manifest.json'))
        for row in manifest['files']:
            content = archive.read(row['path'])
            if row['path'].startswith('game-plugin/'):
                target = next(Path(r['target']) for r in receipt['files']
                              if r['target'].endswith('ets2la_plugin.dll') and not Path(r['target']).is_relative_to(installation))
            else:
                target = installation/row['path'].removeprefix('runtime/')
            package_checks.append(dict(path=row['path'], archive_hash_matches=sha(content)==row['sha256'],
                installed_hash_matches=sha(target.read_bytes())==row['sha256']))
    records = []
    for name in ('steering-replay-20261014T185321.654806Z-automatic_disable.json',
                 'steering-replay-20261014T185321.886684Z-automatic_disable.json',
                 'steering-replay-20261014T185156.878145Z-manual_disable.json'):
        path = installation/'route-diagnostics'/name
        checked = inspect_replay(path)
        replay = checked.pop('replay', {})
        (output/(path.stem+'-decoded.json')).write_text(json.dumps(replay), encoding='utf-8')
        block = replay.get('longitudinal') or {}
        history = block.get('decision_history') or {}
        rows = sorted(history.get('regular_samples',[])+history.get('changes',[]),
                      key=lambda r:r['monotonic_s'])
        records.append(dict(path=str(path), sha256=sha(path.read_bytes()), **checked,
            identity=replay.get('identity'), first_intervention=block.get('first_intervention'),
            sample_count=replay.get('sample_count'), execution_sample_count=replay.get('execution_sample_count'),
            history_metadata={k:v for k,v in history.items() if k not in ('regular_samples','changes','identities')},
            history=rows, events=block.get('events',[])))
    result = dict(source_head=__import__('subprocess').check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(),
        receipt_metadata={k:v for k,v in receipt.items() if k not in ('files','changed_files')},
        installed=installed, package_sha256=sha(package.read_bytes()), package_checks=package_checks,
        records=records)
    (output/'incident-summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(receipt_matches=all(r['receipt_matches'] for r in installed),
        package_matches=all(r['archive_hash_matches'] and r['installed_hash_matches'] for r in package_checks),
        records=[dict(path=r['path'],integrity_valid=r['integrity_valid'],samples=r['sample_count'],
                      execution_samples=r['execution_sample_count'],history_rows=len(r['history'])) for r in records]),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--installation',type=Path,default=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot'))
    p.add_argument('--output',type=Path,default=ROOT/'docs/steering-audit/oct14-roundabout')
    args=p.parse_args(); analyze(args.installation.resolve(),args.output.resolve())
