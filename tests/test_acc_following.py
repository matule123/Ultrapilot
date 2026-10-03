"""Phase 7.3: source limitations and physical-output counterexamples."""
import math
import struct

import pytest

from core.engine import UltraPilotEngine
from tests.test_control_safety_regressions import State
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_longitudinal_arbitration import strict_flow
from core.longitudinal import publish
from core.acc_following import RouteLeadSelector, following_demand, observation
from core.navigation.traffic_producer import TrafficCapture, capture_traffic
from core.sdk.ets2la_data import _TRAFFIC_FMT, _PARKED_FMT, ETS2LAData


def arc(radius=60., direction=1):
    return [[direction*radius*(1-math.cos(i*.01)), 0., -radius*math.sin(i*.01)]
            for i in range(158)]


def car_on(points, i, actor_id=7, speed=8., dx=0., dy=0.):
    a, b = points[i:i+2]
    return dict(id=actor_id, x=a[0]+dx, y=a[1]+dy, z=a[2],
                yaw=math.atan2(-(b[0]-a[0]), -(b[2]-a[2])), speed=speed)


def capture(actors, at):
    moving = [0.] * (46*40)
    for i, a in enumerate(actors):
        b = i*46
        moving[b:b+12] = [a['x'], a['y'], a['z'], math.cos(a['yaw']/2),
                          0., math.sin(a['yaw']/2), 0., 2., 2., 4., a['speed'], 0.]
        moving[b+12:b+16] = [0, a['id'], 0, 0]
    # Shorts/bytes in the actual ABI require integer slots, including empty rows.
    for i in range(40):
        b = i*46
        moving[b+12:b+16] = [int(v) for v in moving[b+12:b+16]]
    parked = [0.]*480
    for i in range(40):
        parked[i*12+10:i*12+12] = [0, 0]
    return TrafficCapture('session', at, struct.pack(_TRAFFIC_FMT, *moving),
                          struct.pack(_PARKED_FMT, *parked), True)


def route_input(state, engine, truck, points):
    from core.longitudinal import context
    binding = context(state)
    lane = state.get('lane_trajectory')
    lane.update(valid=True, points=points)
    state.set('lane_trajectory', lane)
    identity = {k: lane[k] for k in ('source_game_session_id', 'source_map_key',
        'source_dataset_fingerprint', 'navigation_intent_id', 'revision', 'route_build_id')}
    state.set('lane_trajectory_identity', identity)
    state.set('lane_trajectory_publication_token', 'test-geometry')
    debug = state.get('nav_steering_debug')
    debug.update(authority_valid=True, trajectory_identity=identity, tracking_progress_m=0.)
    state.set('nav_steering_debug', debug)
    truck.update(x=points[0][0], y=0., z=points[0][2], rotation=0.)
    state.set('telemetry', {'truck': truck})
    return context(state)


@pytest.mark.parametrize('direction', [-1, 1])
def test_curve_lead_outside_old_straight_strip_and_adjacent_rejection(direction):
    points = arc(direction=direction)
    selector = RouteLeadSelector()
    selector.prepare(points, ('build',))
    lead = car_on(points, 45, speed=4.)
    assert abs(lead['x']) > 2.6  # old straight lane-strip misses it
    ego = dict(x=0., y=0., z=0., rotation=0., speed=15.)
    selected = selector.select([lead], ego, 0.)
    assert selected['target_id'] == '7'
    assert selected['speed_cap_mps'] < ego['speed']
    assert selected['confirmed'] is False
    # A nearby adjacent centreline, opposite direction and another deck.
    neighbour = car_on(points, 20, actor_id=8, dx=3.5*direction)
    opposite = dict(car_on(points, 25, actor_id=9), yaw=lead['yaw']+math.pi)
    bridge = car_on(points, 20, actor_id=10, dy=8.)
    behind = dict(id=11, x=0., y=0., z=5., yaw=0., speed=4.)
    result = selector.select([bridge, neighbour, opposite, behind, lead], ego, 0.)
    assert result['target_id'] == '7'


def test_retention_order_determinism_and_cut_in_cannot_be_hidden():
    points = [[0., 0., -float(i)] for i in range(121)]
    ego = dict(x=0., y=0., z=0., rotation=0., speed=12.)
    s = RouteLeadSelector()
    s.prepare(points, ('build',))
    a, b = car_on(points, 40), car_on(points, 41, actor_id=8)
    assert s.select([a, b], ego, 0.)['target_id'] == '7'
    a = car_on(points, 42)
    retained = s.select([b, a], ego, 0.)
    assert retained['target_id'] == '7'
    assert retained == s.select([a, b], ego, 0.)
    cutin = car_on(points, 8, actor_id=9, speed=0.)
    result = s.select([a, cutin, b], ego, 0.)
    assert result['target_id'] == '9'
    assert result['emergency']
    assert result['speed_cap_mps'] == 0.


