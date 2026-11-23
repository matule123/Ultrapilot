"""Real placed native reader -> Policy/ACC -> AP -> physical writer regression."""
import struct
from unittest.mock import patch

import pytest

from core.longitudinal import context, publish
from core.sdk.signal_snapshot import SCOPED_LAYOUT, compact
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.signals.test_signal_coverage import real_flow
from tests.signals.test_native_signal_direction import authored_heads, place, scoped_bytes, selection
from tests.test_roundabout_intervention_reporting import pedal


def timing_flow(flow, tmp_path, mode=0):
    with patch('tests.signals.test_signal_coverage.actual_path', side_effect=place):
        values, _ = real_flow(flow, tmp_path, 0, mode, scoped=True)
    state, truck, engine, ap, tick, n, clock, writes, collector = values
    _, heads = authored_heads()
    path, _ = place(tmp_path); entry = path.points[0]
    def step(gen, color, *, speed=3., gear=4, progress=35., other=0., remaining=60., age=0., on_steering=None):
        import math
        distance = state.get('lane_trajectory')['signal_passages']['passages'][0]['entry_progress_m']-progress
        truck.update(x=entry.x+distance*math.sin(entry.heading), z=entry.z+distance*math.cos(entry.heading))
        flow[4](gear, speed, dt=.06)
        packet = state.get('nav_steering_debug'); packet['tracking_progress_m'] = progress
        state.set('nav_steering_debug', packet); state.set('truck_speed_ms', speed)
        actual = state.get('telemetry')['truck']
        engine._signal_reader.buffer = timed_bytes(clock[0]-age, gen, actual['sdkFrameTimeUs'],
                                                  [dict(heads[3], color=color)], remaining)
        engine._signal_reader.mapping_size = SCOPED_LAYOUT.size
        signal = engine._signal_observation(actual, context(state))
        light = signal.get('candidate') or signal.get('stop_candidate')
        publish(state, actual, 'traffic', signal=signal, light=light,
            light_brake=engine._light_brake(light), traffic_brake=other, following=None)
        tick.policy.on_tick(.06); tick.acc.on_tick(.06); ap.on_tick(.06)
        original = engine.controller.set_steering
        def write(value):
            original(value)
            on_steering()
        with patch.object(engine.controller, 'set_steering', write if on_steering else original):
            engine._flush_controls()
        return signal
    return values, step


def timed_bytes(now, generation, frame, heads, remaining):
    data = scoped_bytes(now, generation, frame, heads)
    fields = list(SCOPED_LAYOUT.unpack(data))
    payload = bytearray(fields[10])
    for i in range(len(heads)):
        struct.pack_into('<f', payload, i*48+36, remaining)
    fields[10] = bytes(payload)
    return bytearray(SCOPED_LAYOUT.pack(*fields))


def test_compact_preserves_original_countdown_and_native_yellow_direction(tmp_path):
    _, heads = authored_heads()
    selected, _ = selection(tmp_path, [dict(heads[3], color='green')])
    original = selected['candidate']
    reduced = compact(selected)['candidate']
    assert reduced['time_left'] == original['time_left']
    assert reduced['state'] == original['state']
    assert compact(selected)['observed_at'] == 1000.


@pytest.mark.parametrize('mode', [0, 3])
def test_new_green_releases_moving_signal_chain_without_waiting_for_zero(flow, tmp_path, mode):
    with patch('tests.signals.test_signal_coverage.actual_path', side_effect=place):
        values, _ = real_flow(flow, tmp_path, 0, mode, scoped=True)
    state, truck, engine, ap, tick, n, clock, writes, collector = values
    _, heads = authored_heads()
    path, _ = place(tmp_path); entry = path.points[0]
    def step(gen, color, speed=3., other=0., remaining=60.):
        import math
        distance = state.get('lane_trajectory')['signal_passages']['passages'][0]['entry_progress_m']-35.
        truck.update(x=entry.x+distance*math.sin(entry.heading), z=entry.z+distance*math.cos(entry.heading))
        flow[4](4, speed, dt=.06)
        packet = state.get('nav_steering_debug'); packet['tracking_progress_m'] = 35.
        state.set('nav_steering_debug', packet); state.set('truck_speed_ms', speed)
        actual = state.get('telemetry')['truck']
        engine._signal_reader.buffer = timed_bytes(clock[0], gen, actual['sdkFrameTimeUs'],
                                                  [dict(heads[3], color=color)], remaining)
        engine._signal_reader.mapping_size = SCOPED_LAYOUT.size
        signal = engine._signal_observation(actual, context(state))
        light = signal.get('candidate')
        publish(state, actual, 'traffic', signal=signal, light=light,
            light_brake=engine._light_brake(light), traffic_brake=other, following=None)
        tick.policy.on_tick(.06); tick.acc.on_tick(.06); ap.on_tick(.06); engine._flush_controls()
        assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
        return signal
    step(20, 'red')
    assert state.get('simple_auto_service_hold')
    assert pedal(engine, 'aforward') == 0. and pedal(engine, 'abackward') > 0.
    for gen in range(21, 28): step(gen, 'green')
    assert state.get('simple_auto_service_hold') is None
    assert pedal(engine, 'aforward') > 0. and pedal(engine, 'abackward') == 0.
    assert not any(ch == 'parkingbrake' for _, ch, _, _ in writes)


