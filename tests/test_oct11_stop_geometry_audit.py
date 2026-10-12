"""Stop-reference observability and unchanged production-path safeguards.

There is no failing production-distance fix claimed here: line/body evidence
is missing. Synthetic dimensions are explicitly not real truck calibrations.
"""
import copy
import math

import pytest

from core.longitudinal import CURVE_BRAKE_RESPONSE_S, LEASE_S, signal_stop_speed_limit
from core.sdk.signal_snapshot import RouteSignalSelector
from core.vehicle_profile import VehicleProfileProvider, compile_catalog_entry
from tests.test_prefab_signal_binding import parsed_path, plan_for
from tests.test_stage5b1_vehicle_profile import observation, entry
from tools.audit_oct11_stop_geometry import holds, model_case, model_metrics


@pytest.mark.parametrize('turn', [False, True])
@pytest.mark.parametrize('speed', [20., 35., 50.])
def test_selector_and_planner_subtract_spatial_margins_once(tmp_path, turn, speed):
    net, path, _ = parsed_path(tmp_path, turn=turn)
    plan = plan_for(net, path)
    passage = plan['passages'][0]
    progress = 35.
    start, end = path.segments[0].centerline[0], path.segments[0].centerline[-1]
    fraction = progress/math.hypot(end.x-start.x, end.z-start.z)
    truck = dict(x=start.x+(end.x-start.x)*fraction, y=10.,
        z=start.z+(end.z-start.z)*fraction, rotation=passage['entry_heading_rad'], speed=speed/3.6)
    light = dict(id=passage['semaphore_id'], x=2., y=10., z=-105. if turn else -125.,
                 yaw=passage['entry_heading_rad']+math.pi, color='red')
    snap = dict(valid=True, lifecycle=1, generation=1, frame_us=100,
                observed_at=100., lights=[light])
    result = RouteSignalSelector().select(snap, [[p.x, p.y, p.z] for p in path.points],
        'original-geometry', ('same-authority',),
        truck, progress, plan)
    assert result['valid'], result
    target = result['candidate']
    distance = passage['entry_progress_m']-progress-6.-2.
    assert target['distance'] == pytest.approx(distance)
    usable = max(0., distance-speed/3.6*(CURVE_BRAKE_RESPONSE_S+LEASE_S))
    assert signal_stop_speed_limit(target, speed/3.6) == pytest.approx(math.sqrt(2.*usable))
    assert target['stop_line_verified'] is False
    # A different observed lamp position cannot create a new physical line.
    light['z'] -= 1.
    shifted = RouteSignalSelector().select(snap, [[p.x, p.y, p.z] for p in path.points],
        'original-geometry', ('same-authority',),
        truck, progress, plan)
    assert shifted['valid'] and shifted['candidate']['distance'] == pytest.approx(distance)


def test_same_sdk_axles_do_not_determine_truck_front():
    o = observation(now=10.)
    unknown = VehicleProfileProvider().update(o, 10.)
    assert unknown.model is None and unknown.model_failure == 'MISSING_CONFIRMED_BODY_PROFILE'
    assert unknown.axle_geometry[0].wheelbase_m == pytest.approx(3.8)
    short, long = entry(o), copy.deepcopy(entry(o))
    long['bodies'][0]['front_m'] = 6.5
    a, axles_a = compile_catalog_entry(short, o)
    b, axles_b = compile_catalog_entry(long, o)
    assert axles_a == axles_b and a.bodies[0].front_m != b.bodies[0].front_m
    assert a.bodies[0].front_m-axles_a[0].axle_local_m[2] == pytest.approx(2.9)
    assert b.bodies[0].front_m-axles_b[0].axle_local_m[2] == pytest.approx(4.4)
    assert unknown.live_maneuver_ready is False


def test_history_audit_does_not_promote_missing_line_or_front_to_zero():
    r = dict(monotonic_s=12., activation=9, identity_reference='1', signal_id=3,
        hold_phase='holding', sdk_frame_us=100, capture_incomplete=True,
        stop_target=dict(distance=2.55, passage_key='p', stop_line_verified=False))
    value = holds(dict(longitudinal=dict(decision_history=dict(regular_samples=[r], changes=[], identities={}))))[0]
    assert value['sdk_reference_to_derived_target_m'] == [2.55, 2.55]
    assert value['physical_bumper_to_painted_line_m'] is None
    assert value['incomplete_rows'] == 1 and 'NOT RETAINED' in value['detailed_write_timing']


@pytest.mark.parametrize('mode', [0, 3])
@pytest.mark.parametrize('k', [0., 1./60., -1./60.])
def test_real_ppd_control_and_backend_preserve_hold_green_resume(tmp_path, mode, k):
    result = model_case(tmp_path, mode=mode, speed=35., approach_curvature=k)
    metrics = model_metrics(result)
    assert metrics['active'] and metrics['resumed_without_n']
    assert metrics['positive_pedal_overlap'] == metrics['parking_writes'] == 0
    assert metrics['hold_zero_samples'] == metrics['red_entry_overrun_samples'] == 0
    assert metrics['far_low_speed_s'] == 0.
    assert metrics['painted_line_gap_m'] is None
    gaps = metrics['assumed_front_to_authored_entry_m']
    assert gaps['3.0']-gaps['6.0'] == pytest.approx(3.)
    # Even a model entry gap is not the requested physical painted-line gap.
    terminal = next(row for row in result['rows'] if row['hold_phase'] in ('braking', 'holding'))
    last_red = next(row for row in reversed(result['rows']) if row['red'])
    writes = [v for t, channel, v in result['writes'] if channel == 'abackward'
              and terminal['write_checked_at_s'] <= t <= last_red['write_checked_at_s']]
    assert writes and all(v > 0. for v in writes)


@pytest.mark.parametrize('mode', [0, 3])
def test_other_stop_keeps_priority_over_green(tmp_path, mode):
    result = model_case(tmp_path, mode=mode, other_stop=True)
    assert result['active'] and not result['resumed_without_n']
    assert result['rows'][-1]['throttle'] == 0. and result['rows'][-1]['brake'] > 0.
    assert result['simultaneous_positive_physical_writes'] == result['parking_writes'] == 0
