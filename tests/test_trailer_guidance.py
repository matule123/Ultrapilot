from dataclasses import replace
import math

import pytest

from core.navigation.trailer_guidance import (
    GuidanceWorker, derived_lane_corridor, guidance_source_status, plan_sharp_turn,
    plan_hybrid_reference, plan_trailer_guidance, reference_route,
    propose_trailer_reference,
)
from core.swept_envelope import EnvelopeError
from tests.trailer_guidance_cases import case, simulate


def plan(request, speed=5., **kwargs):
    path, identity, model, corridor = request
    return plan_trailer_guidance(path, identity, model, corridor,
        initial_trailer_heading=path.points[0].heading, speed_mps=speed, **kwargs)


@pytest.mark.parametrize('sign', [-1., 1.])
@pytest.mark.parametrize('length,radius,speed,lag,delay,noise', [
    (5., 60., 5., .25, .05, False),
    (8., 80., 5., .32, .10, False),
    (11., 150., 8., .60, .15, True),
])
def test_closed_loop_improves_trailer_without_controller_retuning(sign, length, radius, speed, lag, delay, noise):
    request = case(radius, sign, length)
    p, ident, model, corridor = request
    result = plan(request, speed)
    assert result.accepted, result.failure_reason
    route = reference_route(result, p, ident, model.configuration)
    before, _ = simulate(p, model, speed=speed, lag=lag, delay=delay, noise=noise, jitter=noise, corridor=corridor)
    after, _ = simulate(p, model, route, speed=speed, lag=lag, delay=delay, noise=noise, jitter=noise, corridor=corridor)
    assert before['completed'] and after['completed']
    assert after['trailer_max_cte_m'] <= .85*before['trailer_max_cte_m']
    assert after['cab_max_cte_m'] < .8
    assert after['steering_step'] <= before['steering_step']+.01
    assert after['exit_cab_cte_m'] < .15
    assert after['exit_trailer_cte_m'] < .25
    assert result.minimum_axle_reserve_m > 0
    assert after['minimum_axle_corridor_reserve_m'] > 0
    assert result.body_envelope is None and not result.runtime_authorized


@pytest.mark.parametrize('sign', [-1., 1.])
def test_r150_retimed_reference_improves_delayed_exit_and_step(sign):
    """Pre-fix R150 had a worse exit and larger steering step with delay."""
    p, ident, model, corridor = case(150., sign, 11.)
    result = plan((p, ident, model, corridor), 8.)
    assert result.accepted, result.failure_reason
    assert result.design_speed_mps == 7.
    assert result.speed_reduction_distance_m > 0.
    local = reference_route(result, p, ident, model.configuration)
    for noise in (False, True):
        options = dict(speed=result.design_speed_mps, lag=.60, delay=.15,
                       noise=noise, jitter=noise)
        before, _ = simulate(p, model, None, **options)
        after, _ = simulate(p, model, local, **options)
        assert after['trailer_max_cte_m'] <= .85*before['trailer_max_cte_m']
        assert after['exit_cab_cte_m'] <= before['exit_cab_cte_m']
        assert after['exit_trailer_cte_m'] <= before['exit_trailer_cte_m']
        assert after['steering_step'] <= before['steering_step']


def test_r83_reduces_trailer_error_without_larger_steering_step():
    p, ident, model, _ = case(83., length=8.)
    result = plan((p, ident, model, derived_lane_corridor(p, ident)), 5.)
    assert result.accepted, result.failure_reason
    route = reference_route(result, p, ident, model.configuration)
    options = dict(speed=result.design_speed_mps, lag=.32, delay=.10)
    before, _ = simulate(p, model, **options)
    after, _ = simulate(p, model, route, **options)
    assert after['trailer_max_cte_m'] <= .85*before['trailer_max_cte_m']
    assert after['steering_step'] <= before['steering_step']
    assert after['exit_cab_cte_m'] <= before['exit_cab_cte_m']