def test_source_capture_has_no_invented_publisher_time_or_body_size():
    c = capture([dict(id=4, x=1., y=0., z=-30., yaw=0., speed=6.)], 100.)
    raw = list(struct.unpack(_TRAFFIC_FMT, c.moving))
    raw[7] = 0.
    c = TrafficCapture(c.session, c.observed_at, struct.pack(_TRAFFIC_FMT, *raw), c.parked, True)
    result = observation(c, 100.01)
    assert result['status'] == 'observed'
    assert result['source_timestamp'] is result['source_sequence'] is None
    assert not result['complete'] and not result['atomic'] and not result['confirmed']
    assert result['actors'][0]['dimensions_whl'][0] == 0.
    assert observation(c, 100.101)['status'] == 'stale_receiver_capture'


@pytest.mark.parametrize('fault', ['missing', 'changing', 'duplicate_id', 'nan', 'bad_rotation'])
def test_source_failures_are_not_empty_road(fault):
    a = dict(id=4, x=1., y=0., z=-30., yaw=0., speed=6.)
    c = capture([a, dict(a, z=-40.)] if fault == 'duplicate_id' else [a], 100.)
    if fault in ('missing', 'changing'):
        c = TrafficCapture(c.session, c.observed_at, c.moving,
                           None if fault == 'missing' else c.parked, fault != 'changing')
    else:
        raw = list(struct.unpack(_TRAFFIC_FMT, c.moving))
        if fault == 'nan':
            raw[10] = float('nan')
        if fault == 'bad_rotation':
            raw[3:7] = [0.]*4
        c = TrafficCapture(c.session, c.observed_at, struct.pack(_TRAFFIC_FMT, *raw), c.parked, True)
    assert observation(c, 100.01)['status'] not in ('observed', 'empty_unproven_coverage')


def test_equal_speed_desired_gap_is_not_an_unconditional_brake():
    assert following_demand(32., 10., 10.) == dict(speed_cap_mps=10.,
                                                   desired_gap_m=32., emergency=False)


def test_very_close_forward_actor_is_an_immediate_hazard_not_absent():
    points = [[0., 0., -float(i)] for i in range(121)]
    selector = RouteLeadSelector()
    selector.prepare(points, ('build',))
    result = selector.select([car_on(points, 1, speed=0.)],
        dict(x=0., y=0., z=0., rotation=0., speed=12.), 0.)
    assert result['status'] == 'candidate'
    assert result['emergency']
    assert result['speed_cap_mps'] == 0.


def test_repeated_route_occurrence_is_ambiguous_and_not_confirmed():
    points = [[0., 0., 0.], [0., 0., -50.], [50., 0., -50.],
              [50., 0., 0.], [0., 0., 0.], [0., 0., -50.]]
    selector = RouteLeadSelector()
    selector.prepare(points, ('loop',))
    result = selector.select([dict(id=7, x=0., y=0., z=-25., yaw=0., speed=5.)],
        dict(x=0., y=0., z=0., rotation=0., speed=10.), 0.)
    # The local 120 m horizon never jumps to the next occurrence at s=225.
    assert result['gap_m'] == 25.
    assert not result['confirmed']
    assert selector._project(dict(x=0., y=0., z=-25., yaw=0.), 0., 250.) is None


def test_missing_height_or_direction_does_not_create_a_route_candidate():
    points = [[0., 0., -float(i)] for i in range(121)]
    selector = RouteLeadSelector()
    selector.prepare(points, ('build',))
    for missing in ('y', 'yaw', 'speed', 'id'):
        a = car_on(points, 40)
        del a[missing]
        result = selector.select([a], dict(x=0., y=0., z=0., rotation=0., speed=10.), 0.)
        assert result['status'] != 'candidate'


def test_fixed_capture_cannot_prove_publisher_progress():
    c = capture([dict(id=4, x=1., y=0., z=-30., yaw=0., speed=6.)], 100.)
    later = TrafficCapture(c.session, 110., c.moving, c.parked, True)
    result = observation(later, 110.01)
    assert result['status'] == 'observed'
    assert result['source_timestamp'] is None
    assert result['source_sequence'] is None
    assert not result['confirmed']  # Receiver polling is explicitly NOT freshness proof.


