"""Existing producer/arbitration/Controller path; no game consumption claim."""
import math
import os
from unittest.mock import patch

import pytest

from tests.test_oct11_joint_regressions import joint  # noqa: F401
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_oct14_completion import timed_step


@pytest.fixture(autouse=True)
def committed_stop_baseline(monkeypatch):
    """Frozen entry implementation, without altering any checkout or inputs."""
    if os.environ.get('ULTRAPILOT_OCT14_STOP_BASELINE') != '1':
        return
    import ast
    import subprocess
    import sys
    from pathlib import Path
    from types import ModuleType
    import core.engine as module
    root=Path(__file__).resolve().parents[1]
    source=lambda path:subprocess.check_output(['git','show','add9a19:'+path],cwd=root).decode('utf-8')
    for name in ('core.acc_following','core.service_brake_hold'):
        frozen=ModuleType(name)
        exec(compile(source(name.replace('.','/')+'.py'),'frozen/'+name,'exec'),frozen.__dict__)
        monkeypatch.setitem(sys.modules,name,frozen)
    cls=next(node for node in ast.parse(source('core/engine.py')).body
             if isinstance(node,ast.ClassDef) and node.name=='UltraPilotEngine')
    for name in ('_traffic_control_observation','_publish_traffic_control','_flush_controls_unlocked'):
        method=next(node for node in cls.body if isinstance(node,ast.FunctionDef) and node.name==name)
        namespace=dict(module.__dict__)
        exec(compile(ast.Module(body=[method],type_ignores=[]),'frozen/engine','exec'),namespace)
        monkeypatch.setattr(module.UltraPilotEngine,name,namespace[name])


def test_moving_lead_speed_reduction_is_not_a_terminal_stop(joint):
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    activation=state.get('autopilot_failure_epoch')
    lead=dict(id=29,x=2.25,y=10.,z=45.,yaw=math.pi,speed=8.)
    timed_step(joint,[lead],generation=1,speed=10.)
    assert physical('abackward')>0.
    for generation in range(2,15):
        offset=(generation-1)*8./30.
        timed_step(joint,[dict(lead,z=45.+offset)],generation=generation,
                   speed=8.,z=15.+offset)
        assert state.get('autopilot_active'),state.get('autopilot_intervention')
    assert state.get('autopilot_failure_epoch')==activation
    assert physical('abackward')==0. and physical('aforward')>0.,state.get('simple_auto_service_hold')
    assert not any(ch=='parkingbrake' for row in writes for ch in row[1:2])


def test_parallel_protective_speed_brake_can_recover_with_same_observed_actor(joint):
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    # Outside lead centre gate, inside protective reference band. The same
    # actor remains present and moving; neither a zero demand nor absence clears.
    actor=dict(id=31,x=4.,y=10.,z=44.,yaw=math.pi,speed=10.)
    timed_step(joint,[actor],generation=1,speed=10.)
    assert physical('abackward')>0.
    initial_brake=physical('abackward')
    for generation in range(2,61):
        # Genuine increasing reference gap lowers the same protective request.
        # Allow the unchanged 6 km/h/s upward target pacing to recover drive.
        # Native source frames are 1/30 s apart: move this 10 m/s actor by
        # speed*dt, not the former first 2 m jump (about 60 m/s).
        timed_step(joint,[dict(actor,z=44.+(generation-1)*10./30.)],
                   generation=generation,speed=8.)
    assert state.get('simple_auto_service_hold') is None
    assert physical('abackward') < initial_brake
    assert physical('abackward')==0. and physical('aforward')>0., (
        state.get('longitudinal_command')['throttle'],ap._last_throttle,
        ap._longitudinal_decision, state.get('longitudinal_applied'))
    assert state.get('autopilot_active')
    assert not state.get('autopilot_intervention')


