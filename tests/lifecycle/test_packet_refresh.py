"""Oct 9: real prefab topology work and actual physical freshness boundaries."""
from unittest.mock import patch

import pytest

from core.navigation.road_network import RoadNetwork
from plugins.map.main import Plugin as Map
from sdk.plugin_sdk import PluginSDK
from tests.test_cached_control_output import production_flow
from tests.test_lane_authority_integration import Tags
from tests.signals.test_signal_coverage import actual_path
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_rolling_longitudinal_authority import rolling  # noqa: F401
from core.longitudinal import context, engine_decision, HANDOFF_WAIT_S


def test_map_does_not_deserialize_its_own_unchanged_geometry_each_tick(rolling):
    state, engine, ap, acc, policy, tick, observe, n, physical, writes, clock = rolling
    mapper = tick.publish_map.__self__
    tick()
    reader = mapper.sdk.shared_state._lane_snapshot_reader
    with patch.object(reader, 'read', wraps=reader.read) as decoded:
        for _ in range(6):
            tick(); engine._flush_controls()
            assert state.get('autopilot_active')
            packet = state.get('nav_steering_debug')
            phases = packet['map_reference_phase_times']
            assert (packet['map_road_type_finished_at'] <= phases['reference_read_started_at']
                <= phases['reference_read_finished_at'] <= phases['evidence_harvest_finished_at']
                <= phases['preparation_publish_finished_at'] <= phases['selection_finished_at']
                <= packet['map_calculation_started_at'])
            assert 1 <= len(phases['observation_attempts']) <= 2
            attempt = phases['observation_attempts'][-1]
            assert attempt['sdk_frame_us'] == packet['sdk_frame_us']
            assert attempt['observation_timestamp'] == packet['observation_timestamp']
            assert (attempt['started_at'] <= attempt['route_snapshot_read_finished_at']
                <= attempt['identity_checked_at'] <= attempt['sdk_snapshot_read_finished_at']
                <= attempt['final_validation_finished_at'])
        assert decoded.call_count == 0
    previous = state.get('lane_trajectory')
    from core.ipc.shared_state import SharedState
    SharedState(state.values).set('lane_trajectory',dict(previous,valid=False))
    assert mapper._read_control_lane_snapshot()['valid'] is False
    # Public readers still own independent copies; changing this one cannot
    # mutate the private control reference or the published geometry.
    external = mapper.sdk.get('lane_trajectory')
    external['points'][0][0] += 10.
    assert mapper._read_control_lane_snapshot()['points'] == previous['points']


def test_map_publication_race_does_not_cache_geometry_under_the_previous_token():
    from core.ipc.shared_state import SharedState
    from tests.test_lane_snapshot_transport import Transport
    transport = Transport()
    writer = SharedState(transport)
    mapper = Map(PluginSDK(transport, 'map'))
    writer.set('lane_trajectory', dict(valid=True, revision=7))
    def replace():
        transport.on_geometry_read = None
        writer.set('lane_trajectory', dict(valid=False, revision=8))
    transport.on_geometry_read = replace
    assert mapper._read_control_lane_snapshot() == dict(valid=False, revision=8)
    assert mapper._read_control_lane_snapshot() == dict(valid=False, revision=8)
    writer.set('lane_trajectory', dict(valid=True, revision=9))
    assert mapper._read_control_lane_snapshot() == dict(valid=True, revision=9)


def test_topology_cache_accounts_for_keys_and_bounds_empty_results():
    network = RoadNetwork()
    for index in range(400):
        key = ('synthetic_empty_topology', index, tuple(range(200)))
        assert network._store_prefab_topology(key, []) == []
    assert len(network._prefab_topology_cache) <= 128
    assert network._prefab_topology_cache_bytes <= 1048576
    assert network._prefab_topology_cache_bytes == sum(
        row[1] for row in network._prefab_topology_cache.values())
    assert network._prefab_topology_cache_indices == 0
    oversized = ('oversized', 'x' * 1048576)
    network._store_prefab_topology(oversized, [(1,)])
    assert network._cached_prefab_topology(oversized) is None


