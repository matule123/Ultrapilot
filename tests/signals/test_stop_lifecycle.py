"""Oct 8 stop lifecycle, using real producers and chronological SCS writes.

The SDK response is a model/input. Mapping return is not game consumption.
"""
import math

import pytest

from core.longitudinal import context, publish
from core.sdk.signal_snapshot import RouteSignalSelector
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.signals.test_signal_lifecycle import lifecycle
from tests.test_roundabout_intervention_reporting import pedal
from tests.test_signal_stop_resume import source_bytes


def directed_stop(flow, mode=0, *, start=True):
    values = lifecycle(flow, mode, full_identity=True, start=start)
    state, truck, engine, ap, tick, n, clock, writes, collected = values
    lane = state.get('lane_trajectory')
    lane['signal_passages'] = dict(schema_version=1, status='prepared', blockers=[],
        passages=[dict(passage_key='oct8-directed-entry', semaphore_id=19,
            entry_progress_m=10., entry_xyz=[0.,10.,-10.], entry_heading_rad=0.,
            bounds_xyz=[-5.,9.,-30.,5.,11.,0.], front_allowance_m=6.,
            junction_standoff_m=2., front_geometry_status='test_allowance')])
    state.set('lane_trajectory', lane)
    state.set('lane_trajectory_publication_token', 'oct8-direct')

    def step(gear, speed, *, color=2, missing=False, dt=.05, no_demand=False):
        # The fixture update uses Engine's actual coherent SDK envelope.
        flow[4](gear, speed, dt=dt)
        actual = state.get('telemetry')['truck']
        state.set('truck_speed_ms', speed)
        frame = actual['sdkFrameTimeUs']
        engine._signal_reader.buffer = source_bytes(clock[0], frame, frame,
            color=color, signal_id=77 if missing else 19)
        signal = engine._signal_observation(actual, context(state))
        light = signal.get('candidate') if signal.get('valid') else signal.get('stop_candidate')
        publish(state, actual, 'traffic', signal=signal, light=light,
            light_brake=0. if no_demand else engine._light_brake(light),
            traffic_brake=0., following=None)
        tick.policy.on_tick(dt); tick.acc.on_tick(dt); ap.on_tick(dt)
        engine._flush_controls()
        return signal
    return values, step


def test_no_authored_signal_assignment_is_detection_only():
    head = dict(id=1, x=0.,y=10.,z=-5.,yaw=math.pi,color='red')
    signal = dict(valid=True,lifecycle=11,generation=1,frame_us=100,
                  observed_at=1000.,lights=[head])
    selected = RouteSignalSelector().select(signal, [[0.,10.,0.],[0.,10.,-50.]],
        'route', ('authority',), dict(x=0.,y=10.,z=0.,rotation=0.),0.)
    assert not selected['valid']
    assert selected['candidate'] is None
    assert selected['relevance'] == 'detected_only_unassigned'


@pytest.mark.parametrize('mode', [0, 3])
@pytest.mark.parametrize('metadata', [None, dict(schema_version=1, status='prepared', passages=[])])
def test_unassigned_near_red_requires_takeover_without_becoming_signal_control(flow, mode, metadata):
    values, step = directed_stop(flow, mode)
    state, truck, engine, ap, tick, n, clock, writes, collected = values
    lane = state.get('lane_trajectory'); lane['signal_passages'] = metadata
    state.set('lane_trajectory', lane)
    state.set('lane_trajectory_publication_token', 'unassigned-intersection')
    for _ in range(5):
        signal = step(4, 2., color=2)
        assert not signal['valid'] and signal['candidate'] is None
        assert state.get('longitudinal_traffic')['light'] is None
        # An observed approach head with no proven assignment is not clear
        # road. Retain detection-only identity and use technical handover,
        # never synthesize a red lock or continue positive propulsion.
        assert state.get('autopilot_control_state') == 'controlled_stop'
        assert not state.get('simple_auto_service_hold')
        assert pedal(engine, 'aforward') == 0
        assert 'signal regulation coverage' in state.get('automatic_safety_stop_reason','')


