"""Oct 16 production-flow regressions; synthetic SDK is not game confirmation."""
import math
import os
import struct
from types import SimpleNamespace

import pytest

from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.lifecycle.test_joint_regressions import joint  # noqa: F401
from tests.lifecycle.test_longitudinal_completion import timed_step
from tests.traffic.test_crossing_dev_hud import step, crossing


def dense_capture(actors, at):
    """Actual ABI: 40 moving slots + 40 parked slots, never 80 moving."""
    from tests.test_acc_following import capture
    from core.navigation.traffic_producer import TrafficCapture
    from core.sdk.ets2la_data import _PARKED_FMT
    moving=capture(actors[:39]+actors[-1:],at)
    parked=[0.]*480
    for i in range(40):parked[i*12+10:i*12+12]=[0,0]
    for i,a in enumerate(actors[39:-1]):
        b=i*12
        parked[b:b+12]=[a['x'],a['y'],a['z'],math.cos(a['yaw']/2),0.,
            math.sin(a['yaw']/2),0.,2.,2.,4.,int(a['id']),0]
    return TrafficCapture('session',at,moving.moving,struct.pack(_PARKED_FMT,*parked),True)


@pytest.fixture(autouse=True)
def baseline_geometry(monkeypatch):
    if os.environ.get('UP_OCT16_BASELINE_GEOMETRY')!='1':return
    import ast
    import subprocess
    import core.traffic_dev_hud as module
    source=subprocess.check_output(['git','show','0ed435f:core/traffic_dev_hud.py']).decode()
    node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='geometry')
    namespace=dict(vars(module));exec(compile(ast.Module(body=[node],type_ignores=[]),'baseline/geometry','exec'),namespace)
    original=namespace['geometry']
    monkeypatch.setattr(module,'geometry',lambda *args,**kwargs:original(*args))


def test_observed_crossing_turns_parallel_without_manufacturing_lead_loss(joint):
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    actor=crossing(at=32.,arrival=4.1)
    step(joint,[actor],1)
    assert acc._followed_target
    # Same native actor/slot with bounded movement, on the side road. It
    # turns parallel away: no crossing ray and no predicted body contact.
    turned=dict(actor,x=actor['x']+1.1,yaw=math.pi)
    step(joint,[turned],2)
    assert state.get('autopilot_active'),state.get('autopilot_intervention')
    assert state.get('autopilot_control_state')!='controlled_stop'
    assert not acc._following_fault
    assert not acc._followed_target
    assert not engine._service_brake_hold
    assert not (physical('aforward')>0. and physical('abackward')>0.)


def test_completion_survives_slower_acc_but_not_missing_owner(joint):
    from core.acc_following import observed_crossing_completion
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    actor=crossing(at=32.,arrival=4.1)
    step(joint,[actor],1)
    turned=dict(actor,x=actor['x']+1.1,yaw=math.pi)
    following,_=step(joint,[turned],2,pedals=False)
    first=following['constraint_completion']
    assert first
    following,_=step(joint,[dict(turned,x=turned['x']+.1)],3,pedals=False)
    assert observed_crossing_completion(following,str(actor['id']),clock[0])
    assert following['constraint_completion']['observed_at']>first['observed_at']
    policy.on_tick(.033);acc.on_tick(.033);ap.on_tick(.033);engine._flush_controls()
    assert state.get('autopilot_active') and not acc._followed_target
    # Missing in a NEW acquisition is never a completion witness. Nor can a
    # later reappearance bridge the broken original native continuity chain.
    missing,_=step(joint,[],4,pedals=False)
    assert not missing['constraint_completion']
    returned,_=step(joint,[turned],5,pedals=False)
    assert not returned['constraint_completion']
    returned,_=step(joint,[turned],6,pedals=False)
    assert not returned['constraint_completion']


def test_cached_completion_cannot_hide_changed_geometry_conflict(joint):
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    actor=crossing(at=32.,arrival=4.1)
    step(joint,[actor],1)
    following,_=step(joint,[dict(actor,x=actor['x']+1.1,yaw=math.pi)],2,pedals=False)
    assert following['constraint_completion']
    conflict=dict(following['crossing'],conflicts=[dict(id=actor['id'])])
    assert engine._acc_selector.crossing_completion(conflict,following['body_prediction']) is None


