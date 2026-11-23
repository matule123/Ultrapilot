"""Paired bounded-refresh stress, real control code / modeled clocks and SDK.

Historical modules load in memory, never into either checkout or installation.
Wall/CPU/GC are measured; injected IPC phase delays are MODEL time, not measured
OS wait. Equal-length ordinary runs separate overhead from early baseline exit.
"""
import argparse
import gc
import json
import logging
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.run_longitudinal_handoff_bench import version
from tools.benchmark_oct15_refresh import stats, steady


def run(ref, mode, diagnostics):
    import pytest
    from tests.test_activation_observation_binding import flow
    from tests.lifecycle.test_joint_regressions import joint
    from tests.lifecycle.test_refresh_protocol import run_repeated_response_races
    gc.collect()  # Same initial harness condition, outside every measured flush.
    with version(ref), tempfile.TemporaryDirectory(prefix='ultrapilot-refresh-') as directory:
        f = flow.__wrapped__()
        values = next(f)
        g = joint.__wrapped__(values, SimpleNamespace(param=mode))
        source = next(g)
        gc_started, gc_samples, gc_spans, flush_spans = [], [], [], []
        def collect(phase, info):
            if phase == 'start':
                gc_started.append(time.perf_counter())
            elif gc_started:
                begun, ended = gc_started.pop(), time.perf_counter()
                gc_samples.append(ended-begun)
                gc_spans.append((begun,ended))
        gc.callbacks.append(collect)
        before, cpu_before = time.perf_counter(), time.process_time()
        try:
            with pytest.MonkeyPatch.context() as mp:
                flush = source[1]._flush_controls
                def measure():
                    begun = time.perf_counter()
                    try:
                        return flush()
                    finally:
                        flush_spans.append((begun,time.perf_counter()))
                mp.setattr(source[1], '_flush_controls', measure)
                result = run_repeated_response_races(source, mp, diagnostics=diagnostics,
                    export_directory=Path(directory) if diagnostics else None,
                    clear_mock_history=True)
        finally:
            gc.callbacks.remove(collect)
            g.close(); f.close()
        result.update(total_wall_s=time.perf_counter()-before,
            total_process_cpu_s=time.process_time()-cpu_before, gc_s=stats(gc_samples),
            ref=ref or 'working-tree', mode=mode, diagnostics=diagnostics)
        slow = sorted(flush_spans,key=lambda span:span[1]-span[0],reverse=True)[:5]
        result['slow_flushes'] = [dict(wall_s=end-start,
            overlapping_gc_s=sum(max(0.,min(end,b)-max(start,a)) for a,b in gc_spans))
            for start,end in slow]
        for key in ('wall', 'cpu', 'write_margins', 'publication_margins',
                    'reception_margins', 'observation_ages'):
            result[key] = stats(result[key])
        return result


def ordinary(ref, on):
    gc.collect()
    return steady(ref, on)


def manager_roundtrip(ref, mode, manager):
    """Same operations over a real Manager process, no synthetic IPC sleep.

    SDK/job time remains injected. RPC wall includes server work, transport and
    scheduling; it is not falsely labelled pure blocked time or game latency.
    """
    import pytest
    from tests.test_activation_observation_binding import flow
    from tests.lifecycle.test_joint_regressions import joint
    from tests.lifecycle.test_refresh_protocol import run_repeated_response_races
    gc.collect()
    with version(ref):
        f = flow.__wrapped__(); values = next(f)
        g = joint.__wrapped__(values, SimpleNamespace(param=mode)); source = next(g)
        state, engine, ap, acc, policy, tick = source[:6]
        old = state.values
        raw = manager.dict(old)
        roundtrips = []
        class Meter:
            def call(self, method, *args):
                begun = time.perf_counter()
                try:
                    return getattr(raw, method)(*args)
                finally:
                    roundtrips.append(time.perf_counter()-begun)
            def get(self, key, default=None): return self.call('get', key, default)
            def __getitem__(self, key): return self.call('__getitem__', key)
            def __setitem__(self, key, value): return self.call('__setitem__', key, value)
            def update(self, values): return self.call('update', values)
        proxy = Meter()
        state.values = proxy
        for plugin in (ap,acc,policy,tick.publish_map.__self__):
            for view in (plugin.sdk,*plugin.sdk.__dict__.values()):
                if hasattr(view,'_state') and view._state is old:
                    object.__setattr__(view,'_state',proxy)
        try:
            with pytest.MonkeyPatch.context() as mp:
                result = run_repeated_response_races(source,mp,cycles=20,
                    diagnostics=True,clear_mock_history=True)
        finally:
            g.close(); f.close()
        return dict(ref=ref or 'working-tree',mode=mode,recovered=result['recovered'],
            failure=result['failure'],duration_s=result['duration_s'],
            flush_wall_s=stats(result['wall']),flush_cpu_s=stats(result['cpu']),
            measured_rpc_roundtrip_s=stats(roundtrips),
            physical_write_margin_s=stats(result['write_margins']))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ref', default='eab0026')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--manager-only', action='store_true')
    args = parser.parse_args()
    logging.disable(logging.WARNING)
    if args.manager_only:
        import multiprocessing
        # Start the server before importing fixtures which stub native Pool
        # dependencies. The server registry must retain real picklable classes.
        with multiprocessing.Manager() as manager:
            result = {str(mode):{label:manager_roundtrip(ref,mode,manager)
                      for label,ref in (('baseline',args.ref),('candidate',None))} for mode in (0,3)}
        args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(result,indent=2))
        raise SystemExit(0)
    cases = {f'{mode}/{diagnostics}': [{label:run(ref, mode, diagnostics)
        for label, ref in (('baseline', args.ref), ('candidate', None))} for repeat in range(2)]
        for mode in (0, 3) for diagnostics in (False, True)}
    ordinary = {str(on): [{label:ordinary(ref, on)
        for label, ref in (('baseline', args.ref), ('candidate', None))} for repeat in range(2)]
        for on in (False, True)}
    result = dict(cases=cases, ordinary=ordinary, game_verified=False,
        note='Fixed observed speed, real byte reader/Map/Policy/ACC/AP/Engine/SCS mapping; '
             'phased causal publication + 1.4947 ms final-boundary overrun; not vehicle physics. '
             'CPU includes test deepcopy/RPC doubles; wait cannot be inferred from wall minus CPU. '
             'Mock histories excluded from retained runtime detail-byte accounting.')
    args.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({key:[{label:dict(recovered=v['recovered'], duration_s=v['duration_s'],
        failure=bool(v['failure']), wall=v['wall'], write_margin=v['write_margins'])
        for label, v in pair.items()} for pair in repeats] for key, repeats in cases.items()}, indent=2))
