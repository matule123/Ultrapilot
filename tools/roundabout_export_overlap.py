"""Run an unchanged overlapping replay while a real diagnostic child exports."""

from contextlib import ExitStack
import hashlib
import multiprocessing
import pickle
from pathlib import Path
import shutil
import sys
import threading
import time
from unittest.mock import patch

import psutil

from tools.roundabout_native.compare import control_bytes, load, stats
from tools.roundabout_native.run import write_json


def _retain_sealed_window(arguments, state, connection):
    from core.ipc.shared_state import SharedState
    from core import steering_replay
    from tools.qualify_oct25_traffic_capture import run

    artifact = arguments.pop('sealed_artifact')
    original = steering_replay.export_incident_isolated
    sealed = []

    def capture(directory, window, journal):
        result = original(directory, window, journal)
        if result and not sealed:
            sealed.append((window, journal))
        return result

    try:
        steering_replay.configure_diagnostic_export(SharedState(state))
        with patch.object(steering_replay, 'export_incident_isolated', capture):
            result = run(**arguments, child_memory_external=True)
        if len(sealed) != 1 or not result['post_warm_dossiers']:
            raise RuntimeError('Original capture failed to make a sealed test input')
        with artifact.open('xb') as stream:
            pickle.dump(sealed[0], stream, protocol=pickle.HIGHEST_PROTOCOL)
        connection.send(dict(result=result))
    except Exception as error:
        connection.send(dict(error=type(error).__name__, detail=str(error)))
    finally:
        connection.close()


def capture_fixture(directory):
    """Preserve the original compressed pre-export inputs for the contention probe."""
    from tools import qualify_oct25_traffic_capture as qualification

    directory.mkdir(parents=True, exist_ok=False)
    settings = dict(mode=0, enabled=True, count=40, trailers=3, ticks=1400, pace=.005,
                    directory=directory / 'generated', sealed_artifact=directory / 'sealed.bin')
    with patch.object(qualification, '_daemon_qualification', _retain_sealed_window):
        result = qualification.run_daemon_host(settings)
    write_json(directory / 'capture.json', result)