def test_ending_green_uses_stop_envelope_before_red(flow, tmp_path):
    with patch('tests.signals.test_signal_coverage.actual_path', side_effect=place):
        values, _ = real_flow(flow, tmp_path, 0, 0, scoped=True)
    state, truck, engine, ap, tick, n, clock, writes, collector = values
    _, heads = authored_heads()
    actual = state.get('telemetry')['truck']
    engine._signal_reader.buffer = timed_bytes(clock[0], 30, actual['sdkFrameTimeUs'],
                                               [dict(heads[3], color='green')], 1.)
    engine._signal_reader.mapping_size = SCOPED_LAYOUT.size
    selected = engine._signal_observation(actual, context(state))
    assert selected['candidate']['color'] == 'green'
    assert selected['candidate']['stop_required'] is True
    from core.longitudinal import signal_stop_speed_limit
    assert signal_stop_speed_limit(selected['candidate'], 4.) is not None


@pytest.mark.parametrize('mode', [0, 3])
def test_anticipation_applies_physical_brake_in_preferred_stopping_region(flow, tmp_path, mode):
    values, step = timing_flow(flow, tmp_path, mode)
    state, truck, engine, ap, tick, n, clock, writes, collector = values
    # 42 m to the derived target at 35 km/h: inside preferred 61.8 m reserve,
    # outside existing 26.4 m full-brake planning reserve. No color change.
    signal = step(30, 'green', speed=35./3.6, progress=0., remaining=1.)
    assert signal['candidate']['phase_plan']['status'] == 'ending_green_stop'
    assert state.get('autopilot_active')
    assert pedal(engine, 'aforward') == 0. and pedal(engine, 'abackward') > 0.
    assert state.get('longitudinal_policy')['planned_speed_ms'] < 35./3.6


@pytest.mark.parametrize('kind', ['flicker', 'other_stop', 'short_timer', 'expired', 'duplicate'])
def test_moving_green_cannot_clear_without_complete_witness(flow, tmp_path, kind):
    values, step = timing_flow(flow, tmp_path)
    state, truck, engine, ap, tick, n, clock, writes, collector = values
    step(30, 'red', other=.3 if kind == 'other_stop' else 0.)
    if kind == 'flicker':
        step(31, 'green'); step(32, 'red'); step(33, 'green')
    elif kind == 'expired':
        step(31, 'green', age=.6)
    else:
        for i in range(31, 37):
            step(31 if kind == 'duplicate' else i, 'green',
                 remaining=1. if kind == 'short_timer' else 60.)
    assert pedal(engine, 'aforward') == 0.
    assert state.get('simple_auto_service_hold') or not state.get('autopilot_active')


@pytest.mark.parametrize('remaining', [60., 1., float('nan'), -1.])
@pytest.mark.parametrize('distance', [42., 15., 1.])
def test_timer_decision_retains_original_age_and_does_not_invent_phase(remaining, distance):
    from core.longitudinal import signal_phase_plan
    head = dict(color='green', state=8, time_left=remaining, scope_schema=1,
                distance=distance, passage_length_m=40., passage_speed_ms=10.,
                front_allowance_m=6., junction_standoff_m=2.)
    result = signal_phase_plan(head, dict(speed=35./3.6), 100., 100.2)
    assert result['observed_at'] == 100.
    if remaining == 60.:
        assert not result['stop_required'] and result['remaining_s'] == pytest.approx(59.8)
    elif remaining == 1. and distance < 26.5:
        assert result['status'] == 'green_dilemma'  # coast, not a clearance witness
    else: assert result['stop_required']
    for state in (1, 4):
        yellow = signal_phase_plan(dict(head, color='yellow', state=state), dict(speed=4.), 100., 100.2)
        assert yellow['stop_required'] and yellow['native_state'] == state


def test_planning_dilemma_is_explicit_coast_and_does_not_relaunch_hold(flow, tmp_path):
    values, step = timing_flow(flow, tmp_path)
    engine = values[2]
    signal = step(30, 'green', speed=35./3.6, progress=35., remaining=1.)
    assert signal['candidate']['phase_plan']['status'] == 'green_dilemma'
    assert pedal(engine, 'aforward') == 0.


