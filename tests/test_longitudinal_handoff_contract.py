"""Real producers and physical SCS writes under independent input leases.

Clock/frame inputs model the reported process timing, not an ETS2 experiment.
"""
import copy

import pytest

from core.longitudinal import context, publish
from plugins.drivepolicy.main import Plugin as Policy
from sdk.plugin_sdk import PluginSDK
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_longitudinal_arbitration import strict_flow
from tests.test_longitudinal_evidence_diagnostics import memory_controller
from tests.test_roundabout_intervention_reporting import pedal


def running(flow, mode=0):
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow, mode=mode)
    engine.controller = memory_controller()
    policy = Policy(PluginSDK(state.values, 'drivepolicy'))
    policy.on_start()
    state.set('acc_target_speed', 50.)
    update(8, 10.)
    n()
    policy.on_tick(.033); acc.on_tick(.033); ap.on_tick(.033)
    engine._flush_controls()
    assert state.get('autopilot_active')
    return state, truck, engine, ap, update, n, clock, acc, policy


def curve_packet(state, clock, radius=5000.):
    packet = state.get('nav_steering_debug')
    lane = state.get('lane_trajectory')
    packet.update(trajectory_identity={k: lane[k] for k in (
        'navigation_intent_id', 'revision', 'route_build_id', 'source_game_session_id',
        'source_map_key', 'source_dataset_fingerprint')},
        longitudinal_curve_profile=dict(radius_m=radius, distance_m=200.))
    state.set('nav_steering_debug', packet)
    return copy.deepcopy(packet)


def test_incident_210240_nonbinding_input_cannot_expire_fresh_execution(flow):
    state, truck, engine, ap, update, n, clock, acc, policy = running(flow)
    # Translate the incident's monotonic origin, keeping all exact intervals.
    origin = clock[0] + .01
    offset = origin - 15781.1688093
    update(8, 10., dt=.01)
    old = curve_packet(state, clock)
    update(8, 10., dt=.4684693)  # observation 15781.6372786
    fresh = curve_packet(state, clock)
    state.set('nav_steering_debug', old)  # slow Map; still <500 ms on ACC read
    publish(state, state.get('telemetry')['truck'], 'traffic', traffic_brake=0., light_brake=0.)
    policy.on_tick(.05)
    clock[0] = 15781.6612758 + offset
    acc.on_tick(.05)
    candidate = state.get('longitudinal_acc')
    state.set('nav_steering_debug', fresh)  # real newer frame; no time repair
    clock[0] = 15781.6826799 + offset
    ap.on_tick(.033)
    clock[0] = 15781.6916679 + offset
    engine._flush_controls()
    assert candidate['expires_at'] > clock[0]
    assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    assert pedal(engine, 'aforward') > 0 and pedal(engine, 'abackward') == 0
    assert state.get('longitudinal_command')['observation_timestamp'] == pytest.approx(15781.6372786 + offset)


def test_nonbinding_traffic_and_higher_plan_do_not_shorten_acc_output(flow):
    state, truck, engine, ap, update, n, clock, acc, policy = running(flow)
    old = publish(state, state.get('telemetry')['truck'], 'traffic',
                  traffic_brake=0., light_brake=0., following=None)
    publish(state, state.get('telemetry')['truck'], 'policy',
            planned_speed_ms=25., brake=0.)
    update(8, 10., dt=.47)
    acc.on_tick(.05)
    clock[0] += .04
    assert state.get('longitudinal_acc')['expires_at'] > clock[0]
    assert old['expires_at'] < clock[0]


def test_binding_curve_keeps_original_deadline_and_provenance(flow):
    state, truck, engine, ap, update, n, clock, acc, policy = running(flow)
    old = curve_packet(state, clock, radius=30.)
    old['longitudinal_curve_profile']['distance_m'] = 0.
    state.set('nav_steering_debug', old)
    update(8, 3., dt=.4)
    state.set('nav_steering_debug', old)
    policy.on_tick(.05); acc.on_tick(.05)
    result = state.get('longitudinal_acc')
    assert result['expires_at'] == pytest.approx(old['observation_timestamp'] + .5)
    assert result['deadline_basis']['source'] == 'curve'
    assert result['deadline_basis']['observation_timestamp'] == old['observation_timestamp']
    assert result['deadline_basis']['sdk_frame_us'] == old['sdk_frame_us']


