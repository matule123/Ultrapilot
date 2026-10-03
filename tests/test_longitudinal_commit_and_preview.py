"""Late physical commit and distance-based curve planning regressions."""
import math
import struct

import pytest

from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_rolling_longitudinal_authority import rolling  # noqa: F401
from tests.test_longitudinal_arbitration import strict_flow
from tests.test_phase7_joint_validation import producers
from plugins.autopilot.main import planned_curve_speed_limit_ms


@pytest.mark.parametrize('mode', [0, 3])
@pytest.mark.parametrize('diagnostics', [False, True])
def test_engine_selects_current_pedals_after_slow_navigation_validation(flow, mode, diagnostics):
    from tests.test_longitudinal_evidence_diagnostics import memory_controller, attach
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow, mode=mode)
    policy, eco = producers(state)
    engine.controller = memory_controller()
    update(8, 4.)
    n()
    policy.on_tick(.033)
    acc.on_tick(.033)
    ap.on_tick(.033)
    engine._flush_controls()
    assert state.get('autopilot_active')
    captures = attach(engine) if diagnostics else None
    clock[0] += .2
    original = engine._gps_output_packet_rejection_reason
    fired = []

    def slow_validation(now, snapshot):
        if not fired:
            fired.append(True)
            # Producers continue while the Engine read is delayed. A NEW
            # coherent SDK frame and decisions are available before commit.
            for _ in range(3):
                update(8, 4., dt=.123)
                policy.on_tick(.123)
                acc.on_tick(.123)
                ap.on_tick(.123)
        return original(now, snapshot)

    engine._gps_output_packet_rejection_reason = slow_validation
    engine._flush_controls()
    assert state.get('autopilot_control_state') != 'controlled_stop', state.get('automatic_safety_stop_reason')
    assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    def physical(channel):
        return struct.unpack_from('f', engine.controller.scs._buf.getvalue(),
                                  engine.controller.scs._offsets[channel])[0]
    assert physical('aforward') > 0 and physical('abackward') == 0
    applied = state.get('longitudinal_applied')
    assert applied['source_sdk_frame_us'] == state.get('longitudinal_command')['sdk_frame_us']
    assert applied['source_observation_timestamp'] == state.get('longitudinal_command')['observation_timestamp']
    if captures:
        events = captures.samples[-1].longitudinal['events']
        event = next(e for e in reversed(events) if e['channel'] == 'throttle')
        assert event['source'].get('sdk_frame_us') == applied['sdk_frame_us'], event['source']
        assert event['source']['selected']['sdk_frame_us'] == applied['source_sdk_frame_us']
        assert event['backend']['status'] == 'MAPPING_WRITE_RETURNED'


def test_curve_target_uses_same_existing_envelope_in_policy_and_acc(flow):
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow)
    policy, eco = producers(state)
    update(8, 50. / 3.6)
    n()
    packet = state.get('nav_steering_debug')
    lane = state.get('lane_trajectory')
    packet.update(trajectory_identity={k: lane[k] for k in (
        'navigation_intent_id', 'revision', 'route_build_id',
        'source_game_session_id', 'source_map_key', 'source_dataset_fingerprint')},
        longitudinal_curve_profile={'radius_m': 19., 'distance_m': 80.})
    state.set('nav_steering_debug', packet)
    policy.on_tick(.033)
    acc.on_tick(.033)
    expected, _ = planned_curve_speed_limit_ms(19., 80., 50. / 3.6)
    assert state.get('longitudinal_policy')['planned_speed_ms'] <= expected
    assert state.get('longitudinal_acc')['constrained_speed_kmh'] <= expected * 3.6


def test_map_preview_covers_existing_braking_distance(rolling):
    state, engine, ap, acc, policy, tick, observe, n, physical, writes, clock = rolling
    state.set('acc_target_speed', 50.)
    tick(speed=50. / 3.6)
    profile = state.get('nav_steering_debug')['longitudinal_curve_profile']
    # Existing 1 m/s2 envelope, 20 m setup and 1 s response. A horizon
    # shorter than this cannot present R19 in time even on a complete path.
    required = ((50. / 3.6)**2 - 1.8 * 19.) / 2. + 20. + 50. / 3.6
    assert profile['horizon_m'] >= required


