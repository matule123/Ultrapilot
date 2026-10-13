"""Same explicit stop plant on deployed HEAD vs core lifecycle candidate."""
import argparse
import ast
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import subprocess
from unittest.mock import patch

from tools.audit_oct11_stop_geometry import model_case
from tools.run_oct11_terminal_stop_bench import metrics

BASELINE_REF = 'c7339a405542f55d2ac235161e99b019be4bf101'

def baseline(stack):
    from core.engine import UltraPilotEngine as Engine
    from core import service_brake_hold
    frozen = {}
    for relative, target, names in (
        ('core/engine.py', Engine, ('_resume_signal_wait', '_flush_auto_drive_engagement', '_flush_controls_unlocked')),
        ('core/service_brake_hold.py', service_brake_hold, ('planned_stop',))):
        source = subprocess.check_output(['git', 'show', BASELINE_REF+':'+relative], text=True, encoding='utf-8')
        frozen[relative] = hashlib.sha256(source.encode()).hexdigest()
        tree = ast.parse(source)
        for name in names:
            nodes = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name]
            if len(nodes) != 1: raise ValueError((relative, name))
            namespace = {}; current = getattr(target, name)
            exec(compile(ast.Module(body=nodes, type_ignores=[]), 'HEAD/'+relative, 'exec'),
                 current.__globals__, namespace)
            stack.enter_context(patch.object(target, name, namespace[name]))
    return frozen


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); args.output.parent.mkdir(parents=True, exist_ok=True)
    rows = {}; hashes = None
    for speed in (20., 35., 50.):
        for mode in (0, 3):
            with ExitStack() as stack:
                hashes = baseline(stack)
                before = metrics(model_case(args.output.parent, speed=speed, mode=mode))
            after = metrics(model_case(args.output.parent, speed=speed, mode=mode))
            for key in ('red_target_overruns', 'hold_zero_writes', 'positive_pedal_overlap',
                        'parking_writes', 'red_standstill_drive_writes'):
                if after[key] != 0: raise AssertionError((speed, mode, key, after[key]))
            rows[f'{speed:g}/{mode}'] = dict(before=before, after=after)
            args.output.write_text(json.dumps(dict(baseline_hashes=hashes, cases=rows,
                game_verified=False, physical_line_gap_m=None), indent=2)+'\n', encoding='utf-8')
            print(speed, mode, 'planning residual', before['gap_m'], '->', after['gap_m'], flush=True)
