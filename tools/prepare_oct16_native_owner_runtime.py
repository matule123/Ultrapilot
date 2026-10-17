"""Prepare the corrected native-owner contract candidate; never installs."""
import argparse
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import zipfile

from tools import prepare_oct16_crossing_hud as base

# Include the unchanged physical-write/export boundaries, not just their
# modified consumers. The final full-suite receipt freezes these dependencies
# too; no installation or DLL is written by this preparation tool.
base.RUNTIME=tuple(dict.fromkeys((*base.RUNTIME,'core/controller.py','core/steering_replay.py')))
verify,prepare=base.verify,base.prepare


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--log',type=Path,required=True);p.add_argument('--verify',action='store_true')
    p.add_argument('--output',type=Path);a=p.parse_args()
    if a.verify:raise SystemExit(verify(a.log))
    if not a.output:p.error('--output required')
    with redirect_stdout(io.StringIO()):prepare(a.log,a.output)
    with zipfile.ZipFile(a.output) as archive:payload={k:archive.read(k) for k in archive.namelist()}
    manifest=json.loads(payload['candidate-manifest.json'])
    manifest.update(scope='oct16-native-distance-sorted-identity-and-constraint-lifecycle',
        supersedes_candidate='oct16-owner-handoff-acc135-candidate.zip as future proposal only; originals retained',
        limitations=['Native slot is distance-sorted, not identity; pointer-map short ID is not an incarnation certificate',
            'Identity requires unique native ID, shape, source/lifecycle, original chain and bounded motion; omission is not clearance',
            'Historical rejected complete actor arrays/owner witness are absent; recorded slot transition and independently reproduced defect distinguished',
            'Crossing rays and body prediction do not certify lane membership or future actor intent',
            'Earlier signal reverse input-consumption cause remains unverified; no DLL change, deployment or ETS2 verification'])
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