@pytest.mark.parametrize('changed', ['curve_identity', 'ports', 'nav_nodes'])
def test_cached_real_prefab_cannot_reuse_a_repaired_or_damaged_topology(tmp_path, changed):
    network = RoadNetwork()
    with patch('tests.signals.test_signal_coverage.RoadNetwork', return_value=network):
        path, _ = actual_path(tmp_path, 0)
    a, b = path.segments[0].start_uid, path.segments[0].end_uid
    instance = network._prefab_pairs[(min(a,b),max(a,b))][0]
    original = network._prefab_connector_options(instance,a,b)
    assert original
    returned = network._prefab_connector_options(instance,a,b)
    returned.clear()
    assert network._prefab_connector_options(instance,a,b) == original
    token = instance[0]
    lane = network._prefab_lane_data[token]
    if changed == 'curve_identity':
        for curve in lane['curves']: curve['nav_node_index'] = -1
    elif changed == 'ports':
        lane['nodes'][instance[1].index(a)]['input_lanes'] = (len(lane['curves'])+1,)
    else:
        desc = network._prefab_desc[token]
        network._prefab_desc[token] = (*desc[:2], (), *desc[3:])
    assert network._prefab_connector_options(instance,a,b) == []
    # An independently directed reverse query never shares the forward key.
    reversed_once = network._prefab_connector_options(instance,b,a)
    assert network._prefab_connector_options(instance,b,a) == reversed_once


def test_warm_immutable_prefab_topology_does_not_repeat_search_on_map_control_ticks(tmp_path):
    network = RoadNetwork()
    with patch('tests.signals.test_signal_coverage.RoadNetwork', return_value=network):
        path, _ = actual_path(tmp_path, 0)
    network.loaded = True
    uids = [path.segments[0].start_uid, path.segments[0].end_uid]
    with production_flow() as (state, truck, engine, ap, publish, n, clock):
        state.set('game_route_node_uids', uids)
        mapper = Map(PluginSDK(state.values, 'map'))
        mapper.on_start(); mapper.tags = Tags()
        mapper.road_net = network; mapper._net_attempted = True
        valid_chain = network._curve_chain_is_valid
        with patch.object(network, '_curve_chain_is_valid', wraps=valid_chain) as searched:
            try:
                p = path.points[2]
                truck.update(x=p.x,y=p.y,z=p.z,rotation=p.heading,
                    referenceGeometry=dict(valid=True, source='fixture', wheelbase_m=3.8, reference_ahead_m=2.1))
                publish(8,2.)
                mapper.on_tick(.033333)
                assert state.get('nav_active'), state.get('navigation_failure_reason')
                ap.on_tick(.033333); n()
                # Warm both representative and sibling queries actually used
                # by LaneLocator, then prohibit repeated DFS on unchanged PPD.
                instances = next(v for (a,b),v in network._prefab_pairs.items() if {a,b} == set(uids))
                for instance in instances:
                    network._prefab_connector_options(instance,*uids)
                    network._prefab_parallel_lane_options(instance,*uids)
                prepared = searched.call_count
                for index in range(3, 10):
                    p = path.points[index]
                    truck.update(x=p.x,y=p.y,z=p.z,rotation=p.heading)
                    publish(8,2.)
                    mapper.on_tick(.033333)
                    assert state.get('nav_active'), state.get('navigation_failure_reason')
                    ap.on_tick(.033333); engine._flush_controls()
                    assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
                    packet = state.get('nav_steering_debug')
                    assert packet['sdk_frame_us'] == truck['sdkFrameTimeUs']
                    assert packet['observation_timestamp'] == clock[0]
                assert searched.call_count == prepared
            finally:
                mapper._maneuver_evidence_worker.close(); mapper._maneuver_reference_mux.close()


