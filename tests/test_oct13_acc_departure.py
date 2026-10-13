"""Native-byte traffic -> real Map/policy/ACC/AP/Controller; no game proof."""
import math
import pytest

from tests.test_oct11_joint_regressions import joint, traffic_step  # noqa: F401
from tests.test_activation_observation_binding import flow  # noqa: F401
from core.longitudinal import context


def test_rotated_observed_body_clearance_releases_only_lead_dependency(joint):
    state,engine,ap,acc,policy,tick,observe,n,physical,writes,clock=joint
    lead=dict(id=30,x=2.25,y=10.,z=40.,yaw=math.pi,speed=5.)
    traffic_step(joint,[lead])
    # The native 2x4 m box at yaw 90 degrees is 2.75 m off the
    # reference. Its enclosing disk wrongly reports 2.514 m (<2.6).
    result=traffic_step(joint,[dict(lead,x=7.,yaw=-math.pi/2)],before_acc=True)
    assert result.get('departure'),result
    assert result['departure']['minimum_body_reference_clearance_m']==pytest.approx(2.75)
    assert not acc._following_fault and state.get('autopilot_active')
    assert not state.get('autopilot_intervention')
    assert not (physical('aforward')>0 and physical('abackward')>0)


def test_same_authority_geometry_republication_preserves_departure_witness(joint):
    from core.ipc.shared_state import lane_publication_batch
    state,engine,ap,acc,policy,tick,observe,n,physical,writes,clock=joint
    lead=dict(id=30,x=2.25,y=10.,z=40.,yaw=math.pi,speed=5.)
    traffic_step(joint,[lead])
    old=context(state)
    lane=state.get('lane_trajectory')
    # Changed validated geometry digest, same activation/session/map/intent.
    # Existing Map built this synthetic directed road; subdivide its first
    # edge without changing geometry or inventing another navigation intent.
    points=lane['points'];a,b=points[:2]
    lane['points']=[a,[(u+v)*.5 for u,v in zip(a,b)],*points[1:]]
    lane['lane_path_fingerprint']='b'*64
    def publish_new():
        state.update_batch(lane_publication_batch({'lane_trajectory':lane}))
        debug=state.get('nav_steering_debug');debug['trajectory_identity']=state.get('lane_trajectory_identity')
        state.set('nav_steering_debug',debug)
        assert context(state)!=old and context(state)[:5]==old[:5]
    result=traffic_step(joint,[dict(lead,x=10.,yaw=-math.pi/2)],after_map=publish_new)
    assert result.get('departure'),result
    assert state.get('autopilot_active') and not acc._following_fault


def test_departed_tractor_with_trailer_still_on_route_never_clears(joint):
    state,engine,ap,acc,policy,tick,observe,n,physical,writes,clock=joint
    lead=dict(id=30,x=2.25,y=10.,z=40.,yaw=math.pi,speed=5.)
    traffic_step(joint,[lead])
    trailer=[2.25,10.,39.,0.,0.,1.,0.,2.5,4.,12.]
    result=traffic_step(joint,[dict(lead,x=7.,yaw=-math.pi/2)],trailer=trailer)
    assert not result.get('departure')
    assert physical('aforward')==0.


def test_confirmed_departure_keeps_second_car_and_emergency_priority(joint):
    state,engine,ap,acc,policy,tick,observe,n,physical,writes,clock=joint
    lead=dict(id=30,x=2.25,y=10.,z=40.,yaw=math.pi,speed=5.)
    traffic_step(joint,[lead])
    next_car=dict(lead,id=31,z=60.,speed=6.)
    result=traffic_step(joint,[dict(lead,x=7.,yaw=-math.pi/2),next_car])
    assert result['target_id']=='31' and result['departure']['target_id']=='30'
    assert acc._following_target_id=='31' and not acc._following_fault
    result=traffic_step(joint,[dict(next_car,z=25.,speed=0.)])
    assert result['emergency']
    assert physical('aforward')==0. and physical('abackward')==1.


def test_geometry_refresh_never_clears_missing_old_target(joint):
    from core.ipc.shared_state import lane_publication_batch
    state,engine,ap,acc,policy,tick,observe,n,physical,writes,clock=joint
    lead=dict(id=30,x=2.25,y=10.,z=40.,yaw=math.pi,speed=5.)
    traffic_step(joint,[lead])
    def refresh():
        lane=state.get('lane_trajectory');lane['lane_path_fingerprint']='c'*64
        state.update_batch(lane_publication_batch({'lane_trajectory':lane}))
        debug=state.get('nav_steering_debug');debug['trajectory_identity']=state.get('lane_trajectory_identity')
        state.set('nav_steering_debug',debug)
    result=traffic_step(joint,[],after_map=refresh)
    assert not result.get('departure')
    assert acc._following_fault or state.get('autopilot_intervention')
    assert physical('aforward')==0.


def test_actual_map_horizon_rebuild_preserves_observed_lead_departure(joint):
    state,engine,ap,acc,policy,tick,observe,n,physical,writes,clock=joint
    lead=dict(id=30,x=2.25,y=10.,z=40.,yaw=math.pi,speed=5.)
    traffic_step(joint,[lead])
    before=context(state)
    map_plugin=tick.publish_map.__self__
    # A recovered Map has a fresh local build guard; shared authority and
    # all original network geometry remain unchanged, as on worker restart.
    from core.navigation.navigation_intent import NavigationBuildGuard
    map_plugin._build_guard=NavigationBuildGuard()
    map_plugin._rolling_route_refresh_needed=True
    result=traffic_step(joint,[dict(lead,x=7.,yaw=-math.pi/2)])
    assert context(state)!=before and context(state)[:5]==before[:5]
    assert result['departure']['target_id']=='30'
    assert not state.get('autopilot_intervention') and state.get('autopilot_active')
    assert not (physical('aforward')>0 and physical('abackward')>0)
