"""Only the Oct 6 offline regressions; optionally load original Git sources.

Historical code is compiled in memory. No checkout, installation, game process,
SDK device connection or diagnostic arming is changed. Backend fixtures record
the real Controller/SCSControls writes in BytesIO, not in the game's mapping.
"""
import argparse
import importlib
from pathlib import Path
import subprocess
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref')
    parser.add_argument('--basetemp', type=Path, required=True)
    args = parser.parse_args()
    if args.baseline_ref:
        for name in ('core.sdk.scs_sdk','core.telemetry','core.acc_following',
                'core.transmission_mode','core.service_brake_hold','core.longitudinal',
                'core.engine','plugins.autopilot.main'):
            path = name.replace('.','/')+'.py'
            code = subprocess.check_output(['git','show',f'{args.baseline_ref}:{path}'],cwd=ROOT)
            module = types.ModuleType(name)
            module.__file__ = str(ROOT/path)
            module.__package__ = name.rpartition('.')[0]
            sys.modules[name] = module
            setattr(importlib.import_module(module.__package__),name.rsplit('.',1)[1],module)
            exec(compile(code,module.__file__,'exec'),module.__dict__)
    import pytest
    return pytest.main([str(ROOT/'tests/lifecycle/test_joint_stop_flow.py'),'-q',
        '--tb=short','-p','no:cacheprovider','--basetemp',str(args.basetemp)])


if __name__=='__main__':
    raise SystemExit(main())
