"""No claimed painted-line calibration: real qualified pipeline/physical writes."""
import pytest

from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_oct10_signal_timing import timing_flow
from tests.test_roundabout_intervention_reporting import pedal


@pytest.mark.parametrize('speed,distance', [(.2, 1.), (.39, 1.49)])
def test_first_slow_terminal_request_is_positive_without_full_brake_jump(speed, distance):
    from core.longitudinal import stopping_brake_request
    first = stopping_brake_request(distance, speed)
    continued = stopping_brake_request(distance, speed, continuing=True)
    assert 0. < first == continued < .1


def test_terminal_standstill_request_does_not_fade_to_zero():
    from core.longitudinal import stopping_brake_request
    assert stopping_brake_request(1., 0.) == 1.


@pytest.mark.parametrize('mode', [0, 3])
def test_nonzero_envelope_does_not_invent_full_terminal_brake(flow, tmp_path, mode):
    values, step = timing_flow(flow, tmp_path, mode)
    state, truck, engine, ap, tick, n, clock, writes, collector = values
    # Start the acknowledged planned chain in forward motion, then approach
    # the old 0.5 m/s / 1.5 m discontinuity. Distance = 42 - progress.
    write_start = len(writes)
    step(30, 'red', speed=2., progress=39.1)
    before = pedal(engine, 'abackward')
    assert before > 0.
    step(31, 'red', speed=.39, progress=40.51)
    assert state.get('longitudinal_acc')['constrained_speed_kmh'] > .39*3.6
    # Oct 12 keeps this positive-envelope request with ACC instead of
    # resetting that controller through an independent Traffic pedal.
    assert state.get('longitudinal_traffic')['light_brake'] == 0.
    assert 0. < state.get('longitudinal_acc')['brake'] < .1
    assert 0. < pedal(engine, 'abackward') <= before
    assert pedal(engine, 'aforward') == 0.
    assert state.get('autopilot_active')
    assert not state.get('safety_hazard_active')
    # Inspect actual writes rather than assuming the final shared-state pair.
    assert not any(ch == 'abackward' and value == 0. for _, ch, value, _ in writes[write_start:])
    assert not any(ch == 'parkingbrake' for _, ch, _, _ in writes)


@pytest.mark.parametrize('mode', [0, 3])
def test_existing_red_standstill_is_never_released_to_chase_remaining_metres(flow, tmp_path, mode):
    values, step = timing_flow(flow, tmp_path, mode)
    state, truck, engine, ap, tick, n, clock, writes, collector = values
    step(30, 'red', speed=2., progress=39.1)
    step(31, 'red', speed=.39, progress=40.51)
    start = len(writes)
    for gen in range(32, 42):
        step(gen, 'red', speed=0., gear=0 if mode == 0 else 4, progress=40.7)
        assert state.get('autopilot_active')
        assert state.get('simple_auto_service_hold')['phase'] == 'holding'
        assert pedal(engine, 'abackward') > 0.
        assert pedal(engine, 'aforward') == 0.
    assert all(value > 0. for _, ch, value, _ in writes[start:] if ch == 'abackward')
    assert not any(ch == 'aforward' and value > 0. for _, ch, value, _ in writes[start:])
    assert not any(ch == 'parkingbrake' for _, ch, _, _ in writes)


@pytest.mark.parametrize('distance,speed', [(0., .1), (-.1, .1), (1., .92), (.01, .1)])
def test_actual_exhausted_envelope_keeps_full_brake(distance, speed):
    from core.longitudinal import stopping_brake_request
    assert stopping_brake_request(distance, speed, continuing=True) == 1.


@pytest.mark.parametrize('mode', [0, 3])
@pytest.mark.parametrize('speed', [20., 35., 50.])
def test_closed_terminal_stop_preserves_hold_and_moves_toward_same_target(tmp_path, mode, speed):
    from tools.run_oct11_terminal_stop_bench import compare
    old, new = compare(tmp_path, speed=speed, mode=mode)
    # Before tuning: remove a discontinuous full-brake request without gaining
    # position by crossing the target, releasing red standstill or adding cycles.
    assert 0. <= new['gap_m'] < old['gap_m']
    assert new['maximum_deceleration_mps2'] <= old['maximum_deceleration_mps2']+1e-9
    assert new['maximum_abs_model_jerk_mps3'] <= old['maximum_abs_model_jerk_mps3']+1e-9
    assert new['pedal_transitions'] <= old['pedal_transitions']
    assert new['red_target_overruns'] == 0
    assert new['hold_zero_writes'] == 0
    assert new['positive_pedal_overlap'] == new['parking_writes'] == 0
    assert new['red_standstill_drive_writes'] == 0
    assert new['far_low_speed_s'] == 0.
    assert new['active'] and new['resumed_without_n']