@pytest.mark.parametrize('fault',['absent','changed_id','stopped','reset','crossing','R','stale','identity','backend','manual'])
def test_positive_speed_constraint_cannot_clear_unproved_stop_or_fault(joint,fault):
    state,engine,ap,acc,policy,tick,observe,n,physical,writes,clock=joint
    actor=dict(id=31,x=4.,y=10.,z=44.,yaw=math.pi,speed=10.)
    timed_step(joint,[actor],generation=1,speed=10.)
    if fault in ('stale','identity','backend','manual'):
        if fault=='stale':clock[0]+=.6
        elif fault=='identity':state.set('navigation_intent_id','foreign')
        elif fault=='backend':engine.controller.scs.connected=False
        else:n()
        engine._flush_controls()
        assert physical('aforward')==0.
        assert not state.get('autopilot_active') or state.get('autopilot_control_state')=='controlled_stop'
        return
    for generation in range(2,9):
        actors=[] if fault=='absent' else [dict(actor,
            id=32 if fault=='changed_id' else 31,
            speed=0. if fault=='stopped' else 10.,
            x=-5. if fault=='crossing' else 4.,
            yaw=-math.pi/2 if fault=='crossing' else math.pi)]
        timed_step(joint,actors,generation=generation,speed=8.,
                   gear=-1 if fault=='R' else 4,lifecycle=74 if fault=='reset' else 73)
        assert physical('aforward')==0.
    assert (state.get('simple_auto_service_hold') or state.get('autopilot_intervention'))


def test_terminal_hold_cannot_restart_from_positive_speed_constraint(joint):
    state,engine,ap,acc,policy,tick,observe,n,physical,writes,clock=joint
    actor=dict(id=31,x=4.,y=10.,z=44.,yaw=math.pi,speed=0.)
    timed_step(joint,[actor],generation=1,speed=10.)
    mode=state.get('ets2_transmission_mode')['mode']
    for generation,speed in ((2,3.),(3,.4),(4,0.),(5,0.),(6,0.)):
        timed_step(joint,[dict(actor,z=44.+generation)],generation=generation,
                   speed=speed,gear=0 if speed==0. and mode==0 else 4)
        assert physical('aforward')==0.
    for generation in range(7,11):
        timed_step(joint,[dict(actor,z=44.+generation,speed=10.)],generation=generation,
                   speed=0.,gear=0 if mode==0 else 4)
        assert physical('aforward')==0.
    # A newer positive cap is not clearance of the original terminal cause.
    hold=state.get('simple_auto_service_hold')
    assert hold or state.get('autopilot_intervention')
    assert not hold or hold['phase']=='holding'


def test_motion_constraint_source_survives_existing_integrity_export(joint,tmp_path):
    from core.navigation.longitudinal_diagnostics import PedalJournal
    from core.steering_replay import SteeringReplayBuffer,inspect_replay
    state,engine,ap,acc,policy,tick,observe,n,physical,writes,clock=joint
    journal=engine.controller._pedal_journal=PedalJournal();journal.enabled=True
    actors=[dict(id=31+i,x=4.,y=10.,z=44.+i*2.,yaw=math.pi,speed=10.) for i in range(2)]
    timed_step(joint,actors,generation=1,speed=10.)
    original=state.get('longitudinal_traffic')['motion_constraint']
    for generation in range(2,12):
        # This helper serializes list positions as actual native array slots.
        # Reversing tests transport order independence, not an ID reassignment:
        # native slots are sorted positions. Motion still uses speed*dt.
        following=timed_step(joint,[dict(a,z=a['z']+(generation-1)*10./30.) for a in reversed(actors)],
                   generation=generation,speed=8.)
        assert all(w['chain_valid'] and w['current_slot']==32-int(w['target_id'])
                   for w in following['owner_witnesses'])
    assert state.get('simple_auto_service_hold') is None
    assert state.get('autopilot_active')
    assert not state.get('autopilot_intervention')
    path=SteeringReplayBuffer(2).export(tmp_path,reason='manual_disable',
        longitudinal=journal.snapshot(expanded=False,include_history=True))
    inspected=inspect_replay(path)
    assert inspected['integrity_valid']
    block=inspected['replay']['longitudinal']
    rows=block['decision_history']['regular_samples']+block['decision_history']['changes']
    expected={k:v for k,v in original.items() if k!='authority'}
    assert any(row.get('motion_constraint')==expected for row in rows)
    assert not block['game_consumption_verified']
    assert journal._bytes<=journal.MAX_BYTES


