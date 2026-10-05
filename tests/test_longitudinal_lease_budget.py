"""Dependency leases through real producers, Engine and mapped Controller writes."""
import pytest

from core.longitudinal import publish, context, rejection
from plugins.drivepolicy.main import Plugin as Policy
from sdk.plugin_sdk import PluginSDK
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_longitudinal_arbitration import strict_flow
from tests.test_longitudinal_evidence_diagnostics import memory_controller
from tests.test_roundabout_intervention_reporting import pedal
from plugins.map.main import Plugin as Map
from core.longitudinal import curve_input


def producers(flow):
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow)
    engine.controller = memory_controller()
    policy = Policy(PluginSDK(state.values, 'drivepolicy')); policy.on_start()
    state.set('acc_target_speed', 50.)
    update(8, 10.)
    policy.on_tick(.05); acc.on_tick(.05); ap.on_tick(.05)
    n()
    return state, truck, engine, ap, update, clock, acc, policy


@pytest.mark.parametrize('cap', [60., 35.])
def test_recorded_lease_budget_only_inherits_applicable_map_limit(flow, cap):
    state, truck, engine, ap, update, clock, acc, policy = producers(flow)
    old = publish(state, state.get('telemetry')['truck'], 'road', speed_cap_kmh=cap)
    update(8, 10., dt=.424918)
    publish(state, state.get('telemetry')['truck'], 'traffic', traffic_brake=0., light_brake=0.)
    clock[0] += .0462607
    policy.on_tick(.05); acc.on_tick(.05); ap.on_tick(.05)
    command = state.get('longitudinal_command')
    clock[0] += .0366207
    engine._flush_controls()
    assert clock[0] - old['expires_at'] == pytest.approx(.0077994)
    if cap == 60.:
        assert rejection(command, context(state), clock[0]) == ''
        assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
        assert pedal(engine, 'aforward') > 0 and pedal(engine, 'abackward') == 0
    else:
        # The consumed constraint retains its original deadline. A separate
        # bounded ZERO-drive refresh transition is not the expired drive packet.
        assert state.get('longitudinal_acc')['expires_at'] <= old['expires_at']
        assert command['throttle'] == 0.
        assert command['refresh_pending']
        assert command['expires_at'] <= old['expires_at'] + .1
        assert pedal(engine, 'aforward') == 0


def test_nonbinding_map_producer_cadence_for_more_than_one_minute(flow):
    state, truck, engine, ap, update, clock, acc, policy = producers(flow)
    start, last = clock[0], -1.
    for i in range(1300):
        update(8, 10., dt=.05)
        if clock[0] - last >= .52:
            publish(state, state.get('telemetry')['truck'], 'road', speed_cap_kmh=60.)
            last = clock[0]
        publish(state, state.get('telemetry')['truck'], 'traffic', traffic_brake=0., light_brake=0.)
        clock[0] += .03
        policy.on_tick(.05); acc.on_tick(.05); ap.on_tick(.05)
        clock[0] += .06  # Packet handoff / next executor tick, not a renewed timestamp.
        engine._flush_controls()
        assert state.get('autopilot_active'), (i, state.get('autopilot_disable_reason'))
        assert pedal(engine, 'aforward') > 0 and pedal(engine, 'abackward') == 0
    assert clock[0] - start > 60.
    clock[0] += .501
    engine._flush_controls()
    assert pedal(engine, 'aforward') == 0


def test_roundabout_semantics_limits_real_producers_before_entry(flow):
    state, truck, engine, ap, update, clock, acc, policy = producers(flow)
    lane = state.get('lane_trajectory')
    lane['turn_events'] = [dict(kind='roundabout', start_s_m=200., end_s_m=250.)]
    profile = dict(radius_m=100., distance_m=0., horizon_m=130.)
    # Real Map metadata operation; the numerical target is the acceptance gate.
    operation = getattr(Map, '_roundabout_speed_profile', lambda snapshot, curve, progress: dict(curve))
    profile = operation(lane, profile, 190.)
    update(8, 10.)
    packet = state.get('nav_steering_debug')
    packet.update(trajectory_identity={k:lane[k] for k in (
        'navigation_intent_id','revision','route_build_id','source_game_session_id',
        'source_map_key','source_dataset_fingerprint')}, longitudinal_curve_profile=profile)
    state.set('nav_steering_debug', packet)
    policy.on_tick(.05); acc.on_tick(.05); ap.on_tick(.05); engine._flush_controls()
    assert state.get('longitudinal_acc')['constrained_speed_kmh'] <= 35.
    assert state.get('longitudinal_policy')['planned_speed_ms'] * 3.6 <= 35.
    assert curve_input(state)['roundabout_entry_distance_m'] == 10.
    # An ordinary prefab/road is not assigned a blanket 35 km/h limit.
    lane['turn_events'][0]['kind'] = 'prefab'
    assert 'roundabout_entry_distance_m' not in operation(lane, profile, 190.)


