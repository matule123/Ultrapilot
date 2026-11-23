"""Oct 5 counterexamples; actual plugin arbitration and SCS float writes."""
import math

import pytest

from core.longitudinal import publish, curve_constraint_speed, context, engine_decision
from core.navigation.route import Route
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_longitudinal_arbitration import strict_flow
from tests.test_longitudinal_evidence_diagnostics import memory_controller
from tests.test_signal_stop_resume import signal_stop, signal_tick, pedal, source_bytes
from tests.test_acc_following import capture, car_on, route_input
from core.navigation.traffic_producer import TrafficCapture
from plugins.drivepolicy.main import Plugin as Policy
from sdk.plugin_sdk import PluginSDK


@pytest.mark.parametrize('mode', [0, 3])
def test_unconstraining_candidate_is_not_an_acquired_following_target(flow, mode):
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow, mode=mode)
    engine.controller = memory_controller()
    state.set('acc_target_speed', 50.)
    update(8, 10.)
    n()
    current = state.get('telemetry')['truck']
    points = [[0., 0., -float(i)] for i in range(121)]
    binding = route_input(state, engine, current, points)
    raw = capture([car_on(points, 100, speed=15.)], clock[0])
    raw = TrafficCapture(str(binding[1]), raw.observed_at, raw.moving, raw.parked, raw.stable)
    following = engine._route_lead_observation(raw, current, binding)
    assert following['speed_cap_mps'] == pytest.approx(49.)
    policy = Policy(PluginSDK(state.values, 'drivepolicy')); policy.on_start()
    publish(state, state.get('telemetry')['truck'], 'traffic', traffic_brake=0.,
            light_brake=0., light=None, following=following)
    policy.on_tick(.033)
    acc.on_tick(.033); ap.on_tick(.033); engine._flush_controls()
    assert not state.get('longitudinal_acc')['following_required']
    for _ in range(5):
        update(8, 10.)
        current = state.get('telemetry')['truck']; current['y'] = 0.
        state.set('telemetry', {'truck': current})
        debug = state.get('nav_steering_debug')
        debug['trajectory_identity'] = state.get('lane_trajectory_identity')
        state.set('nav_steering_debug', debug)
        raw = capture([], clock[0])
        raw = TrafficCapture(str(binding[1]), raw.observed_at, raw.moving, raw.parked, raw.stable)
        following = engine._route_lead_observation(raw, current, binding)
        assert following['status'] == 'no_candidate_unproven_coverage'
        publish(state, current, 'traffic', traffic_brake=0., light_brake=0., light=None,
                following=following)
        policy.on_tick(.033)
        acc.on_tick(.033); ap.on_tick(.033); engine._flush_controls()
        assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
        assert pedal(engine, 'aforward') > 0 and pedal(engine, 'abackward') == 0


def test_passive_or_previous_activation_does_not_acquire_a_target(flow):
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow)
    update(8, 10.)
    candidate = dict(status='candidate', target_id='7', gap_m=30., speed_mps=8.,
                     speed_cap_mps=8., confirmed=False)
    publish(state, state.get('telemetry')['truck'], 'traffic', traffic_brake=0.,
            light_brake=0., light=None, following=candidate)
    acc.on_tick(.033)
    assert not acc._followed_target
    n()
    publish(state, state.get('telemetry')['truck'], 'traffic', traffic_brake=0.,
            light_brake=0., light=None, following=candidate)
    acc.on_tick(.033)
    assert acc._followed_target
    n(); acc.on_tick(update(8, 10.))
    assert not acc._followed_target and acc._following_target_id is None
    n()
    publish(state, state.get('telemetry')['truck'], 'traffic', traffic_brake=0.,
            light_brake=0., light=None,
            following=dict(status='no_candidate_unproven_coverage', confirmed=False))
    acc.on_tick(.033); ap.on_tick(.033); engine._flush_controls()
    assert state.get('autopilot_active'), state.get('autopilot_disable_reason')


def test_lost_protective_target_receipt_keeps_id_and_original_evidence(flow):
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow)
    update(8, 10.); n()
    publish(state, state.get('telemetry')['truck'], 'traffic', traffic_brake=0.,
            light_brake=0., light=None,
            following=dict(status='candidate', target_id='7', speed_cap_mps=8., confirmed=False))
    acc.on_tick(.033); ap.on_tick(.033); engine._flush_controls()
    assert acc._followed_target
    # Loss between plugin ticks, including malformed data, is still fail-closed.
    lost = publish(state, state.get('telemetry')['truck'], 'traffic',
                   traffic_brake=0., light_brake=0., light=None, following=[])
    details = {}
    output, reason = engine_decision(state, state.get('telemetry')['truck'], rejection_info=details)
    assert output is None and reason == 'ACC target unavailable or unconfirmed departure'
    assert details['following_target_id'] == '7'
    assert details['following_confirmed'] is False
    assert details['following_status'] is None
    assert details['observation_timestamp'] == state.get('longitudinal_traffic')['observation_timestamp']
    engine._flush_controls()
    assert engine.controller.throttle == 0.


