"""Measure the existing roundabout replay against isolated Python runtimes."""

import argparse
import ast
from collections import Counter
from contextlib import ExitStack, contextmanager
import ctypes
from functools import wraps
import json
import inspect
from pathlib import Path
import shutil
import sys
from textwrap import dedent
import threading
import time
from unittest.mock import patch

from tools.roundabout_native.run import frozen_runtime, sha, write_json


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ('actor_motion.py', 'acc_following.py', 'acc_body_prediction.py')
OVERLAY_FILES = ('engine.py', 'transmission_mode.py', 'navigation/longitudinal_diagnostics.py')
ENGINE_READS = {
    '_autopilot_activation_rejection_reason': 1,
    '_begin_auto_drive_engagement': 1,
    '_flush_auto_drive_engagement': 3,
    '_wait_for_first_pedal_command': 1,
    '_record_drive_boundary': 1,
    '_flush_controls_unlocked': 1,
}

if __name__ in ('__main__', '__mp_main__'):
    # Frozen offline fixtures supply their own Controller backend.
    sys.modules['vgamepad'] = None


def engine_overlay(frozen, workspace):
    """Apply only our route reader and acquisition change to archived Engine."""
    def methods(source):
        cls = next(node for node in ast.parse(source).body
                   if isinstance(node, ast.ClassDef) and node.name == 'UltraPilotEngine')
        return {node.name: node for node in cls.body if isinstance(node, ast.FunctionDef)}

    original_methods = methods(frozen)
    workspace_methods = methods(workspace)
    lines = frozen.splitlines(keepends=True)
    old = 'self.shared_state.get("lane_trajectory", {}) or {}'
    new = 'self._read_control_lane_snapshot()'
    for name, expected in ENGINE_READS.items():
        a = original_methods[name]
        b = workspace_methods[name]
        before = ''.join(lines[a.lineno - 1:a.end_lineno])
        after = '\n'.join(workspace.splitlines()[b.lineno - 1:b.end_lineno])
        if before.count(old) - after.count(old) != expected or after.count(new) != expected:
            raise ValueError(f'Engine cache site changed in {name}')
        for i in range(a.lineno - 1, a.end_lineno):
            if old in lines[i] and ('snapshot =' in lines[i] or name == '_record_drive_boundary'):
                lines[i] = lines[i].replace('(' + old + ')', new).replace(old, new)
    activation = original_methods['_autopilot_activation_rejection_reason']
    reader = workspace_methods['_read_control_lane_snapshot']
    lines.insert(activation.lineno - 1, '\n'.join(workspace.splitlines()[reader.lineno - 1:reader.end_lineno]) + '\n\n')
    source = ''.join(lines)
    old_motion = "selector.source_motion(observed['actors'], observed.get('source'))"
    new_motion = old_motion[:-1] + ', include_predictions=False)'
    if source.count(old_motion) != 1 or workspace.count(new_motion) != 1:
        raise ValueError('Engine acquisition site changed')
    return source.replace(old_motion, new_motion)


