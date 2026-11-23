"""Actual reader/policy/AP/Engine/Controller flow; modeled SDK response only."""
import pytest

from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.signals.test_signal_timing import timing_flow
from tests.test_roundabout_intervention_reporting import pedal
from tests.lifecycle.test_joint_regressions import joint  # noqa: F401


@pytest.mark.parametrize('mode', [0, 3])
@pytest.mark.parametrize('green_speed', [2./3.6, .08])
@pytest.mark.parametrize('ipc_delay', [0., .025])
def test_green_during_approach_restarts_admitted_zero_ratio(flow, tmp_path, mode, green_speed, ipc_delay):
    values, step = timing_flow(flow, tmp_path, mode)
    state, truck, engine, ap, tick, n, clock, writes, collector = values
    step(30, 'red', speed=3., progress=35.)
    step(31, 'red', speed=.99, progress=39.)
    assert state.get('simple_auto_service_hold')['phase'] == 'approaching'
    step(32, 'yellow', speed=.72, progress=40.4)
    start = len(writes)
    for gen in range(33, 52):
        # More than the fixed 500 ms zero-ratio bridge: the modeled gearbox
        # confirms forward again only after actual automatic drive is allowed.
        speed = green_speed if gen < 45 else .30
        gear = 0 if mode == 0 and gen < 45 else 4
        def delayed_boundary(): clock[0] += ipc_delay
        step(gen, 'green', speed=speed, gear=gear, progress=40.5+(gen-33)*.01,
             on_steering=delayed_boundary)
        assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    assert state.get('simple_auto_service_hold') is None
    assert pedal(engine, 'aforward') > 0. and pedal(engine, 'abackward') == 0.
    assert not any(ch == 'parkingbrake' for _, ch, _, _ in writes[start:])


@pytest.mark.parametrize('mode', [0, 3])
def test_obstacle_brake_from_motion_survives_zero_ratio_stop(flow, tmp_path, mode):
    values, step = timing_flow(flow, tmp_path, mode)
    state, truck, engine, ap, tick, n, clock, writes, collector = values
    # A fresh non-signal traffic demand, as in the second incident. Not a
    # claim that the recorded crossing actor was truly on a collision course.
    step(30, 'green', speed=4., progress=35., other=.48)
    start = len(writes)
    for gen, speed in enumerate((2.35, 1.53, .877, .246, .039, 0., 0.), 31):
        step(gen, 'green', speed=speed, gear=0 if mode == 0 and speed < .3 else 4,
             progress=35., other=.53)
        assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
        assert pedal(engine, 'aforward') == 0. and pedal(engine, 'abackward') > 0.
    assert state.get('simple_auto_service_hold')['phase'] == 'holding'
    # Disappearance is not clearance; a green signal cannot clear an obstacle.
    for gen in range(38, 44):
        step(gen, 'green', speed=0., gear=0 if mode == 0 else 4, progress=35., other=0.)
        assert state.get('autopilot_active')
        assert pedal(engine, 'aforward') == 0. and pedal(engine, 'abackward') > 0.
    assert all(value > 0 for _, ch, value, _ in writes[start:] if ch == 'abackward')
    n(); engine._flush_controls()
    assert not state.get('autopilot_active')
    assert pedal(engine, 'aforward') == pedal(engine, 'abackward') == 0.


@pytest.mark.parametrize('fault', ['R', 'backward', 'stale', 'cancel', 'backend', 'identity'])
def test_moving_green_does_not_override_real_fault(flow, tmp_path, fault):
    values, step = timing_flow(flow, tmp_path)
    state, truck, engine, ap, tick, n, clock, writes, collector = values
    step(30, 'red', speed=3., progress=35.)
    step(31, 'red', speed=.99, progress=39.)
    step(32, 'yellow', speed=.72, progress=40.4)
    step(33, 'green', speed=.43, gear=0, progress=40.5)
    if fault == 'cancel': n(); engine._flush_controls()
    if fault == 'backend': engine.controller.scs.connected = False
    if fault == 'identity':
        lane = state.get('lane_trajectory'); lane['route_build_id'] = 'foreign'
        state.set('lane_trajectory', lane)
    start = len(writes)
    for gen in range(34, 40):
        step(gen, 'green', speed=-.2 if fault == 'backward' else .43,
             gear=-1 if fault == 'R' else 0, progress=40.5,
             age=.6 if fault == 'stale' else 0.)
    assert not any(ch == 'aforward' and value > 0. for _, ch, value, _ in writes[start:])
    assert pedal(engine, 'aforward') == 0.


def test_native_crossing_demand_has_physical_hold_witness(joint):
    import math
    from types import SimpleNamespace
    from tests.test_acc_following import capture
    from core.navigation.traffic_producer import capture_traffic
    from core.longitudinal import context
    state, engine, ap, acc, policy, tick, observe, n, physical, writes, clock = joint
    for gear, speed in ((4, 4.), (4, 2.), (4, .5), (0, .2), (0, .039), (0, 0.)):
        if state.get('ets2_transmission_mode')['mode'] == 3: gear = 4
        tick(gear=gear, speed=speed, z=15., pedals=False)
        truck = state.get('telemetry')['truck']
        raw = capture([dict(id=91, x=8., y=10., z=20., yaw=math.pi/2., speed=2.)], clock[0])
        consumed = capture_traffic(SimpleNamespace(_traffic_buf=raw.moving, _parked_buf=raw.parked),
                                   str(context(state)[1]), clock[0])
        following, brake = engine._traffic_control_observation(consumed, truck, context(state), [])
        assert brake > 0., following
        engine._publish_traffic_control(truck, truck['_control_observation']['observed_at'],
            context(state), [], consumed, following, brake,
            dict(valid=False, candidate=None, coverage={}), None)
        policy.on_tick(.033); acc.on_tick(.033); ap.on_tick(.033); engine._flush_controls()
        assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
        assert physical('aforward') == 0. and physical('abackward') > 0.
    hold = state.get('simple_auto_service_hold')
    assert hold['phase'] == 'holding' and hold['other_stop_unverified']
    assert not hold['automatic_restart_supported']