def test_crossing_does_not_overwrite_stronger_leads_departure_owner(joint):
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    lead=dict(id=29,x=2.25,y=10.,z=45.,yaw=math.pi,speed=3.)
    following,packet=step(joint,[lead,crossing(at=40.,arrival=4.1)],1)
    scope=packet['motion_constraint'];assert len(scope['targets'])==2
    winner=min(scope['targets'],key=lambda t:(t['cap_mps'],t['id']))
    assert winner['id']=='29' and acc._following_target_id=='29'
    assert engine._acc_selector.target_id=='29'


def test_published_owner_is_actual_stronger_crossing_not_projected_lead(joint):
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    lead=dict(id=29,x=2.25,y=10.,z=65.,yaw=math.pi,speed=5.)
    actor=crossing(at=32.,arrival=4.1)
    step(joint,[lead,actor],1)
    assert acc._following_target_id=='83' and acc._following_kind=='crossing'
    assert state.get('longitudinal_acc')['following_target_id']=='83'
    assert engine._acc_selector.target_id=='83'
    # Losing an unused projection must not masquerade as losing the actual
    # acquired owner. The original controlling crossing still has fresh data.
    # Native write_active_traffic_data sorts/compacts each acquisition. Losing
    # the unused lead moves the same uniquely identified crossing to slot 0.
    following,_=step(joint,[dict(actor,x=actor['x']+.1)],2)
    witness=next(w for w in following['owner_witnesses'] if w['target_id']=='83')
    assert witness['slot']==1 and witness['current_slot']==0 and witness['chain_valid']
    assert state.get('autopilot_active'),state.get('autopilot_intervention')
    assert not acc._following_fault


def test_slow_acc_receives_original_completion_while_new_crossing_owns_cap(joint):
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    original=crossing(at=32.,arrival=4.1)
    step(joint,[original],1)
    turned=dict(original,x=original['x']+1.1,yaw=math.pi)
    other=crossing(at=40.,arrival=4.5,aid=84)
    step(joint,[turned,other],2,pedals=False)
    step(joint,[dict(turned,x=turned['x']+.1),dict(other,x=other['x']+.1)],3,pedals=False)
    policy.on_tick(.033);acc.on_tick(.033);ap.on_tick(.033);engine._flush_controls()
    assert state.get('autopilot_active'),state.get('autopilot_intervention')
    assert not acc._following_fault and acc._following_target_id=='84'


def test_two_completions_before_acc_tick_preserve_both_original_owners(joint):
    from core.acc_following import observed_crossing_completion
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    original=crossing(at=32.,arrival=4.1)
    step(joint,[original],1)
    turned=dict(original,x=original['x']+1.1,yaw=math.pi)
    other=crossing(at=40.,arrival=4.5,aid=84)
    step(joint,[turned,other],2,pedals=False)
    following,packet=step(joint,[dict(turned,x=turned['x']+.1),
        dict(other,x=other['x']+1.1,yaw=math.pi)],3,pedals=False)
    assert len(following['constraint_completions'])==2
    assert observed_crossing_completion(following,'83',clock[0])
    assert observed_crossing_completion(following,'84',clock[0])
    # The final write gate can consume this traffic publication before ACC.
    engine._flush_controls()
    assert not state.get('autopilot_intervention')
    assert physical('aforward')==0.
    policy.on_tick(.033);acc.on_tick(.033);ap.on_tick(.033);engine._flush_controls()
    assert state.get('autopilot_active') and not acc._followed_target
    assert not acc._following_fault


def test_new_lead_projection_cannot_erase_original_crossing_completion(joint):
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    original=crossing(at=32.,arrival=4.1)
    step(joint,[original],1)
    turned=dict(original,x=original['x']+1.1,yaw=math.pi)
    lead=dict(id=29,x=2.25,y=10.,z=65.,yaw=math.pi,speed=5.)
    step(joint,[turned,lead],2)
    assert not acc._following_fault
    assert state.get('autopilot_active'),state.get('autopilot_intervention')
    assert state.get('longitudinal_acc')['following_target_id']=='29'


