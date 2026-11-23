"""Native traffic.cpp sorts by truck distance: array slot is NOT identity."""
import math
import pytest

from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.lifecycle.test_joint_regressions import joint  # noqa: F401
from tests.traffic.test_crossing_dev_hud import step, crossing


def producer_order(actors):
    # Same distance ordering/40 moving-record capacity as write_active_traffic_data.
    # Fixture ego is (2.25,10,15), no additional sensor or invented stable slot.
    return sorted(actors,key=lambda a:math.dist((a['x'],a['y'],a['z']),(2.25,10.,15.)))[:40]


@pytest.mark.parametrize('kind',['lead','crossing'])
@pytest.mark.parametrize('publications',[1,4])
def test_native_distance_sorted_owner_can_move_slot_without_losing_authority(joint,kind,publications):
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    original=(crossing(at=32.,arrival=4.1,aid=25) if kind=='crossing' else
              dict(id=25,x=2.25,y=10.,z=45.,yaw=math.pi,speed=3.))
    other=dict(id=51,x=34.5 if kind=='lead' else 48.,y=10.,z=15.,yaw=0.,speed=10.)
    first=producer_order([original,other])
    step(joint,first,1)
    assert acc._following_target_id=='25'
    original_slot=next(w['slot'] for w in state.get('longitudinal_traffic')['following']['owner_witnesses']
                       if w['target_id']=='25')
    for gen in range(2,8):
        # A different vehicle gets nearer, leaving our acquired object unchanged.
        # Sorting itself now changes its slot; original motion is not invented.
        other=dict(other,x=other['x']-.9)
        following,_=step(joint,producer_order([original,other]),gen,pedals=gen%publications==0)
    policy.on_tick(.033);acc.on_tick(.033);ap.on_tick(.033);engine._flush_controls()
    witness=next(w for w in following['owner_witnesses'] if w['target_id']=='25')
    assert not acc._following_fault,state.get('autopilot_intervention')
    assert state.get('autopilot_active')
    assert not state.get('autopilot_intervention')
    assert witness['current_slot']!=original_slot
    assert witness['chain_valid'],witness
    assert not (physical('aforward')>0. and physical('abackward')>0.)


def test_ineffective_auxiliary_cap_does_not_become_required_at_positive_write(joint,monkeypatch):
    from core import longitudinal
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    # At this gap/speed the cap is above cruise. It did not acquire ACC.
    actor=dict(id=53,x=4.,y=10.,z=100.,yaw=math.pi,speed=30.)
    for gen in range(1,5):step(joint,[actor],gen)
    assert not acc._followed_target
    original=longitudinal.signal_drive_write_guard
    def changed(*args,**kwargs):
        packet=state.get('longitudinal_traffic');packet['motion_constraint']=None
        state.set('longitudinal_traffic',packet)
        return original(*args,**kwargs)
    monkeypatch.setattr(longitudinal,'signal_drive_write_guard',changed)
    engine._flush_controls()
    assert not state.get('autopilot_intervention')
    assert state.get('autopilot_active')


def test_duplicate_id_is_not_identity_after_slot_sort(joint):
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    original=crossing(at=32.,arrival=4.1,aid=25)
    step(joint,[original],1)
    # A duplicated ID in the native acquisition is ambiguous even at same pose.
    step(joint,[original,dict(original,x=original['x']+.1)],2)
    assert physical('aforward')==0.
    assert state.get('autopilot_intervention') or state.get('autopilot_control_state')=='controlled_stop'


def test_capacity_omission_is_not_departure_but_sorted_slot_39_is_valid(joint):
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    lead=dict(id=25,x=2.25,y=10.,z=45.,yaw=math.pi,speed=3.)
    far=[dict(id=100+i,x=100.+i,y=10.,z=15.,yaw=0.,speed=2.) for i in range(39)]
    step(joint,producer_order([lead,*far]),1)
    close=[dict(id=200+i,x=8.+i*.1,y=10.,z=15.,yaw=0.,speed=2.) for i in range(40)]
    following,_=step(joint,producer_order([lead,*close[:39]]),2)
    witness=next(w for w in following['owner_witnesses'] if w['target_id']=='25')
    assert witness['current_slot']==39 and witness['chain_valid']
    assert state.get('autopilot_active') and not state.get('autopilot_intervention')
    following,_=step(joint,producer_order([lead,*close]),3)
    witness=next(w for w in following.get('owner_witnesses',()) if w['target_id']=='25')
    assert witness['continuity_reason']=='missing'
    assert physical('aforward')==0.
    assert state.get('autopilot_intervention') or state.get('autopilot_control_state')=='controlled_stop'


def test_same_short_id_changed_shape_cannot_inherit_sorted_owner(joint,monkeypatch):
    import dataclasses
    import struct
    import tests.traffic.test_crossing_dev_hud as fixture
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    lead=dict(id=25,x=2.25,y=10.,z=45.,yaw=math.pi,speed=3.)
    step(joint,[lead],1)
    capture=fixture.capture
    def changed_shape(actors,at):
        raw=capture(actors,at);buf=bytearray(raw.moving)
        struct.pack_into('<3f',buf,28,3.,4.,10.)
        return dataclasses.replace(raw,moving=bytes(buf))
    monkeypatch.setattr(fixture,'capture',changed_shape)
    following,_=step(joint,[lead],2)
    witness=next(w for w in following['owner_witnesses'] if w['target_id']=='25')
    assert witness['continuity_reason']=='identity_shape_changed'
    assert not witness['chain_valid'] and physical('aforward')==0.
    assert state.get('autopilot_intervention')