def run_replay(fixture, directory, reference, *, bind_probe=None):
    from core import actor_motion, steering_replay
    from core.ipc.shared_state import DiagnosticStateManager, SharedState
    from core.navigation.longitudinal_diagnostics import diagnostic_build_limits
    from tools.reproduce_roundabout_prediction import main

    directory.mkdir(parents=True, exist_ok=False)
    # Only load this locally generated sealed artifact, from capture_fixture.
    with (fixture / 'sealed.bin').open('rb') as stream:
        window, journal = pickle.load(stream)
    name = f'incident-{window["incident_id"]}.json'
    dossier = next((item for item in load(fixture / 'capture.json')['post_warm_dossiers']
                    if item['name'] == name), None)
    if dossier is None:
        raise RuntimeError('The sealed input has no matching original export')
    if not dossier['assembly_complete'] or dossier['incomplete']:
        raise RuntimeError('Contention probe requires a complete original sealed input')
    part = dossier['parts']['autopilot']['name']
    limits = diagnostic_build_limits()
    results = {}
    manifests = {}
    baseline = {run['mode']: run for run in load(reference)}

    for mode in (0, 3):
        output = directory / f'mode-{mode}'
        output.mkdir()
        shutil.copyfile(fixture / 'generated' / part, output / part)
        ticks, child_samples = [], []
        ready, stop = threading.Event(), threading.Event()
        host = psutil.Process()
        parent_peak = 0
        host_peak = 0
        broker_peak = 0
        family_peak = 0
        children_peak = 0
        concurrency_peak = 0
        used = 0

        def monitor():
            nonlocal parent_peak, host_peak, broker_peak, family_peak, children_peak, concurrency_peak
            while not stop.is_set():
                at = time.perf_counter()
                own_rss = host.memory_info().rss
                broker_rss = broker.memory_info().rss
                parent = own_rss + broker_rss
                host_peak = max(host_peak, own_rss)
                broker_peak = max(broker_peak, broker_rss)
                resident = 0
                live = []
                for process in broker.children():
                    try:
                        live.append(process.pid)
                        resident += process.memory_info().rss
                    except psutil.NoSuchProcess:
                        live.pop()
                if live:
                    child_samples.append((at, live, resident))
                    ready.set()
                parent_peak = max(parent_peak, parent)
                family_peak = max(family_peak, parent + resident)
                children_peak = max(children_peak, resident)
                concurrency_peak = max(concurrency_peak, len(live))
                stop.wait(.02)

        def observe(run_mode, index, start, flush, end, pauses, row):
            nonlocal used
            ticks.append(dict(index=index, start=start, end=end, timed_pair_admissions=used,
                              whole_tick_ms=row['whole_tick_ms'], flush_ms=row['engine_flush_ms'],
                              projection_ms=row['projection_ms'], projection_cpu_ms=row['projection_cpu_ms'],
                              gc_ms=row['runtime_gc_ms']))
            used = 0

        original = actor_motion.crossing_pairs

        def admission(*args, **kwargs):
            nonlocal used
            used += int(kwargs.get('arrival_windows') is not None)
            return original(*args, **kwargs)

        exporter = steering_replay.AsyncReplayExporter()
        watcher = threading.Thread(target=monitor, daemon=True)
        with DiagnosticStateManager(ctx=multiprocessing.get_context('spawn')) as manager, patch.object(
                steering_replay, '_diagnostic_export_service', None):
            service_state = SharedState(manager.dict())
            if not steering_replay.configure_diagnostic_export(service_state):
                raise RuntimeError('Original diagnostic broker unavailable')
            broker = psutil.Process(manager._process.pid)
            watcher.start()
            try:
                if not exporter.submit(lambda: steering_replay.export_incident_isolated(output, window, journal)):
                    raise RuntimeError('Original exporter admission rejected')
                if not ready.wait(20.):
                    raise RuntimeError('No diagnostic child observed')
                replay_args = ['score', '--maximum-traffic', '--spread', '--out', str(output / 'replay.json')]
                with ExitStack() as scope:
                    scope.enter_context(patch.object(sys, 'argv', [sys.argv[0], *replay_args]))
                    scope.enter_context(patch.object(actor_motion, 'crossing_pairs', admission))
                    if bind_probe is None:
                        main(tick_probe=observe, modes=(mode,))
                    else:
                        profile_tick, profile_rows = scope.enter_context(bind_probe(bind_profile=True))

                        def observe_profile(*args):
                            observe(*args)
                            profile_tick(*args)

                        main(tick_probe=observe_profile, modes=(mode,))
                        write_json(output / 'bind-profile.json', profile_rows)
                status = exporter.wait(65.)
            finally:
                stop.set()
                watcher.join(2.)
        exporter_pid = child_samples[0][1][0]
        exporter_times = [at for at, active_pids, _ in child_samples if exporter_pid in active_pids]
        first_child, last_child = exporter_times[0], exporter_times[-1]
        active = [tick for tick in ticks if first_child <= tick['start'] and tick['end'] <= last_child]
        if not active or not sum(row['timed_pair_admissions'] for row in active):
            raise RuntimeError('No complete optimized ticks during the observed child lifetime')
        export_returned = not status['busy'] and not status['error'] and bool(status['path'])
        if export_returned:
            manifests[mode] = status['path']
        whole = stats(row['whole_tick_ms'] for row in active)
        flush = stats(row['flush_ms'] for row in active)
        parent_upper = host_peak + broker_peak
        family_upper = parent_upper + children_peak
        results[mode] = dict(ticks=ticks, child_samples=child_samples, child_active_count=len(active),
            optimized_child_active_count=sum(row['timed_pair_admissions'] > 0 for row in active),
            child_active_whole_tick=whole, child_active_engine_flush=flush,
            parent_peak_rss=parent_peak, child_peak_rss=children_peak, family_peak_rss=family_peak,
            parent_peak_upper_rss=parent_upper, family_peak_upper_rss=family_upper,
            max_children=concurrency_peak, exporter_pid=exporter_pid, exporter_status=status,
            verified_dossier=None,
            rss_scope='replay host plus existing diagnostic broker and admitted child',
            gates=dict(whole_p99=whole['p99'] < 50., whole_max=whole['max'] < 100.,
                       flush_p99=flush['p99'] <= 16.67, flush_max=flush['max'] < 50.,
                       parent=parent_upper <= limits['parent_additional_rss_bytes'],
                       child=children_peak <= limits['export_child_rss_bytes'],
                       family=family_upper <= limits['additional_family_rss_bytes'], concurrent=concurrency_peak == 1,
                       export_complete=False))
    # Readback materializes the dossier. Keep this verifier outside both
    # measured process-family RSS windows, as in the original qualification.
    for mode, result in results.items():
        if mode in manifests:
            manifest = manifests[mode]
            verified = steering_replay.inspect_incident(manifest)
            complete = verified['integrity_valid'] and not verified['incomplete'] and verified['assembly_complete']
            result['gates']['export_complete'] = bool(complete)
            result['verified_dossier'] = Path(manifest).name if complete else None
            result['export_readback_reason'] = verified.get('reason')
            del verified
        actual, = load(directory / f'mode-{mode}' / 'replay.json')
        expected = baseline[mode]
        actual_control = control_bytes(actual)
        if actual_control != control_bytes(expected):
            raise AssertionError(f'Mode {mode}: overlapping replay changed during export')
        result['exact_control_match'] = True
        result['control_sha256'] = hashlib.sha256(actual_control).hexdigest()
    write_json(directory / 'overlap-export.json', results)
    return not all(all(run['gates'].values()) for run in results.values())