@pytest.mark.parametrize('consumer', ['autopilot', 'engine'])
def test_expired_inherited_decision_refreshes_without_stale_drive_or_revocation(flow, consumer):
    state, truck, engine, ap, update, n, clock, acc, policy = running(flow)
    old = curve_packet(state, clock, radius=30.)
    old['longitudinal_curve_profile']['distance_m'] = 0.
    state.set('nav_steering_debug', old)
    update(8, 3., dt=.47)
    fresh = state.get('nav_steering_debug')
    state.set('nav_steering_debug', old)
    policy.on_tick(.05); acc.on_tick(.05)
    state.set('nav_steering_debug', fresh)
    ap.on_tick(.033)
    clock[0] += .04
    if consumer == 'autopilot':
        ap.on_tick(.033)
    engine._flush_controls()
    assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    assert state.get('autopilot_control_state') != 'controlled_stop'
    assert pedal(engine, 'aforward') == 0 and pedal(engine, 'abackward') == 0
    # Producer ticks compute a NEW decision; consumers never repair old expiry.
    previous = state.get('longitudinal_acc')
    update(8, 3., dt=.02)
    policy.on_tick(.02); acc.on_tick(.02); ap.on_tick(.02)
    engine._flush_controls()
    assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    assert pedal(engine, 'aforward') > 0 and pedal(engine, 'abackward') == 0
    assert state.get('longitudinal_acc')['expires_at'] > previous['expires_at']


def test_refresh_wait_is_bounded_and_does_not_rearm_after_technical_fault(flow):
    state, truck, engine, ap, update, n, clock, acc, policy = running(flow)
    old = curve_packet(state, clock, radius=30.)
    old['longitudinal_curve_profile']['distance_m'] = 0.
    state.set('nav_steering_debug', old)
    update(8, 3., dt=.47)
    fresh = state.get('nav_steering_debug')
    state.set('nav_steering_debug', old)
    policy.on_tick(.05); acc.on_tick(.05)
    state.set('nav_steering_debug', fresh)
    ap.on_tick(.033)
    clock[0] += .04
    ap.on_tick(.033); engine._flush_controls()
    assert state.get('autopilot_control_state') != 'controlled_stop'
    started = state.get('longitudinal_refresh_request')['started_at']
    for _ in range(8):
        update(8, 3., dt=.02)  # real SDK available, but required producer hung
        ap.on_tick(.02); engine._flush_controls()
    assert state.get('autopilot_control_state') == 'controlled_stop' or not state.get('autopilot_active')
    assert pedal(engine, 'aforward') == 0
    assert state.get('longitudinal_refresh_request')['started_at'] == started
    update(8, 3., dt=.02)
    policy.on_tick(.02); acc.on_tick(.02); ap.on_tick(.02); engine._flush_controls()
    assert pedal(engine, 'aforward') == 0


def test_final_positive_write_rechecks_after_diagnostic_binding(flow, monkeypatch):
    state, truck, engine, ap, update, n, clock, acc, policy = running(flow)
    old = curve_packet(state, clock, radius=30.)
    old['longitudinal_curve_profile']['distance_m'] = 0.
    state.set('nav_steering_debug', old)
    update(8, 3., dt=.4)
    fresh = state.get('nav_steering_debug')
    state.set('nav_steering_debug', old)
    policy.on_tick(.033); acc.on_tick(.033)
    state.set('nav_steering_debug', fresh)
    ap.on_tick(.033)
    previous = state.get('longitudinal_command')
    bind = engine._bind_longitudinal_output
    delayed = []
    def slow_binding(*args, **kwargs):
        bind(*args, **kwargs)
        if args[0] == 'active' and not delayed:
            delayed.append(True)
            clock[0] += .12
    monkeypatch.setattr(engine, '_bind_longitudinal_output', slow_binding)
    engine._flush_controls()
    assert delayed and previous['expires_at'] < clock[0]
    assert pedal(engine, 'aforward') == 0
    assert state.get('autopilot_active')