@pytest.mark.parametrize('mode', [0, 3])
def test_locked_signal_survives_passed_head_without_replacing_it(flow, mode):
    values, writes = signal_stop(flow, mode)
    state, truck, engine, ap, update, n, clock, acc, collected = values
    # The source head is at z=-5; this is NOT a measured stop line. A locked
    # head behind the SDK reference must still be observed for clearance.
    truck['z'] = -15.
    signal = signal_tick(values, 6, color=8, gear=8 if mode == 3 else 0)
    assert signal['valid'], signal
    assert signal['candidate']['id'] == 19
    # Distance is to the derived stop target, not the observed head at -5 m:
    # entry 9 m - progress 15 m - front 6 m - stand-off 2 m.
    assert signal['candidate']['distance'] == pytest.approx(9. - 15. - 6. - 2.)
    assert signal['candidate']['distance_basis'] == 'sdk_reference_to_derived_stop_target'
    signal_tick(values, 7, color=8, gear=8 if mode == 3 else 0, dt=.12)
    signal_tick(values, 8, color=8, gear=8 if mode == 3 else 0)
    assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    # Retaining the actual head does not authorize launch after the vehicle
    # has already overrun the directed junction entry at 9 m.
    assert pedal(engine, 'aforward') == 0 and pedal(engine, 'abackward') > 0
    hold = state.get('simple_auto_service_hold')
    assert hold['entry_overrun'] is True
    assert hold['restart_blocker'] == 'directed junction entry passed before stop; driver takeover required'
    assert not any(channel == 'parkingbrake' for _, channel, _ in writes)


def test_retained_signal_cannot_authorize_from_beyond_backward_bound(flow):
    values, writes = signal_stop(flow)
    state, truck, engine, ap, update, n, clock, acc, collected = values
    # Retention is bounded from the authored entry at 9 m, not the head at 5 m.
    truck['z'] = -30.
    update(0, 0.)
    packet = state.get('nav_steering_debug'); packet['tracking_progress_m'] = 30.
    state.set('nav_steering_debug', packet)
    engine._signal_reader.buffer = source_bytes(clock[0], 6, truck['sdkFrameTimeUs'], color=8)
    signal = engine._signal_observation(state.get('telemetry')['truck'], context(state))
    assert not signal['valid'] and signal['candidate'] is None
    assert signal['reason'] == 'locked prefab entry passed outside bounded lookup'
    assert pedal(engine, 'aforward') == 0 and pedal(engine, 'abackward') > 0


def two_bends(direction=1, approach=25., between=90.):
    x = z = 0.
    heading = math.pi
    points = [(x, z)]
    for curvature, length in [(0., approach), (direction/40., 30.),
                              (0., between), (direction/15., 25.), (0., 50.)]:
        for _ in range(int(length)):
            heading -= curvature
            x -= math.sin(heading); z -= math.cos(heading)
            points.append((x, z))
    return points


@pytest.mark.parametrize('direction', [-1, 1])
def test_nearer_bend_not_hidden_by_sharper_distant_bend(direction):
    route = Route(two_bends(direction))
    profile = route.curve_profile_ahead((0., 0.), math.pi, 180., speed_ms=50./3.6)
    # The old maximum-curvature ranking chooses R15 at ~170 m and authorizes
    # 50 km/h through the near R40 bend. All existing distance laws must apply.
    assert profile['distance_m'] < 60.
    assert curve_constraint_speed(profile, 50./3.6)*3.6 < 40.


@pytest.mark.parametrize('direction', [-1, 1])
def test_two_bend_profile_reaches_first_entry_limit_through_physical_backend(direction):
    from tools.run_curve_approach_bench import run
    # Same 200 m approach / 70 m separation as the paired closed-loop bench.
    # These are simulated curve entries, not measured physical roundabouts.
    points = two_bends(direction, approach=200., between=70.)
    options = dict(direction=direction, load=1.4, jitter=True,
        baseline_ref='9350be7', custom_points=points, entry_points=(200., 300.), radius=40.)
    before = run(baseline=True, **options)
    after = run(**options)
    assert before['entry_samples']['200.0']['speed_kmh'] > 35.
    assert after['entry_samples']['200.0']['speed_kmh'] <= 35.
    assert after['first_35_distance_to_entry_m'] > 0.
    assert after['brake_start_distance_to_entry_m'] > before['brake_start_distance_to_entry_m']
    assert after['simultaneous_positive_pedals'] == 0