@pytest.mark.parametrize('fault',['missing','ambiguous','teleport','prediction','duplicate'])
def test_crossing_completion_requires_original_fresh_continuous_owner(joint,fault):
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    actor=crossing(at=32.,arrival=4.1)
    step(joint,[actor],1)
    turned=dict(actor,x=actor['x']+1.1,yaw=math.pi)
    actors=([ ] if fault=='missing' else [dict(turned,x=turned['x']+.1),turned] if fault=='ambiguous'
        else [dict(turned,x=turned['x']+80.)] if fault=='teleport' else [turned])
    following,_=step(joint,actors,2,pedals=False)
    if fault=='prediction':
        selector=engine._acc_selector
        selector._constraint_completion=None
        selector.target_id=str(actor['id']);selector._target_is_crossing=True
        assert selector.crossing_completion(following['crossing'],{}) is None
    elif fault=='duplicate':
        proof=following['constraint_completion'];assert proof
        again=engine._acc_selector.crossing_completion(following['crossing'],following['body_prediction'])
        assert again==proof and again['observed_at']==proof['observed_at']
        from core.acc_following import observed_crossing_completion
        assert not observed_crossing_completion(following,str(actor['id']),proof['observed_at']+.501)
    else:assert not following.get('constraint_completion')


@pytest.mark.parametrize('count',[65,80])
def test_dense_scene_retains_actual_priority_actor_in_original_budget(joint,count,monkeypatch):
    from core.navigation.longitudinal_diagnostics import bounded_copy
    from core.traffic_dev_hud import FRAME_BUDGET
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    state.set('dev_hud_enabled',True)
    monkeypatch.setattr('tests.traffic.test_crossing_dev_hud.capture',dense_capture)
    # Put the actual relevant lead LAST in native order. The rest are real
    # decoded, distant detections, not made-up substitute display geometry.
    actors=[dict(id=100+i,x=70.+i,y=10.,z=180.+i,yaw=math.pi,speed=5.)
        for i in range(count-1)]
    actors.append(dict(id=29,x=2.25,y=10.,z=45.,yaw=math.pi,speed=3.))
    for generation in range(1,6):step(joint,actors,generation)
    snapshot=engine._dev_hud.snapshot();frame=snapshot['detection']
    assert frame.get('actors'),frame
    assert 29 in {a['id'] for a in frame['actors']}
    assert frame['omitted_actors']==count-len(frame['actors'])
    assert not bounded_copy(frame,limit=FRAME_BUDGET)[0].get('snapshot_status')
    assert not state.get('autopilot_intervention')
    engine._dev_hud.close()


def test_dense_scene_preserves_emergency_body_and_long_identity(joint,monkeypatch):
    from core.traffic_dev_hud import FRAME_BUDGET,geometry
    from core.navigation.longitudinal_diagnostics import bounded_copy
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    state.set('dev_hud_enabled',True)
    monkeypatch.setattr('tests.traffic.test_crossing_dev_hud.capture',dense_capture)
    actors=[dict(id=100+i,x=70.+i,y=10.,z=180.+i,yaw=math.pi,speed=5.) for i in range(79)]
    actors.append(dict(id=29,x=2.25,y=10.,z=16.,yaw=math.pi,speed=0.))
    saved={};original=geometry
    def inspect(*args,**kwargs):
        frame=original(*args,**kwargs);saved['frame']=frame
        # Same decoded acquisition and physical owners, adversarial display
        # identity length. This is a budget probe, not route-authority proof.
        extended=list(args);extended[4]=['identity-'+str(i)+'x'*2048 for i in range(8)]
        long=original(*extended,**kwargs);saved['long']=long
        return frame
    monkeypatch.setattr('core.traffic_dev_hud.geometry',inspect)
    step(joint,actors,1)
    for frame in saved.values():
        assert frame['actors'][0]['id']==29
        assert frame['actors'][0]['bodies']
        assert frame['omitted_priority_actors']==0
        assert frame['omitted_actors']==80-len(frame['actors'])
        assert not bounded_copy(frame,limit=FRAME_BUDGET)[0].get('snapshot_status')
    assert physical('aforward')==0. and physical('abackward')==1.
    engine._dev_hud.close()


