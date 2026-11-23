"""Recorded dimensions with MODELED poses, not actor 85's missing fault frame."""
import math,struct,dataclasses
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.lifecycle.test_joint_regressions import joint  # noqa: F401
from tests.traffic.test_crossing_dev_hud import step,crossing


def test_reused_native_short_id_cannot_inherit_acquired_crossing(joint,monkeypatch):
    import tests.traffic.test_crossing_dev_hud as fixture
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    capture=fixture.capture
    dimensions=[(2.00836,1.61401,4.95951)]
    def exact_shape(actors,at):
        original=capture(actors,at);moving=bytearray(original.moving)
        struct.pack_into('<3f',moving,28,*dimensions[0])
        return dataclasses.replace(original,moving=bytes(moving))
    monkeypatch.setattr(fixture,'capture',exact_shape)
    step(joint,[crossing(at=32.,arrival=4.1,aid=85)],7717)
    assert acc._following_target_id=='85'
    dimensions[0]=(2.15642,1.51575,4.85840)
    following,_=step(joint,[dict(id=85,x=5.15,y=10.,z=7.,yaw=math.pi,speed=3.)],7718)
    owner=next(w for w in following['owner_witnesses'] if w['target_id']=='85')
    assert not owner['chain_valid'] and owner['continuity_reason']=='identity_shape_changed'
    assert physical('aforward')==0.
    assert state.get('autopilot_intervention') or state.get('autopilot_control_state')=='controlled_stop'


def test_rear_noncolliding_actor_is_not_a_fresh_braking_owner(joint):
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    for generation in range(1,5):
        following,packet=step(joint,[dict(id=85,x=5.15,y=10.,z=7.,yaw=math.pi,speed=3.)],generation)
        assert packet['traffic_brake']==0.
        assert not packet.get('motion_constraint')
        assert not acc._followed_target
        assert physical('abackward')==0.
        assert state.get('autopilot_active') and not state.get('autopilot_intervention')
