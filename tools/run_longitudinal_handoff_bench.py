"""Phased production handoff comparison; no game, device or diagnostic arming.

The SDK moves at 3 m/s on a synthetic directed road. Manager-like copying/RPC
cost and independent periods are explicit stress inputs, not measured ETS2
physics. Actual Map, Policy, ACC, Autopilot, Engine, Controller and SCS memory
writes run; no comfort/steering controller is replaced with a test controller.
"""
import argparse
from contextlib import contextmanager, ExitStack
import importlib
import json
import logging
from pathlib import Path
import subprocess
import sys
import types
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@contextmanager
def version(ref):
    if ref is None:
        yield
        return
    # In-memory historical modules; never reset or change any checkout file.
    with ExitStack() as stack:
        loaded = {}
        for name, path in (
            ('core.longitudinal', 'core/longitudinal.py'),
            ('core.engine', 'core/engine.py'),
            ('plugins.acc.main', 'plugins/acc/main.py'),
            ('plugins.drivepolicy.main', 'plugins/drivepolicy/main.py'),
            ('plugins.autopilot.main', 'plugins/autopilot/main.py')):
            source = subprocess.check_output(['git', 'show', f'{ref}:{path}'], cwd=ROOT).decode('utf-8')
            module = types.ModuleType(name)
            stack.enter_context(patch.dict(sys.modules, {name: module}))
            exec(compile(source, f'baseline/{path}', 'exec'), module.__dict__)
            loaded[name] = module
        for name, attribute, replacement in (
            ('tests.test_drive_engagement_safety', 'UltraPilotEngine', loaded['core.engine'].UltraPilotEngine),
            ('tests.test_activation_observation_binding', 'Plugin', loaded['plugins.autopilot.main'].Plugin),
            ('tests.test_longitudinal_arbitration', 'ACC', loaded['plugins.acc.main'].Plugin),
            ('tests.test_phase7_joint_validation', 'Policy', loaded['plugins.drivepolicy.main'].Plugin),
            ('tests.test_longitudinal_handoff_cadence', 'publish', loaded['core.longitudinal'].publish)):
            stack.enter_context(patch.object(importlib.import_module(name), attribute, replacement))
        yield


def run(ref, seconds, phase, rpc, diagnostics):
    from tests.test_activation_observation_binding import flow
    from tests.test_rolling_longitudinal_authority import rolling
    from tests.test_longitudinal_handoff_cadence import run_cadence
    with version(ref):
        f = flow.__wrapped__()
        values = next(f)
        r = rolling.__wrapped__(values)
        try:
            return run_cadence(next(r), values, seconds=seconds, phase=phase,
                               rpc=rpc, diagnostics=diagnostics)
        finally:
            r.close()
            f.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ref', default='HEAD')
    parser.add_argument('--seconds', type=float, default=75.)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    logging.disable(logging.WARNING)
    result = dict(baseline_ref=subprocess.check_output(['git','rev-parse',args.ref],cwd=ROOT).decode().strip(),
        model='synthetic SDK, independent no-catch-up jobs, copying RPC; not ETS2', cases={})
    for diagnostics in (False, True):
        for phase, rpc in ((0., .00006), (.003, .00012), (.007, .0002)):
            key = f'diagnostic={diagnostics}; phase={phase}; rpc={rpc}'
            result['cases'][key] = {label: run(ref, args.seconds, phase, rpc, diagnostics)
                for label, ref in (('baseline', args.ref), ('candidate', None))}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps({k: {v: dict(duration_s=r['duration_s'], faults=r['faults'],
        write_margin=r['physical_write_margin_s']) for v,r in rows.items()}
        for k,rows in result['cases'].items()}, indent=2))


if __name__ == '__main__':
    main()