def test_urgent_valid_evidence_bypasses_handoff_reserve(flow):
    state, truck, engine, ap, update, n, clock, acc, policy = running(flow)
    original_truck = state.get('telemetry')['truck']
    update(8, 10., dt=.47)
    # Newly evaluated urgent demand from an old-but-still-valid observation.
    # The 50 ms executable-drive reserve must not defer its immediate brake.
    publish(state, original_truck, 'traffic', traffic_brake=1., light_brake=0.)
    policy.on_tick(.033); acc.on_tick(.033); ap.on_tick(.033)
    engine._flush_controls()
    assert pedal(engine, 'aforward') == 0
    assert pedal(engine, 'abackward') == 1.


def test_deadline_journal_roundtrip_retains_each_original_receipt():
    from core.navigation.longitudinal_diagnostics import PedalJournal, bounded_input
    from core.longitudinal import dependency
    binding = [1, 'session', 'map', 'dataset', 'intent', 7, 'build', 'geometry']
    source = dict(context=binding, sdk_frame_us=20, observation_timestamp=100.,
                  phase='active', inputs={})
    for name, frame, stamp in [('road', 19, 99.9), ('acc', 20, 100.)]:
        value = dict(source=name, sdk_frame_us=frame, observation_timestamp=stamp,
                     expires_at=stamp+.5, context=binding, computed_at=100., valid=True)
        value['deadline_basis'] = dependency(value)['deadline_basis']
        source['inputs'][name] = bounded_input(value)
    journal = PedalJournal(); journal.enabled = True
    journal.bind(source)
    journal.record('throttle', .2, 100., 100.001, 'SCS_SDK',
                   dict(status='MAPPING_WRITE_RETURNED', value=.2))
    assert journal.drain()['events'][0]['source'] == source


def test_route_candidate_deadline_records_consumed_map_observation(flow):
    from tests.test_phase7_joint_validation import offer_route_candidate
    state, truck, engine, ap, update, n, clock, acc, policy = running(flow)
    following = offer_route_candidate(state, engine, clock)
    assert following['deadline_dependencies']
    projection = next(p for p in following['deadline_dependencies']
                      if p['source'] == 'route_projection')
    actual = state.get('nav_steering_debug')
    assert projection['sdk_frame_us'] == actual['sdk_frame_us']
    assert projection['observation_timestamp'] == actual['observation_timestamp']
    assert projection['expires_at'] == actual['observation_timestamp']+.5
    assert projection['context'] == context(state)


def test_zero_drive_refresh_packet_cannot_clear_unfinished_handoff(flow):
    from core.longitudinal import finalize
    state, truck, engine, ap, update, n, clock, acc, policy = running(flow)
    request = dict(context=context(state), started_at=clock[0], expires_at=clock[0]+.1)
    state.set('longitudinal_refresh_request', request)
    finalize(state, state.get('telemetry')['truck'], 0., 0., dict(
        source='decision_refresh', reason='waiting for a new longitudinal decision',
        refresh_pending=True, expires_at=request['expires_at']), context(state))
    engine._flush_controls()
    assert state.get('longitudinal_applied')['refresh_pending'] is True
    assert state.get('longitudinal_refresh_request')['started_at'] == request['started_at']
    assert pedal(engine, 'aforward') == 0.


