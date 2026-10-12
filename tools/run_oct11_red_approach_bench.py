"""Paired delayed closed plant; installed Oct 11 methods are the read-only baseline."""
import argparse
import ast
from contextlib import ExitStack
import json
from pathlib import Path
from unittest.mock import patch

from core import engine, service_brake_hold, longitudinal
from plugins.acc import main as acc
from plugins.drivepolicy import main as policy
from tools import run_prefab_signal_bench as bench
from tools.audit_oct10_native_signal import placed_route
from tools.run_oct10_signal_timing_bench import snapshot

INSTALL = Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')
BASELINE_HASHES = {
    'core/engine.py': '45ee49c7af1f99111df362975f388c155f6217a70aa7b72376c68436adb9bbe6',
    'core/longitudinal.py': '439833cc50fc0dfd186e1cdb3019c3f8d6c8d438374743818cf5dace1f49ea19',
    'core/service_brake_hold.py': 'b492650eb2210348d3e82585bf62d4d9ef12933fd98e281af00aadcece87c8ea',
    'plugins/acc/main.py': 'a10093e043113cb32eb0e7061c3a99894e3feff2f76897a8ad77b0d8649881c8',
    'plugins/drivepolicy/main.py': '3c8d7c9e28f93032edb987e39202064297c24832ad4ed4d36fe65170fc5099df',
}


def installed_function(relative, name, module):
    import hashlib
    source = INSTALL / relative
    expected = BASELINE_HASHES[relative]
    if source.exists() and hashlib.sha256(source.read_bytes()).hexdigest() == expected:
        tree = ast.parse(source.read_text(encoding='utf-8-sig'))
    else:
        # Frozen exact functions from the SHA-verified pre-deployment backup;
        # later deployments cannot silently turn into the old counterfactual.
        fixture = Path(__file__).resolve().parents[1]/'tests/fixtures/oct11-red-original-functions.json'
        saved = json.loads(fixture.read_text())[relative]
        if saved['original_source_sha256'] != expected:
            raise ValueError('Original baseline identity mismatch: '+relative)
        tree = ast.parse(saved['functions'][name])
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
    namespace = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(INSTALL / relative), 'exec'),
         vars(module), namespace)
    return namespace[name]


def baseline_methods(stack):
    for relative, module, owner, names in (
        ('core/engine.py', engine, engine.UltraPilotEngine, ('_light_brake', '_flush_controls_unlocked')),
        ('plugins/acc/main.py', acc, acc.Plugin, ('on_tick',)),
        ('plugins/drivepolicy/main.py', policy, policy.Plugin, ('_compute_planned_speed', 'on_tick')),
        ('core/service_brake_hold.py', service_brake_hold, service_brake_hold,
         ('rejection', 'planned_stop', 'after_write')),
        ('core/longitudinal.py', longitudinal, longitudinal, ('signal_stop_brake_request',))):
        for name in names:
            stack.enter_context(patch.object(owner, name, installed_function(relative, name, module)))


def compare(directory, *, mode, speed, approach, before, scenario='red_stop'):
    with ExitStack() as stack:
        stack.enter_context(patch.object(bench, 'plan_for',
            side_effect=lambda net, path: placed_route(directory)[2]))
        if before:
            baseline_methods(stack)
        program = None
        if scenario == 'moving_green':
            program = lambda t, stop: dict(state=2 if t < 4. else 8, remaining_s=60.)
        elif scenario == 'ending_green':
            program = lambda t, stop: dict(state=8 if t < 1. else 2 if t < 12. else 8,
                remaining_s=max(0., 1.-t) if t < 1. else 60.)
        result = bench.run(directory, mode=mode, speed_kmh=speed, jitter=True,
            approach=approach, path_factory=placed_route, snapshot_factory=snapshot,
            observer_y=6.90234375, phase_program=program,
            duration_limit_s=70. if scenario == 'disturbance' else 40. if program else None,
            low_speed_disturbance=scenario == 'disturbance',
            idle_speed_mps=.92 if scenario == 'disturbance' else None,
            allow_rejection=scenario == 'disturbance')
    far = [r for r in result['rows'] if r['red'] and r['light_distance'] is not None
           and r['light_distance'] > 10. and r['speed_mps'] * 3.6 < 5.]
    result['far_low_speed_s'] = sum(r['dt'] for r in far)
    result['far_low_speed_distance_m'] = sum(r['speed_mps'] * r['dt'] for r in far)
    result['minimum_target_kmh_while_far'] = min((r['target'] for r in result['rows']
        if r['light_distance'] is not None and r['light_distance'] > 10.), default=None)
    result['resumed_without_n'] = bool(result['stop'] and result['green_drive_return_s'] is not None
        and result['active'])
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workdir', type=Path, required=True)
    p.add_argument('--before', action='store_true')
    p.add_argument('--speeds', type=float, nargs='+', default=[20., 35., 50.])
    p.add_argument('--distances', type=float, nargs='+', default=[40., 60., 100.])
    p.add_argument('--scenarios', nargs='+', default=['red_stop'])
    p.add_argument('--runtime-cost-output', type=Path,
                   help='Three paired unarmed in-process Engine timings, not ETS2 IPC latency')
    a = p.parse_args(); a.workdir.mkdir(parents=True, exist_ok=True)
    if a.runtime_cost_output:
        from tools.benchmark_automatic_longitudinal import scenario, distribution
        paired = []
        for _ in range(3):
            with ExitStack() as stack:
                baseline_methods(stack)
                old = scenario(False, 360)
            current = scenario(False, 360)
            paired.append(dict(before=distribution(old['costs']),
                after=distribution(current['costs']),
                physical_writes_identical=old['writes'] == current['writes'],
                mappings_identical=old['mapping_frames'] == current['mapping_frames'],
                traffic_reads_before=old['ipc_gets'].get('longitudinal_traffic', 0),
                traffic_reads_after=current['ipc_gets'].get('longitudinal_traffic', 0)))
        a.runtime_cost_output.write_text(json.dumps(dict(runs=paired,
            limitation='Copying in-process IPC and BytesIO backend; diagnostics unarmed. '
            'Wall-clock Engine cost, not a measurement of live process scheduling or game latency.'),
            indent=2)+'\n', encoding='utf-8')
        print(json.dumps(paired, indent=2))
        return
    results = {}
    for scenario in a.scenarios:
        for speed in a.speeds:
            for distance in a.distances:
                for mode in (0, 3):
                    name = f'{scenario}-{speed:g}-{distance:g}-{mode}'
                    output = a.workdir / (name+'.json')
                    result = json.loads(output.read_text()) if output.exists() else compare(
                        a.workdir, mode=mode, speed=speed, approach=distance,
                        before=a.before, scenario=scenario)
                    output.write_text(json.dumps(result)+'\n', encoding='utf-8')
                    results[name] = {k:v for k,v in result.items() if k not in ('rows','writes','captures')}
                    print(name, json.dumps(results[name]), flush=True)
    (a.workdir/'summary.json').write_text(json.dumps(results, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__': main()