@pytest.mark.parametrize('mode', [0, 3])
def test_actual_capture_selector_acc_arbitration_engine_physical_chain(flow, mode):
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow, mode=mode)
    update(8, 15.)
    n()
    current = state.get('telemetry')['truck']
    points = arc()
    binding = route_input(state, engine, current, points)
    c = capture([car_on(points, 45, speed=4.)], clock[0])
    # Actual shared-buffer capture operation and decoder, no manual target stub.
    reader = ETS2LAData()
    reader._traffic_buf, reader._parked_buf = c.moving, c.parked
    captured = capture_traffic(reader, str(binding[1]), clock[0])
    following = engine._route_lead_observation(captured, current, binding)
    assert following['status'] == 'candidate', following
    publish(state, current, 'traffic', traffic_brake=0., light_brake=0.,
            light=None, following=following)
    acc.on_tick(.033)
    ap.on_tick(.033)
    engine._flush_controls()
    assert state.get('longitudinal_acc')['constrained_speed_kmh'] < 15.*3.6
    assert engine.controller.throttle == 0.
    assert engine.controller.brake > 0.
    applied = state.get('longitudinal_applied')
    assert applied['throttle'] == engine.controller.throttle
    assert applied['brake'] == engine.controller.brake
    assert applied['written_at'] == clock[0]


@pytest.mark.parametrize('lost', ['missing', 'empty', 'expired', 'route_unavailable'])
def test_target_loss_latches_no_drive_without_reusing_old_lease(flow, lost):
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow)
    update(8, 10.)
    n()
    candidate = dict(status='candidate', target_id='7', gap_m=50., speed_mps=10.,
                     speed_cap_mps=10., emergency=False, confirmed=False)
    publish(state, state.get('telemetry')['truck'], 'traffic',
            traffic_brake=0., light_brake=0., light=None, following=candidate)
    acc.on_tick(.033)
    original = state.get('longitudinal_traffic')
    update(8, 10.)
    if lost == 'missing':
        state.set('longitudinal_traffic', None)
    elif lost == 'expired':
        original['expires_at'] = clock[0]-.01
        state.set('longitudinal_traffic', original)
    else:
        publish(state, state.get('telemetry')['truck'], 'traffic', traffic_brake=0.,
            light_brake=0., light=None, following=dict(status=lost, confirmed=False))
    acc.on_tick(.033)
    assert state.get('longitudinal_acc')['valid'] is False
    assert state.get('longitudinal_acc')['throttle'] == 0.
    ap.on_tick(.033)
    engine._flush_controls()
    assert engine.controller.throttle == 0.


def test_candidate_ceiling_cannot_raise_curve_limit_and_emergency_is_same_flush(flow):
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow)
    update(8, 10.)
    n()
    current = state.get('telemetry')['truck']
    publish(state, current, 'traffic', traffic_brake=0., light_brake=0., light=None,
            following=dict(status='candidate', target_id='7', speed_cap_mps=15.))
    publish(state, current, 'road', speed_cap_kmh=20.)
    acc.on_tick(.033)
    ap.on_tick(.033)
    assert state.get('longitudinal_acc')['constrained_speed_kmh'] <= 20.
    publish(state, current, 'traffic', traffic_brake=1., light_brake=0., light=None)
    engine._flush_controls()
    assert engine.controller.throttle == 0.
    assert engine.controller.brake == 1.


def test_legacy_bridge_actor_is_not_a_same_lane_lead():
    engine = UltraPilotEngine.__new__(UltraPilotEngine)
    engine.shared_state = State({'truck_speed_ms': 15.,
                                  'telemetry': {'truck': {'y': 0.}}})
    brake = engine._lead_brake([dict(x=0., y=8., z=-12., yaw=0., speed=0.)],
                               (0., 0.), 0., 15.)
    assert brake == 0.
    assert engine.shared_state.get('lead_distance') is None


def test_missing_actor_speed_is_not_a_measured_stationary_lead():
    engine = UltraPilotEngine.__new__(UltraPilotEngine)
    engine.shared_state = State({'truck_speed_ms': 15.})
    assert engine._lead_brake([dict(x=0., z=-12., yaw=0.)], (0., 0.), 0., 15.) == 0.


def test_lost_observed_acc_target_does_not_restore_physical_drive(flow):
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow)
    update(8, 10.)
    n()
    publish(state, state.get('telemetry')['truck'], 'traffic',
            traffic_brake=0., light_brake=0., light=None,
            following=dict(status='candidate', target_id='moving:7', gap_m=40.,
                           speed_mps=8., speed_cap_mps=8., emergency=False,
                           confirmed=False, reason='receiver observation only'))
    acc.on_tick(.033)
    ap.on_tick(.033)
    # Buffer failure after a candidate must not become clear-road acceleration.
    update(8, 10.)
    state.set('longitudinal_traffic', None)
    acc.on_tick(.033)
    ap.on_tick(.033)
    engine._flush_controls()
    assert engine.controller.throttle == 0.
    assert 'target' in state.get('longitudinal_acc')['speed_control_reason']