def test_slow_actuator_requires_speed_reduction_before_turn():
    p, ident, model, _ = case(150., length=11.)
    result = plan((p, ident, model, derived_lane_corridor(p, ident)), 8.,
                  actuator_response_s=1., actuator_delay_s=.2)
    assert result.failure_reason == 'INSUFFICIENT_APPROACH_FOR_DESIGN_SPEED'
    assert 0 < result.handoff_before_m < 40
    assert not result.runtime_authorized


def test_centerline_width_never_authorizes_reference():
    p, ident, model, _ = case()
    assert guidance_source_status(p) == 'MISSING_CONFIRMED_USABLE_LANE_CORRIDOR'
    result = plan((p, ident, model, None))
    assert result.failure_reason == 'MISSING_CONFIRMED_USABLE_LANE_CORRIDOR'
    assert result.points == ()


@pytest.mark.parametrize('radius,length,speed', [
    (60., 5., 5.), (83., 8., 5.), (150., 11., 8.),
])
def test_derived_lane_budget_is_small_and_not_physical_clearance(radius, length, speed):
    p, ident, model, _ = case(radius, length=length)
    derived = derived_lane_corridor(p, ident)
    result = plan((p, ident, model, derived), speed)
    assert result.accepted, result.failure_reason
    assert result.corridor_basis == 'derived_lane_placement'
    assert result.tractor_max_offset_m <= .15
    assert result.minimum_axle_reserve_m > 0
    assert result.body_envelope is None and not result.runtime_authorized
    assert result.design_speed_mps <= speed
    assert not plan((p, replace(ident, revision=9), model, derived), speed).accepted
    assert not plan((p, ident, model, replace(derived, width_source='measured')), speed).accepted
    assert not plan((p, ident, model, replace(derived, uncertainty_m=.1)), speed).accepted


def test_derived_lane_cannot_rescue_sharp_or_unknown_trailer():
    for radius in (35., 25., 18.):
        p, ident, model, _ = case(radius, length=5.)
        result = plan((p, ident, model, derived_lane_corridor(p, ident)), 3.)
        assert result.failure_reason == 'SHARP_TURN_REQUIRES_PHASE5_PLANNER'
    p, ident, model, _ = case(83.)
    result = plan((p, ident, replace(model, confirmed=False),
                   derived_lane_corridor(p, ident)))
    assert result.failure_reason == 'MISSING_CONFIRMED_TRAILER_KINEMATICS'


def test_straight_and_s_bend_do_not_create_unproven_lateral_deviation():
    straight = case(sections=((0., 150.),))
    p, ident, model, _ = straight
    plan_result = plan((p, ident, model, derived_lane_corridor(p, ident)))
    assert plan_result.failure_reason == 'NO_MEANINGFUL_TRAILER_OFFTRACKING'
    s_bend = case(sections=((0., 40.), (1/83., 55.),
                            (-1/83., 55.), (0., 75.)))
    p, ident, model, _ = s_bend
    plan_result = plan((p, ident, model, derived_lane_corridor(p, ident)))
    assert plan_result.failure_reason in (
        'COMPOUND_TURN_OUTSIDE_LIGHT_GUIDANCE_DOMAIN',
        'SHARP_TURN_REQUIRES_PHASE5_PLANNER')


def test_hybrid_sharp_trajectory_uses_original_envelope_or_handoffs_before_turn():
    from core.navigation.maneuver_planner import PlannerLimits
    from tests.maneuver_cases import junction
    vehicle, start, p, surface, ident = junction(half_width=3.5)
    absent = plan_hybrid_reference(p, ident, None, None,
        initial_trailer_heading=p.points[0].heading, speed_mps=2.)
    assert not absent.accepted and absent.handoff_before_m > 0
    assert absent.failure_reason == 'SHARP_TURN_REQUIRES_CONFIRMED_BODY_SURFACE_AND_GROUND_FRAME'
    result = plan_hybrid_reference(p, ident, None, None,
        initial_trailer_heading=p.points[0].heading, speed_mps=2.,
        vehicle=vehicle, ground_frame=start, sharp_surface=surface,
        limits=PlannerLimits(max_candidates=9))
    assert result.accepted, result.failure_reason
    assert result.body_envelope.minimum_clearance_m > .15
    assert result.corridor_basis == 'confirmed_surface'
    assert result.design_speed_mps == 2.
    assert not result.runtime_authorized
    assert len(reference_route(result, p, ident, result.configuration)) > 100
    late = plan_hybrid_reference(p, ident, None, None,
        initial_trailer_heading=p.points[0].heading, speed_mps=8.,
        vehicle=vehicle, ground_frame=start, sharp_surface=surface,
        limits=PlannerLimits(max_candidates=9))
    assert late.failure_reason == 'INSUFFICIENT_APPROACH_FOR_SHARP_DESIGN_SPEED'
    assert late.handoff_before_m > 0


