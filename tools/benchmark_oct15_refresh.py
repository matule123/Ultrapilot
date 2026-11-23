"""Paired real-flow stress and CPU timings; a controlled SDK model, not ETS2.

The long scenario is the regression itself (125 late boundaries + 5 signal
cycles). Existing independent-cadence benchmark separately supplies RPC load.
No new runtime collector, physical device, or installation is used.
"""
import argparse
import hashlib
import json
import logging
import math
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.run_longitudinal_handoff_bench import version


def stats(values):
    values = sorted(values)
    return dict(n=len(values), minimum=min(values) if values else None,
        **{label: values[max(0, math.ceil(len(values)*q)-1)] if values else None
           for label, q in (('p50', .5), ('p95', .95), ('p99', .99), ('maximum', 1.))})


def run(ref, mode, diagnostics):
    import pytest
    from tests.test_activation_observation_binding import flow
    from tests.lifecycle.test_traffic_refresh import test_repeated_late_refresh_and_signal_cycles_exceed_a_minute
    with version(ref):
        from tests.test_drive_engagement_safety import UltraPilotEngine
        generator = flow.__wrapped__()
        fixture = next(generator)
        wall, cpu, margins, ages, publication, faults = [], [], [], [], [], []
        retained = {}
        state, clock = fixture[0], fixture[6]
        first = clock[0]
        flush, set_value = UltraPilotEngine._flush_controls, state.set
        observed = set()
        def output(engine):
            before, cpu_before = time.perf_counter(), time.process_time()
            result = flush(engine)
            cpu.append(time.process_time()-cpu_before)
            wall.append(time.perf_counter()-before)
            applied = state.get('longitudinal_applied') or {}
            token = applied.get('written_at')
            if token is not None and token not in observed:
                observed.add(token)
                # Receipt identifies the actual selected command; no current
                # shared packet/header is substituted for an earlier write.
                at = applied.get('write_started_at')
                if at is not None:
                    margins.append(applied['expires_at']-at)
                    ages.append(at-applied['source_observation_timestamp'])
            fault = state.get('autopilot_first_fault_engine')
            if fault and fault.get('sequence') not in {f['sequence'] for f in faults}:
                faults.append(fault)
            journal = getattr(engine.controller, '_pedal_journal', None)
            if journal is not None:
                retained.update(detail_bytes=journal._bytes, detail_budget=journal.MAX_BYTES)
            return result
        def publish(key, value):
            result = set_value(key, value)
            if key in ('longitudinal_command', 'longitudinal_acc') and isinstance(value, dict):
                publication.append(value['expires_at']-clock[0])
            return result
        failure = None
        try:
            with patch.object(UltraPilotEngine, '_flush_controls', output), patch.object(state, 'set', publish):
                with pytest.MonkeyPatch.context() as mp:
                    try:
                        test_repeated_late_refresh_and_signal_cycles_exceed_a_minute(fixture, mp, mode, diagnostics)
                    except AssertionError as exc:
                        failure = str(exc) or 'unchanged regression assertion failed'
        finally:
            generator.close()
        return dict(ref=ref or 'working-tree', mode=mode, diagnostics=diagnostics,
            duration_s=clock[0]-first, assertion_failure=failure,
            technical_faults=len(faults), first_fault=faults[0] if faults else None,
            publication_margin_s=stats(publication), physical_write_margin_s=stats(margins),
            observation_age_at_write_s=stats(ages), flush_wall_s=stats(wall), flush_cpu_s=stats(cpu),
            runtime_detail_ring=retained,
            expired_normal_writes=sum(m < 0 for m in margins))


def steady(ref, diagnostics):
    """Equal-length paired ordinary driving; exclude the mock combined sink."""
    from tests.test_activation_observation_binding import flow
    from tests.signals.test_signal_lifecycle import lifecycle
    with version(ref):
        generator = flow.__wrapped__()
        fixture = next(generator)
        state, truck, engine, ap, tick, n, clock, writes, _ = lifecycle(fixture)
        engine._maneuver_diagnostic_collector = None
        engine._automatic_longitudinal_diagnostics = diagnostics
        wall, cpu, output, held_bytes = [], [], [], []
        try:
            for i in range(220):
                tick(4, 3., flush=False)
                before, cpu_before = time.perf_counter(), time.process_time()
                engine._flush_controls()
                elapsed, cpu_elapsed = time.perf_counter()-before, time.process_time()-cpu_before
                if i >= 20:
                    wall.append(elapsed); cpu.append(cpu_elapsed)
                    from tests.test_roundabout_intervention_reporting import pedal
                    output.append([pedal(engine, 'aforward'), pedal(engine, 'abackward')])
                    held_bytes.append(engine.controller._pedal_journal._bytes)
                if state.get('autopilot_first_fault_engine'):
                    raise AssertionError('Steady benchmark lost authority')
        finally:
            generator.close()
        return dict(wall_s=stats(wall), cpu_s=stats(cpu),
            output_sha256=hashlib.sha256(json.dumps(output).encode()).hexdigest(),
            maximum_detail_ring_bytes=max(held_bytes), detail_budget=65536,
            model='200 ordinary flushes after 20 warmups; no unbounded combined mock sink')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ref', default='3ee9786')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--cadence', action='store_true', help='Paired independent-cadence/RPC stress instead of late-boundary cycles')
    p.add_argument('--steady', action='store_true', help='Equal-length ordinary-flow overhead comparison')
    args = p.parse_args()
    logging.disable(logging.WARNING)
    if args.steady:
        cases = {str(enabled):[{label:steady(ref, enabled) for label,ref in
            (('baseline', args.ref), ('candidate', None))} for repeat in range(2)]
            for enabled in (False, True)}
        args.output.write_text(json.dumps(dict(cases=cases, game_verified=False), indent=2)+'\n', encoding='utf-8')
        print(json.dumps(cases, indent=2))
        raise SystemExit(0)
    if args.cadence:
        from tools.run_longitudinal_handoff_bench import run as cadence_run
        cases = {str(diagnostics):{label:cadence_run(ref, 75., .007, .0002, diagnostics)
                 for label, ref in (('baseline', args.ref), ('candidate', None))}
                 for diagnostics in (False, True)}
        args.output.write_text(json.dumps(dict(model='independent producers; copying RPC 200us; phase 7ms; not ETS2',
            cases=cases), indent=2)+'\n', encoding='utf-8')
        print(json.dumps({k:{l:dict(faults=v['faults'], margin=v['physical_write_margin_s'])
            for l,v in c.items()} for k,c in cases.items()}, indent=2))
        raise SystemExit(0)
    cases = {}
    for mode in (0, 3):
        for diagnostics in (False, True):
            cases[f'mode={mode};diagnostics={diagnostics}'] = {
                label: run(ref, mode, diagnostics) for label, ref in
                (('baseline', args.ref), ('candidate', None))}
    args.output.write_text(json.dumps(dict(model='controlled SDK + real producers and memory backend; not ETS2',
        cpu_timing_includes_test_doubles=True, cases=cases), indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k:{label:dict(duration_s=v['duration_s'], technical_faults=v['technical_faults'],
        write_margin=v['physical_write_margin_s'], observation_age=v['observation_age_at_write_s'],
        wall=v['flush_wall_s']) for label,v in c.items()} for k,c in cases.items()}, indent=2))
