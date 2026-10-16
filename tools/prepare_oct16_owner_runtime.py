"""Prepare a source/hash-bound owner-handoff candidate. Never installs files."""
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
    with redirect_stdout(io.StringIO()):prepare(a.log,a.output)
    with zipfile.ZipFile(a.output) as archive:payload={k:archive.read(k) for k in archive.namelist()}
    manifest=json.loads(payload['candidate-manifest.json'])
    manifest.update(scope='oct16-original-acc-owner-continuity-and-historical-intervention-display',
        supersedes_candidate='oct16-joint-traffic-acc134-candidate.zip as future deployment proposal only; originals retained',
        limitations=['Historical rejected ID 28 actor array is not retained; production owner mismatch reproduced independently',
            'ID 26 model contact is not a proven physical collision or lane assignment; exact future directed XYZ path/full actor bodies not retained',
            'Separate 15:54:24 signal incident observed actual reverse gear; cause of R not established from successful software writes',
            'No DLL change, no installation, no ETS2 verification'])
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
