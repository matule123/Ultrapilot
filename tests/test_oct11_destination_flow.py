"""Actual Map/producers/AP/physical Controller, not a zero-distance arrival inference."""
from unittest.mock import patch
from types import SimpleNamespace

import pytest

from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_rolling_longitudinal_authority import rolling  # noqa: F401
from tests.test_oct10_signal_timing import timing_flow
from tests.test_roundabout_intervention_reporting import pedal


@pytest.mark.parametrize('mode', [0, 3])
def test_destination_envelope_starts_before_fixed_35m_flag(flow, tmp_path, mode):
    values, step = timing_flow(flow, tmp_path, mode)
    state, truck, engine, ap, tick, n, clock, writes, collector = values
    state.set('acc_target_speed', 80.)
    state.set('game_gps_navigation_active', True)
    truck['routeDistance'] = 60.
    state.set('navigation_arrival_pending', False)
    step(30, 'green', speed=50./3.6, progress=0.)
    assert state.get('autopilot_active')
    assert state.get('longitudinal_acc')['constrained_speed_kmh'] < 50.
    assert pedal(engine, 'abackward') > 0.
    assert pedal(engine, 'aforward') == 0.


@pytest.mark.parametrize('mode', [0, 3])
def test_confirmed_positive_destination_distance_stops_then_normal_release(flow, tmp_path, mode):
    values, step = timing_flow(flow, tmp_path, mode)
    state, truck, engine, ap, tick, n, clock, writes, collector = values
    state.set('acc_target_speed', 50.)
    state.set('game_gps_navigation_active', True)
    for i, (distance, speed) in enumerate(((40., 10.), (20., 7.), (8., 3.), (2., 1.), (1., .4))):
        truck['routeDistance'] = distance
        step(30+i, 'green', speed=speed, progress=0.)
        assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    assert pedal(engine, 'abackward') > 0.
    truck['routeDistance'] = 1.
    step(36, 'green', speed=0., gear=0 if mode == 0 else 4, progress=0.)
    assert not state.get('autopilot_active')
    assert state.get('autopilot_control_state') == 'arrived'
    assert state.get('autopilot_intervention') is None
    assert pedal(engine, 'aforward') == pedal(engine, 'abackward') == 0.
    assert not any(ch in ('parkingbrake', 'hazard') and value for _, ch, value, _ in writes)


@pytest.mark.parametrize('remaining', [20., 0.])
def test_engine_keeps_positive_near_destination_route_buffer(rolling, remaining):
    state, engine, ap, acc, policy, tick, observe, n, physical, writes, clock = rolling
    window = state.get('game_route_node_uids')
    truck = state.get('telemetry')['truck']
    from core.navigation.navigation_intent import NavigationIntentTracker
    original = state.get('lane_trajectory')
    engine.running = True
    engine._last_game_route_distance = 30.
    engine._last_navigation_buffer_log = None
    engine._last_route_signature = None
    engine._had_game_destination = True
    engine._navigation_intent_tracker = NavigationIntentTracker()
    engine._last_runtime_preflight = clock[0]
    engine.fps = 60
    engine._last_nav_log_seq = engine._last_autopilot_log_seq = None
    state.set('navigation_log_event', {})
    state.set('autopilot_log_event', {})
    items = [dict(uid=u, distance=20.+i*.1) for i,u in enumerate(window)]
    from core.navigation.navigation_intent import destination_identity
    engine._navigation_intent_tracker.update(items, destination_present=True,
        destination=destination_identity('', items), context=(state.get('game_session_id'),
        state.get('active_map_key'), state.get('active_dataset_fingerprint')))
    read_calls = []
    def read():
        read_calls.append(True)
        engine.running = False
        return items
    engine.ets2la_route = SimpleNamespace(read=read)
    engine.ets2la = SimpleNamespace()
    engine.settings = SimpleNamespace(settings={})
    engine.camera_snapshot_producer = SimpleNamespace(read=lambda *a: {})
    frame = dict(truck, routeDistance=remaining)
    with patch.object(engine, '_telemetry_snapshot', return_value=(True,
            dict(truck=frame, raw=dict(sdkActive=True)), clock[0], 1)), \
            patch.object(engine, '_camera_diagnostic'), patch.object(engine, '_autostart_truck'), \
            patch.object(engine, '_check_hotkey'), patch.object(engine, '_process_autopilot_command'), \
            patch('core.engine.production_data_availability', side_effect=StopIteration), \
            patch('core.engine.time.sleep', side_effect=lambda *_: setattr(engine,'running',False)):
        with pytest.raises(StopIteration):
            engine.run_loop()  # End only after the real navigation publication.
    if remaining > 0.:
        assert read_calls  # Old code discards a real positive <=25 m destination.
        assert state.get('lane_trajectory')['valid'], state.get('navigation_status')
        assert state.get('lane_trajectory')['route_build_id'] == original['route_build_id']
    else:
        assert not read_calls
        assert not state.get('lane_trajectory')['valid']
        assert state.get('autopilot_control_state') != 'arrived'


@pytest.mark.parametrize('fault', ['R', 'stale', 'identity', 'manual', 'backend', 'release_backend', 'other', 'zero', 'missing'])
def test_destination_fault_or_other_stop_cannot_be_successful_arrival(flow, tmp_path, fault):
    values, step = timing_flow(flow, tmp_path)
    state, truck, engine, ap, tick, n, clock, writes, collector = values
    state.set('game_gps_navigation_active', True)
    for gen, distance, speed in ((30,40.,10.), (31,8.,3.), (32,1.,.4)):
        truck['routeDistance'] = distance
        step(gen, 'green', speed=speed, progress=0., other=.3 if fault == 'other' else 0.)
    truck['routeDistance'] = 1.
    if fault == 'R':
        step(33, 'green', speed=0., gear=-1, progress=0.)
    elif fault in ('zero', 'missing'):
        if fault == 'zero':
            truck['routeDistance'] = 0.
        else:
            truck.pop('routeDistance')
        step(33, 'green', speed=0., gear=0, progress=0.)
    elif fault == 'manual':
        n(); engine._flush_controls()
    elif fault == 'backend':
        engine.controller.scs.connected = False
        step(33, 'green', speed=0., gear=0, progress=0.)
    elif fault == 'release_backend':
        release = engine.controller.release_all
        def fail_release():
            release()
            engine.controller.scs.connected = False
        with patch.object(engine.controller, 'release_all', fail_release):
            step(33, 'green', speed=0., gear=0, progress=0.)
    elif fault == 'identity':
        state.set('navigation_intent_id', 'foreign')
        engine._flush_controls()
    elif fault == 'stale':
        clock[0] += .6
        engine._flush_controls()
    else:
        step(33, 'green', speed=0., gear=0, progress=0., other=.3)
    assert state.get('autopilot_control_state') != 'arrived'
    assert pedal(engine, 'aforward') == 0.


def test_existing_source_codec_keeps_original_gps_remainder_without_new_reads():
    from core.navigation.longitudinal_diagnostics import local_source_snapshot, pack_source, unpack_source
    original = dict(speed=4., gear=4, sdkFrameTimeUs=123, routeDistance=20., routeTime=3.,
        _control_observation=dict(schema_version=1, sdk_frame_us=123, observed_at=100., valid=True))
    captured = local_source_snapshot(original)
    original['routeDistance'] = 0.
    restored = unpack_source(pack_source(captured))
    assert restored['gps_remainder_m'] == 20.
    assert restored['gps_route_time_s'] == 3.
    assert restored['observation_timestamp'] == 100.
