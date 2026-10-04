"""Legacy semaphore bytes are candidates, never producer-proven clearance.

The in-memory fixture uses the shipped producer ABI, not a replacement sensor.
These tests preserve the blocked release contract; they do not prove stop-and-go.
"""
import struct

import pytest

from core.longitudinal import publish
from core.sdk.ets2la_data import ETS2LAData, _SEM, _SEM_SIZE, nearest_light_ahead
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_continuous_service_stop import continuous_stop
from tests.test_roundabout_intervention_reporting import pedal


def semaphore_buffer(state=8, signal_id=19, x=0., y=10., z=-5.):
    # Quaternion w,y,x,z = 0,0,1,0 faces the truck approaching heading zero.
    record = struct.pack('=' + _SEM, x, y, z, 0, 0, 0., 0., 1., 0.,
                         1, 10., state, signal_id)
    assert len(record) == 48
    return bytearray(record + bytes(_SEM_SIZE-len(record)))


def reader_for(data):
    reader = ETS2LAData()
    reader._ensure = lambda: None  # No live mapping or game process is opened.
    reader._sem_buf = data
    return reader


def test_repeated_real_abi_reads_do_not_manufacture_source_generation_or_time():
    reader = reader_for(semaphore_buffer())
    first = reader.read_traffic_lights()
    assert first == reader.read_traffic_lights()
    assert len(first) == 1 and first[0]['id'] == 19 and first[0]['color'] == 'green'
    assert set(first[0]) == {
        'x', 'y', 'z', 'tile_x', 'tile_z', 'yaw', 'state', 'color', 'time_left', 'id'}
    # No truck/receiver time, timer countdown, or content hash is source freshness.
    assert not any(k in first[0] for k in ('source_timestamp', 'generation',
                   'session', 'source_game_session_id', 'lane_id', 'route_relevant'))


def test_color_change_in_real_abi_does_not_supply_missing_source_contract():
    data = semaphore_buffer(state=2)
    reader = reader_for(data)
    red = reader.read_traffic_lights()[0]
    data[:] = semaphore_buffer(state=8)
    green = reader.read_traffic_lights()[0]
    assert red['color'] == 'red' and green['color'] == 'green'
    assert red['id'] == green['id']
    assert set(red) == set(green)  # A changed color still has no origin time/session.


def test_geometric_candidate_does_not_prove_directed_lane_or_height_membership():
    light = reader_for(semaphore_buffer(x=4., y=50.)).read_traffic_lights()
    selected = nearest_light_ahead(light, (0., 0.), 0.)
    # The selector sees XY heading/proximity only; it has no truck height,
    # LanePath, connector, LaneId or route identity input. Do not reinterpret
    # its result as producer confirmation for a route-specific green release.
    assert selected is not None and selected['y'] == 50.
    assert selected['lateral_distance'] == 4.
    assert 'route_relevant' not in selected and 'lane_id' not in selected


@pytest.mark.parametrize('fault', ['unchanged', 'changed_color', 'missing',
                                 'other_signal', 'unknown_color'])
def test_reader_to_arbitration_to_physical_backend_never_releases_unproven_green(flow, fault):
    values, writes = continuous_stop(flow)
    state, truck, engine, ap, update, n, clock, acc, collected = values
    original = state.get('simple_auto_service_hold')['stop_reason']
    data = semaphore_buffer(state=2 if fault == 'changed_color' else 8,
                            signal_id=20 if fault == 'other_signal' else 19)
    reader = reader_for(data)
    reader.read_traffic_lights()  # Earlier observation, not a published generation.
    if fault == 'changed_color':
        data[:] = semaphore_buffer(state=8)
    elif fault == 'missing':
        data[:] = bytes(_SEM_SIZE)
    elif fault == 'unknown_color':
        data[:] = semaphore_buffer(state=0)
    count = len(writes)
    for _ in range(12):
        update(0, 0., dt=.1)
        light = nearest_light_ahead(reader.read_traffic_lights(), (0., 0.), 0.)
        publish(state, state.get('telemetry')['truck'], 'traffic',
                traffic_brake=0., light_brake=engine._light_brake(light), light=light,
                following=None)
        publish(state, state.get('telemetry')['truck'], 'acc', throttle=.4,
                brake=0., emergency=False, control_target_kmh=50.)
        ap.on_tick(.1)
        engine._flush_controls()
        assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
        assert state.get('simple_auto_service_hold')['stop_reason'] == original
        assert state.get('autopilot_control_state') == 'planned_wait'
        assert pedal(engine, 'aforward') == 0 and pedal(engine, 'abackward') > 0
    assert all(v > 0 for _, name, v in writes[count:] if name == 'abackward')
    assert all(v == 0 for _, name, v in writes[count:] if name == 'aforward')
    assert state.get('simple_auto_service_hold')['automatic_restart_supported'] is False

