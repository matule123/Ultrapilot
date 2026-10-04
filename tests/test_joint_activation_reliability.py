"""Real producers and mapping writes; gearbox effect remains a declared model."""
from unittest import mock

import pytest

from core.longitudinal import context, rejection
from sdk.plugin_sdk import PluginSDK
from plugins.drivepolicy.main import Plugin as DrivePolicy
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_oct4_signal_lifecycle import lifecycle
from tests.test_roundabout_intervention_reporting import pedal
from tests.test_steering_fresh_handoff import prepared_map


@pytest.mark.parametrize('mode', [0, 3])
def test_driver_held_request_at_red_waits_then_launches_without_another_n(flow, mode):
    state, truck, engine, ap, tick, n, clock, writes, _ = lifecycle(
        flow, mode, start=False, initial_color=2)
    n()
    request = engine._drive_engagement['request_id']
    for _ in range(65):  # Red duration exceeds the LAUNCH deadline, not SDK freshness.
        tick(0, 0., color=2)
        assert engine._drive_engagement is not None, state.get('autopilot_disable_reason')
        assert state.get('auto_drive_pending')
        # Pending is deliberately NOT autonomous stationary holding. The
        # interface cannot safely create a new brake edge in simple automatic.
        assert not state.get('autopilot_active')
        assert state.get('simple_auto_service_hold') is None
        assert state.get('autopilot_control_state') == 'activation_wait'
        assert pedal(engine, 'aforward') == pedal(engine, 'abackward') == 0
    assert 'vodič' in state.get('navigation_status').lower()
    assert not engine.controller.current_hazard
    assert all(value == 0 for _, channel, value, _ in writes if channel in ('aforward', 'abackward'))
    for _ in range(5):
        tick(0, 0., color=8)
    assert engine._drive_engagement['request_id'] == request
    assert pedal(engine, 'aforward') == pytest.approx(.12 if mode == 0 else 0.)
    for speed in (.001, .2, .3, .5):
        tick(4, speed)
    assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    assert pedal(engine, 'aforward') > 0
    # Subsequent planned stop/restart keeps the SAME activation and actual chain.
    tick(4, .3, color=2)
    for speed in (.1, .01, 0., 0.):
        tick(0 if mode == 0 else 4, speed, color=2)
        assert state.get('autopilot_active')
        assert pedal(engine, 'abackward') > 0 and pedal(engine, 'aforward') == 0
    for _ in range(5):
        tick(0 if mode == 0 else 4, 0., color=8)
    for speed in (.001, .2, .3):
        tick(4, speed)
    assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    assert not any(channel == 'parkingbrake' for _, channel, _, _ in writes)


def test_stationary_request_cannot_reuse_a_previous_positive_brake_receipt(flow):
    state, truck, engine, ap, tick, n, clock, writes, _ = lifecycle(
        flow, start=False, initial_color=2)
    # A previously written brake does not establish a current activation's
    # forward-started hold. N must never manufacture that missing witness.
    engine.controller.set_brake(.4)
    writes.clear()
    n()
    tick(0, 0., color=2)
    assert not state.get('autopilot_active')
    assert state.get('simple_auto_service_hold') is None
    assert 'vodič' in state.get('navigation_status').lower()
    assert all(v == 0 for _, ch, v, _ in writes if ch == 'abackward')


def test_current_red_sidecar_blocks_probe_even_before_traffic_publication(flow):
    state, truck, engine, ap, tick, n, clock, writes, _ = lifecycle(flow, start=False)
    # Traffic slot still contains previous green. Producer independently acquired red.
    from tests.test_signal_stop_resume import source_bytes
    n()
    tick(0, 0., flush=False)
    engine._signal_reader.buffer = source_bytes(clock[0], 100, truck['sdkFrameTimeUs'], color=2)
    engine._flush_controls()
    assert pedal(engine, 'aforward') == 0
    assert state.get('autopilot_control_state') == 'activation_wait'