@pytest.mark.parametrize('field,value', [('revision', 9), ('build', 'new-build'),
    ('intent', 'new-intent'), ('session', 'new-session'), ('dataset', 'new-dataset')])
def test_stale_identity_never_reuses_candidate(field, value):
    request = case()
    p, ident, model, corridor = request
    result = plan((p, replace(ident, **{field: value}), model, corridor))
    assert not result.accepted


def test_sharp_90_degree_and_prefab_use_existing_full_geometry_gate():
    request = case(18.)
    result = plan(request, 2.)
    assert result.failure_reason == 'SHARP_TURN_REQUIRES_PHASE5_PLANNER'
    p, ident, model, corridor = case()
    p = replace(p, segments=(replace(p.segments[0], lane_type='prefab'),))
    result = plan((p, ident, model, corridor))
    assert not result.accepted
    from tests.maneuver_cases import junction
    vehicle, start, p, _, ident = junction()
    rejected = plan_sharp_turn(vehicle, start, p, None, ident)
    assert not rejected.accepted and not rejected.runtime_authorized
    assert rejected.failure_reason == 'MISSING_CONFIRMED_DRIVABLE_BOUNDARY'


def test_unknown_kinematics_and_deadline_fail_closed():
    p, ident, model, corridor = case()
    assert plan((p, ident, replace(model, confirmed=False), corridor)).failure_reason == 'MISSING_CONFIRMED_TRAILER_KINEMATICS'
    assert plan((p, ident, model, corridor), deadline=0.).failure_reason == 'GUIDANCE_DEADLINE_EXPIRED'


def test_narrow_corridor_rejects_instead_of_clipping_offset():
    result = plan(case(60., length=11., half_width=.7))
    assert not result.accepted
    assert not result.runtime_authorized


def test_worker_one_job_and_stale_callback():
    request = case()
    p, ident, model, corridor = request
    worker = GuidanceWorker()
    try:
        assert worker.offer(('rev8', model.configuration), p, ident, model, corridor,
            initial_trailer_heading=math.pi, speed_mps=5., deadline=0.)
        assert not worker.offer(('rev9',), p, ident, model, corridor)
        worker._future.result(timeout=10)
        assert worker.harvest(('rev9', model.configuration)) is None
    finally:
        worker.close()


def test_reference_seams_and_configuration_binding():
    from core.navigation.route import Route
    request = case()
    p, ident, model, _ = request
    result = plan(request)
    assert result.accepted, result.failure_reason
    local = reference_route(result, p, ident, model.configuration)
    original = Route([(q.x, q.y, q.z) for q in p.points])
    for point in (p.points[0], p.points[-4]):
        args = ((point.x, point.z), point.heading, 5.)
        before = original.steering(*args)
        after = local.steering(*args)
        assert abs(before-after) < 1e-6
        for key in ('geometric_cte', 'local_curvature', 'local_tangent_heading_rad'):
            assert abs(original.last_steering_debug[key]-local.last_steering_debug[key]) < 1e-6
    with pytest.raises(EnvelopeError, match='STALE_GUIDANCE_REFERENCE'):
        reference_route(result, p, ident, 'd'*64)
    with pytest.raises(EnvelopeError, match='STALE_GUIDANCE_REFERENCE'):
        reference_route(result, p, replace(ident, build='new'), model.configuration)
    changed = replace(result, points=result.points[:10]+(
        replace(result.points[10], x=result.points[10].x+.1),)+result.points[11:])
    with pytest.raises(EnvelopeError, match='MUTATED_GUIDANCE_REFERENCE'):
        reference_route(changed, p, ident, model.configuration)
    from core.navigation.maneuver_reference import build_prepared_reference_packet
    with pytest.raises(EnvelopeError, match='NO_PREPARABLE_MANEUVER_GEOMETRY'):
        build_prepared_reference_packet(result, 1)


