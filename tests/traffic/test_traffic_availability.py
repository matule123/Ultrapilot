"""Real capture/selector/producers/Engine/Controller; modeled source actors.

No fixture actor is claimed to be the missing Oct 10 native record. Backend
return proves a write, not consumption by ETS2.
"""
from dataclasses import replace
from copy import deepcopy
import math

import pytest

from core.acc_following import observation
from core.longitudinal import context, read
from core.navigation.traffic_producer import capture_traffic
from core.sdk.ets2la_data import ETS2LAData
from core.sdk.ets2la_data import _PARKED_FMT
import struct
from tests.test_acc_following import capture
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.traffic.test_traffic_control_contract import setup_route, forward_actor
from tests.test_roundabout_intervention_reporting import pedal


def produce(values, actors, *, fault=None, signal=None):
    state, truck, engine, ap, tick, n, clock, writes, collected = values
    binding = context(state)
    raw = capture(actors, clock[0])
    reader = ETS2LAData()
    reader._traffic_buf, reader._parked_buf = raw.moving, raw.parked
    cap = capture_traffic(reader, binding[1], clock[0])
    if fault == 'changing': cap = replace(cap, stable=False)
    if fault == 'missing': cap = replace(cap, moving=None)
    if fault == 'stale': cap = replace(cap, observed_at=clock[0]-.101)
    actual = state.get('telemetry')['truck']
    following, brake = engine._traffic_control_observation(cap, actual, binding, [])
    signal = signal or dict(valid=False, reason='prefab semaphore ID missing or spatially ambiguous',
        relevance='route_geometry_heuristic', coverage=dict(status='NOT_VERIFIED', requires_takeover=False))
    packet = engine._publish_traffic_control(actual, actual['_control_observation']['observed_at'],
        binding, [], cap, following, brake, signal, None)
    tick.policy.on_tick(.05); tick.acc.on_tick(.05); ap.on_tick(.05); engine._flush_controls()
    return cap, following, packet


@pytest.mark.parametrize('mode', [0,3])
@pytest.mark.parametrize('fault', ['duplicate', 'zero_id', 'changing', 'missing', 'stale'])
def test_optional_unusable_capture_is_not_invalid_vehicle_or_clearance(flow, mode, fault):
    values = setup_route(flow, mode)
    actor = forward_actor(values, lateral=10.)
    actors = [actor, dict(actor, z=actor['z']-10.)] if fault=='duplicate' else [dict(actor, id=0)] if fault=='zero_id' else [actor]
    cap, following, packet = produce(values, actors, fault=fault)
    assert packet['valid'] is True  # Vehicle/identity envelope, not usable actor evidence.
    assert packet['traffic_availability']['actors_usable'] is False
    assert not following.get('confirmed')
    assert packet['traffic_brake']==0 and pedal(values[2], 'abackward')==0
    assert values[0].get('autopilot_active')
    assert observation(cap,values[6][0])['complete'] is False


def test_coverage_fault_retains_specific_cause_despite_unusable_actors(flow):
    values=setup_route(flow,0)
    actor=forward_actor(values)
    signal=dict(valid=False,reason='unassigned direction', observed_at=values[6][0], frame_us=34,
        coverage=dict(status='UNASSIGNED',requires_takeover=True,reason='signal coverage requires takeover'))
    _,following,packet=produce(values,[actor,actor],signal=signal)
    assert values[0].get('autopilot_control_state')=='controlled_stop'
    assert 'signal coverage requires takeover' in values[0].get('automatic_safety_stop_reason','')
    assert pedal(values[2],'aforward')==0


def test_missing_and_duplicate_identity_keeps_bounded_original_slot_evidence():
    actor=dict(id=0,x=1.,y=10.,z=-20.,yaw=0.,speed=2.)
    result=observation(capture([actor],100.),100.01)
    assert result['status']=='ambiguous_actor_id'
    assert result['actor_identity']['missing_count']==1
    actor['id']=12
    result=observation(capture([actor,dict(actor,z=-30.)],100.),100.01)
    assert result['actor_identity']['duplicate_count']==1
    assert result['actor_identity']['examples'][0]['id']==12
    assert result['actor_identity']['examples'][0]['same_source_record'] is False
    assert result['receiver_time']==100. and result['source_timestamp'] is None


