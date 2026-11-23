"""Recorded signed stop speeds; other poses/route are explicit models."""
import math
import pytest
from tests.lifecycle.test_joint_regressions import joint  # noqa: F401
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.lifecycle.test_longitudinal_completion import timed_step
from tests.traffic.test_crossing_dev_hud import crossing


def test_acquired_crossing_survives_valid_small_signed_stop_speed(joint):
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    lead=crossing(at=32.,arrival=4.1)
    bodies=[(2.25,10.,15.,0.,0.,1.,0.,2.5,4.,6.)]
    first=timed_step(joint,[lead],generation=1,speed=7.6,ego=bodies)
    assert acc._followed_target and acc._following_kind=='crossing'
    assert first['owner_witnesses']
    # Native and SDK speeds are the actual Nov 2 signed near-stop values.
    # Timed_step uses the SDK value for native too in this narrow model;
    # the original native/SDK pair is exercised in the data replay tool.
    latest=timed_step(joint,[dict(lead,x=lead['x']+.1)],generation=2,
        speed=-.022485010,gear=4,ego=bodies)
    assert latest['body_prediction']['status']=='protective_observed_body_prediction'
    assert latest['crossing']['status']!='crossing_projection_unavailable'
    assert state.get('longitudinal_acc')['valid'],state.get('longitudinal_acc')
    assert not acc._following_fault
    assert state.get('autopilot_active'),state.get('autopilot_disable_reason')
    assert not (physical('aforward')>0. and physical('abackward')>0.)


def test_observed_body_protection_keeps_signed_motion_and_actual_reverse_guard(joint):
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    body=[(2.25,10.,15.,0.,0.,1.,0.,2.5,4.,6.)]
    actor=dict(id=20,x=2.25,y=10.,z=15.,yaw=math.pi,speed=0.)
    latest=timed_step(joint,[actor],generation=1,speed=-.039795611,gear=4,ego=body)
    prediction=latest['body_prediction']
    assert prediction['brake']==1.
    assert prediction['conflicts'][0]['ego_observed_speed_mps']==pytest.approx(-.039795611)
    assert physical('aforward')==0.
    timed_step(joint,[actor],generation=2,speed=-.2,gear=-1,ego=body)
    assert physical('aforward')==0.
    assert not state.get('autopilot_active') or state.get('autopilot_control_state')=='controlled_stop'
