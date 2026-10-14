"""Complete user-authorized suite, bound to candidate runtime hashes.

No deployment. Report/tools may be edited afterward, runtime may not: the ZIP
preparer refuses to package content different from the before/after test receipt.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.prepare_oct14_runtime import RUNTIME


if __name__=='__main__':
    sha=lambda value:hashlib.sha256(value).hexdigest()
    hashes=lambda:{name:sha((ROOT/name).read_bytes()) for name in RUNTIME}
    before=hashes()
    log=ROOT/'docs/steering-audit/oct14-completion/full-suite-completion-v4.log'
    if log.exists():raise ValueError('Preserve existing evidence; use a new verification revision')
    env=dict(os.environ,PYTHONCASEOK='1')
    with log.open('x',encoding='utf-8') as out:
        result=subprocess.run([sys.executable,'-m','pytest','tests','-q'],cwd=ROOT,env=env,
                              stdout=out,stderr=subprocess.STDOUT)
    after=hashes()
    if after != before:raise ValueError('Runtime changed during verification')
    receipt=dict(exit_code=result.returncode,runtime_sha256=after,log_sha256=sha(log.read_bytes()),
        source_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(),
        game_verified=False)
    log.with_suffix('.verified.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print('\n'.join(log.read_text(errors='replace').splitlines()[-35:]),flush=True)
    raise SystemExit(result.returncode)
