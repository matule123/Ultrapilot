"""Hash-bound Oct 16 joint candidate; reuse existing verification, never deploy."""
import argparse
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import zipfile

from tools.prepare_oct16_crossing_hud import verify,prepare


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--log',type=Path,required=True);p.add_argument('--verify',action='store_true')
    p.add_argument('--output',type=Path);a=p.parse_args()
    if a.verify:raise SystemExit(verify(a.log))
    if not a.output:p.error('--output required')
    # Existing preparer verifies the complete suite/runtime/base installation
    # hashes and refuses overwrite. Its archive format/limits remain unchanged.
    with redirect_stdout(io.StringIO()):prepare(a.log,a.output)
    # This is a NEW not-yet-delivered workspace candidate, not original evidence.
    # Rewrite only the candidate metadata, retaining the same verified payloads.
    with zipfile.ZipFile(a.output) as archive:
        payload={name:archive.read(name) for name in archive.namelist()}
    manifest=json.loads(payload['candidate-manifest.json'])
    manifest.update(scope='oct16-crossing-completion-dense-dev-and-signal-phase',
        supersedes_candidate='oct16-crossing-qualification-continuity-and-classic-3d-dev-hud; originals retained',
        limitations=['Original Oct16 rejected actor array is not retained; exact disappearance/projection branch remains unverified',
            'Oct16 earlier red approaches lack a retained immutable pedal/signal chain; reproduced reset is not asserted as its unique historical cause',
            'Constant-motion heuristic completion does not certify an empty road, lane membership or future actor intent',
            '5 m reference offset is unchanged; model front extent is not a painted-line survey',
            'No deployment or ETS2 verification'])
    payload['candidate-manifest.json']=json.dumps(manifest,indent=2).encode()
    temporary=a.output.with_suffix('.pending.zip')
    with zipfile.ZipFile(temporary,'x',zipfile.ZIP_DEFLATED) as archive:
        for name,data in payload.items():archive.writestr(name,data)
    with zipfile.ZipFile(temporary) as archive:
        for row in manifest['files']:
            assert hashlib.sha256(archive.read(row['path'])).hexdigest()==row['sha256']
    temporary.replace(a.output)
    a.output.with_suffix('.manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps(dict(path=str(a.output.resolve()),sha256=hashlib.sha256(a.output.read_bytes()).hexdigest(),
        files=len(manifest['files']),deployed=False),indent=2))


if __name__=='__main__':main()
