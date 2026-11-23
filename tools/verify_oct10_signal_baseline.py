"""Restore only the installed offending selector for narrow before reproductions.

No source/install file is modified. New tests keep their candidate expectations;
expected failures demonstrate the distance-independent deployed takeover.
"""
from pathlib import Path
import importlib.util
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from core.sdk import signal_snapshot

if __name__=='__main__':
    path=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot\core\sdk\signal_snapshot.py')
    spec=importlib.util.spec_from_file_location('oct10_installed_signal',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    signal_snapshot.RouteSignalSelector=module.RouteSignalSelector
    result=pytest.main(['tests/signals/test_signal_approach.py','-q',
        '-k','distant_native or pending_uncertainty or full_unknown_approach',
        '--basetemp=.tmp-oct10-signal-baseline'])
    raise SystemExit(0 if result==1 else 2)
