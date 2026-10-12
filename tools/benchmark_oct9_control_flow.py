"""Offline real-route control throughput, with real Manager IPC and SCS memory.

No game process, SDK mapping or installed file is modified. Recorded planar
poses drive a modeled advancing SDK producer; Y and reference geometry are
explicit model inputs. This measures software, not vehicle physics or the
historical cause of an unsampled scheduler/GC pause.
"""
import argparse
from contextlib import contextmanager
import gc
import hashlib
import json
import logging
import multiprocessing
from multiprocessing.managers import BaseProxy
from pathlib import Path
import sys
import time
import types
import threading
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.profile_oct9_map import window
from tools.analyze_oct9_packet_flow import distribution
from core.ipc.shared_state import SharedState
from core.navigation.road_network import RoadNetwork
from core.steering_replay import inspect_replay
from core.longitudinal import publish
from sdk.plugin_sdk import PluginSDK
from plugins.map.main import Plugin as Map
from tests.test_cached_control_output import production_flow
from tests.test_longitudinal_arbitration import strict_flow
from tests.test_longitudinal_evidence_diagnostics import memory_controller
from plugins.drivepolicy.main import Plugin as Policy
from tests.test_lane_authority_integration import Tags
from core.engine import UltraPilotEngine


class OperationProfile:
    """Benchmark-only inclusive spans; never installed as runtime telemetry.

    Thread CPU excludes other workers. RPC wall minus client CPU includes
    server work, serialization, scheduling and transport, not just wire time.
    Nested spans overlap and must not be summed into a whole-tick duration.
    """
    def __init__(self):
        self.active, self.rows = [], {}
        self.wall, self.cpu = time.perf_counter, time.thread_time
        self.owner = threading.get_ident()

    @contextmanager
    def span(self, name):
        row = dict(rpc_wall_s=0., rpc_client_cpu_s=0., rpc_calls=0)
        self.active.append(row)
        wall, cpu = self.wall(), self.cpu()
        try:
            yield
        finally:
            row.update(wall_s=self.wall()-wall, thread_cpu_s=self.cpu()-cpu)
            row['outside_rpc_wall_s'] = max(0., row['wall_s']-row['rpc_wall_s'])
            row['non_cpu_wall_s'] = max(0., row['wall_s']-row['thread_cpu_s'])
            self.rows.setdefault(name, []).append(row)
            self.active.pop()

    def wrap(self, name, operation):
        def run(*args, **kwargs):
            with self.span(name):
                return operation(*args, **kwargs)
        return run

    def rpc(self, original):
        def call(proxy, *args, **kwargs):
            if threading.get_ident() != self.owner or not self.active:
                return original(proxy, *args, **kwargs)
            wall, cpu = self.wall(), self.cpu()
            try:
                return original(proxy, *args, **kwargs)
            finally:
                duration, used = self.wall()-wall, self.cpu()-cpu
                for row in self.active:
                    row['rpc_wall_s'] += duration
                    row['rpc_client_cpu_s'] += used
                    row['rpc_calls'] += 1
        return call

    def summary(self):
        return {name:{**{key:distribution([row[key] for row in rows]) for key in rows[0]},
                      'totals':{key:sum(row[key] for row in rows) for key in rows[0]}}
                for name,rows in self.rows.items()}


