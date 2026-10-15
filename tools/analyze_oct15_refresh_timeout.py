"""Read-only afternoon renewal incident decoding and installed hash checks."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.steering_replay import inspect_replay


def main():
    install = Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')
    out = ROOT / 'docs/steering-audit/oct15-refresh-protocol'
    out.mkdir(parents=True, exist_ok=True)
    sha = lambda b: hashlib.sha256(b).hexdigest()
    receipt_bytes = (install/'manual-deployment.json').read_bytes()
    receipt = json.loads(receipt_bytes.decode('utf-8-sig'))
    for row in receipt['files']:
        assert sha(Path(row['target']).read_bytes()) == row['sha256'].lower(), row['target']
    base = ROOT/'docs/steering-audit/oct15-traffic-lease/ultrapilot-oct15-traffic-lease-candidate-v1.zip'
    with zipfile.ZipFile(base) as archive:
        manifest = json.loads(archive.read('candidate-manifest.json'))
        for row in manifest['files']:
            assert sha(archive.read(row['path'])) == row['sha256']
            assert sha((install/row['path'].removeprefix('runtime/')).read_bytes()) == row['sha256']
    evidence = []
    for name in ('steering-replay-20261015T115402.250913Z-automatic_disable.json',
                 'steering-replay-20261015T115403.607836Z-automatic_disable.json'):
        original = install/'route-diagnostics'/name
        checked = inspect_replay(original)
        assert checked['integrity_valid'], name
        value = checked.pop('replay')
        (out/(original.stem+'-decoded.json')).write_text(json.dumps(value), encoding='utf-8')
        evidence.append(dict(path=str(original), sha256=sha(original.read_bytes()), **checked,
            identity=value['identity'], first=(value.get('longitudinal') or {}).get('first_intervention')))
    summary = dict(receipt_sha256=sha(receipt_bytes), receipt_files=len(receipt['files']),
        deployed_package_sha256=sha(base.read_bytes()), package_payloads=len(manifest['files']),
        receipt={k:v for k,v in receipt.items() if k not in ('files','changed_files')}, evidence=evidence)
    (out/'integrity-summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