def test_missing_authored_extent_cannot_certify_scoped_green_reserve():
    from core.longitudinal import signal_phase_plan
    light = dict(color='green',state=8,time_left=60.,scope_schema=1,distance=30.)
    result = signal_phase_plan(light, dict(speed=5.), 100., 100.01)
    assert result['stop_required'] and result['status'] == 'phase_extent_not_verified'


def test_real_timing_decision_survives_existing_integrity_export(flow, tmp_path):
    from core.steering_replay import SteeringReplayBuffer, inspect_replay
    values, step = timing_flow(flow, tmp_path)
    state, truck, engine, ap, tick, n, clock, writes, collector = values
    selected = step(30, 'green', speed=35./3.6, progress=0., remaining=1.)
    saved = engine.controller._pedal_journal.snapshot(include_history=True)
    path = SteeringReplayBuffer(2).export(tmp_path, reason='significant_event', longitudinal=saved)
    checked = inspect_replay(path)
    assert checked['integrity_valid'] and checked['confirmed'] is False
    rows = checked['replay']['longitudinal']['decision_history']['regular_samples']
    row = rows[-1]
    assert row['signal_time_left_s'] == 1. and row['signal_native_state'] == 8
    assert row['signal_observed_at'] == selected['observed_at']
    assert row['signal_generation'] == 30
    assert row['signal_phase_plan'] == selected['candidate']['phase_plan']
    assert row['written_throttle'] == 0. and row['written_brake'] > 0.


def test_countdown_history_keeps_thirty_seconds_without_budget_growth(flow, tmp_path):
    values, step = timing_flow(flow, tmp_path)
    state, truck, engine, ap, tick, n, clock, writes, collector = values
    originals = {}
    for i in range(1000):  # 60 s; supplied SDK, not a vehicle-dynamics claim
        signal = step(30+i, 'red' if i%400<200 else 'green')
        originals[signal['generation']] = (signal['observed_at'], signal['frame_us'])
        assert state.get('autopilot_active')
        writes.clear()  # test assertion history is not a runtime memory budget
    journal = engine.controller._pedal_journal
    saved = journal.snapshot(include_history=True)
    history = saved['decision_history']
    assert history['observed_range_s']['duration'] >= 29.9
    assert history['capture_failures'] == 0
    assert history['byte_budget'] == 1024*1024
    assert history['retained_bytes'] <= history['byte_budget']
    assert saved['retained_bytes'] <= 65536
    last = history['regular_samples'][-1]
    assert (last['signal_observed_at'],last['signal_frame_us']) == originals[last['signal_generation']]
    # 10 Hz summaries are not an every-tick trace. Verify their real unsampled
    # tail instead of falsely assigning the final frame to the previous row.
    assert history['unsampled_tail_s'] <= history['regular_period_s']


def test_green_lost_during_output_cannot_clear_continuous_brake(flow, tmp_path):
    from copy import deepcopy
    values, step = timing_flow(flow, tmp_path)
    state, truck, engine, ap, tick, n, clock, writes, collector = values
    step(30, 'red'); step(31, 'green'); step(32, 'green')
    def new_red():
        prior = deepcopy(state.get('longitudinal_traffic')['signal'])
        clock[0] += .001
        prior.update(observed_at=clock[0], generation=prior['generation']+1, frame_us=prior['frame_us']+16666)
        prior['candidate'].update(color='red', state=2, stop_required=True)
        publish(state, state.get('telemetry')['truck'], 'traffic', signal=prior,
                light=prior['candidate'], light_brake=.3, traffic_brake=0., following=None)
    step(33, 'green', on_steering=new_red)
    assert pedal(engine, 'aforward') == 0. and pedal(engine, 'abackward') > 0.
    assert state.get('simple_auto_service_hold')


@pytest.mark.parametrize('mode', [0, 3])
def test_closed_plant_releases_moving_green_and_brakes_before_phase_change(tmp_path, mode):
    from tools.run_oct10_signal_timing_bench import compare
    before = compare(tmp_path, mode=mode, speed=35., scenario='moving_green', before=True)
    after = compare(tmp_path, mode=mode, speed=35., scenario='moving_green', before=False)
    # Semantic criterion: release while still moving rather than wait for a
    # standstill. No fitted comfort/jerk threshold is introduced by this test.
    first_drive = next(r for r in after['rows'] if r['t']>=after['green_first_at_s'] and r['throttle']>0.)
    assert first_drive['speed_mps'] > .05
    assert after['green_drive_return_s'] < before['green_drive_return_s']
    ending = compare(tmp_path, mode=mode, speed=35., scenario='ending_green', before=False)
    assert any(r['t']<1. and r['native_state']==8 and r['brake']>0. for r in ending['rows'])
    for result in (after, ending):
        assert result['active'] and result['termination_reason'] is None
        assert result['simultaneous_positive_physical_writes'] == 0
        assert result['parking_writes'] == result['red_entry_overrun_samples'] == 0