def export_load_process(directory, source, go, ready, failures):
    """Actual bounded combined/chunk and replay writers, isolated modeled load.

    Fixtures are labeled diagnostic-only; they are NOT this route's driving
    measurements. A separate process models the runtime process boundary so
    replay writer GIL work cannot be mislabeled as Map's local CPU.
    """
    from core.navigation.evidence_diagnostics import EvidenceDiagnosticCollector, inspect_collection
    from core.steering_replay import SteeringReplayBuffer, AsyncReplayExporter
    from tests.test_real_evidence_diagnostics import capture, command
    try:
        collector = EvidenceDiagnosticCollector(directory/'evidence-diagnostics', capacity=300)
        collector.apply_command(command(1, collection_id='isolated-export-load'))
        for i in range(180): collector._ingest(capture(i))
        replay = SteeringReplayBuffer(300)
        for row in inspect_replay(source)['replay']['samples']: replay.append(row)
        ready.set()
        if not go.wait(60.): raise RuntimeError('Export start was not signaled')
        writer = AsyncReplayExporter()
        writer.submit(lambda: replay.export(directory/'route-diagnostics', reason='offline_load'))
        collector.apply_command(command(2, 'finish', collection_id='isolated-export-load'))
        checked = inspect_collection(directory/'evidence-diagnostics'/'isolated-export-load')
        assert checked['integrity_valid'], checked
        assert writer.wait(30.)['error'] is None
    except Exception as exc:
        failures.append(repr(exc)); ready.set()


def modeled_sdk_process(proxy, model, stop, ready, failures):
    """SDK acquisition is independent of Map's GIL/GC, as in the runtime."""
    state = SharedState(proxy)
    engine = UltraPilotEngine.__new__(UltraPilotEngine)
    truck, frame = model['truck'], model['truck']['sdkFrameTimeUs']
    try:
        while not stop.is_set():
            x, y, z, heading = model['pose']
            stamp = time.monotonic()
            frame += 16667
            observed = dict(truck, x=x, y=y, z=z, rotation=heading, gear=4,
                speed=4., sdkFrameTimeUs=frame, pose_valid=True,
                referenceGeometry=dict(valid=True, source='explicit_benchmark_model',
                    wheelbase_m=3.8, reference_ahead_m=2.1))
            payload = engine._vehicle_telemetry_payload(
                {'truck':observed, 'raw':{'sdkActive':True}}, stamp)
            mode = state.get('ets2_transmission_mode')
            mode['observed_at'] = stamp
            payload['ets2_transmission_mode'] = mode
            state.update_batch(payload)
            ready.set()
            stop.wait(1/60.)
    except Exception as exc:
        failures.append(repr(exc))
        stop.set()


def old_class(path, name, cls):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(path.read_text(encoding='utf-8'), str(path), 'exec'), module.__dict__)
    return getattr(module, cls)