def test_near_expiry_curve_refresh_survives_ipc_without_reusing_propulsion(rolling):
    state, engine, ap, acc, policy, tick, observe, n, physical, writes, clock = rolling
    tick(speed=4.)
    # Real Map curve calculated on an older, still-valid observation, with
    # fresh drivetrain telemetry and a new decision. Oct 9 remaining 3.9616ms.
    debug = state.get('nav_steering_debug')
    debug.update(observation_timestamp=clock[0]-.4960384,computed_at=clock[0]-.4763045)
    state.set('nav_steering_debug',debug)
    command = state.get('longitudinal_command')
    expiry = debug['observation_timestamp']+.5
    command.update(expires_at=expiry, handoff_required=True,
        deadline_basis=dict(source='curve',kind='spatial_observation',
            observation_timestamp=debug['observation_timestamp'],sdk_frame_us=debug['sdk_frame_us'],expires_at=expiry))
    state.set('longitudinal_command',command)
    original = state.get
    def delayed(key, default=None):
        value = original(key,default)
        # Publication/RPC takes the remaining 4ms AFTER returning a still-valid
        # immutable leaf. No producer timestamp/frame is changed.
        if key == 'nav_steering_debug':clock[0] += .0045
        return value
    with patch.object(state,'get',side_effect=delayed):
        selected, reason = engine_decision(state,state.get('telemetry')['truck'])
    assert not reason, reason
    assert selected['refresh_pending'] and selected['throttle'] == 0.
    request = state.get('longitudinal_refresh_request')
    assert request['rejected']['observation_timestamp'] == command['observation_timestamp']
    assert request['expires_at'] == pytest.approx(expiry+HANDOFF_WAIT_S)
    # Real Map advances before the independently scheduled pedal producers.
    # Engine executes the bounded zero-drive handoff, never the old throttle.
    tick(pedals=False)
    engine._flush_controls()
    assert state.get('autopilot_active'), state.get('automatic_safety_stop_reason')
    assert physical('aforward') == physical('abackward') == 0.
    assert state.get('longitudinal_applied')['refresh_pending']
    policy.on_tick(.02); acc.on_tick(.02); ap.on_tick(.02)
    engine._flush_controls()
    assert state.get('autopilot_active')
    assert physical('aforward') > 0 and physical('abackward') == 0


@pytest.mark.parametrize('fault', ['expired_start', 'wrong_frame', 'wrong_leaf', 'identity'])
def test_expiring_leaf_cannot_authorize_a_foreign_or_late_refresh(rolling, fault):
    from core.longitudinal import refresh_handoff
    state, engine, ap, acc, policy, tick, observe, n, physical, writes, clock = rolling
    debug = state.get('nav_steering_debug')
    debug.update(observation_timestamp=clock[0]-.496, computed_at=clock[0]-.476)
    state.set('nav_steering_debug', debug)
    command = state.get('longitudinal_command')
    expiry = debug['observation_timestamp']+.5
    command.update(expires_at=expiry, deadline_basis=dict(source='curve', kind='spatial_observation',
        observation_timestamp=debug['observation_timestamp'], sdk_frame_us=debug['sdk_frame_us'], expires_at=expiry))
    binding = context(state)
    if fault == 'expired_start': clock[0] += .005
    elif fault == 'wrong_frame': command['deadline_basis']['sdk_frame_us'] += 1
    elif fault == 'wrong_leaf': command['expires_at'] -= .001
    else: command['context'] = ('old_activation', *binding[1:])
    result = refresh_handoff(state, state.get('telemetry')['truck'], command,
        binding, 'longitudinal decision needs refresh')
    assert result is None
    assert state.get('longitudinal_refresh_request') is None


def test_busy_evidence_worker_does_not_fetch_discarded_inputs_after_publication(rolling):
    """Two delayed unused RPCs must not age the newly published control packet.

    This is a reproduced scheduling failure, not a recovered historical RPC
    duration. The actual one-job worker owns a pending Future throughout.
    """
    from concurrent.futures import Future
    state, engine, ap, acc, policy, tick, observe, n, physical, writes, clock = rolling
    mapper = tick.publish_map.__self__
    worker = mapper._maneuver_evidence_worker
    worker._future = Future()
    unused = []
    original = mapper.sdk.get
    def slow_discarded_input(key, default=None):
        result = original(key, default)
        if key in ('vehicle_profile_snapshot', 'maneuver_traffic_capture'):
            unused.append(key)
            clock[0] += .260
        return result
    try:
        with patch.object(mapper.sdk, 'get', side_effect=slow_discarded_input):
            tick()
            engine._flush_controls()
        assert state.get('autopilot_active'), state.get('automatic_safety_stop_reason')
        assert state.get('autopilot_control_state') != 'controlled_stop'
        assert unused == []
        assert physical('aforward') >= 0. and physical('abackward') == 0.
        assert not worker._future.done()
    finally:
        worker._future = None