def test_retained_preincident_packet_alone_is_not_the_first_fault(flow):
    """Retained zero-demand/coverage=false packet is optional on deployed code.

    Its first physical source is before the AP rejection, not a replacement
    for that missing compared snapshot. Model the same fields/ages separately.
    """
    values=setup_route(flow,0)
    state,truck,engine,ap,tick,n,clock,writes,collected=values
    _,_,packet=produce(values,[forward_actor(values),forward_actor(values)])
    packet.update(valid=False,observation_timestamp=clock[0]-.1327139,
        computed_at=clock[0]-.1166689,expires_at=clock[0]+.3672861)
    state.set('longitudinal_traffic',packet)
    selected,reason=read(state,'traffic')
    assert selected is None and reason==''
    tick.policy.on_tick(.05);tick.acc.on_tick(.05);ap.on_tick(.05);engine._flush_controls()
    assert state.get('autopilot_active') and not state.get('automatic_safety_stop_reason')


def test_required_traffic_rejection_survives_detail_budget_and_export(flow,tmp_path):
    from core.control_timing import record_control_fault, first_control_fault_record
    from core.steering_replay import inspect_replay
    from core.navigation.longitudinal_diagnostics import bounded_fault_details
    values=setup_route(flow,0)
    actor=forward_actor(values)
    _,following,packet=produce(values,[actor,actor])
    details={}; _,reason=read(values[0],'traffic',required=True,rejection_info=details)
    # Explicitly required actor evidence cannot be satisfied by a valid envelope.
    assert reason and 'ambiguous_actor_id' in reason
    details['unrelated']='x'*20000
    saved=bounded_fault_details(details)
    assert saved['traffic_comparison']['following_status']=='ambiguous_actor_id'
    assert saved['sdk_frame_us']==packet['sdk_frame_us']
    assert saved['observation_timestamp']==packet['observation_timestamp']
    record_control_fault(values[0],'engine',reason,details=details)
    original=deepcopy(first_control_fault_record(values[0]))
    values[2]._automatic_replay_directory=str(tmp_path)
    values[2]._automatic_safety_stop(reason)
    values[2].controller.release_all()
    journal=values[2].controller._pedal_journal
    values[2]._finish_automatic_longitudinal_incident(journal,shutdown=True)
    exported=values[2]._automatic_replay_writer.wait(5.)['path']
    result=inspect_replay(exported)
    assert result['integrity_valid']
    fault=result['replay']['longitudinal']['first_intervention']
    assert fault['reason']==original['reason']
    assert fault['details']['traffic_comparison']['following_status']=='ambiguous_actor_id'


@pytest.mark.parametrize('same_values',[True,False])
def test_native_cross_buffer_overlap_is_not_content_deduplicated(same_values):
    actor=dict(id=23,x=1.,y=10.,z=-20.,yaw=0.,speed=0.)
    cap=capture([actor],100.)
    parked=list(struct.unpack(_PARKED_FMT,cap.parked))
    parked[:12]=[1.,10.,-20. if same_values else -50.,1.,0.,0.,0.,2.,2.,4.,23,0]
    cap=replace(cap,parked=struct.pack(_PARKED_FMT,*parked))
    result=observation(cap,100.01)
    assert result['status']=='ambiguous_actor_id' and len(result['actors'])==2
    example=result['actor_identity']['examples'][0]
    assert (example['prior_source'],example['source'])==('moving','parked')
    assert example['same_source_record'] is False


@pytest.mark.parametrize('mode',[0,3])
def test_acquired_following_loss_cannot_restore_cruise_on_ambiguity(flow,mode):
    values=setup_route(flow,mode)
    # Geometrically relevant slow lead, not a confirmed lane/coverage sensor.
    _,following,packet=produce(values,[forward_actor(values)])
    assert following['status']=='candidate'
    assert values[0].get('longitudinal_acc')['following_required']
    _,following,packet=produce(values,[forward_actor(values),forward_actor(values)])
    assert values[0].get('autopilot_control_state')=='controlled_stop'
    assert pedal(values[2],'aforward')==0
    assert values[0].get('autopilot_intervention')