def test_buffer_loss_between_plugin_ticks_revokes_old_positive_drive(flow):
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow)
    update(8, 10.)
    n()
    publish(state, state.get('telemetry')['truck'], 'traffic',
            traffic_brake=0., light_brake=0., light=None,
            following=dict(status='candidate', target_id='7', gap_m=80.,
                           speed_mps=15., speed_cap_mps=20.))
    acc.on_tick(.033)
    ap.on_tick(.033)
    engine._flush_controls()
    assert engine.controller.throttle > 0.
    state.set('longitudinal_traffic', None)
    engine._flush_controls()
    assert engine.controller.throttle == 0.


def test_source_reappearance_cannot_erase_unacknowledged_target_loss(flow):
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow)
    update(8, 10.)
    n()
    def offer():
        publish(state, state.get('telemetry')['truck'], 'traffic', traffic_brake=0.,
            light_brake=0., light=None,
            following=dict(status='candidate', target_id='7', speed_cap_mps=20.))
    offer()
    acc.on_tick(.033)
    state.set('longitudinal_traffic', None)
    acc.on_tick(update(8, 10.))
    assert not state.get('longitudinal_acc')['valid']
    offer()
    acc.on_tick(.033)
    assert not state.get('longitudinal_acc')['valid']
    assert state.get('longitudinal_acc')['throttle'] == 0.
    assert 'target unavailable' in state.get('acc_following_status')


def test_route_change_during_projection_cannot_publish_previous_candidate(flow):
    from unittest.mock import patch
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow)
    update(8, 10.)
    current = state.get('telemetry')['truck']
    points = arc()
    binding = route_input(state, engine, current, points)
    c = capture([car_on(points, 45)], clock[0])
    c = TrafficCapture(str(binding[1]), c.observed_at, c.moving, c.parked, c.stable)
    original = RouteLeadSelector.select
    def changed(selector, *args):
        result = original(selector, *args)
        state.set('navigation_intent_id', 'other')
        return result
    with patch.object(RouteLeadSelector, 'select', changed):
        assert engine._route_lead_observation(c, current, binding)['status'] != 'candidate'


def test_wrong_receiver_session_cannot_be_relabelled(flow):
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow)
    current = state.get('telemetry')['truck']
    binding = route_input(state, engine, current, arc())
    c = capture([car_on(arc(), 45)], clock[0])
    assert c.session != str(binding[1])
    result = engine._route_lead_observation(c, current, binding)
    assert result['status'] == 'traffic_receiver_session_changed'


def test_low_speed_following_requires_driver_not_automatic_resume(flow):
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow)
    update(8, .5)
    n()
    publish(state, state.get('telemetry')['truck'], 'traffic',
            traffic_brake=0., light_brake=0., light=None,
            following=dict(status='candidate', target_id='7', speed_cap_mps=0.))
    acc.on_tick(.033)
    assert state.get('longitudinal_acc')['valid'] is False
    assert 'stop-and-go unavailable' in state.get('longitudinal_acc')['speed_control_reason']


def test_emergency_is_not_masked_by_latched_source_loss(flow):
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow)
    update(8, 10.)
    n()
    publish(state, state.get('telemetry')['truck'], 'traffic',
            traffic_brake=0., light_brake=0., light=None,
            following=dict(status='candidate', target_id='7', speed_cap_mps=20.))
    acc.on_tick(.033)
    ap.on_tick(.033)
    state.set('longitudinal_traffic', None)
    acc.on_tick(update(8, 10.))
    assert acc._following_fault
    publish(state, state.get('telemetry')['truck'], 'traffic',
            traffic_brake=1., light_brake=0., light=None)
    acc.on_tick(.033)
    assert state.get('longitudinal_acc')['emergency']
    ap.on_tick(.033)
    engine._flush_controls()
    assert engine.controller.brake == 1.
    assert engine.controller.throttle == 0.


def test_cached_geometry_does_not_rebuild_or_copy_on_each_traffic_sample():
    selector = RouteLeadSelector()
    points = [[0., 0., -float(i)] for i in range(1001)]
    selector.prepare(points, ('build',))
    edges = selector.edges
    class Unreadable:
        def __len__(self):
            raise AssertionError('unchanged geometry must not be reread')
    selector.prepare(Unreadable(), ('build',))
    assert selector.edges is edges
    selector.prepare(points, ('other-build',))
    assert selector.edges is not edges
    assert selector.target_id is None


