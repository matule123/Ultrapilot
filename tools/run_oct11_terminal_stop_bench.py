"""Paired same-target terminal approach; synthetic plant, never an ETS2 result."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch
from contextlib import ExitStack

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.audit_oct11_stop_geometry import model_case, model_metrics
import core.longitudinal as longitudinal


def original():
    record = json.loads((ROOT/'tests/fixtures/oct11-terminal-original.json').read_text())
    if hashlib.sha256(record['source'].encode()).hexdigest() != record['sha256']:
        raise ValueError('frozen current-working-tree baseline hash mismatch')
    namespace = {}
    exec(compile(record['source'], 'frozen-terminal-baseline', 'exec'),
         vars(longitudinal), namespace)
    return namespace['stopping_brake_request']


def metrics(result):
    m = model_metrics(result)
    stopped, green = result['stop'], result['green_first_at_s']
    rows = result['rows']
    terminal = next((r for r in rows if r['hold_phase'] in ('braking', 'holding')), None)
    red_end = next((r for r in reversed(rows) if r['red']), None)
    # Physical timestamp/receipt range, not a final scalar or SDK consumption.
    m['hold_zero_writes'] = (sum(channel == 'abackward' and value == 0.
        for t, channel, value in result['writes']
        if terminal['write_checked_at_s'] <= t <= red_end['write_checked_at_s'])
        if terminal and red_end else None)
    # Observation and write are different clocks. Use the exact modeled tick
    # range to inspect writes after first standstill and before green.
    standstill = next((r for r in rows if stopped and r['t'] >= stopped['t']), None)
    green_row = next((r for r in rows if green is not None and r['t'] >= green), None)
    m['red_standstill_drive_writes'] = (sum(channel == 'aforward' and value > 0.
        for t, channel, value in result['writes']
        if standstill['write_checked_at_s'] <= t < green_row['write_checked_at_s'])
        if standstill and green_row else None)
    m.update(gap_m=m['sdk_reference_to_derived_target_m'],
        red_target_overruns=sum(r['red'] and r.get('light_distance') is not None
                               and r['light_distance'] < 0. for r in rows),
        stop_at_s=stopped['t'] if stopped else None,
        below_5_kmh_moving_s=sum(r['dt'] for r in rows
            if r['red'] and .05 < r['speed_mps'] < 5./3.6),
        green_drive_return_s=result['green_drive_return_s'])
    return m


def compare(directory, *, speed=35., mode=0, curvature=0., plant=None):
    # Same exact geometry, PID, random dt, signal program and physical model;
    # only the captured baseline helper is substituted for the first run.
    from core.engine import UltraPilotEngine
    record = json.loads((ROOT/'tests/fixtures/oct12-original-functions.json').read_text())
    # Preserve the earlier producer/terminal contract alongside the earlier
    # brake helper. Mixing it with the new ACC-owned terminal approach removes
    # the old first-positive Traffic request and is not the frozen baseline.
    def saved(relative, name, globals_):
        namespace = {}
        exec(record[relative]['functions'][name], globals_, namespace)
        return namespace[name]
    with ExitStack() as stack:
        stack.enter_context(patch.object(longitudinal, 'stopping_brake_request', original()))
        stack.enter_context(patch.object(longitudinal, 'signal_speed_control',
            saved('core/longitudinal.py', 'signal_speed_control', vars(longitudinal))))
        stack.enter_context(patch.object(UltraPilotEngine, '_light_brake',
            saved('core/engine.py', '_light_brake', UltraPilotEngine._light_brake.__globals__)))
        before = model_case(directory, speed=speed, mode=mode,
                            approach_curvature=curvature, plant_options=plant)
    after = model_case(directory, speed=speed, mode=mode,
                       approach_curvature=curvature, plant_options=plant)
    return metrics(before), metrics(after)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if not args.output.resolve().is_relative_to(ROOT/'docs/steering-audit'):
        raise ValueError('analysis output must remain in workspace steering-audit')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    results = {}
    plants = dict(normal={}, quick=dict(brake_response_s=.2, input_delay_s=.05),
                  slow_loaded=dict(brake_response_s=.6, input_delay_s=.22, mass_ratio=1.8))
    for name, plant in plants.items():
        for k in (0., 1./60., -1./60.):
            for speed in (20., 35., 50.):
                for mode in (0, 3):
                    label = f'{name}/{k:.6f}/{speed:g}/{mode}'
                    old, new = compare(args.output.parent, speed=speed, mode=mode, curvature=k, plant=plant)
                    results[label] = dict(before=old, after=new, plant=plant,
                                          game_verified=False)
                    # Retain completed offline cases if a long analysis is
                    # interrupted. Completeness is the explicit case count,
                    # never inferred from the output file merely existing.
                    args.output.write_text(json.dumps(results, indent=2)+'\n', encoding='utf-8')
                    print(label, 'gap', old['gap_m'], '->', new['gap_m'], flush=True)
    args.output.write_text(json.dumps(results, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