@pytest.mark.parametrize('fault',['absent','missing_packet','changed_id','expired','foreign'])
def test_publication_at_positive_write_cannot_execute_old_moving_drive(joint,fault):
    from core import longitudinal
    state,engine,ap,acc,policy,tick,observe,n,physical,writes,clock=joint
    actor=dict(id=31,x=4.,y=10.,z=70.,yaw=math.pi,speed=10.)
    for generation in range(1,5):
        timed_step(joint,[actor],generation=generation,speed=8.)
    assert physical('aforward')>0.
    original=longitudinal.signal_drive_write_guard
    def concurrent_publication(*args,**kwargs):
        packet=state.get('longitudinal_traffic')
        if fault=='missing_packet':packet=None
        elif fault=='absent':packet['motion_constraint']=None
        elif fault=='changed_id':packet['motion_constraint']['targets'][0]['id']='different'
        elif fault=='expired':packet['motion_constraint']['source_acquisition']['observed_at']-=.501
        else:packet['motion_constraint']['authority']=('foreign',)
        state.set('longitudinal_traffic',packet)
        return original(*args,**kwargs)
    start=len(writes)
    with patch.object(longitudinal,'signal_drive_write_guard',concurrent_publication):
        engine._flush_controls()
    assert physical('aforward')==0.
    assert not any(channel=='aforward' and value>0. for _,channel,value in writes[start:])
    if fault in ('absent','missing_packet','changed_id'):
        # No ACC owner was acquired in this scene. Still discard the positive
        # write, but a vanished ineffective auxiliary model is not a technical
        # navigation failure. Stale/foreign data below must remain rejected.
        assert not acc._followed_target
        assert not state.get('autopilot_intervention')
        assert state.get('autopilot_active')
    else:
        assert state.get('autopilot_intervention')


@pytest.mark.parametrize('mode',[0,3])
def test_closed_moving_protective_model_does_not_create_terminal_hold(mode):
    from tools.compare_oct14_stop_completion import moving_model
    result=moving_model(mode,False)
    assert result['stopped_samples']==result['terminal_hold_samples']==0
    assert result['settled_speed_rms_kmh']<=1.  # Existing Phase 7.2 speed criterion.
    assert result['final_throttle']>0. and result['final_brake']==0.


@pytest.mark.parametrize('mode', [0,3])
def test_destination_standstill_does_not_drop_hold_without_driver_handover(flow,tmp_path,mode):
    from tests.test_oct10_signal_timing import timing_flow
    values,step=timing_flow(flow,tmp_path,mode)
    state,truck,engine,ap,tick,n,clock,writes,collector=values
    state.set('game_gps_navigation_active',True)
    for generation,distance,speed in ((30,40.,10.),(31,20.,7.),(32,8.,3.),(33,2.,1.),(34,1.,.4)):
        truck['routeDistance']=distance
        step(generation,'green',speed=speed,progress=0.)
    from tests.test_roundabout_intervention_reporting import pedal
    start=len(writes)
    for generation in range(35,39):
        truck['routeDistance']=1.
        step(generation,'green',speed=0.,gear=0 if mode==0 else 4,progress=0.)
    assert state.get('autopilot_active')
    assert state.get('autopilot_control_state')=='destination_handover_pending'
    assert pedal(engine,'aforward')==0. and pedal(engine,'abackward')>0.
    assert not any(ch=='abackward' and value==0. for _,ch,value,_ in writes[start:])
    assert 'N' in state.get('navigation_status')
    assert state.get('autopilot_intervention') is None
    n();engine._flush_controls()
    assert not state.get('autopilot_active')
    assert pedal(engine,'aforward')==pedal(engine,'abackward')==0.
