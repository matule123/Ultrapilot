"""Consumed red/green -> actual service-brake receipts, not game consumption."""
import pytest
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_oct10_signal_timing import timing_flow
from tests.test_roundabout_intervention_reporting import pedal
from tools.reproduce_oct17_open_signal_profile import test_same_red_stop_target_cannot_rebound_as_vehicle_slows  # noqa: F401


@pytest.mark.parametrize('mode', [0, 3])
@pytest.mark.parametrize('green_at', ['after_hold', 'zero'])
def test_positive_approach_receipt_survives_zero_before_terminal_zone(flow, tmp_path, mode, green_at):
    values, step = timing_flow(flow, tmp_path, mode)
    state, truck, engine, ap, tick, n, clock, writes, collector = values
    truck['powertrainObservation'] = dict(schema=1, engine_enabled=True, engine_rpm=650.)
    step(60, 'red', speed=10., progress=0.)
    held = state.get('simple_auto_service_hold')
    assert held['phase'] == 'approaching' and held['brake'] > 0.
    start = len(writes)
    # The previously acknowledged moving brake is still physically positive.
    # No new brake edge at rest and no inferred future green are admissible.
    step(61, 'green' if green_at == 'zero' else 'red', speed=0., gear=0, progress=34.5)
    assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    assert pedal(engine, 'abackward') > 0. and pedal(engine, 'aforward') == 0.
    if green_at == 'after_hold':
        for gen in range(62, 66):
            step(gen, 'red', speed=0., gear=0, progress=34.5)
        assert all(v > 0 for _, ch, v, _ in writes[start:] if ch == 'abackward')
    for gen in range(66, 72):
        step(gen, 'green', speed=0., gear=0, progress=34.5)
        assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    for gen in range(72, 78):
        step(gen, 'green', speed=.4, gear=4, progress=34.6)
    assert state.get('autopilot_active') and not state.get('safety_hazard_active')
    assert pedal(engine, 'aforward') > 0. and pedal(engine, 'abackward') == 0.
    assert not any(ch == 'parkingbrake' for _, ch, _, _ in writes)


@pytest.mark.parametrize('mode', [0, 3])
@pytest.mark.parametrize('fault', ['interrupted', 'backend', 'reverse', 'stale', 'identity'])
def test_approach_zero_requires_original_positive_receipt(flow, tmp_path, mode, fault):
    values, step = timing_flow(flow, tmp_path, mode)
    state, truck, engine, ap, tick, n, clock, writes, collector = values
    step(60, 'red', speed=10., progress=0.)
    if fault == 'interrupted': engine.controller.set_brake(0.)
    elif fault == 'backend': engine.controller.scs.connected = False
    elif fault == 'identity': state.set('autopilot_failure_epoch', 'foreign')
    start = len(writes)
    step(61, 'red', speed=0., gear=-1 if fault == 'reverse' else 0,
         progress=34.5, age=.6 if fault == 'stale' else 0.)
    assert not any(ch == 'aforward' and v > 0 for _, ch, v, _ in writes[start:])
    if fault in ('interrupted', 'backend', 'reverse', 'identity'):
        assert not state.get('autopilot_active') or state.get('autopilot_control_state') == 'controlled_stop'


@pytest.mark.parametrize('field', ['brake', 'chain', 'write_sequence'])
def test_incomplete_approach_receipt_is_rejected_without_new_pedal(flow, tmp_path, field):
    values, step = timing_flow(flow, tmp_path, 0)
    state, truck, engine, ap, tick, n, clock, writes, collector = values
    step(60,'red',speed=10.,progress=0.)
    held=state.get('simple_auto_service_hold');held[field]=None
    state.set('simple_auto_service_hold',held)
    start=len(writes)
    step(61,'red',speed=0.,gear=0,progress=34.5)
    assert not state.get('autopilot_active')
    assert not any(ch=='aforward' and v>0. for _,ch,v,_ in writes[start:])


