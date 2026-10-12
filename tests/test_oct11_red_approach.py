"""Qualified real reader -> Policy -> ACC -> AP -> Engine -> physical writer."""
from unittest.mock import patch

import pytest

from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_oct10_signal_timing import timing_flow
from tests.test_roundabout_intervention_reporting import pedal


@pytest.mark.parametrize('mode', [0, 3])
def test_far_red_does_not_latch_tiny_brake_below_distance_profile(flow, tmp_path, mode):
    values, step = timing_flow(flow, tmp_path, mode)
    state, truck, engine, ap, tick, n, clock, writes, collector = values
    step(30, 'red', speed=50./3.6, progress=0.)  # 42 m to derived target
    assert pedal(engine, 'abackward') > 0.
    original = state.get('simple_auto_service_hold')['signal_lock']['candidate']['id']
    for i in range(31, 43):
        step(i, 'red', speed=3.3/3.6, progress=3.)  # still 39 m away
    assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    assert pedal(engine, 'aforward') > 0., state.get('longitudinal_acc')
    assert pedal(engine, 'abackward') == 0.
    hold = state.get('simple_auto_service_hold')
    assert hold['phase'] == 'approaching'
    assert hold['signal_lock']['candidate']['id'] == original
    assert not any(ch == 'parkingbrake' for _, ch, _, _ in writes)


@pytest.mark.parametrize('mode', [0, 3])
def test_far_signal_uses_one_speed_controller_not_external_pedal_reset(flow, tmp_path, mode):
    values, step = timing_flow(flow, tmp_path, mode)
    state = values[0]
    signal = step(30, 'red', speed=35./3.6, progress=0.)
    assert signal['candidate']['distance'] == pytest.approx(42.)
    assert state.get('longitudinal_traffic')['light_brake'] == 0.
    assert state.get('longitudinal_policy')['brake'] == 0.
    acc = state.get('longitudinal_acc')
    assert acc['signal_stop_control'] is True
    assert acc['brake'] > 0.
    assert acc['speed_control_reason'] != 'external braking inhibits speed drive'


def test_zero_stopping_envelope_does_not_fade_against_idle_load():
    from core.longitudinal import signal_stop_brake_request, signal_stop_speed_limit
    light = dict(color='red', stop_target_kind='derived_directed_curve_entry', distance=1.)
    assert signal_stop_speed_limit(light, .92) == 0.
    assert signal_stop_brake_request(light, .92, continuing=True) == 1.


def test_current_red_ceiling_wins_between_speed_producer_ticks(flow, tmp_path):
    from copy import deepcopy
    from core.longitudinal import publish
    values, step = timing_flow(flow, tmp_path)
    state, truck, engine, ap, tick, n, clock, writes, collector = values
    state.set('acc_target_speed', 50.)
    def red_during_steering_write():
        packet = state.get('longitudinal_command')
        assert packet['throttle'] > 0.  # old validated green decision
        signal = deepcopy(state.get('longitudinal_traffic')['signal'])
        clock[0] += .001
        signal.update(observed_at=clock[0], generation=signal['generation']+1,
                      frame_us=signal['frame_us']+16666)
        signal['candidate'].update(color='red', state=2, stop_required=True)
        light = signal['candidate']
        assert engine._light_brake(light) == 0.  # non-terminal distance constraint
        publish(state, state.get('telemetry')['truck'], 'traffic', signal=signal,
                light=light, light_brake=0., traffic_brake=0., following=None)
    step(30, 'green', speed=10., progress=0., on_steering=red_during_steering_write)
    assert state.get('autopilot_active')
    assert pedal(engine, 'aforward') == 0.


@pytest.mark.parametrize('corruption', ['expired', 'future', 'foreign', 'cancel'])
def test_signal_write_guard_cannot_authorize_invalid_current_source(flow, tmp_path, corruption):
    from copy import deepcopy
    values, step = timing_flow(flow, tmp_path)
    state, truck, engine, ap, tick, n, clock, writes, collector = values
    state.set('acc_target_speed', 50.)
    boundary = []
    def invalidate_source():
        boundary.append(len(writes))
        value = deepcopy(state.get('longitudinal_traffic'))
        if corruption == 'cancel':
            state.set('autopilot_active', False)
            return
        if corruption == 'expired':
            value['expires_at'] = clock[0] - .001
        elif corruption == 'future':
            value['observation_timestamp'] = clock[0] + 1.
        else:
            value['context'] = ('previous-activation', *value['context'][1:])
        state.set('longitudinal_traffic', value)
    step(30, 'green', speed=10., progress=0., on_steering=invalidate_source)
    assert boundary
    assert not any(ch == 'aforward' and value > 0 for _, ch, value, _ in writes[boundary[0]:])


@pytest.mark.parametrize('mode', [0, 3])
def test_closed_idle_disturbance_recovers_and_stops_before_target(tmp_path, mode):
    from tools.run_oct11_red_approach_bench import compare
    baseline = compare(tmp_path, mode=mode, speed=35., approach=100., before=True, scenario='disturbance')
    result = compare(tmp_path, mode=mode, speed=35., approach=100., before=False, scenario='disturbance')
    assert result['far_low_speed_s'] < baseline['far_low_speed_s']
    assert result['stop'] and result['stop']['reference_gap_to_target_m'] >= 0.
    assert result['red_entry_overrun_samples'] == 0
    assert result['resumed_without_n']
    assert result['simultaneous_positive_physical_writes'] == 0
    assert result['hold_brake_zero_count'] == 0
    assert result['parking_writes'] == 0
