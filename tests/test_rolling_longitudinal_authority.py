"""Rolling GPS windows are observations, not new pedal activations."""
import struct

import pytest

from core.navigation.navigation_intent import NavigationIntentTracker
from core.longitudinal import context, rejection
from core.ipc.shared_state import SharedState
from plugins.map.main import Plugin as Map
from sdk.plugin_sdk import PluginSDK
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_longitudinal_arbitration import strict_flow
from tests.test_phase7_joint_validation import producers
from tests.test_longitudinal_evidence_diagnostics import memory_controller
from tests.test_lane_route_builder import SyntheticMap


@pytest.fixture
def rolling(flow):
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow)
    tracker = NavigationIntentTracker()
    window = list(range(1, 9))
    world = (state.get('game_session_id'), state.get('active_map_key'),
             state.get('active_dataset_fingerprint'))

    def observe(uids, *, destination=True, route_context=None):
        decision = tracker.update(uids, destination_present=destination,
                                  context=world if route_context is None else route_context)
        state.update_batch({'game_route_node_uids': list(uids),
            'navigation_intent_id': decision.intent_id,
            'nav_recalc_request': decision.intent_id,
            'navigation_buffer_classification': decision.classification.value})
        return decision

    observe(window)
    synthetic = SyntheticMap()
    for uid in window:
        synthetic.node(uid, 0., (uid - 1) * 40., 10.)
    for a, b in zip(window, window[1:]):
        synthetic.road(a, b, 2)
    map_plugin = Map(PluginSDK(state.values, 'map'))
    map_plugin.on_start()
    map_plugin.road_net = synthetic.net
    map_plugin._net_attempted = True
    engine.controller = memory_controller()
    writes = []
    original = engine.controller.scs._write_float

    def write(channel, value):
        original(channel, value)
        if channel in ('aforward', 'abackward'):
            writes.append((clock[0], channel, value))
    engine.controller.scs._write_float = write
    policy, eco = producers(state)

    def tick(gear=4, speed=4., z=15., *, pedals=True):
        truck.update(x=2.25, y=10., z=z, rotation=3.141592653589793)
        dt = update(gear, speed)
        observation = state.get('telemetry')['truck']['_control_observation']
        state.update_batch({'truck_world_pos': (2.25, z), 'truck_altitude': 10.,
            'truck_heading': truck['rotation'], 'truck_speed_ms': speed,
            'vehicle_envelope_snapshot': {
                'timestamp': observation['observed_at'], 'sdk_frame_us': truck['sdkFrameTimeUs'],
                'tractor_position': (2.25, 10., z), 'tractor_heading': truck['rotation'],
                'tractor_speed_ms': speed, 'tractor_reference_geometry': dict(
                    valid=True, source='synthetic_4x2', wheelbase_m=3.8, reference_ahead_m=2.1)}})
        map_plugin.on_tick(dt)
        assert state.get('lane_trajectory')['valid'], state.get('navigation_failure_reason')
        assert state.get('nav_steering_debug')['authority_valid'], state.get('nav_steering_debug')
        if pedals:
            policy.on_tick(dt)
            acc.on_tick(dt)
            ap.on_tick(dt)
        return dt

    def physical(channel):
        return struct.unpack_from('f', engine.controller.scs._buf.getvalue(),
                                  engine.controller.scs._offsets[channel])[0]

    tick(0, 0.)
    n()
    for gear, speed in [(0, 0.), (4, 0.), (4, .2), (4, .4), (4, 4.)]:
        tick(gear, speed)
        engine._flush_controls()
    assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    assert engine._drive_engagement is None
    assert physical('aforward') > 0
    try:
        yield state, engine, ap, acc, policy, tick, observe, n, physical, writes, clock
    finally:
        map_plugin._maneuver_evidence_worker.close()
        map_plugin._maneuver_reference_mux.close()


def test_prefix_republication_between_pedal_ticks_preserves_the_same_activation(rolling):
    state, engine, ap, acc, policy, tick, observe, n, physical, writes, clock = rolling
    activation = state.get('autopilot_failure_epoch')
    original_context = context(state)
    original_packet = state.get('longitudinal_command')
    original_geometry = state.get('lane_trajectory')['points']
    original_lane = state.get('lane_match')['active_lane_id']
    z = 15.
    for offset in (1, 2, 3):
        target = 15. + offset * 40.
        while z < target - .5:
            z += .5
            tick(speed=15., z=z)
            engine._flush_controls()
            assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
        before_transport = state.get('lane_trajectory_publication_token')
        previous_command = state.get('longitudinal_command')
        assert observe(list(range(1 + offset, 9))).classification.value == 'ADVANCED_PREFIX'
        # Map publishes the proven rebase before asynchronous pedal producers
        # get their next tick. Engine must not mistake transport for authority.
        z = target
        tick(speed=15., z=z, pedals=False)
        assert state.get('lane_trajectory_publication_token') != before_transport
        assert state.get('lane_trajectory')['points'] == original_geometry
        assert state.get('longitudinal_command') == previous_command
        engine._flush_controls()
        assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
        assert state.get('autopilot_control_state') != 'controlled_stop', (
            state.get('automatic_safety_stop_reason'))
        assert physical('aforward') > 0 and physical('abackward') == 0, (
            state.get('automatic_safety_stop_reason'))
        assert context(state) == original_context
        policy.on_tick(.033333)
        acc.on_tick(.033333)
        ap.on_tick(.033333)
        engine._flush_controls()
        assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    assert state.get('autopilot_failure_epoch') == activation
    assert original_packet['context'] == original_context
    assert original_packet['observation_timestamp'] < state.get('longitudinal_command')['observation_timestamp']
    assert observe(list(range(4, 9))).classification.value == 'SAME_EXACT'
    tick(speed=15., z=135.5)
    engine._flush_controls()
    assert state.get('autopilot_active')
    assert state.get('lane_match')['active_lane_id'] != original_lane
    # The recording contains actual float32 mapping writes, not only intents.
    assert writes and all(0. <= v <= 1. for _, _, v in writes)


