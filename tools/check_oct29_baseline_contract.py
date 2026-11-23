"""Demonstrate the unrelated installed-versus-worktree publication contract."""
from pathlib import Path
import json
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
APP=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')
OUT=ROOT/'docs/steering-audit/oct29-transition/release01'


def main():
    stage=OUT/'baseline-verification-runtime';assert not stage.exists()
    for folder in ('core','plugins','sdk','ui'):
        for path in (APP/folder).rglob('*.py'):
            target=stage/path.relative_to(APP);target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(path.read_bytes())
    for folder in [stage/n for n in ('core','plugins','sdk','ui')]+[
            p for p in stage.rglob('*') if p.is_dir() and any(p.glob('*.py'))]:
        marker=folder/'__init__.py'
        if not marker.exists():marker.write_text('# Offline unchanged installed base.\n',encoding='utf-8')
    targets=['tests/traffic/test_crossing_dev_hud.py::test_invalid_acc_cause_survives_compact_fault_receipt','-k','identity','-q']
    code='import sys;sys.path.insert(0,'+repr(str(stage))+');import pytest;raise SystemExit(pytest.main('+repr(targets)+'))'
    log=OUT/'baseline-publication-contract.log'
    with log.open('x',encoding='utf-8') as stream:
        result=subprocess.run([sys.executable,'-c',code],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
    print(log.read_text(encoding='utf-8')[-1800:]);print('Unchanged baseline exit:',result.returncode)


if __name__=='__main__':main()