def test_first_fault_retains_deadline_with_full_runtime_identity(flow):
    from core.control_timing import record_control_fault
    from core.longitudinal import rejection_details
    state, truck, engine, ap, update, n, clock, acc, policy = running(flow)
    binding = (15769995551900, '1', 'promods-1.59', 'd6cc7936fce4e902761abb5d',
        'ebea77f0a0bd446cbcbdad9ae13f4e22', 7, 'f5320dcad68e4cf2b331802977dc7cb4',
        ('lane_path', 'f6e44b5a0a280f891ddcadaf2975d6a12dc7fd6a2dc58a166df6c0bbe895fff9', True))
    value = state.get('longitudinal_command')
    value.update(context=binding)
    details = rejection_details(value, binding, clock[0])
    details.update(vehicle_sdk_frame_us=20, vehicle_observation=dict(
        sdk_frame_us=20, observed_at=clock[0], valid=True, reason=None))
    fault = record_control_fault(state, 'engine', 'longitudinal input lease expired before write',
                                 details=details)
    assert fault['details']['deadline_basis'] == value['deadline_basis']
    assert tuple(fault['details']['actual_context'][:7]) == binding[:7]
    assert fault['details']['expected_context'] == fault['details']['actual_context']


@pytest.mark.parametrize('mode', [0, 3])
def test_refresh_preserves_existing_physical_signal_brake_chain(flow, mode):
    from tests.test_oct4_signal_lifecycle import lifecycle
    state, truck, engine, ap, tick, n, clock, writes, _ = lifecycle(flow, mode)
    tick(4, .2, color=2)
    tick(0 if mode == 0 else 4, 0., color=2)
    assert state.get('autopilot_control_state') == 'planned_wait'
    old = state.get('longitudinal_traffic')
    count = len(writes)
    # New genuine signal/SDK/Map data exist, but producer decisions inherited
    # a nearly expired signal leaf. The Engine may preserve its physical witness;
    # it may not execute the expired pedals or invent a new observation.
    tick(0 if mode == 0 else 4, 0., color=2, dt=.47, flush=False)
    fresh = state.get('longitudinal_traffic')
    state.set('longitudinal_traffic', old)
    tick.policy.on_tick(.033); tick.acc.on_tick(.033)
    ap.on_tick(.033)
    state.set('longitudinal_traffic', fresh)
    engine._flush_controls()
    assert state.get('longitudinal_applied')['refresh_pending']
    clock[0] += .04  # Expired inherited leaf; actual SDK and physical hold fresh.
    ap.on_tick(.033); engine._flush_controls()
    assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    assert pedal(engine, 'aforward') == 0. and pedal(engine, 'abackward') > 0.
    assert all(v > 0. for _, ch, v, _ in writes[count:] if ch == 'abackward')
    assert not engine.controller.current_hazard


@pytest.mark.parametrize('mode', [0, 3])
def test_refresh_preserves_forward_started_braking_before_stationary_hold(flow, mode):
    state, truck, engine, ap, update, n, clock, acc, policy = running(flow, mode)
    update(8, .2)
    old = publish(state, state.get('telemetry')['truck'], 'traffic',
        traffic_brake=0., light_brake=1., light=dict(id=19, color='red', distance=5.))
    policy.on_tick(.033); acc.on_tick(.033); ap.on_tick(.033)
    engine._flush_controls()
    witness = state.get('simple_auto_service_hold')
    assert witness['phase'] == 'braking' and not witness.get('signal_lock')
    writes = []
    original = engine.controller.set_brake
    def record_brake(value):
        original(value)
        writes.append((clock[0], value))
    engine.controller.set_brake = record_brake
    update(8, .15, dt=.47)
    fresh = publish(state, state.get('telemetry')['truck'], 'traffic',
        traffic_brake=0., light_brake=1., light=dict(id=19, color='red', distance=5.))
    state.set('longitudinal_traffic', old)
    policy.on_tick(.033); acc.on_tick(.033); ap.on_tick(.033)
    state.set('longitudinal_traffic', fresh)
    engine._flush_controls()
    assert state.get('longitudinal_applied')['refresh_pending']
    assert writes and all(value > 0. for _, value in writes), writes
    assert pedal(engine, 'aforward') == 0 and pedal(engine, 'abackward') > 0
    assert state.get('simple_auto_service_hold')['chain'] == witness['chain']
    assert state.get('autopilot_active') and not engine.controller.current_hazard