@pytest.mark.parametrize('mode', [0,3])
def test_unobserved_authored_stop_cannot_drop_written_chain_or_restore_drive(flow, mode):
    values, step = directed_stop(flow, mode)
    state, truck, engine, ap, tick, n, clock, writes, collected = values
    step(4, 2., color=8)  # actually acquire this control before its disappearance
    signal = step(4, 2., missing=True)
    assert not signal['valid'] and signal['stop_candidate']['head_observed'] is False
    assert pedal(engine,'abackward') > 0 and state.get('simple_auto_service_hold')
    start = len(writes)
    # Reproduce a producer/source transition while the SDK is still moving:
    # no new positive demand does NOT establish clearance of the planned stop.
    for speed in (1., .683, .194, .04, 0., 0.):
        step(4 if speed > .05 or mode == 3 else 0, speed, missing=True, no_demand=True)
        assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
        assert pedal(engine,'abackward') > 0 and pedal(engine,'aforward') == 0
        assert state.get('simple_auto_service_hold') is not None
    assert all(v > 0 for _,ch,v,_ in writes[start:] if ch == 'abackward')
    assert not any(ch == 'aforward' and v > 0 for _,ch,v,_ in writes[start:])


def test_full_consumed_signal_survives_diagnostic_budget(flow):
    from core.navigation.longitudinal_diagnostics import bounded_input
    values, step = directed_stop(flow)
    state, truck, engine, ap, tick, n, clock, writes, collected = values
    signal = step(4, 2.)
    packet = state.get('longitudinal_traffic')
    # Production crossing attribution carries candidate IDs plus a decisive
    # candidate; unrelated display strings must not erase the signal receipt.
    packet['brake_basis'] = dict(kind='directed_crossing_heuristic',
        candidate_ids=list(range(16)), decisive=dict(id='actor', reason='x'*2500))
    saved = bounded_input(packet)
    assert saved['signal']['candidate']['id'] == 19
    assert saved['signal']['candidate']['color'] == 'red'
    assert saved['signal']['generation'] == signal['generation']
    assert saved['signal']['observed_at'] == signal['observed_at']
    assert saved.get('capture_incomplete') is True  # no silent discard
    state.set('longitudinal_traffic', packet)
    clock[0] += .12  # existing data remain within their original leases
    engine._flush_controls()
    history = engine.controller._pedal_journal.snapshot(include_history=True)['decision_history']
    assert history['incomplete'] and history['capture_failures'] > 0
    latest = max(history['regular_samples'] + history['changes'], key=lambda row: row['sequence'])
    assert latest['signal_id'] == 19 and latest['signal_color'] == 'red'


def test_unobserved_authored_target_retains_original_geometry_in_existing_export(flow, tmp_path):
    from core.steering_replay import SteeringReplayBuffer, inspect_replay
    values, step = directed_stop(flow)
    state, truck, engine, ap, tick, n, clock, writes, collected = values
    step(4, 2., color=8)
    signal = step(4, 2., missing=True)
    journal = engine.controller._pedal_journal
    snapshot = journal.snapshot(include_history=True)
    path = SteeringReplayBuffer(2).export(tmp_path, reason='automatic_disable', longitudinal=snapshot)
    checked = inspect_replay(path)
    assert checked['integrity_valid'] and checked['confirmed'] is False
    history = checked['replay']['longitudinal']['decision_history']
    latest = max(history['regular_samples'] + history['changes'], key=lambda row: row['sequence'])
    assert latest['signal_id'] == 19 and latest['signal_color'] == 'unknown'
    assert latest['signal_reason'] and latest['signal_relevance'] == signal['relevance']
    assert latest['signal_frame_us'] == signal['frame_us']
    assert latest['signal_observed_at'] == signal['observed_at']
    for key in ('distance_basis', 'entry_xyz', 'entry_progress_m'):
        assert latest['stop_target'][key] == signal['stop_candidate'][key]
    assert latest['light_brake'] > 0 and latest['last_backend_status'] == 'MAPPING_WRITE_RETURNED'


@pytest.mark.parametrize('mode', [0,3])
def test_repeated_directed_red_wait_green_and_no_zero_edge(flow, mode):
    values, step = directed_stop(flow, mode)
    state, truck, engine, ap, tick, n, clock, writes, collected = values
    for cycle in range(3):
        step(4, 2.)
        start = len(writes)
        for speed in (1., .4, .12, .04, 0., 0.):
            step(4 if speed > .05 or mode == 3 else 0, speed)
            assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
            assert pedal(engine,'aforward') == 0 and pedal(engine,'abackward') > 0
        assert not engine.controller.current_hazard
        assert state.get('autopilot_control_state') == 'planned_wait'
        assert all(v > 0 for _,ch,v,_ in writes[start:] if ch == 'abackward')
        step(0 if mode == 0 else 4, 0., color=8)
        assert pedal(engine,'abackward') > 0
        step(0 if mode == 0 else 4, 0., color=8, dt=.12)
        for gear, speed in ((4,.001),(4,.2),(4,.3),(4,.5)):
            step(gear,speed,color=8)
        assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
        assert pedal(engine,'aforward') > 0 and pedal(engine,'abackward') == 0
    assert engine.controller.scs.test_gearbox.reverse_edges == 0