def test_unknown_shape_cannot_qualify_same_short_id_continuity(joint,monkeypatch):
    import dataclasses
    import struct
    import tests.traffic.test_crossing_dev_hud as fixture
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    capture=fixture.capture
    def unknown_shape(actors,at):
        raw=capture(actors,at);buf=bytearray(raw.moving)
        struct.pack_into('<3f',buf,28,0.,0.,0.)
        return dataclasses.replace(raw,moving=bytes(buf))
    monkeypatch.setattr(fixture,'capture',unknown_shape)
    lead=dict(id=25,x=2.25,y=10.,z=45.,yaw=math.pi,speed=3.)
    step(joint,[lead],1)
    following,_=step(joint,[lead],2)
    witness=next(w for w in following['owner_witnesses'] if w['target_id']=='25')
    assert witness['continuity_reason']=='identity_shape_unavailable'
    assert not witness['chain_valid'] and physical('aforward')==0.
    assert state.get('autopilot_intervention')


def test_ambiguous_acquisition_between_slow_acc_ticks_cannot_be_skipped(joint):
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    original=crossing(at=32.,arrival=4.1,aid=25)
    step(joint,[original],1)
    step(joint,[original,dict(original,x=original['x']+.1)],2,pedals=False)
    step(joint,[original],3,pedals=False)
    policy.on_tick(.033);acc.on_tick(.033);ap.on_tick(.033);engine._flush_controls()
    assert not state.get('longitudinal_acc')['valid']
    assert physical('aforward')==0.
    assert state.get('autopilot_intervention')


def test_reappearing_body_cannot_clear_original_terminal_stop(joint):
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    hazard=dict(id=26,x=-9.2,y=10.,z=38.,yaw=-math.pi/2,speed=4.)
    step(joint,[hazard],1)
    assert engine._service_brake_hold['traffic_lock']['targets']
    step(joint,[],2,pedals=False)
    step(joint,[dict(hazard,x=10.)],3,pedals=False)
    for gen in range(4,8):
        following,_=step(joint,[dict(hazard,x=10.+.15*(gen-3))],gen,pedals=False)
    assert following.get('stop_clearance') is None
    assert engine._service_brake_hold['traffic_lock']['targets']


def test_auxiliary_model_change_at_write_cannot_delay_new_emergency(joint,monkeypatch):
    from core import longitudinal
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    actor=dict(id=53,x=4.,y=10.,z=100.,yaw=math.pi,speed=30.)
    for gen in range(1,5):step(joint,[actor],gen)
    assert not acc._followed_target and physical('aforward')>0.
    original=longitudinal.signal_drive_write_guard
    def changed(*args,**kwargs):
        packet=state.get('longitudinal_traffic')
        packet.update(motion_constraint=None,traffic_brake=1.)
        state.set('longitudinal_traffic',packet)
        return original(*args,**kwargs)
    monkeypatch.setattr(longitudinal,'signal_drive_write_guard',changed)
    engine._flush_controls()
    assert physical('aforward')==0. and physical('abackward')==1.
    assert state.get('autopilot_intervention')['kind']=='emergency'


@pytest.mark.parametrize('dev',[False,True])
def test_sorted_owner_slow_acc_ipc_and_existing_async_export(joint,tmp_path,dev):
    from core.steering_replay import AsyncReplayExporter,SteeringReplayBuffer,inspect_replay
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    state.set('dev_hud_enabled',dev)
    journal=engine.controller._pedal_journal
    journal.enabled=True
    original_get=state.get
    reads=[0]
    def delayed_get(key,default=None):
        # Explicit deterministic IPC model, no source time is rewritten.
        reads[0]+=1
        if reads[0]%17==0:clock[0]+=.0004
        return original_get(key,default)
    state.get=delayed_get
    exporter=AsyncReplayExporter()
    exports=[]
    try:
        for generation in range(1,81):
            lead=dict(id=25,x=2.25,y=10.,z=45.+.1*generation,yaw=math.pi,speed=3.)
            side=dict(id=51,x=40. if generation==1 else 31.+2.*math.sin(generation*.2),
                      y=10.,z=15.,yaw=0.,speed=10.)
            step(joint,producer_order([lead,side]),generation,pedals=generation==1 or generation%4==0)
            assert state.get('autopilot_active') and not state.get('autopilot_intervention')
            if generation in (20,40,60,80):
                snapshot=journal.snapshot(expanded=False,include_history=True)
                buffer=SteeringReplayBuffer(2)
                assert not exporter.wait(5.)['busy']
                assert exporter.submit(lambda b=buffer,s=snapshot:exports.append(
                    b.export(tmp_path,reason='manual_disable',longitudinal=s)))
        assert not exporter.wait(5.)['busy']
        assert len(exports)==4 and all(inspect_replay(p)['integrity_valid'] for p in exports)
        assert acc._following_target_id=='25' and not acc._following_fault
        pair={'aforward':0.,'abackward':0.}
        for _,channel,value in writes:
            if channel in pair:pair[channel]=value
            assert not all(v>0 for v in pair.values())
    finally:
        exporter.wait(5.)
        if getattr(engine,'_dev_hud',None):engine._dev_hud.close()
