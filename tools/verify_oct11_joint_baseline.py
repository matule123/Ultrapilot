"""Run only the new counterexamples with frozen, hash-identified installed code.

No production files, installed files or test expectations are rewritten.
Exit 0 means the baseline reproduced the nine required failures, not a test PASS.
"""
import ast
import json
from pathlib import Path
import sys
from types import ModuleType
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def module(name, source):
    result = ModuleType(name)
    exec(compile(source, f'<frozen {name}>', 'exec'), result.__dict__)
    return result


def run():
    import pytest
    from core import acc_following, engine, plugin_manager
    import tests.test_oct11_joint_regressions as tests
    fixture = json.loads((ROOT/'tests/fixtures/oct11-joint-original-functions.json').read_text())
    files = fixture['files']
    actors = module('oct11_original_acc', files['core/acc_following.py']['source'])
    manager = module('oct11_original_manager', files['core/plugin_manager.py']['source'])
    indicators = module('oct11_original_indicators', files['plugins/turnsignals/main.py']['source'])
    namespace = dict(engine.__dict__)
    for source in files['core/engine.py']['source'].values():
        exec(compile(ast.parse(source), '<frozen Engine>', 'exec'), namespace)
    replacements = [
        patch.object(acc_following, 'observation', actors.observation),
        patch.object(acc_following, 'RouteLeadSelector', actors.RouteLeadSelector),
        patch.object(engine.UltraPilotEngine, '_route_lead_observation', namespace['_route_lead_observation']),
        patch.object(engine.UltraPilotEngine, '_flush_controls', namespace['_flush_controls']),
        patch.object(engine.UltraPilotEngine, '_flush_controls_unlocked', namespace['_flush_controls_unlocked']),
        patch.object(plugin_manager, 'PluginManager', manager.PluginManager),
        patch.object(tests, 'TurnSignals', indicators.Plugin),
    ]
    class Count:
        failed = 0
        passed = 0
        errors = 0
        def pytest_runtest_logreport(self, report):
            if report.when == 'call':
                self.failed += report.failed
                self.passed += report.passed
            elif report.failed:
                self.errors += 1
    counter = Count()
    for replacement in replacements: replacement.start()
    try:
        code = pytest.main([
            str(ROOT/'tests/test_oct11_joint_regressions.py'), '-q', '--tb=short',
            '-k', 'observed_lead_departure or trailer_crossing or ui_enable or no_route_turn'],
            plugins=[counter])
    finally:
        for replacement in reversed(replacements): replacement.stop()
    print(json.dumps(dict(build=fixture['build'], failed=counter.failed,
                         passed=counter.passed, setup_errors=counter.errors)))
    return 0 if code == 1 and counter.failed == 9 and not counter.errors else 1


if __name__ == '__main__':
    raise SystemExit(run())