@pytest.mark.parametrize('speed,allowed', [(-.049,True),(-.051,False),(.049,True),(.051,False)])
def test_hold_motion_contract_is_not_relabelled_as_noise(flow, speed, allowed):
    values, step = directed_stop(flow)
    state, truck, engine, ap, tick, n, clock, writes, collected = values
    step(4,2.);step(4,1.);step(4,.2);step(0,0.)
    assert state.get('simple_auto_service_hold')['phase'] == 'holding'
    step(0,speed)
    assert bool(state.get('autopilot_active')) == allowed
    assert pedal(engine,'aforward') == 0
    if not allowed:
        assert 'vehicle motion observed' in state.get('autopilot_disable_reason')


def test_first_forward_activation_with_engine_before_plugin_is_bounded(flow):
    values = lifecycle(flow, start=False)
    state, truck, engine, ap, tick, n, clock, writes, collected = values
    tick(8,9.4114189148)
    n()
    engine._flush_controls()
    assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    assert not state.get('safety_hazard_active')
    assert pedal(engine,'aforward') == 0
    for _ in range(5):
        tick(8,9.4114189148)
        assert state.get('autopilot_active'), state.get('autopilot_disable_reason')


def test_actual_invalid_acc_still_cannot_authorize_drive(flow):
    values, step = directed_stop(flow)
    state, truck, engine, ap, tick, n, clock, writes, collected = values
    packet = state.get('longitudinal_acc'); packet['valid'] = False
    state.set('longitudinal_acc',packet)
    count = len(writes)
    ap.on_tick(.05);engine._flush_controls()
    assert not state.get('autopilot_active') or state.get('autopilot_control_state') == 'controlled_stop'
    assert not any(ch == 'aforward' and v > 0 for _,ch,v,_ in writes[count:])


def test_recovered_same_directed_red_acquires_actual_clearance_receipt(flow):
    values, step = directed_stop(flow)
    state, truck, engine, ap, tick, n, clock, writes, collected = values
    step(4,2.,color=8)
    step(4,2.,missing=True)
    assert not state.get('simple_auto_service_hold').get('signal_lock')
    step(4,2.)  # recovered head, still above the approach ceiling: keep braking
    hold = state.get('simple_auto_service_hold')
    assert hold['signal_lock']['candidate']['id'] == 19
    assert hold['signal_lock']['candidate']['color'] == 'red'
    for speed in (.2, .04,0.,0.):
        step(0 if speed < .05 else 4,speed)
    step(0,0.,color=8);step(0,0.,color=8,dt=.12)
    for speed in (.001,.2,.3):
        step(4,speed,color=8)
    assert state.get('autopilot_active') and pedal(engine,'aforward') > 0


@pytest.mark.parametrize('mode', [0, 3])
def test_closed_model_missing_head_does_not_cycle_pedals_or_change_valid_red_profile(tmp_path, mode):
    from tools.run_prefab_signal_bench import run
    known = run(tmp_path, mode=mode, speed_kmh=35., jitter=True)
    recovered = run(tmp_path, mode=mode, speed_kmh=35., jitter=True,
                    head_missing_during_approach=True)
    assert recovered['active'] and recovered['resumed_without_n']
    assert recovered['drive_brake_transitions'] == 2  # drive -> brake -> permitted drive
    assert recovered['hold_brake_zero_count'] == 0
    assert recovered['simultaneous_positive_pedals'] == recovered['parking_writes'] == 0
    # An observed red below the approach ceiling can release while moving;
    # an unknown previously observed control cannot. These are distinct
    # evidence contracts, so an earlier protective stop is expected. Preserve
    # the no-entry-overrun, continuous brake and confirmed restart assertions.
    assert recovered['stop']['front_gap_to_entry_m'] > 0.
    assert known['stop']['front_gap_to_entry_m'] > 0.
