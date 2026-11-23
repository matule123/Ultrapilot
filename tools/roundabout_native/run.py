"""Run existing UltraPilot fixtures against the frozen offline namespaces."""

import argparse
from collections import defaultdict
from contextlib import ExitStack, contextmanager
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
from unittest.mock import patch

from tools.roundabout_native.bridge import CrossingBatch, use_native


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'docs/steering-audit/nov2-roundabout'

# The original fixtures use an in-memory Controller backend. Suppress the
# optional joystick import even in Windows spawn children; it opens ViGEm at import.
if __name__ in ('__main__', '__mp_main__'):
    sys.modules['vgamepad'] = None


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen_runtime(stage):
    directory = EVIDENCE / stage
    runtime = directory / 'verification-runtime'
    manifest = json.loads((directory / 'qualification-summary.json').read_bytes())['runtime_sha256']
    for name, expected in manifest.items():
        if sha(runtime / name) != expected:
            raise RuntimeError(f'{stage}: frozen file hash differs for {name}')
    return runtime


def write_json(path, data):
    with path.open('x', encoding='utf-8') as output:
        json.dump(data, output, indent=2, sort_keys=True)


@contextmanager
def observe_replay(*, profile, audit, batch):
    from core import acc_body_prediction, actor_motion
    from core.acc_following import RouteLeadSelector
    from core.engine import UltraPilotEngine
    from tests.test_activation_observation_binding import IPCState

    records = []
    spans = None

    def measure(scope, owner, name, label, include=lambda *args, **kwargs: True):
        method = getattr(owner, name)

        @wraps(method)
        def measured(*args, **kwargs):
            if spans is None or not include(*args, **kwargs):
                return method(*args, **kwargs)
            started = time.perf_counter()
            try:
                return method(*args, **kwargs)
            finally:
                spans[label][0] += time.perf_counter() - started
                spans[label][1] += 1

        scope.enter_context(patch.object(owner, name, measured))

    original = UltraPilotEngine._traffic_control_observation

    @wraps(original)
    def observation(engine, *args, **kwargs):
        nonlocal spans
        spans = defaultdict(lambda: [0., 0]) if profile else None
        calls_before = batch.calls if batch else 0
        try:
            result = original(engine, *args, **kwargs)
            record = dict(phases=dict(spans or {}))
        finally:
            spans = None
        if batch:
            calls = batch.calls - calls_before
            if calls > 1:
                raise RuntimeError('More than one crossing batch in a traffic tick')
            if calls and profile:
                pack, call, handle, buffer_bytes = batch.spans.pop()
                record.update(native_seconds=dict(pack=pack, call=call, handle=handle),
                              native_arrays_bytes=buffer_bytes)
        if audit:
            selector = engine._acc_selector
            acquisition = selector._native_current
            actors = acquisition[1] if acquisition else {}
            record['branches'] = {str(key): hashlib.sha256(json.dumps(
                selector.actor_motion(actor), sort_keys=True, separators=(',', ':'),
                allow_nan=False).encode()).hexdigest()
                for key, actor in actors.items()}
        records.append(record)
        return result

    with ExitStack() as scope:
        if profile:
            measure(scope, RouteLeadSelector, 'prepare', 'cold_selector',
                    lambda route, points, binding, **kwargs: route.binding != binding)
            measure(scope, RouteLeadSelector, 'actor_motion', 'branch_selection',
                    lambda route, actor: actor['id'] not in route._actor_motion_cache)
            if hasattr(RouteLeadSelector, 'actor_body_motion'):
                measure(scope, RouteLeadSelector, 'actor_body_motion', 'body_pose_preparation')
            measure(scope, RouteLeadSelector, 'crossing', 'crossing')
            measure(scope, actor_motion, 'crossing_pairs', 'python_pairs')
            measure(scope, acc_body_prediction, 'predict', 'swept_body')
            for method in ('get', 'set', 'update_batch'):
                measure(scope, IPCState, method, 'fixture_ipc_copy')
        scope.enter_context(patch.object(UltraPilotEngine, '_traffic_control_observation', observation))
        yield records


def replay(args, batch):
    from tools.reproduce_roundabout_prediction import main

    command = ['score', '--out', str(args.out), '--repeat', str(args.repeat)]
    if args.overlap:
        command += ['--maximum-traffic', '--spread']
    if args.wall_clock:
        command += ['--wall-clock']
    if args.out.exists() or args.out.with_suffix('.probe.json').exists():
        raise FileExistsError(args.out)
    with ExitStack() as scope:
        if args.profile or args.audit:
            records = scope.enter_context(observe_replay(profile=args.profile, audit=args.audit, batch=batch))
        else:
            records = []
        scope.enter_context(patch.object(sys, 'argv', [sys.argv[0], *command]))
        main()

    meta = dict(stage=args.stage, native_calls=batch.calls if batch else 0,
                checked_actors=batch.checked_actors if batch else 0,
                peak_arrays_bytes=batch.peak_buffer_bytes if batch else 0,
                fixture_sha256=sha(ROOT / 'tests/fixtures/nov2-roundabout-native.json'),
                library_sha256=sha(args.library) if args.library else None,
                records=records)
    write_json(args.out.with_suffix('.probe.json'), meta)


