"""Freeze/verify and prepare a signal-handoff candidate; never deploy.

The second-roundabout cause remains explicitly unresolved in its manifest.
"""
import argparse
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile

from tools import prepare_oct16_native_owner_runtime as native

base=native.base
base.RUNTIME=tuple(dict.fromkeys((*base.RUNTIME,'core/transmission_mode.py')))
verify=base.verify


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--log',type=Path);p.add_argument('--verify',action='store_true')
    p.add_argument('--freeze',type=Path,help='Hash-only pending manual verification record; does not claim PASS or build a ZIP')
    p.add_argument('--output',type=Path);a=p.parse_args()
    if a.freeze:
        if not a.freeze.resolve().is_relative_to(base.ROOT/'docs/steering-audit') or a.freeze.exists():
            p.error('Use a new workspace audit freeze record')
        code={str(path.relative_to(base.ROOT)).replace('\\','/'):hashlib.sha256(path.read_bytes()).hexdigest()
              for folder in ('core','plugins','sdk','ui','tests')
              for path in (base.ROOT/folder).rglob('*.py')}
        record=dict(kind='pending_user_full_suite',full_suite_passed=None,game_verified=False,
            runtime_authorized=False,task_complete=False,
            source_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=base.ROOT).decode().strip(),
            working_tree_uncommitted=True,runtime_sha256=base.hashes(),python_source_sha256=code,
            note='Hash snapshot only; no test execution or PASS attestation. Compare unchanged files when user supplies full result.')
        a.freeze.write_text(json.dumps(record,indent=2),encoding='utf-8')
        print(json.dumps(dict(path=str(a.freeze.resolve()),runtime_files=len(record['runtime_sha256']),
            source_files=len(code),sha256=hashlib.sha256(a.freeze.read_bytes()).hexdigest(),
            full_suite_passed=None),indent=2));return
    if not a.log:p.error('--log required for full verification or candidate preparation')
    if a.verify:raise SystemExit(verify(a.log))
    if not a.output:p.error('--output required')
    with redirect_stdout(io.StringIO()):base.prepare(a.log,a.output)
    with zipfile.ZipFile(a.output) as archive:payload={n:archive.read(n) for n in archive.namelist()}
    manifest=json.loads(payload['candidate-manifest.json'])
    manifest.update(scope='oct16-signal-terminal-brake-and-bounded-green-handoff',
        supersedes_candidate='oct16-native-owner-acc136-candidate.zip as proposal only; preserve its evidence and deployed base',
        task_complete=False,unresolved=['Second-roundabout oscillation: missing contemporaneous consumed longitudinal inputs and physical pedal writes'],
        limitations=['Historical first rejection remained on recorded red; exact reported immediate-green acquisition is absent',
            'Five archived deployed-code regressions fail, candidate signal handoffs pass offline; no ETS2 verification',
            'Zero-output green pairing and interrupted-probe handoff never authorize a new stationary brake',
            'Backend return is not game consumption; no claim of verified hill hold or native R input semantics',
            'Installed significant-event quota needs explicit archival; candidate adds readiness, bounded retry and full sealed-event fault fallback, not recovery of missing historical inputs',
            'No second-roundabout predictor/controller tuning without its missing original constraints',
            'GPS destination removal at 21:36:59 outside scope; no DLL, steering or geometry change'])
    payload['candidate-manifest.json']=json.dumps(manifest,indent=2).encode()
    pending=a.output.with_suffix('.pending.zip')
    with zipfile.ZipFile(pending,'x',zipfile.ZIP_DEFLATED) as archive:
        for name,data in payload.items():archive.writestr(name,data)
    with zipfile.ZipFile(pending) as archive:
        for row in manifest['files']:
            assert hashlib.sha256(archive.read(row['path'])).hexdigest()==row['sha256']
    pending.replace(a.output)
    a.output.with_suffix('.manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps(dict(path=str(a.output.resolve()),files=len(manifest['files']),
        sha256=hashlib.sha256(a.output.read_bytes()).hexdigest(),deployed=False,task_complete=False),indent=2))


if __name__=='__main__':main()