@pytest.mark.parametrize('fault', ['stale', 'reverse', 'backwards', 'identity', 'manual'])
def test_post_preparation_snapshot_is_rechecked_before_pedal_write(rolling, fault):
    state, engine, ap, acc, policy, tick, observe, n, physical, writes, clock = rolling
    before = len(writes)
    original = engine._gps_output_packet_rejection_reason
    fired = []
    def during_validation(now, snapshot):
        if not fired:
            fired.append(True)
            if fault == 'stale':
                clock[0] += .501
            elif fault == 'identity':
                state.set('active_dataset_fingerprint', 'other-dataset')
            elif fault == 'manual':
                n()
            else:
                tick(gear=-1 if fault == 'reverse' else 4,
                     speed=-.2 if fault == 'backwards' else .3, pedals=False)
        return original(now, snapshot)
    engine._gps_output_packet_rejection_reason = during_validation
    engine._flush_controls()
    assert physical('aforward') == 0
    assert not any(channel == 'aforward' and value > 0 for _, channel, value in writes[before:])


def test_real_lock_wait_precedes_snapshot_selection(rolling):
    import threading
    state, engine, ap, acc, policy, tick, observe, n, physical, writes, clock = rolling
    engine._controller_io_lock = threading.RLock()
    started = threading.Event()
    finished = threading.Event()
    def flush():
        started.set()
        try:
            engine._flush_controls()
        finally:
            finished.set()
    with engine._controller_io_lock:
        thread = threading.Thread(target=flush)
        thread.start()
        assert started.wait(1.)
        # A waiting writer must select the new frame after it obtains the lock.
        for _ in range(6):
            clock[0] += .1
            tick()
        assert not finished.is_set()
    thread.join(2.)
    assert finished.is_set()
    assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    assert physical('aforward') > 0


def test_preview_is_clipped_to_real_remaining_geometry_and_bounded():
    from core.longitudinal import curve_preview_horizon_m
    from core.navigation.route import Route
    query = curve_preview_horizon_m(50./3.6, 50.)
    route = Route([(0., 0.), (0., 30.)])
    assert route.curve_profile_ahead((0., 0.), math.pi, query)['horizon_m'] == 30.
    assert curve_preview_horizon_m(44., 160.) <= 400.
    assert curve_preview_horizon_m(6., 50.) >= curve_preview_horizon_m(50./3.6, 50.)


@pytest.mark.parametrize('fault', ['lease', 'identity'])
def test_final_write_check_still_rejects_change_after_arbitration(rolling, fault):
    state, engine, ap, acc, policy, tick, observe, n, physical, writes, clock = rolling
    original = engine.controller.set_steering
    def late_change(value):
        original(value)
        if fault == 'lease':
            clock[0] += .501
        else:
            state.set('autopilot_failure_epoch', 'next-activation')
    engine.controller.set_steering = late_change
    engine._flush_controls()
    assert physical('aforward') == 0
    assert state.get('autopilot_control_state') == 'controlled_stop'
    reason = state.get('automatic_safety_stop_reason')
    assert ('expired' if fault == 'lease' else 'identity') in reason


@pytest.mark.parametrize('direction', [-1, 1])
def test_closed_curve_approach_preserves_entry_limit_with_earlier_gentler_braking(direction):
    from tools.run_curve_approach_bench import run
    before = run(baseline=True, direction=direction)
    after = run(direction=direction)
    assert after['brake_start_distance_to_entry_m'] > before['brake_start_distance_to_entry_m']
    assert after['entry_speed_kmh'] <= before['entry_speed_kmh']
    assert after['entry_overspeed_kmh'] == 0
    assert after['maximum_deceleration_mps2'] < before['maximum_deceleration_mps2']
    assert after['maximum_abs_model_jerk_mps3'] < before['maximum_abs_model_jerk_mps3']
    assert after['simultaneous_positive_pedals'] == 0