def test_dense_ambiguous_ids_keep_exact_omission_counts(joint,monkeypatch):
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    state.set('dev_hud_enabled',True)
    monkeypatch.setattr('tests.traffic.test_crossing_dev_hud.capture',dense_capture)
    actors=[dict(id=100+i,x=70.+i,y=10.,z=180.+i,yaw=math.pi,speed=5.) for i in range(79)]
    actors[-1]['id']=actors[0]['id']  # Different parked source record; no deduplication.
    actors.append(dict(id=29,x=2.25,y=10.,z=45.,yaw=math.pi,speed=3.))
    step(joint,actors,1,pedals=False)
    frame=engine._dev_hud.snapshot()['detection']
    assert frame['omitted_actors']>0
    assert frame['omitted_bodies']==80-sum(len(a['bodies']) for a in frame['actors'])
    engine._dev_hud.close()


def test_fresh_native_detection_is_available_without_active_navigation(joint):
    from core.traffic_dev_hud import for_display,actor_style
    from core.longitudinal import context
    state,engine,ap,acc,policy,tick,_,n,physical,writes,clock=joint
    n();engine._flush_controls()
    state.set('dev_hud_enabled',True)
    debug=state.get('nav_steering_debug');debug['authority_valid']=False
    state.set('nav_steering_debug',debug)
    # The actual SDK snapshot from the prior tick is still fresh, but Map has
    # no authority. Offer that real capture without calling the fixture's
    # active-navigation assertion/update again.
    values=list(joint);values[5]=lambda *args,**kwargs:None
    step(values,[dict(id=9,x=2.25,y=10.,z=45.,yaw=math.pi,speed=3.)],1)
    snapshot=engine._dev_hud.snapshot()
    assert snapshot['detection'] and snapshot['detection']['actors']
    shown=for_display(snapshot,context(state),False)
    assert actor_style(shown['detection']['actors'][0],shown,clock[0])[0]=='passive'
    assert physical('aforward')==0.
    engine._dev_hud.close()


@pytest.mark.parametrize('mode',[0,3])
def test_same_red_stop_remembers_braking_across_external_limit(flow,mode,monkeypatch):
    from tests.signals.test_signal_lifecycle import lifecycle
    from core.longitudinal import publish
    from tests.test_roundabout_intervention_reporting import pedal
    state,truck,engine,ap,tick,n,clock,writes,collector=lifecycle(flow,mode)
    # Extend the existing authored directed passage to a moving approach.
    lane=state.get('lane_trajectory');lane['points']=[[0.,10.,0.],[0.,10.,-150.]]
    p=lane['signal_passages']['passages'][0]
    p.update(entry_xyz=[0.,10.,-40.],entry_progress_m=40.,
        bounds_xyz=[-5.,9.,-60.,5.,11.,0.])
    state.set('lane_trajectory',lane)
    state.set('lane_trajectory_publication_token','oct16-moving-signal')
    acc=tick.acc;policy=tick.policy
    tick(4,8.0,color=2)
    assert acc._signal_stop_started
    # Same red target, a short independent producer brake. Its withdrawal is
    # NOT a new approach: the previous brake response can still be acting.
    original=policy.on_tick
    def extra(dt):
        original(dt)
        truck=state.get('telemetry')['truck']
        old=state.get('longitudinal_policy')
        publish(state,truck,'policy',brake=.12,planned_speed_ms=old['planned_speed_ms'])
    monkeypatch.setattr(policy,'on_tick',extra)
    tick(4,6.0,color=2)
    monkeypatch.setattr(policy,'on_tick',original)
    tick(4,6.0,color=2)
    assert state.get('autopilot_active'),state.get('autopilot_intervention')
    assert pedal(engine,'aforward')==0.
    assert acc._signal_stop_started