@pytest.mark.parametrize('fault', ['reroute', 'session', 'dataset', 'removed',
                                 'geometry', 'stale', 'reverse', 'backwards'])
def test_true_authority_loss_cannot_reuse_the_previous_drive(rolling, fault):
    state, engine, ap, acc, policy, tick, observe, n, physical, writes, clock = rolling
    before = state.get('longitudinal_command')
    if fault == 'reroute':
        assert observe([1, 2, 99, 100]).classification.value == 'TRUE_REROUTE'
    elif fault in ('session', 'dataset'):
        key = 'game_session_id' if fault == 'session' else 'active_dataset_fingerprint'
        state.set(key, 'new')
        world = (state.get('game_session_id'), state.get('active_map_key'),
                 state.get('active_dataset_fingerprint'))
        assert observe(list(range(1, 9)), route_context=world).classification.value == 'SESSION_OR_DATASET_CHANGED'
    elif fault == 'removed':
        assert observe([], destination=False).classification.value == 'DESTINATION_REMOVED'
    elif fault == 'geometry':
        snapshot = state.get('lane_trajectory')
        # Different validated geometry identity even if a buggy publisher kept
        # the revision/build. Transport alone must not make the old drive valid.
        snapshot['lane_path_fingerprint'] = 'f' * 64
        SharedState(state.values).set('lane_trajectory', snapshot)
        assert rejection(before, context(state), clock[0]) == 'longitudinal identity or activation changed'
    elif fault == 'stale':
        clock[0] += .501
    else:
        tick(gear=-1 if fault == 'reverse' else 4,
             speed=-.2 if fault == 'backwards' else .3, pedals=False)
    engine._flush_controls()
    assert physical('aforward') == 0
    assert (not state.get('autopilot_active') or
            state.get('autopilot_control_state') == 'controlled_stop')
    first = state.get('automatic_safety_stop_reason') or state.get('autopilot_disable_reason')
    assert first
    engine._flush_controls()
    assert (state.get('automatic_safety_stop_reason') or state.get('autopilot_disable_reason')) == first
    assert before['context'] != context(state) or fault in ('stale', 'reverse', 'backwards')


def test_previous_activation_command_is_zero_until_a_current_command_exists(rolling):
    state, engine, ap, acc, policy, tick, observe, n, physical, writes, clock = rolling
    old = state.get('longitudinal_command')
    n()
    engine._flush_controls()
    assert physical('aforward') == physical('abackward') == physical('steering') == 0
    tick(pedals=False)
    n()
    state.set('longitudinal_command', old)
    engine._flush_controls()
    assert physical('aforward') == physical('abackward') == 0
    assert rejection(old, context(state), clock[0]) == 'longitudinal identity or activation changed'
    for _ in range(3):
        tick()
        engine._flush_controls()
        assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
        assert physical('aforward') > 0 and physical('abackward') == 0


@pytest.mark.parametrize('change', ['prefix', 'reroute'])
def test_publication_during_pedal_ipc_preserves_only_the_same_authority(rolling, change):
    state, engine, ap, acc, policy, tick, observe, n, physical, writes, clock = rolling
    if change == 'prefix':
        for step in range(1, 81):
            tick(speed=15., z=15. + step * .5)
            engine._flush_controls()
    def during_read(key):
        if key != 'longitudinal_command':
            return
        state.hook = None
        if change == 'prefix':
            # Exercise actual Map rebase with a now-passed first UID.
            observe(list(range(2, 9)))
            tick(speed=15., z=55.5, pedals=False)
        else:
            observe([1, 2, 99, 100])
    state.hook = during_read
    engine._flush_controls()
    assert state.hook is None
    if change == 'prefix':
        assert state.get('autopilot_control_state') != 'controlled_stop'
        assert physical('aforward') > 0
    else:
        assert physical('aforward') == 0


@pytest.mark.parametrize('writer_kind', [SharedState, PluginSDK])
def test_compact_geometry_binding_and_transport_invalidation_are_separate(writer_kind):
    raw = {}
    writer = writer_kind(raw)
    state = SharedState(raw)
    snapshot = dict(valid=True, revision=7, route_build_id='build',
                    lane_path_fingerprint='a' * 64, source_gps_uids=[1, 2, 3])
    writer.set('lane_trajectory', snapshot)
    authority = context(state)
    publication = state.get('lane_trajectory_publication_token')
    writer.set('lane_trajectory', dict(snapshot, source_gps_uids=[2, 3]))
    assert context(state) == authority
    assert state.get('lane_trajectory_publication_token') != publication
    assert state.get('lane_trajectory')['source_gps_uids'] == [2, 3]
    writer.set('lane_trajectory', dict(snapshot, lane_path_fingerprint='b' * 64))
    assert context(state) != authority
    writer.set('lane_trajectory', dict(snapshot, valid=False))
    assert context(state) != authority
    # Without a valid fingerprint, keep the old fail-closed publication rule.
    snapshot.pop('lane_path_fingerprint')
    writer.set('lane_trajectory', snapshot)
    unknown = context(state)
    writer.set('lane_trajectory', snapshot)
    assert context(state) != unknown