def stage(destination):
    original = frozen_runtime('perf21-offline')
    destination.mkdir(parents=True, exist_ok=False)
    for package in ('core', 'plugins', 'sdk', 'ui'):
        shutil.copytree(original / package, destination / package,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.log'))
    for name in PAYLOAD:
        shutil.copyfile(ROOT / 'core' / name, destination / 'core' / name)
    diagnostics = 'core/navigation/longitudinal_diagnostics.py'
    shutil.copyfile(ROOT / diagnostics, destination / diagnostics)
    engine = destination / 'core/engine.py'
    engine.write_text(engine_overlay(engine.read_text(encoding='utf-8'),
                                     (ROOT / 'core/engine.py').read_text(encoding='utf-8')), encoding='utf-8')
    mode = destination / 'core/transmission_mode.py'
    frozen_mode = mode.read_text(encoding='utf-8')
    workspace_mode = (ROOT / 'core/transmission_mode.py').read_text(encoding='utf-8')
    # Keep the unrelated workspace restart changes out of this comparison.
    before = 'def simple_auto_context(state):'
    after = '    try:\n        frame = int(truck["sdkFrameTimeUs"])'
    start = frozen_mode.index(before)
    end = frozen_mode.index(after, start)
    new_start = workspace_mode.index('def _forward_lane_identity(state):')
    new_end = workspace_mode.index(after, new_start)
    mode.write_text(frozen_mode[:start] + workspace_mode[new_start:new_end] + frozen_mode[end:], encoding='utf-8')
    write_json(destination / 'workspace-sources.json', {name: sha(destination / 'core' / name)
                                                        for name in (*PAYLOAD, *OVERLAY_FILES)})


def select_runtime(source):
    if source in ('release11', 'perf21-offline'):
        runtime = frozen_runtime(source)
    else:
        runtime = Path(source).resolve(strict=True)
        hashes = json.loads((runtime / 'workspace-sources.json').read_bytes())
        if (not set(PAYLOAD) <= set(hashes) <= {*PAYLOAD, *OVERLAY_FILES}
                or any(sha(runtime / 'core' / name) != value for name, value in hashes.items())):
            raise ValueError('Staged sources differ from the measured copy')
    sys.path.insert(0, str(runtime))
    return runtime


@contextmanager
def counters(*, bind_profile=False):
    from core import acc_body_prediction, actor_motion, engine
    from core.acc_following import RouteLeadSelector
    from core.navigation import longitudinal_diagnostics as diagnostic
    from tests.test_activation_observation_binding import IPCState
    from tools import reproduce_roundabout_prediction as replay

    records = []
    counts, phases, ipc = Counter(), Counter(), Counter()
    seen_envelopes = {}
    active = False
    flush = False
    binding = None
    bind_rows = []
    replay_thread = threading.get_ident()

    if bind_profile:
        # Windows thread time is useful but coarse on this host. Report the
        # native cycle counter separately, without converting cycles to time.
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetCurrentThread.restype = ctypes.c_void_p
        kernel.QueryThreadCycleTime.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint64))
        kernel.QueryThreadCycleTime.restype = ctypes.c_int
        thread = kernel.GetCurrentThread()
        cycles = ctypes.c_uint64()

        def read_cycles():
            if not kernel.QueryThreadCycleTime(thread, ctypes.byref(cycles)):
                raise ctypes.WinError(ctypes.get_last_error())
            return cycles.value

    def measure(scope, owner, name, label, count=None):
        original = getattr(owner, name)

        @wraps(original)
        def measured(*args, **kwargs):
            if not active:
                return original(*args, **kwargs)
            started = time.perf_counter()
            result = original(*args, **kwargs)
            phases[label] += time.perf_counter() - started
            counts[label + '_calls'] += 1
            if count:
                count(result, args, kwargs)
            return result

        scope.enter_context(patch.object(owner, name, measured))

    def branches(result, args, kwargs):
        if result:
            counts['forecast_results'] += len(result['branches'])
            counts['forecast_poses'] += sum(len(branch['poses']) for branch in result['branches'])
            counts['new_forecast_pose_tuples'] += len({id(pose) for branch in result['branches']
                                                       for pose in branch['poses']})

    def poses(result, args, kwargs):
        body_count, branch_count, sample_count, components = result.shape
        counts['cab_poses'] += branch_count * sample_count
        counts['trailer_poses'] += (body_count - 1) * branch_count * sample_count
        if kwargs.get('horizontal') is None:
            counts['body_array_bytes'] += result.base.nbytes if components == 2 else result.nbytes
        kind = 'horizontal' if components == 2 else 'full'
        counts[f'{kind}_body_arrays'] += 1
        counts['reused_horizontal_arrays'] += int(kwargs.get('horizontal') is not None)

    def envelope(result, args, kwargs):
        if id(result) not in seen_envelopes:
            counts['arrival_masks_allocated'] += 1
            counts['arrival_mask_bytes'] += result[1].nbytes
            seen_envelopes[id(result)] = result

    def pairs(result, args, kwargs):
        motion, edges = args[2:4]
        counts['potential_crossing_pairs'] += len(edges) * len(args[1]) * sum(
            len(branch['poses']) - 1 for branch in motion['branches'])
        counts['crossing_piece_rows'] += sum(map(len, result.values()))
        counts['crossing_pairs_to_scalar'] += sum(len(indices) for pieces in result.values()
                                                   for _, indices in pieces)

    def contact(result, args, kwargs):
        kind = 'observed' if args[4] == 0. else 'swept'
        counts[kind + '_exact_contacts'] += 1

    def probe(mode, index, start, flush_started, end, pauses, row):
        nonlocal active
        active = False
        gc_spans = [(max(start, lo), min(end, hi), generation) for lo, hi, generation in pauses
                    if lo < end and hi > start]
        where = {'projection': (start, start + row['projection_ms'] / 1000.),
                 'flush': (flush_started, end), 'tick': (start, end)}
        gc_ms = {phase: 1000. * sum(max(0., min(hi, limit) - max(lo, begin))
                                   for lo, hi, _ in gc_spans)
                 for phase, (begin, limit) in where.items()}
        records.append(dict(mode=mode, index=index, at_s=row['at_s'], counts=dict(counts),
                            phases_ms={k: 1000. * v for k, v in phases.items()},
                            ipc_ms={k: 1000. * v for k, v in ipc.items()}, gc_ms=gc_ms,
                            gc_generations=[generation for _, _, generation in gc_spans],
                            whole_tick_ms=row['whole_tick_ms'], engine_flush_ms=row['engine_flush_ms'],
                            projection_ms=row['projection_ms'], projection_cpu_ms=row['projection_cpu_ms']))
        if bind_profile:
            for call in bind_rows:
                lo, hi = call.pop('wall_interval')
                call['gc_ms'] = 1000. * sum(max(0., min(hi, end) - max(lo, begin))
                                            for begin, end, _ in gc_spans)
                # Subphase walls can contain scheduling delay. This residual
                # is unattributed wall time, not a measurement of scheduler wait.
                call['outside_instrumented_subphases_ms'] = max(0., call['wall_ms'] - sum(call['subphase_wall_ms'].values()))
            records[-1]['bind'] = bind_rows.copy()
            bind_rows.clear()
        counts.clear()
        phases.clear()
        ipc.clear()
        seen_envelopes.clear()

    old_apply = replay.apply_frame
    old_flush = engine.UltraPilotEngine._flush_controls

    def apply_frame(*args, **kwargs):
        nonlocal active
        active = True
        return old_apply(*args, **kwargs)

    def flush_controls(*args, **kwargs):
        nonlocal flush
        flush = active
        if flush and getattr(args[0], '_controller_io_lock', None) is None:
            counts['flush_without_controller_lock'] += 1
        started = time.thread_time()
        try:
            return old_flush(*args, **kwargs)
        finally:
            if flush:
                phases['engine_flush_thread_cpu'] += time.thread_time() - started
            flush = False

    def state_access(scope, name):
        original = getattr(IPCState, name)

        def measured(self, key, *args):
            if not active:
                return original(self, key, *args)
            started = time.perf_counter()
            value = original(self, key, *args)
            phase = 'flush' if flush else 'before_flush'
            field = key if isinstance(key, str) else 'batch'
            elapsed = time.perf_counter() - started
            ipc[f'{phase}:{name}:{field}'] += elapsed
            if binding is not None and threading.get_ident() == replay_thread:
                binding['fixture_state_access_wall_ms'] += elapsed * 1000.
            if field == 'lane_trajectory':
                caller = sys._getframe(1).f_code.co_name
                counts[f'lane_read:{phase}:{caller}'] += 1
            counts[f'ipc_{phase}_{name}_calls'] += 1
            return value

        scope.enter_context(patch.object(IPCState, name, measured))

    def detail(scope, owner, name, label):
        original = getattr(owner, name)

        @wraps(original)
        def measured(*args, **kwargs):
            if binding is None or threading.get_ident() != replay_thread:
                return original(*args, **kwargs)
            started = time.perf_counter()
            cpu = time.thread_time()
            cycles_before = read_cycles()
            wall_before = sum(binding['subphase_wall_ms'].values())
            try:
                result = original(*args, **kwargs)
                if label == 'primitive_freeze':
                    binding['freezes'].append((result['raw_bytes'], result['raw_sha256']))
                return result
            finally:
                # Count the outer boundary once when named operations nest.
                elapsed = (time.perf_counter() - started) * 1000.
                nested = sum(binding['subphase_wall_ms'].values()) - wall_before
                binding['subphase_wall_ms'][label] += max(0., elapsed - nested)
                binding['subphase_cpu_ms_inclusive'][label] += (time.thread_time() - cpu) * 1000.
                binding['subphase_cycles_inclusive'][label] += read_cycles() - cycles_before

        scope.enter_context(patch.object(owner, name, measured))

    def observe_bind(scope):
        original = diagnostic.PedalJournal.bind

        class RingLock:
            def __init__(self, real):
                self.real = real

            def __enter__(self):
                started = time.perf_counter()
                result = self.real.__enter__()
                if binding is not None and threading.get_ident() == replay_thread:
                    binding['ring_lock_acquire_wall_ms'] += (time.perf_counter() - started) * 1000.
                    binding['ring_lock_acquisitions'] += 1
                return result

            def __exit__(self, *exc):
                return self.real.__exit__(*exc)

            def __getattr__(self, name):
                return getattr(self.real, name)

        @wraps(original)
        def bind(journal, value):
            nonlocal binding
            if not active or binding is not None or threading.get_ident() != replay_thread:
                return original(journal, value)
            window = journal._incident_window
            lock = window.lock if window is not None else None
            if window is not None:
                window.lock = RingLock(lock)
            binding = dict(phase=value.get('phase') if isinstance(value, dict) else None,
                           value_present=value is not None, ring=window is not None,
                           simple_records=bool(window is not None and window.simple_records),
                           fixture_state_access_wall_ms=0., ring_lock_acquire_wall_ms=0.,
                           ring_lock_acquisitions=0, freezes=[], subphase_wall_ms=Counter(),
                           subphase_cpu_ms_inclusive=Counter(), subphase_cycles_inclusive=Counter())
            started = time.perf_counter()
            cpu = time.thread_time()
            cycle = read_cycles()
            try:
                return original(journal, value)
            finally:
                end = time.perf_counter()
                binding.update(wall_ms=(end-started)*1000., cpu_ms=(time.thread_time()-cpu)*1000.,
                               cpu_cycles=read_cycles()-cycle, wall_interval=(started, end))
                bind_rows.append(binding)
                binding = None
                if window is not None:
                    window.lock = lock

        scope.enter_context(patch.object(diagnostic.PedalJournal, 'bind', bind))
        for name, label in (('freeze_primitive_record', 'primitive_freeze'), ('_freeze_input', 'freeze_input'),
                            ('pack_source', 'pack_source'), ('_pack_intervention', 'pack_intervention'),
                            ('bounded_copy', 'bounded_copy'), ('_decision_summary', 'decision_summary')):
            detail(scope, diagnostic, name, label)

    with ExitStack() as scope:
        scope.enter_context(patch.object(replay, 'apply_frame', apply_frame))
        scope.enter_context(patch.object(engine.UltraPilotEngine, '_flush_controls', flush_controls))
        for method in ('get', 'set', 'update_batch'):
            state_access(scope, method)
        measure(scope, actor_motion.ActorMotionGraph, '__init__', 'graph_preparation',
                lambda _, a, k: counts.update(authored_graphs=int(bool(a[1]))))
        measure(scope, actor_motion.ActorMotionGraph, 'hypotheses', 'branch_forecast', branches)
        measure(scope, actor_motion, 'projected_bodies', 'body_preparation', poses)
        measure(scope, actor_motion, 'crossing_pairs', 'crossing_admission', pairs)
        if hasattr(actor_motion, 'CrossingWindows'):
            measure(scope, actor_motion.CrossingWindows, 'envelope', 'arrival_envelope_lookup', envelope)
        measure(scope, RouteLeadSelector, 'crossing', 'crossing_inclusive')
        measure(scope, acc_body_prediction, 'predict', 'body_prediction_inclusive')
        measure(scope, acc_body_prediction, 'contact_interval', 'exact_contact', contact)
        for name in ('pack_source', '_freeze_input'):
            measure(scope, diagnostic, name, ('flush_' if name == 'pack_source' else '') + name)
        for name in ('bind', 'record', 'finish_decision'):
            measure(scope, diagnostic.PedalJournal, name, 'journal_' + name)
        if bind_profile:
            observe_bind(scope)
        yield probe, records