def _native_daemon(arguments, state, connection):
    from core.ipc.shared_state import SharedState
    from core.steering_replay import configure_diagnostic_export
    from tools.qualify_oct25_traffic_capture import run

    try:
        library = arguments.pop('native_library')
        batch = CrossingBatch(library)
        configure_diagnostic_export(SharedState(state))
        with use_native(batch):
            result = run(**arguments, child_memory_external=True)
        result.update(native_calls=batch.calls, native_peak_arrays_bytes=batch.peak_buffer_bytes)
        connection.send(dict(result=result))
    except Exception as error:
        connection.send(dict(error=type(error).__name__, detail=str(error)))
    finally:
        connection.close()


def export(args):
    from tools import qualify_oct25_traffic_capture as qualification
    from tools.assess_oct25_traffic_qualification import assess

    args.out.mkdir(parents=True, exist_ok=False)
    original = EVIDENCE / 'perf21-offline/load'
    for name in ('ACCEPTANCE.md', 'original03-identity.json', 'approved-budget.json',
                 'baseline-scope-approval.json'):
        shutil.copyfile(original / name, args.out / name)
    with ExitStack() as scope:
        if args.library:
            scope.enter_context(patch.object(qualification, '_daemon_qualification', _native_daemon))
        for mode, label in ((0, 'simple'), (3, 'real')):
            for enabled in (False, True):
                name = f'final-max-{label}-{"on" if enabled else "off"}'
                print(f'Running {name}', flush=True)
                settings = dict(mode=mode, enabled=enabled, count=40, trailers=3, ticks=1400,
                                directory=args.out / name, pace=.005)
                if args.library:
                    settings['native_library'] = str(args.library.resolve(strict=True))
                result = qualification.run_daemon_host(settings)
                write_json(args.out / f'{name}.json', result)
                print(json.dumps({key: result[key] for key in ('whole_tick', 'engine_flush',
                      'concurrent_export_tick', 'active', 'fault')}), flush=True)
    result = assess(args.out)
    write_json(args.out / 'assessment.json', result)
    print(json.dumps({key: result[key] for key in ('verdict', 'failures')}), flush=True)
    return bool(result['failures'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('release11', 'perf21-offline'))
    parser.add_argument('--library', type=Path)
    commands = parser.add_subparsers(required=True, dest='command')
    replay_parser = commands.add_parser('replay')
    replay_parser.add_argument('--out', type=Path, required=True)
    replay_parser.add_argument('--repeat', type=int, default=1)
    replay_parser.add_argument('--overlap', action='store_true')
    replay_parser.add_argument('--wall-clock', action='store_true')
    replay_parser.add_argument('--profile', action='store_true')
    replay_parser.add_argument('--audit', action='store_true')
    test_parser = commands.add_parser('test')
    test_parser.add_argument('pytest_args', nargs=argparse.REMAINDER)
    export_parser = commands.add_parser('export')
    export_parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.library and args.stage != 'perf21-offline':
        parser.error('The native adapter is specific to perf21')
    runtime = frozen_runtime(args.stage)
    sys.path.insert(0, str(runtime))
    from core import acc_following, actor_motion, engine

    for module in (acc_following, actor_motion, engine):
        if not Path(module.__file__).resolve().is_relative_to(runtime):
            raise RuntimeError(f'Unexpected runtime module: {module.__file__}')
    if args.command == 'export':
        return export(args)
    with ExitStack() as scope:
        batch = None
        if args.library:
            batch = CrossingBatch(args.library, check_pairs=args.command == 'test' or args.audit,
                                  profile=args.command == 'replay' and args.profile)
            scope.enter_context(use_native(batch))
        if args.command == 'replay':
            replay(args, batch)
        else:
            import pytest

            if batch:
                scope.enter_context(patch.dict(os.environ, {
                    'UP_ROUNDABOUT_OFFLINE_DLL': str(args.library.resolve(strict=True))}))
            result = pytest.main(args.pytest_args[1:] if args.pytest_args[:1] == ['--'] else args.pytest_args)
            if batch:
                print(f'Native calls: {batch.calls}, exact actor pair comparisons: {batch.checked_actors}')
            return result


if __name__ == '__main__':
    raise SystemExit(main())