@pytest.mark.parametrize('mode', [0, 3])
def test_long_repeated_signal_cycles_retain_continuous_brake_and_fresh_drive(flow, mode):
    from tests.test_oct4_signal_lifecycle import lifecycle
    state, truck, engine, ap, tick, n, clock, writes, _ = lifecycle(flow, mode)
    start = clock[0]
    for _ in range(3):
        tick(4, .2, color=2)
        count = len(writes)
        for i in range(450):
            tick(0 if mode == 0 else 4, 0., color=2)
            assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
            assert pedal(engine, 'aforward') == 0 and pedal(engine, 'abackward') > 0
        assert all(v > 0 for _, ch, v, _ in writes[count:] if ch == 'abackward')
        tick(0 if mode == 0 else 4, 0., color=8)
        tick(0 if mode == 0 else 4, 0., color=8, dt=.12)
        for speed in (.001, .2, .3, .4):
            tick(4, speed)
        assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
        assert pedal(engine, 'aforward') > 0 and pedal(engine, 'abackward') == 0
    assert clock[0] - start > 60.
    assert engine.controller.scs.test_gearbox.reverse_edges == 0
    assert not any(ch == 'parkingbrake' for _, ch, _, _ in writes)
    paired = {'aforward': 0., 'abackward': 0.}
    for _, ch, value, _ in writes:
        if ch in paired:
            paired[ch] = value
            assert not (paired['aforward'] > 0 and paired['abackward'] > 0)


@pytest.mark.parametrize('distance,expected', [(0.,35.),(10.,35.),(100.,None)])
def test_roundabout_ceiling_is_anticipatory_and_tighter_curvature_still_wins(distance, expected):
    from core.longitudinal import curve_constraint_speed
    c = dict(radius_m=100., distance_m=100., roundabout_entry_distance_m=distance)
    value = curve_constraint_speed(c, 50./3.6) * 3.6
    if expected is not None:
        assert value <= expected
    else:
        assert value > 35.  # 35 is required at entry, not globally on approach.
    c.update(radius_m=19., distance_m=0.)
    assert curve_constraint_speed(c, 50./3.6)*3.6 < 35.


@pytest.mark.parametrize('progress', [60.,251.])
def test_roundabout_cap_is_absent_outside_known_forward_horizon(progress):
    snapshot = dict(turn_events=[dict(kind='roundabout', start_s_m=200., end_s_m=250.)])
    assert 'roundabout_entry_distance_m' not in Map._roundabout_speed_profile(
        snapshot, dict(radius_m=100., distance_m=0., horizon_m=130.), progress)


def test_real_map_tick_publishes_bound_roundabout_profile_without_changing_curvature():
    from tests.test_steering_fresh_handoff import prepared_map
    plugin, sdk, point, observation = prepared_map()
    lane = sdk.get('lane_trajectory')
    lane['turn_events'] = [dict(kind='roundabout', start_s_m=0., end_s_m=1000.)]
    sdk.set('lane_trajectory', lane)
    plugin.on_tick(.02)
    packet = sdk.get('nav_steering_debug')
    assert packet['longitudinal_curve_profile']['roundabout_entry_distance_m'] == 0.
    assert packet['sdk_frame_us'] == observation['sdk_frame_us']
    assert packet['observation_timestamp'] == observation['timestamp']
    assert packet['trajectory_identity']['route_build_id'] == lane['route_build_id']


def test_closed_loop_roundabout_reaches_user_ceiling_before_entry():
    from tools.run_curve_approach_bench import run
    result = run(radius=80., roundabout=True)
    assert result['entry_speed_kmh'] <= 35.
    assert result['first_35_distance_to_entry_m'] > 0.
    assert result['entry_overspeed_kmh'] == 0.
    assert result['simultaneous_positive_pedals'] == 0
