"""Paired closed plant; no live SDK. Same real PPD, delay and native phase inputs."""
import argparse
import ast
from contextlib import ExitStack
import inspect
import json
from pathlib import Path
import sys
import textwrap
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import core.engine as engine_module
from core.engine import UltraPilotEngine as Engine
from core import longitudinal
from tools.audit_oct10_native_signal import placed_route
from tools.run_prefab_signal_bench import run
from tools import run_prefab_signal_bench as bench
from tests.signals.test_native_signal_direction import authored_heads
from tests.signals.test_signal_timing import timed_bytes


def snapshot(now, generation, frame, heads):
    _, authored = authored_heads()
    model = heads[0]
    own = dict(authored[3], color={1:'yellow',2:'red',4:'yellow',8:'green'}[model['state']])
    data = timed_bytes(now, generation, frame, [own], model['time_left'])
    # Preserve native yellow direction, not just the display color.
    from core.sdk.signal_snapshot import SCOPED_LAYOUT
    import struct
    fields = list(SCOPED_LAYOUT.unpack(data)); payload = bytearray(fields[10])
    struct.pack_into('<i', payload, 40, model['state']); fields[10] = bytes(payload)
    return bytearray(SCOPED_LAYOUT.pack(*fields))


def compare(directory, *, mode, speed, scenario, before):
    if scenario == 'moving_green':
        program = lambda t, stop: dict(state=2 if t<4. else 8, remaining_s=60.)
    elif scenario == 'ending_green':
        program = lambda t, stop: dict(state=8 if t<1. else 2 if t<12. else 8,
                                       remaining_s=max(0.,1.-t) if t<1. else 60.)
    elif scenario == 'enough_green':
        program = lambda t, stop: dict(state=8, remaining_s=60.-t)
    else:
        program = None
    with ExitStack() as stack:
        stack.enter_context(patch.object(bench, 'plan_for',
            side_effect=lambda net,path: placed_route(directory)[2]))
        if before:
            # Exact former standstill-only release and no phase prediction.
            source = textwrap.dedent(inspect.getsource(Engine._flush_controls_unlocked))
            source = source.replace('if clear_signal is not None:',
                "if clear_signal is not None and abs(float(truck_telemetry['speed'])) < .05:")
            source = source.replace("if clear_signal is not None and not hold.get('destination_lock'):",
                "if clear_signal is not None and not hold.get('destination_lock') and abs(float(truck_telemetry['speed'])) < .05:")
            namespace = {}
            exec(compile(source, '<pre-moving-clearance>', 'exec'), vars(engine_module), namespace)
            stack.enter_context(patch.object(Engine, '_flush_controls_unlocked', namespace['_flush_controls_unlocked']))
            # Keep this counterfactual about the old standstill-only clearance:
            # the later single-PID approach must not silently become its baseline.
            from core import service_brake_hold
            stack.enter_context(patch.object(service_brake_hold, 'profile_approach_allowed', lambda *args: False))
            light_source = textwrap.dedent(inspect.getsource(Engine._light_brake))
            light_tree = ast.parse(light_source)
            class OpenLoopSignal(ast.NodeTransformer):
                removed = 0
                def visit_If(self, node):
                    text = ast.unparse(node.test)
                    if 'longitudinal_acc_active' in text and 'head_observed' in text:
                        self.removed += 1
                        return None
                    return self.generic_visit(node)
            transform = OpenLoopSignal()
            light_tree = ast.fix_missing_locations(transform.visit(light_tree))
            if transform.removed != 1:
                raise ValueError('standstill/open-loop counterfactual suppression branch changed')
            old_light = {}
            exec(compile(light_tree, '<pre-single-PID-approach>', 'exec'), vars(engine_module), old_light)
            stack.enter_context(patch.object(Engine, '_light_brake', old_light['_light_brake']))
            stack.enter_context(patch.object(longitudinal, 'signal_phase_plan',
                lambda light,*args: dict(stop_required=light.get('color')!='green',status='before_no_countdown')))
        result = run(directory, mode=mode, speed_kmh=speed, jitter=True,
            approach=60. if scenario == 'ending_green' else 100.,
            path_factory=placed_route, snapshot_factory=snapshot, observer_y=6.90234375,
            phase_program=program, duration_limit_s=35. if program else None)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True); p.add_argument('--workdir',type=Path,required=True)
    p.add_argument('--speeds', type=float, nargs='+', default=[20.,35.,50.])
    a = p.parse_args(); a.workdir.mkdir(exist_ok=False)
    results = {}
    for scenario in ('red_stop','moving_green','ending_green','enough_green'):
        for speed in a.speeds:
            for mode in (0,3):
                for before in (True,False):
                    name = f'{scenario}/{speed:g}/{mode}/{"before" if before else "after"}'
                    result = compare(a.workdir,mode=mode,speed=speed,scenario=scenario,before=before)
                    (a.workdir/(name.replace('/','-')+'.json')).write_text(json.dumps(result,indent=2)+'\n')
                    results[name] = {k:v for k,v in result.items() if k not in ('rows','writes','captures')}
                    print(name, json.dumps(results[name]))
    a.output.write_text(json.dumps(results,indent=2)+'\n')


if __name__ == '__main__': main()