@pytest.mark.parametrize('delay', [.369, .4439514])
def test_road_lease_uses_actual_post_preparation_pose_not_initial_frame(delay):
    plugin, sdk, point, old = prepared_map()
    now = [old['timestamp']]
    original = plugin._publish_road_type
    final = dict(old, sdk_frame_us=old['sdk_frame_us']+int(delay*1e6),
                 timestamp=now[0]+delay,
                 tractor_position=(point.x, point.y, point.z+.02))
    seen = []
    real_classify = plugin.road_net.road_type_at

    def classify(pos):
        seen.append(tuple(pos))
        return real_classify(pos)

    def slow(pos):
        original(pos)
        now[0] += delay
        sdk.set('vehicle_envelope_snapshot', final)

    with mock.patch('time.monotonic', side_effect=lambda: now[0]), \
            mock.patch.object(plugin, '_publish_road_type', side_effect=slow), \
            mock.patch.object(plugin.road_net, 'road_type_at', side_effect=classify):
        plugin.on_tick(.02)
        value = sdk.get('longitudinal_road')
        assert value['sdk_frame_us'] == final['sdk_frame_us']
        assert value['observation_timestamp'] == final['timestamp']
        assert seen[-1] == (final['tractor_position'][0], final['tractor_position'][2])
        assert value['expires_at'] - now[0] == pytest.approx(.5)
        assert rejection(value, context(sdk.shared_state), now[0]+.072) == ''
        assert rejection(value, context(sdk.shared_state), now[0]+.501)


def test_planned_brake_during_confirmed_handoff_transfers_to_normal_stop(flow):
    state, truck, engine, ap, tick, n, clock, writes, _ = lifecycle(flow, start=False)
    n()
    tick(0, 0.)
    tick(4, .001)
    assert engine._drive_engagement['phase'] == 'handoff'
    tick(4, .2, color=2)
    assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    assert pedal(engine, 'abackward') > 0
    assert state.get('simple_auto_service_hold')
    for speed in (.02, 0., 0.):
        tick(0, speed, color=2)
        assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
        assert pedal(engine, 'abackward') > 0 and pedal(engine, 'aforward') == 0
    assert state.get('navigation_status').startswith('Čakám na zelenú')
    assert not engine.controller.current_hazard


@pytest.mark.parametrize('mode', [0, 3])
def test_stationary_forward_ratio_at_red_is_not_a_launch_permission(flow, mode):
    state, truck, engine, ap, tick, n, clock, writes, _ = lifecycle(
        flow, mode, start=False, initial_color=2)
    tick(4, 0., color=2)
    n()
    for _ in range(4):
        tick(4, 0., color=2)
        assert state.get('autopilot_control_state') == 'activation_wait'
        assert pedal(engine, 'aforward') == pedal(engine, 'abackward') == 0
    for _ in range(6):
        tick(4, 0., color=8)
    for speed in (.2, .3, .5):
        tick(4, speed)
    assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    assert pedal(engine, 'aforward') > 0


@pytest.mark.parametrize('fault', ['manual', 'R', 'rolling', 'stale', 'identity', 'backend'])
def test_waiting_activation_cancels_fault_and_never_restores_drive(flow, fault):
    state, truck, engine, ap, tick, n, clock, writes, _ = lifecycle(flow, start=False, initial_color=2)
    n(); tick(0, 0., color=2)
    if fault == 'manual':
        n()
    elif fault == 'R':
        tick(-1, 0., color=2, flush=False)
    elif fault == 'rolling':
        tick(0, .06, color=2, flush=False)
    elif fault == 'stale':
        clock[0] += .501
    elif fault == 'identity':
        state.set('navigation_intent_id', 'other')
    else:
        engine.controller.scs.connected = False
    engine._flush_controls()
    assert engine._drive_engagement is None
    assert not state.get('autopilot_active')
    if fault != 'backend':
        assert pedal(engine, 'aforward') == pedal(engine, 'abackward') == 0
    assert not any(v > 0 for _, ch, v, _ in writes if ch == 'aforward')


def test_late_red_sidecar_prevents_clearance_from_older_green_traffic_slot(flow):
    state, truck, engine, ap, tick, n, clock, writes, _ = lifecycle(flow, start=False, initial_color=2)
    from tests.test_signal_stop_resume import source_bytes
    n(); tick(0, 0., color=2)
    tick(0, 0., color=8)
    tick(0, 0., color=8, dt=.12, flush=False)
    engine._signal_reader.buffer = source_bytes(clock[0], 100, truck['sdkFrameTimeUs'], color=2)
    engine._flush_controls()
    assert engine._drive_engagement['phase'] == 'activation_wait'
    assert pedal(engine, 'aforward') == pedal(engine, 'abackward') == 0