def test_successful_episode_exports_reference_phases_without_automatic_disable(rolling, tmp_path):
    from core.steering_replay import inspect_replay
    state, engine, ap, acc, policy, tick, observe, n, physical, writes, clock = rolling
    for _ in range(12):
        tick(); engine._flush_controls()
        assert state.get('autopilot_active')
    with patch('plugins.autopilot.main.app_dir', return_value=str(tmp_path)):
        ap.on_stop()
    files = list((tmp_path/'route-diagnostics').glob('*.json'))
    assert files
    samples = []
    for path in files:
        exported = inspect_replay(path)
        assert exported['integrity_valid'], exported
        assert exported['replay']['reason'] == 'plugin_stop'
        samples.extend(exported['replay']['samples'])
    timed = [row for row in samples if row.get('map_reference_phase_times')]
    assert timed
    for row in timed:
        phase = row['map_reference_phase_times']['observation_attempts'][-1]
        assert phase['observation_timestamp'] == row['observation_timestamp']
        frame = row.get('calculation_sdk_frame_us', row.get('sdk_frame_us'))
        assert phase['sdk_frame_us'] == frame
        previous = row['previous_map_tick_timing']
        if previous is None:
            assert row['calculation_sequence'] == 1  # No completed tick at cold start.
            continue
        assert previous['started_at'] <= previous['finished_at'] <= row['map_tick_started_at']
        prior = previous['published_packet']
        assert prior['sequence'] < row['calculation_sequence']
        assert prior['sdk_frame_us'] < frame
        assert previous['after_publication_s'] >= 0.
    assert any(row.get('previous_map_tick_timing') for row in timed)


def test_combined_success_export_preserves_exact_completed_tick_of_written_target(rolling, tmp_path):
    from copy import deepcopy
    from dataclasses import replace
    from threading import Lock
    from core.navigation.evidence_diagnostics import (
        EvidenceDiagnosticCollector, inspect_collection, read_json)
    from tests.test_real_evidence_diagnostics import capture, command
    state, engine, ap, acc, policy, tick, observe, n, physical, writes, clock = rolling
    state.set('maneuver_evidence_diagnostic_active', True)
    collector=EvidenceDiagnosticCollector(tmp_path/'evidence-diagnostics',capacity=60,clock=lambda:clock[0])
    collector.apply_command(command(1,collection_id='successful-control-timing'))
    offered=[]
    class DirectOffer:
        def should_sample(self, _now): return True
        def offer(self, value):
            offered.append(value)
            source=value.applied_target['source_packet']
            assert source['map_reference_phase_times']
            assert source['previous_map_tick_timing']['finished_at'] <= source['map_tick_started_at']
            # Explicitly modeled body observation, not a measured game profile.
            profile=deepcopy(capture(0).profile)
            profile['observation'].update(sdk_frame_us=value.truck['sdkFrameTimeUs'],
                captured_at=value.truck['_control_observation']['observed_at'])
            collector._ingest(replace(value,profile=profile))
            return True
    engine._maneuver_diagnostic_collector=DirectOffer()
    engine._telemetry_lock=Lock()
    engine._latest_telemetry_success=True
    # Run the sole actual executor deterministically. The ordinary synchronous
    # fixture bypasses submit/observer and therefore has no source_packet; it
    # must not synthesize that binding from the latest Map header.
    # submit() and step() must share the fixture's simulated clock. The
    # executor's default clock was captured before time.monotonic was patched.
    ap._steering_executor._clock=lambda:clock[0]
    ap._steering_executor._running=True
    for i in range(40):
        tick()
        ap._steering_executor.step(.017,now=clock[0])
        engine._flush_controls()
        assert state.get('autopilot_control_state') != 'controlled_stop'
    collector.apply_command(command(2,'finish',collection_id='successful-control-timing'))
    checked=inspect_collection(tmp_path/'evidence-diagnostics'/'successful-control-timing')
    assert checked['integrity_valid'],checked
    assert checked['sample_count']==40
    assert checked['confirmed'] is checked['runtime_authorized'] is False
    assert len(offered)==40
    rows=read_json(tmp_path/'evidence-diagnostics'/'successful-control-timing'/
        'automatic-observations.json')['samples']
    assert len(rows)==40
    for row, original in zip(rows, offered):
        assert row['executor']['source_packet']==original.applied_target['source_packet']
        assert row['backend_sent'] and row['command_binding_proven']
        assert row['steering_boundary']['steering_write_returned_at_s'] is not None