def test_opposing_space_display_source_and_wrong_level_are_rejected():
    p, ident, model, corridor = case()
    assert plan((p, ident, model, replace(corridor, same_lane_only=False))).failure_reason == 'MISSING_CONFIRMED_SAME_LANE_USE_CORRIDOR'
    boundary = replace(corridor.boundary, source='ppd_map_points_visual_only')
    assert plan((p, ident, model, replace(corridor, boundary=boundary))).failure_reason == 'UNPROVEN_GUIDANCE_CORRIDOR_SOURCE'
    boundary = replace(corridor.boundary, surface=replace(corridor.boundary.surface, y_m=8.))
    assert plan((p, ident, model, replace(corridor, boundary=boundary))).failure_reason == 'GUIDANCE_ELEVATION_MISMATCH'


def test_body_model_enables_additional_original_swept_validator():
    import time
    from core.swept_envelope import Body, Vehicle
    p, ident, model, corridor = case()
    vehicle = Vehicle((
        Body('cab', 2.5, 5., 1.2, 0., 0., 'synthetic', True, 'fixed_axle'),
        Body('trailer', 2.5, 9., 2., 8., 0., 'synthetic', True, 'fixed_axle')),
        3.8, .7, 2., .15, .15)
    result = plan((p, ident, model, corridor), 2., vehicle=vehicle,
                  deadline=time.monotonic()+60.)
    assert result.accepted, result.failure_reason
    assert result.body_envelope.accepted
    assert result.body_envelope.minimum_clearance_m > 0
    assert not result.runtime_authorized


def test_road_to_prefab_boundary_never_uses_light_reference():
    from tests.maneuver_cases import junction
    from core.navigation.trailer_guidance import UsableLaneCorridor
    _v, _start, p, surface, ident = junction(radius=80., angle=.6)
    _p, _i, model, _c = case()
    corridor = UsableLaneCorridor(surface, ident.lanes, 'synthetic lane use', 'b'*64, True)
    result = plan((p, ident, model, corridor), 2.)
    assert result.failure_reason == 'SENSITIVE_TURN_REQUIRES_PHASE5_PLANNER'


def test_map_preserves_width_provenance(monkeypatch):
    from pathlib import Path
    import sys
    from types import ModuleType
    sdk = ModuleType('sdk')
    sdk.__path__ = [str(Path(__file__).resolve().parents[1] / 'SDK')]
    monkeypatch.setitem(sys.modules, 'sdk', sdk)
    from plugins.map.main import Plugin
    p, *_ = case()
    plugin = Plugin.__new__(Plugin)
    assert plugin._lane_corridor_payload(p)[0]['lane_width_source'] == 'derived'


def test_sharp_strategy_uses_original_planner_only_with_real_contracts():
    from core.navigation.maneuver_planner import PlannerLimits
    from tests.maneuver_cases import junction
    vehicle, start, p, surface, ident = junction(half_width=3.5)
    strategy, result = propose_trailer_reference(p, ident, None, None,
        initial_trailer_heading=0., speed_mps=2.)
    assert strategy == 'phase5_swept'
    assert result.failure_reason == 'SHARP_TURN_REQUIRES_CONFIRMED_BODY_AND_GROUND_FRAME'
    strategy, result = propose_trailer_reference(p, ident, None, None,
        initial_trailer_heading=0., speed_mps=2., vehicle=vehicle,
        ground_frame=start, sharp_surface=surface, limits=PlannerLimits(max_candidates=9))
    assert result.accepted, result.failure_reason
    assert result.envelope.minimum_clearance_m > .15
    assert not result.runtime_authorized