@pytest.mark.parametrize('delay,vehicle_gap,ap_delay,write_delay', [
    (.3545584, .089393, .0392865, .017744),
    (.0530612, .3902978, .0548445, .0172396)])
def test_preparation_lease_through_real_map_policy_acc_ap_engine_backend(
        flow, delay, vehicle_gap, ap_delay, write_delay):
    # Recorded lease budgets: fresh SDK age 57/72 ms but old road input
    # expiry crossed by .982/15.443 ms. Actual production operations are used.
    state, truck, engine, ap, update, n, clock = flow
    from tests.test_longitudinal_arbitration import strict_flow
    from tests.test_longitudinal_evidence_diagnostics import attach
    from core.longitudinal import publish
    _, _, _, _, _, _, _, acc = strict_flow(flow)
    policy = DrivePolicy(PluginSDK(state.values, 'drivepolicy')); policy.on_start()
    attach(engine)
    mp, sdk, point, observation = prepared_map()
    snapshot = dict(sdk.get('lane_trajectory'))
    expected = state.get('lane_trajectory')
    for key in ('source_game_session_id', 'source_map_key', 'source_dataset_fingerprint'):
        snapshot[key] = expected[key]
    snapshot.update(navigation_intent_id='intent', request_id='intent')
    mp._lane_authority_identity = tuple(snapshot[key] for key in (
        'navigation_intent_id', 'request_id', 'route_build_id',
        'source_game_session_id', 'source_map_key', 'source_dataset_fingerprint'))
    state.update_batch(dict(lane_trajectory=snapshot, lane_trajectory_revision=snapshot['revision'],
        game_route_node_uids=list(snapshot['source_gps_uids']), lane_match=sdk.get('lane_match')))
    sdk.shared_state = state
    truck.update(x=point.x, y=point.y, z=point.z, rotation=point.heading,
                 referenceGeometry=observation['tractor_reference_geometry'])

    def observe(dt=.03):
        before = state.get('nav_steering_debug')
        heartbeat = state.get('lane_trajectory_heartbeat')
        update(8, 4., dt=dt)
        state.set('nav_steering_debug', before)
        state.set('lane_trajectory_heartbeat', heartbeat)

    def pedals():
        publish(state, state.get('telemetry')['truck'], 'traffic', traffic_brake=0., light_brake=0.)
        policy.on_tick(.03); acc.on_tick(.03); ap.on_tick(.03)

    try:
        observe(); mp.on_tick(.03); pedals(); n()
        observe(); mp.on_tick(.03); pedals(); engine._flush_controls()
        assert state.get('autopilot_active')
        original = mp._publish_road_type

        def delayed(pos):
            original(pos)
            observe(delay)  # A new actual SDK snapshot, not a timestamp update.

        observe()
        with mock.patch.object(mp, '_publish_road_type', side_effect=delayed):
            mp.on_tick(.03)
        refreshed = state.get('telemetry')['truck']['_control_observation']['observed_at']
        # The Autopilot's newer drivetrain observation is NOT evidence that
        # the older Map constraint acquired a new source observation.
        observe(vehicle_gap)
        vehicle_observed = state.get('telemetry')['truck']['_control_observation']['observed_at']
        clock[0] += ap_delay
        pedals()
        stages = [state.get('longitudinal_'+s) for s in ('road', 'policy', 'acc')]
        stages.append(state.get('longitudinal_command'))
        clock[0] += write_delay
        engine._flush_controls()
        assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
        assert pedal(engine, 'aforward') > 0 and pedal(engine, 'abackward') == 0
        for value in stages:
            assert value['expires_at'] == pytest.approx(refreshed+.5, abs=1e-9)
            assert rejection(value, context(state), clock[0]) == ''
        clock[0] = vehicle_observed+.501
        engine._flush_controls()
        assert pedal(engine, 'aforward') == 0  # Never renew a lease by rereading.
    finally:
        mp._maneuver_evidence_worker.close(); mp._maneuver_reference_mux.close()