def run(args):
    real_monotonic = time.monotonic
    checked = inspect_replay(args.replay)
    assert checked['integrity_valid'], checked
    rows = [r for r in checked['replay']['samples'] if r.get('packet_binding_valid')]
    assert rows and all(r['route_build_id'] == args.build for r in rows)
    network_class, map_class = RoadNetwork, Map
    if args.baseline_dir:
        network_class = old_class(args.baseline_dir/'road_network.py', 'oct9_baseline_network', 'RoadNetwork')
        map_class = old_class(args.baseline_dir/'main.py', 'oct9_baseline_map', 'Plugin')
    load_started, load_cpu = time.perf_counter(), time.thread_time()
    network = network_class()
    assert network._try_load_cache(str(args.dataset)), 'Read-only matching cache required'
    uids = window(network, args.log, args.build)
    network.loaded = True
    cold_load = dict(wall_s=time.perf_counter()-load_started, thread_cpu_s=time.thread_time()-load_cpu)
    operations = OperationProfile()
    gc_events, gc_started = [], {}
    def gc_observer(phase, info):
        if phase == 'start':
            gc_started[info['generation']] = (time.perf_counter(), threading.get_ident())
        else:
            started, owner = gc_started[info['generation']]
            completed = time.perf_counter()
            gc_events.append(dict(generation=info['generation'],started_at=started,
                completed_at=completed, thread_id=owner, duration_s=completed-started))
    ticks, packets, applied, faults, physical_steering, tick_spans = [], [], [], [], [], []
    with production_flow() as f, multiprocessing.Manager() as manager:
        original_state, truck, engine, ap, update, n, clock, acc = strict_flow(f)
        proxy = manager.dict(original_state.values)
        state = engine.shared_state = SharedState(proxy)
        ap.sdk = PluginSDK(proxy, 'autopilot')
        acc.sdk = PluginSDK(proxy, 'acc')
        policy = Policy(PluginSDK(proxy, 'drivepolicy'))
        policy.on_start()
        mapper = map_class(PluginSDK(proxy, 'map'))
        mapper.on_start(); mapper.tags = Tags()
        mapper.road_net = network; mapper._net_attempted = True
        if args.profile:
            for name in ('_update_lane_trajectory', '_refresh_steering_observation',
                         '_publish_road_constraint', '_schedule_map_exploration_save'):
                if hasattr(mapper,name):
                    setattr(mapper,name,operations.wrap('map.'+name, getattr(mapper,name)))
            for owner, name in ((getattr(mapper,'_maneuver_evidence_worker',None),'evidence'),
                                (getattr(mapper,'_maneuver_reference_mux',None),'reference')):
                for method in ('harvest','offer','preparation_payload','select'):
                    if owner is not None and hasattr(owner,method):
                        setattr(owner,method,operations.wrap('map.'+name+'.'+method,getattr(owner,method)))
        if args.busy_evidence_ms:
            evidence = mapper._maneuver_evidence_worker
            produce = evidence._produce
            def pending_work(*values, **kw):
                result = produce(*values, **kw)
                threading.Event().wait(args.busy_evidence_ms/1000.)
                return result
            evidence._produce = pending_work
        engine.controller = memory_controller()
        from core.navigation.longitudinal_diagnostics import PedalJournal
        engine.controller._pedal_journal = PedalJournal()
        engine.controller._pedal_journal.enabled = args.diagnostics
        write_source = [None]
        raw_write = engine.controller.scs._write_float
        def record_mapping(channel, value):
            started = real_monotonic()
            result = raw_write(channel, value)
            finished = real_monotonic()
            if channel == 'steering' and write_source[0]:
                source = write_source[0]
                physical_steering.append(dict(write_started_at=started, write_returned_at=finished,
                    value=value, sdk_frame_us=source['sdk_frame_us'],
                    calculation_sequence=source['calculation_sequence'],
                    observation_timestamp=source['observation_timestamp'], computed_at=source['computed_at'],
                    observation_age_s=started-source['observation_timestamp'],
                    calculation_to_write_s=started-source['computed_at']))
            return result
        engine.controller.scs._write_float = record_mapping
        state.update_batch(dict(game_route_node_uids=uids,
            game_route_active=True, game_has_destination=True, acc_target_speed=40.))
        poses = [(r['observation_xz'][0], network.altitude_near(r['observation_xz']),
                  r['observation_xz'][1], r['observation_heading_rad']) for r in rows]
        model = manager.dict(truck=truck, pose=poses[0])
        stop, ready, failures = multiprocessing.Event(), multiprocessing.Event(), manager.list()
        # The traffic buffers have the actual existing wire sizes. This is an
        # explicitly empty modeled observation, never qualified traffic.
        if args.busy_evidence_ms:
            from tests.test_real_evidence_diagnostics import capture
            modeled = capture(0)
            state.set('vehicle_profile_snapshot', modeled.profile)
            state.set('maneuver_traffic_capture', modeled.traffic_capture)
        export_worker = None
        export_go, export_ready = multiprocessing.Event(), multiprocessing.Event()
        with patch('time.monotonic', real_monotonic), \
             patch.object(BaseProxy,'_callmethod', operations.rpc(BaseProxy._callmethod)):
            worker = multiprocessing.Process(target=modeled_sdk_process,
                args=(proxy,model,stop,ready,failures),name='modeled-sdk',daemon=True)
            worker.start()
            try:
                assert ready.wait(2.), failures
                if args.export_load:
                    export_worker=multiprocessing.Process(target=export_load_process,
                        args=(args.output.parent/(args.output.stem+'-load'),args.replay,
                              export_go,export_ready,failures),name='isolated-exports',daemon=True)
                    export_worker.start()
                    assert export_ready.wait(15.), 'Isolated export load did not initialize'
                with operations.span('cold_map_tick'):
                    mapper.on_tick(.02)
                assert state.get('nav_active'), state.get('navigation_failure_reason')
                cold_packet = state.get('nav_steering_debug')
                cold_age = real_monotonic()-cold_packet['observation_timestamp']
                locator = getattr(network,'_runtime_lane_locator',None)
                if args.profile and locator is not None:
                    locator.locate = operations.wrap('map.localization',locator.locate)
                # Same warm-up for both variants; preserve/report the actual
                # cold packet age instead of re-labeling it as current.
                mapper.on_tick(.02)
                policy.on_tick(.02); acc.on_tick(.02); ap.on_tick(.02)
                n()
                assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
                gc.callbacks.append(gc_observer)
                previous_map_finished=None
                for i in range(args.ticks):
                    if export_worker is not None and i == 20: export_go.set()
                    model['pose'] = poses[i]
                    # Do not connect the last recorded pose back to the first;
                    # repeats are separate modeled runs with the same geometry.
                    started = time.perf_counter()
                    map_started=real_monotonic()
                    with operations.span('map_tick'): mapper.on_tick(.02)
                    map_finished = real_monotonic()
                    observed = state.get('telemetry')['truck']
                    publish(state, observed, 'traffic', traffic_brake=0., light_brake=0.)
                    with operations.span('policy_tick'): policy.on_tick(.02)
                    with operations.span('acc_tick'): acc.on_tick(.02)
                    with operations.span('autopilot_tick'): ap.on_tick(.02)
                    # Synchronous test mode: pin the actual accepted source
                    # before Engine; there is no concurrent Map/AP in this
                    # process and no replay header or later IPC substitution.
                    source = ap._accepted_navigation_command
                    write_source[0] = {k:source[k] for k in ('sdk_frame_us','calculation_sequence',
                        'observation_timestamp','computed_at')} if source else None
                    with operations.span('engine_write'): engine._flush_controls()
                    finished = time.perf_counter()
                    packet = state.get('nav_steering_debug')
                    packets.append({k: packet.get(k) for k in ('calculation_sequence',
                        'sdk_frame_us', 'observation_timestamp', 'computed_at', 'output',
                        'map_tick_started_at','map_lane_update_finished_at',
                        'map_reference_finished_at','map_calculation_started_at',
                        'map_packet_publish_started_at','map_reference_phase_times',
                        'previous_map_tick_timing')})
                    receipt_map=state.get('map_steering_publish_receipt') or {}
                    tick_spans.append(dict(started_at=map_started,
                        map_finished_at=map_finished, publication_completed_at=receipt_map.get('completed_at'),
                        gap_before_map_tick_s=(map_started-previous_map_finished if previous_map_finished else None),
                        map_after_publication_s=(map_finished-receipt_map['completed_at']
                            if receipt_map.get('completed_at') else None)))
                    previous_map_finished=map_finished
                    receipt = state.get('longitudinal_applied')
                    if receipt and receipt.get('write_started_at') is not None:
                        applied.append(dict(age_s=receipt['write_started_at']-
                            receipt['source_observation_timestamp'],
                            remaining_s=receipt['expires_at']-receipt['write_started_at']))
                    ticks.append(finished-started)
                    if not state.get('autopilot_active') or state.get('autopilot_control_state') == 'controlled_stop':
                        faults.append(dict(tick=i, reason=state.get('automatic_safety_stop_reason')
                            or state.get('autopilot_disable_reason')))
                        break
                    # Wait only unused time: no queue of overdue ticks.
                    stop.wait(max(0., .02-(time.perf_counter()-started)))
            finally:
                if gc_observer in gc.callbacks: gc.callbacks.remove(gc_observer)
                stop.set(); worker.join(timeout=2.)
                assert not worker.is_alive(), 'Modeled producer did not stop'
                if export_worker is not None:
                    export_go.set(); export_worker.join(timeout=30.)
                    assert not export_worker.is_alive(), 'Isolated export load did not finish'
                for name in ('_maneuver_evidence_worker','_maneuver_reference_mux'):
                    owner=getattr(mapper,name,None)
                    if owner is not None: owner.close()
            producer_failures = list(failures)
    unique = {p['calculation_sequence']:p for p in packets if p['calculation_sequence'] is not None}
    ordered = list(unique.values())
    intervals = [b['computed_at']-a['computed_at'] for a,b in zip(ordered,ordered[1:])]
    result = dict(source_replay=str(args.replay), replay_sha256=hashlib.sha256(args.replay.read_bytes()).hexdigest(),
        source_build=args.build, dataset=str(args.dataset), ticks=len(ticks), new_packets=len(ordered),
        baseline=bool(args.baseline_dir), diagnostics=args.diagnostics, real_manager_ipc=True,
        cold_dataset_load=cold_load, cold_steering_observation_age_s=cold_age,
        operation_profile=operations.summary(), tick_spans=tick_spans,
        concurrent_export_load=bool(args.export_load), modeled_evidence_job_ms=args.busy_evidence_ms,
        tick_duration_s=distribution(ticks), packet_interval_s=distribution(intervals),
        age_at_pedal_write_s=distribution([p['age_s'] for p in applied]),
        remaining_at_pedal_write_s=distribution([p['remaining_s'] for p in applied]),
        observation_over_500ms=sum(p['age_s']>.5 for p in applied), faults=faults,
        steering_observation_age_at_write_s=distribution([p['observation_age_s'] for p in physical_steering]),
        steering_calculation_to_write_s=distribution([p['calculation_to_write_s'] for p in physical_steering]),
        steering_writes_over_500ms=sum(p['observation_age_s']>.5 for p in physical_steering),
        physical_steering_writes=physical_steering,
        producer_failures=producer_failures, gc_events=gc_events, packets=packets,
        topology_cache_accounted_bytes=getattr(network,'_prefab_topology_cache_bytes',0),
        limitations='Modeled SDK on recorded planar poses; 4m/s, map-derived Y, explicit 3.8m wheelbase/2.1m reference. Serial real control producers with independent process for 60Hz modeled SDK; real Manager IPC. Export load, when enabled, uses real bounded writers on separate synthetic evidence in another process; its rows are not route measurements. Evidence delay is explicit modeled I/O, not historical duration. Inclusive operation spans overlap. RPC wall-client CPU includes server work/scheduling. Windows thread CPU has coarse accounting. No measured ETS2 physics or proof of the historical unsampled internal stall.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('packets','gc_events','physical_steering_writes','operation_profile','tick_spans')}, indent=2))


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',type=Path,required=True); p.add_argument('--log',type=Path,required=True)
    p.add_argument('--replay',type=Path,required=True); p.add_argument('--build',required=True)
    p.add_argument('--baseline-dir',type=Path); p.add_argument('--output',type=Path,required=True)
    p.add_argument('--ticks',type=int,default=240); p.add_argument('--diagnostics',action='store_true')
    p.add_argument('--profile',action='store_true'); p.add_argument('--export-load',action='store_true')
    p.add_argument('--busy-evidence-ms',type=float,default=0.)
    args=p.parse_args()
    if not args.output.resolve().is_relative_to(ROOT): p.error('Output must stay in workspace')
    if not 1 <= args.ticks <= 261: p.error('Use one contiguous retained section, 1..261 ticks')
    if not 0 <= args.busy_evidence_ms <= 200: p.error('Modeled evidence work must stay in 0..200 ms')
    logging.disable(logging.WARNING)
    run(args)
