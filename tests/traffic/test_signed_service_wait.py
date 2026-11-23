"""Modeled contact approach and raw signed stop speed; no ETS2 physics claim."""
import math
from tests.lifecycle.test_joint_regressions import joint  # noqa: F401
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.lifecycle.test_longitudinal_completion import timed_step


def test_owned_forward_brake_stays_continuous_at_zero_ratio_signed_stop(joint):
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    actor=dict(id=83,x=2.25-8.,y=10.,z=35.,yaw=-math.pi/2,speed=2.5)
    ego=[(2.25,10.,15.,0.,0.,1.,0.,2.5,4.,6.)]
    first=timed_step(joint,[actor],generation=1,speed=8.,gear=4,ego=ego)
    assert 0.<first['body_prediction']['brake']<=.7,first['body_prediction']
    assert physical('abackward')>0. and physical('aforward')==0.
    start=len(writes)
    mode=state.get('ets2_transmission_mode')['mode']
    latest=timed_step(joint,[dict(actor,x=actor['x']+.1)],generation=2,
        speed=.01,gear=0 if mode==0 else 4,ego=ego)
    latest=timed_step(joint,[dict(actor,x=actor['x']+.2)],generation=3,
        speed=-.022485010,gear=0 if mode==0 else 4,ego=ego)
    assert latest['body_prediction']['prediction_duration_s']==3.
    assert state.get('longitudinal_acc')['valid'],state.get('longitudinal_acc')
    assert state.get('autopilot_active'),state.get('autopilot_disable_reason')
    assert not state.get('safety_hazard_active')
    assert physical('abackward')>0. and physical('aforward')==0.
    assert all(value>0. for _,channel,value in writes[start:] if channel=='abackward')