@contextmanager
def native_trial(library, profile):
    """Measure the previous batch DLL with the new Python and Engine work."""
    from core.acc_following import RouteLeadSelector
    from tools.roundabout_native.bridge import CrossingBatch

    batch = CrossingBatch(library, profile=profile)
    original = RouteLeadSelector.crossing
    source = inspect.getsource(original)
    start = source.index('            arrival_windows = None\n')
    end = source.index('                bodies = original.get', start)
    source = (source[:start] + '''            mapped_actors = (_offline_batch(self, actors, first, last)
                             if not timed or speed > .1 else {})
            for original in actors:
                motion = self.actor_motion(original) if not timed or speed > .1 else None
                mapped = mapped_actors.get(original['id'])
''' + source[end:])
    start = source.index('                        if mapped is None:\n')
    end = source.index('                        paired = mapped.get', start)
    source = source[:start] + source[end:]

    def batch_for_tick(selector, actors, first, last):
        jobs = []
        for actor in actors:
            motion = selector.actor_motion(actor)
            if motion:
                bodies = actor.get('bodies') or [actor]
                jobs.append((actor, bodies, motion, selector.actor_body_motion(actor, motion)))
        pairs = batch.admit(jobs, selector._crossing_bounds[first:last], selector._crossing_values[first:last], first)
        return {actor['id']: result for (actor, _, _, _), result in zip(jobs, pairs, strict=True)}

    namespace = dict(original.__globals__, _offline_batch=batch_for_tick)
    exec(compile(dedent(source), '<offline native timing trial>', 'exec'), namespace)
    with patch.object(RouteLeadSelector, 'crossing', namespace['crossing']):
        yield batch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('stage').add_argument('path', type=Path)
    for command in ('replay', 'test', 'export', 'seal-export', 'overlap-export'):
        command_parser = commands.add_parser(command)
        command_parser.add_argument('runtime')
        if command == 'test':
            command_parser.add_argument('pytest_args', nargs=argparse.REMAINDER)
        else:
            command_parser.add_argument('--out', type=Path, required=True)
        if command == 'replay':
            command_parser.add_argument('--profile', action='store_true')
            command_parser.add_argument('--bind-profile', action='store_true')
            command_parser.add_argument('--audit', action='store_true')
            command_parser.add_argument('--repeat', type=int, default=3)
            command_parser.add_argument('--original', action='store_true')
            command_parser.add_argument('--unfiltered', action='store_true')
            command_parser.add_argument('--trial-library', type=Path)
        if command == 'overlap-export':
            command_parser.add_argument('--sealed', type=Path, required=True)
            command_parser.add_argument('--reference', type=Path, required=True)
            command_parser.add_argument('--bind-profile', action='store_true')
    args = parser.parse_args()
    if args.command == 'stage':
        return stage(args.path)
    runtime = select_runtime(args.runtime)
    from core import actor_motion

    if not Path(actor_motion.__file__).resolve().is_relative_to(runtime):
        raise RuntimeError('Wrong actor motion runtime')
    if args.command == 'test':
        import pytest

        return pytest.main(args.pytest_args[1:] if args.pytest_args[:1] == ['--'] else args.pytest_args)
    if args.command == 'export':
        from tools.roundabout_native.run import export

        args.library = None
        return export(args)
    if args.command == 'seal-export':
        from tools.roundabout_export_overlap import capture_fixture

        return capture_fixture(args.out.resolve())
    if args.command == 'overlap-export':
        from tools.roundabout_export_overlap import run_replay

        return run_replay(args.sealed.resolve(strict=True), args.out.resolve(), args.reference,
                          bind_probe=counters if args.bind_profile else None)

    from tools.reproduce_roundabout_prediction import main as play
    from tools.roundabout_native.run import replay

    with ExitStack() as scope:
        batch = None
        if args.trial_library:
            batch = scope.enter_context(native_trial(args.trial_library, args.profile))
        if args.audit:
            args.overlap = not args.original
            args.wall_clock = False
            args.stage = args.runtime
            args.library = args.trial_library
            if args.unfiltered:
                from core import acc_body_prediction

                old_pairs = actor_motion.crossing_pairs
                old_predict = acc_body_prediction.predict

                def pairs(*a, **kw):
                    return old_pairs(*a, **dict(kw, arrival_windows=None))

                def predict(*a, **kw):
                    return old_predict(*a, **dict(kw, prefilter=False))

                scope.enter_context(patch.object(actor_motion, 'crossing_pairs', pairs))
                scope.enter_context(patch.object(acc_body_prediction, 'predict', predict))
            return replay(args, batch)
        if args.out.exists():
            raise FileExistsError(args.out)
        command = ['score', '--repeat', str(args.repeat), '--out', str(args.out)]
        if not args.original:
            command += ['--maximum-traffic', '--spread']
        probe = None
        if args.profile or args.bind_profile:
            probe, records = scope.enter_context(counters(bind_profile=args.bind_profile))
        scope.enter_context(patch.object(sys, 'argv', [sys.argv[0], *command]))
        play(tick_probe=probe)
        if args.profile or args.bind_profile:
            write_json(args.out.with_suffix('.work.json'), records)
        if batch:
            write_json(args.out.with_suffix('.native.json'), dict(calls=batch.calls, peak_array_bytes=batch.peak_buffer_bytes,
                                                                 library_sha256=sha(args.trial_library), spans=batch.spans))


if __name__ == '__main__':
    raise SystemExit(main())