@pytest.mark.parametrize('mode',[0,3])
def test_unusable_actor_feed_does_not_interrupt_same_signal_hold_and_restart(flow,mode):
    from tests.signals.test_stop_lifecycle import directed_stop
    from tests.test_signal_stop_resume import source_bytes
    values,_=directed_stop(flow,mode)
    state,truck,engine,ap,tick,n,clock,writes,collected=values
    def step(gear,speed,color):
        flow[4](gear,speed,dt=.05)
        engine._signal_reader.buffer=source_bytes(clock[0],truck['sdkFrameTimeUs'],
            truck['sdkFrameTimeUs'],color=color,signal_id=19)
        actual=state.get('telemetry')['truck']
        signal=engine._signal_observation(actual,context(state))
        actor=dict(id=44,x=40.,y=10.,z=-20.,yaw=0.,speed=1.)
        produce(values,[actor,actor],signal=signal)
    for cycle in range(2):
        step(4,2.,2)
        start=len(writes)
        for speed in (1.,.3,.03,0.,0.,0.):
            step(4 if mode==3 or speed>.05 else 0,speed,2)
            assert state.get('autopilot_active'),state.get('automatic_safety_stop_reason')
            assert pedal(engine,'aforward')==0 and pedal(engine,'abackward')>0
        assert all(v>0 for _,ch,v,_ in writes[start:] if ch=='abackward')
        for _ in range(5): step(0 if mode==0 else 4,0.,8)
        step(4,.2,8)
        for _ in range(3): step(4,.4,8)
        assert state.get('autopilot_active'),state.get('automatic_safety_stop_reason')
        assert pedal(engine,'aforward')>0 and pedal(engine,'abackward')==0
        assert not engine.controller.current_hazard


@pytest.mark.parametrize('fault',['phantom_brake','stale','identity','R','backend'])
def test_output_boundary_still_rejects_real_faults(flow,fault):
    values=setup_route(flow,0)
    _,_,packet=produce(values,[])
    state,truck,engine,ap,tick,n,clock,writes,collected=values
    if fault=='phantom_brake':
        packet['traffic_availability']['actors_usable']=False
        packet['following']['status']='ambiguous_actor_id'
        packet['traffic_brake']=.9
        state.set('longitudinal_traffic',packet)
    elif fault=='stale':
        packet['observation_timestamp']=clock[0]-.6
        packet['expires_at']=clock[0]-.1
        packet['following']['status']='candidate'
        state.set('longitudinal_traffic',packet)
    elif fault=='identity': state.set('navigation_intent_id','different-intent')
    elif fault=='R':
        flow[4](-1,0.,dt=.05)
    else: engine.controller.scs._buf.close()
    engine._flush_controls()
    if fault!='backend': assert pedal(engine,'aforward')==0
    assert state.get('autopilot_control_state')=='controlled_stop' or not state.get('autopilot_active')


def test_capture_detects_changed_bytes_but_cannot_certify_cross_buffer_generation():
    from types import SimpleNamespace
    old=capture([dict(id=3,x=1.,y=10.,z=-20.,yaw=0.,speed=2.)],100.)
    new=capture([dict(id=3,x=1.,y=10.,z=-21.,yaw=0.,speed=2.)],100.)
    class Changing:
        def __init__(self): self.reads=0
        def __getitem__(self,key):
            self.reads+=1
            return (old.moving if self.reads==1 else new.moving)[key]
    cap=capture_traffic(SimpleNamespace(_traffic_buf=Changing(),_parked_buf=old.parked),'session',100.)
    assert not cap.stable
    assert observation(cap,100.01)['status']=='changing_buffers'
    cap=capture_traffic(SimpleNamespace(_traffic_buf=new.moving,_parked_buf=old.parked),'session',100.)
    assert cap.stable  # Two stable buffers still have no common generation.
    decoded=observation(cap,100.01)
    assert decoded['atomic'] is False and decoded['source_sequence'] is None


@pytest.mark.parametrize('mode',[0,3])
def test_manual_disable_discards_old_traffic_activation(flow,mode):
    values=setup_route(flow,mode)
    _,_,packet=produce(values,[])
    state,truck,engine,ap,tick,n,clock,writes,collected=values
    n();engine._flush_controls()
    assert not state.get('autopilot_active')
    assert pedal(engine,'aforward')==pedal(engine,'abackward')==0.
    flow[4](4,.3,dt=.05);n()
    state.set('longitudinal_traffic',packet)
    packet['traffic_brake']=1.
    state.set('longitudinal_traffic',packet)
    engine._flush_controls()
    assert pedal(engine,'aforward')==0.


@pytest.mark.parametrize('shape',['following','availability'])
def test_malformed_roles_fail_closed_without_diagnostic_exception(flow,shape):
    values=setup_route(flow,0)
    _,_,packet=produce(values,[])
    if shape=='following':packet['following']=['invalid']
    else:packet['traffic_availability']={'schema_version':1,'actors_usable':'yes'}
    packet['traffic_brake']=.8
    values[0].set('longitudinal_traffic',packet)
    details={}
    selected,reason=read(values[0],'traffic',rejection_info=details)
    assert selected is None and reason and details['rejected_source']=='traffic'