@pytest.mark.parametrize('progress', [float('nan'), float('inf'), -1., 500.])
def test_invalid_progress_is_not_route_authority(progress):
    selector = RouteLeadSelector()
    selector.prepare([[0., 0., 0.], [0., 0., -120.]], ('build',))
    result = selector.select([dict(id=7, x=0., y=0., z=-25., yaw=0., speed=5.)],
        dict(x=0., y=0., z=0., rotation=0., speed=10.), progress)
    assert result['status'] == 'invalid_route_progress'


def test_route_candidate_expiry_inherits_old_calculation_age(flow):
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow)
    current = state.get('telemetry')['truck']
    binding = route_input(state, engine, current, arc())
    debug = state.get('nav_steering_debug')
    debug['observation_timestamp'] = clock[0]-.45
    state.set('nav_steering_debug', debug)
    c = capture([car_on(arc(), 45)], clock[0])
    c = TrafficCapture(str(binding[1]), c.observed_at, c.moving, c.parked, c.stable)
    result = engine._route_lead_observation(c, current, binding)
    assert result['status'] == 'candidate'
    assert result['expires_at'] == pytest.approx(clock[0]+.05)


def test_closed_loop_following_and_cut_in_fixed_model():
    from tools.run_acc_following_bench import simulate, CASES
    for name in ('slower_left', 'cut_in', 'jitter_noise_heavy'):
        case = next(c for c in CASES if c['name'] == name)
        result = simulate(case)
        assert not result['reference_collision']
        assert result['target_absent_samples'] == 0
        assert result['target_switches'] <= (1 if name == 'cut_in' else 0)


@pytest.mark.parametrize('speed,lead,gap', [(20., 10., 30.), (15., 0., 25.),
                                         (10., 10., 12.), (0., 0., 6.)])
def test_route_following_keeps_existing_engine_emergency_floor(speed, lead, gap):
    engine = UltraPilotEngine.__new__(UltraPilotEngine)
    engine.shared_state = State({'truck_speed_ms': speed})
    old_demand = engine._lead_brake([dict(x=0., z=-gap, yaw=0., speed=lead)],
                                   (0., 0.), 0., speed)
    assert old_demand > .7
    assert following_demand(gap, lead, speed)['emergency']


def test_known_target_speed_recovery_is_paced_and_below_other_caps(flow):
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow)
    update(8, 10.)
    n()
    def offer(cap):
        publish(state, state.get('telemetry')['truck'], 'traffic', traffic_brake=0.,
                light_brake=0., light=None,
                following=dict(status='candidate', target_id='7', speed_cap_mps=cap))
    offer(10.)
    acc.on_tick(.033)
    previous = state.get('longitudinal_acc')['control_target_kmh']
    dt = update(8, 10., dt=.05)
    offer(20.)
    publish(state, state.get('telemetry')['truck'], 'road', speed_cap_kmh=45.)
    acc.on_tick(dt)
    request = state.get('longitudinal_acc')
    assert previous < request['control_target_kmh'] <= previous+6.*dt+1e-9
    assert request['constrained_speed_kmh'] <= 45.


@pytest.mark.parametrize('changed', ['navigation_intent_id', 'game_session_id',
                                   'active_dataset_fingerprint', 'lane_trajectory_revision'])
def test_route_context_change_cannot_apply_previous_following_command(flow, changed):
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow)
    update(8, 10.)
    n()
    publish(state, state.get('telemetry')['truck'], 'traffic',
            traffic_brake=0., light_brake=0., light=None,
            following=dict(status='candidate', target_id='7', speed_cap_mps=20.))
    acc.on_tick(.033)
    ap.on_tick(.033)
    state.set(changed, 9 if changed == 'lane_trajectory_revision' else 'other')
    engine._flush_controls()
    assert engine.controller.throttle == 0.


def test_disable_releases_following_and_reactivation_has_no_old_target(flow):
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow)
    update(8, 10.)
    n()
    publish(state, state.get('telemetry')['truck'], 'traffic',
            traffic_brake=0., light_brake=0., light=None,
            following=dict(status='candidate', target_id='7', speed_cap_mps=20.))
    acc.on_tick(.033)
    ap.on_tick(.033)
    engine._flush_controls()
    n()
    engine._flush_controls()
    assert engine.controller.throttle == engine.controller.brake == 0.
    assert state.get('longitudinal_command') is None
    state.set('longitudinal_traffic', None)
    acc.on_tick(update(8, 10.))
    assert not acc._followed_target