@pytest.mark.parametrize('mode', [0, 3])
def test_confirmed_green_cannot_restart_known_stopped_engine(flow, tmp_path, mode):
    values, step = timing_flow(flow, tmp_path, mode)
    state, truck, engine, ap, tick, n, clock, writes, collector = values
    step(60, 'red', speed=10., progress=0.)
    step(61, 'red', speed=0., gear=0, progress=34.5)
    assert state.get('autopilot_active')
    truck['powertrainObservation'] = dict(schema=1, engine_enabled=False, engine_rpm=0.)
    start = len(writes)
    for gen in range(62, 70): step(gen, 'green', speed=0., gear=0, progress=34.5)
    assert not any(ch == 'aforward' and v > 0. for _, ch, v, _ in writes[start:])
    assert not state.get('autopilot_active')
    assert 'engine' in state.get('autopilot_disable_reason', '')


@pytest.mark.parametrize('mode', [0, 3])
def test_engine_off_published_during_final_restart_read_never_gets_probe(flow, tmp_path, mode, monkeypatch):
    values, step = timing_flow(flow, tmp_path, mode)
    state, truck, engine, ap, tick, n, clock, writes, collector = values
    truck['powertrainObservation'] = dict(schema=1,engine_enabled=True,engine_rpm=650.)
    step(60, 'red', speed=10., progress=0.)
    step(61, 'red', speed=0., gear=0, progress=34.5)
    original = engine._resume_signal_wait
    fired = []
    def enter(captured, witness):
        def during_read(key):
            if key == 'telemetry':
                state.hook = None
                fired.append(True)
                truck['powertrainObservation'] = dict(schema=1,engine_enabled=False,engine_rpm=0.)
                flow[4](0,0.,dt=.001)  # A genuinely newer SDK observation.
        state.hook = during_read
        return original(captured,witness)
    monkeypatch.setattr(engine,'_resume_signal_wait',enter)
    start = len(writes)
    for gen in range(62,70): step(gen,'green',speed=0.,gear=0,progress=34.5)
    assert fired == [True]
    assert not any(ch == 'aforward' and v > 0. for _,ch,v,_ in writes[start:])
    assert not state.get('autopilot_active')
    record = state.get('autopilot_intervention')
    assert record['details']['source'] == 'planned_restart_powertrain'
    assert record['details']['powertrain_observation']['engine_enabled'] is False


@pytest.mark.parametrize('mode', [0, 3])
@pytest.mark.parametrize('speed', [20., 35., 50.])
@pytest.mark.parametrize('delay', [.12, .35])
def test_closed_production_profile_without_repeated_drive_brake(tmp_path, mode, speed, delay):
    from tools.verify_oct17_joint_lifecycle import run
    before = run(tmp_path, mode, speed, delay, True)
    after = run(tmp_path, mode, speed, delay, False)
    assert before['coherent_processing_clock'] and after['coherent_processing_clock']
    assert after['active'] and after['resumed_without_n'], after
    assert after['termination_reason'] is None
    assert 0. <= after['stop']['reference_gap_to_target_m'] <= 1.5
    assert after['red_target_overrun_samples'] == 0
    assert after['red_drive_brake_transitions'] <= 1
    assert after['drive_brake_transitions'] <= before['drive_brake_transitions']
    assert after['maximum_deceleration_mps2'] <= before['maximum_deceleration_mps2']+1e-9
    assert after['maximum_abs_model_jerk_mps3'] <= before['maximum_abs_model_jerk_mps3']+1e-9
    assert after['far_low_speed_s'] == 0.
    assert after['hold_brake_zero_count'] == 0
    assert after['simultaneous_positive_physical_writes'] == 0
    assert after['simultaneous_positive_pedals'] == after['parking_writes'] == 0


@pytest.mark.parametrize('mode', [0, 3])
@pytest.mark.parametrize('green_at', ['moving', 'last_metres'])
def test_closed_green_removes_distance_deceleration_without_waiting_for_stop(tmp_path, mode, green_at):
    from tools.verify_oct17_joint_lifecycle import run
    reference = run(tmp_path, mode, 35., .35, False)
    change = 4. if green_at == 'moving' else reference['stop']['t']-.2
    program = lambda t, stopped: dict(state=2 if t < change else 8, remaining_s=60.)
    result = run(tmp_path, mode, 35., .35, False, phase_program=program, duration_s=30.)
    assert result['active'] and result['termination_reason'] is None
    assert result['green_drive_return_s'] is not None and result['green_drive_return_s'] < 2.5
    assert result['red_target_overrun_samples'] == 0
    assert result['simultaneous_positive_physical_writes'] == result['parking_writes'] == 0

