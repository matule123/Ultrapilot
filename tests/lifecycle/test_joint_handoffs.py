"""Oct 18 causal counterexamples; actor poses are models, not missing history."""
import math
from copy import deepcopy

import pytest

from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.lifecycle.test_joint_regressions import joint  # noqa: F401
from tests.traffic.test_crossing_dev_hud import crossing, step
from tests.lifecycle.test_longitudinal_completion import timed_step


@pytest.mark.parametrize('speed', [10., 11., 12.])
def test_continuing_crossing_owner_keeps_its_scope_after_lead_selection(joint, speed):
    state, engine, ap, acc, policy, tick, _, _, physical, writes, clock = joint
    owner = crossing(at=60., arrival=6., aid=78)
    step(joint, [owner], 1, speed=15.)
    assert acc._following_target_id == '78' and acc._following_kind == 'crossing'
    lead = dict(id=107, x=2.25, y=10., z=110., yaw=math.pi, speed=5.)
    result = timed_step(joint, [dict(owner, x=owner['x']+.1), lead], generation=2,
        speed=speed, ego=[(2.25,10.,15.,0.,0.,1.,0.,2.5,4.,6.)])
    assert state.get('autopilot_active'), state.get('autopilot_intervention')
    assert not acc._following_fault
    assert state.get('longitudinal_acc')['valid']
    assert not (physical('aforward')>0. and physical('abackward')>0.)
    assert result.get('owner_witnesses')


def test_old_calculation_cannot_overwrite_a_new_epoch_result(joint, monkeypatch):
    from core.longitudinal import context, publish
    import core.longitudinal as module
    state, engine, ap, acc, policy, tick, _, n, physical, writes, clock = joint
    old_binding=context(state)
    truck=state.get('telemetry')['truck']
    original=module.packet
    accepted=[]
    def during_calculation(*args, **kwargs):
        # Cancellation/new N occurs while an old producer calculation is live.
        n(); clock[0]+=.001; n()
        current=context(state)
        assert current[0]!=old_binding[0]
        new=original(state, truck, 'acc', binding=current, throttle=0., brake=0., emergency=False)
        state.set('longitudinal_acc',new); accepted.append(deepcopy(new))
        return original(*args, **kwargs)
    monkeypatch.setattr(module,'packet',during_calculation)
    rejected=publish(state, truck, 'acc', binding=old_binding, throttle=.2, brake=0., emergency=False)
    assert rejected['valid'] is False
    assert state.get('longitudinal_acc')==accepted[0]
    engine._flush_controls()
    assert physical('aforward')==0.


def test_actual_acc_tick_cancelled_during_publication_cannot_poison_new_n(joint,monkeypatch):
    import plugins.acc.main as producer
    from core.longitudinal import context, packet
    state,engine,ap,acc,policy,tick,_,n,physical,writes,clock=joint
    tick(speed=4.,pedals=False)
    old_binding=context(state)
    publish=producer.publish
    offered=[]
    def late(*args,**kwargs):
        monkeypatch.setattr(producer,'publish',publish)
        n();clock[0]+=.001;n()
        assert context(state)[0]!=old_binding[0]
        current=packet(state,state.get('telemetry')['truck'],'acc',throttle=0.,brake=0.,emergency=False)
        state.set('longitudinal_acc',current)
        rejected=publish(*args,**kwargs)
        offered.append((current,rejected))
        return rejected
    monkeypatch.setattr(producer,'publish',late)
    acc.on_tick(.033)
    assert offered and offered[0][1]['valid'] is False
    assert state.get('longitudinal_acc')==offered[0][0]
    # New native/Map -> Policy/ACC -> AP -> actual physical owner, no restart.
    for generation in range(1,8):
        timed_step(joint,[],generation=generation,speed=4.,
            ego=[(2.25,10.,15.,0.,0.,1.,0.,2.5,4.,6.)])
    assert state.get('autopilot_active'),state.get('autopilot_intervention')
    assert not state.get('autopilot_intervention')
    assert physical('aforward')>0. and physical('abackward')==0.


def test_retired_malformed_ap_result_cannot_poison_a_new_activation(joint):
    from core.longitudinal import COMMAND_KEY, context, finalize, packet
    state,engine,ap,acc,policy,tick,_,n,physical,writes,clock=joint
    retired=context(state)
    n();clock[0]+=.001;n()
    current=packet(state,state.get('telemetry')['truck'],'autopilot',
        throttle=0.,brake=0.,emergency=False)
    state.set(COMMAND_KEY,current)
    assert context(state)!=retired
    finalize(state,state.get('telemetry')['truck'],float('nan'),0.,{},retired)
    assert state.get(COMMAND_KEY)==current
    for generation in range(1,5):
        timed_step(joint,[],generation=generation,speed=4.,
            ego=[(2.25,10.,15.,0.,0.,1.,0.,2.5,4.,6.)])
    assert state.get('autopilot_active'),state.get('autopilot_intervention')
    assert not state.get('autopilot_intervention')
    assert physical('aforward')>0. and physical('abackward')==0.
    # The same fault from the CURRENT activation must remain visible and stop
    # physical propulsion; publication isolation is not error suppression.
    finalize(state,state.get('telemetry')['truck'],float('nan'),0.,{},context(state))
    assert state.get(COMMAND_KEY)['valid'] is False
    engine._flush_controls()
    assert physical('aforward')==0.
    assert state.get('autopilot_intervention')


@pytest.mark.parametrize('mode',[0,3])
def test_repeated_complete_native_signal_cycles_preserve_the_same_activation(flow,tmp_path,mode):
    from tests.signals.test_signal_timing import timing_flow
    from tests.test_roundabout_intervention_reporting import pedal
    values,signal_step=timing_flow(flow,tmp_path,mode)
    state,truck,engine,ap,tick,n,clock,writes,collector=values
    activation=state.get('autopilot_failure_epoch')
    generation=100
    for cycle in range(5):
        signal_step(generation,'red',speed=10.,gear=4,progress=0.)
        for _ in range(12):
            generation+=1;signal_step(generation,'red',speed=0.,gear=0,progress=34.5)
            assert pedal(engine,'aforward')==0. and pedal(engine,'abackward')>0.
        for _ in range(6):
            generation+=1;signal_step(generation,'green',speed=0.,gear=0,progress=34.5)
        for _ in range(6):
            generation+=1;signal_step(generation,'green',speed=.4,gear=4,progress=34.6)
        assert state.get('autopilot_active'),state.get('autopilot_intervention')
        assert not state.get('autopilot_intervention')
        assert state.get('autopilot_failure_epoch')==activation
        assert pedal(engine,'aforward')>0. and pedal(engine,'abackward')==0.
        generation+=1
    assert not any(ch=='parkingbrake' for _,ch,_,_ in writes)


@pytest.mark.parametrize('mode',[0,3])
@pytest.mark.parametrize('publication_key',['simple_auto_launch','simple_auto_service_hold'])
@pytest.mark.parametrize('newer_vehicle',[False,True])
def test_green_resume_cannot_mix_pre_release_history_with_post_release_hold(flow,tmp_path,mode,publication_key,newer_vehicle,monkeypatch):
    from tests.signals.test_signal_timing import timing_flow
    from tests.test_roundabout_intervention_reporting import pedal
    values, signal_step=timing_flow(flow,tmp_path,mode)
    state, truck, engine, ap, tick, n, clock, writes, collector=values
    from core.navigation.longitudinal_diagnostics import PedalJournal
    journal=engine.controller._pedal_journal=PedalJournal();journal.enabled=True
    truck['powertrainObservation']=dict(schema=1,engine_enabled=True,engine_rpm=650.)
    signal_step(60,'red',speed=10.,progress=0.)
    for generation in range(61,74):
        signal_step(generation,'red',speed=0.,gear=0,progress=34.5)
    original=engine._resume_signal_wait
    pending=[]
    monkeypatch.setattr(engine,'_resume_signal_wait',lambda t,w:pending.append((deepcopy(t),deepcopy(w))))
    for generation in range(74,80):
        signal_step(generation,'green',speed=0.,gear=0,progress=34.5)
        if pending:break
    assert pending and state.get('simple_auto_service_hold')
    monkeypatch.setattr(engine,'_resume_signal_wait',original)
    fired=[]
    def publication(key):
        if key==publication_key:
            state.hook=None
            fired.append(True)
            if newer_vehicle:
                from core.transmission_mode import simple_auto_forward_transition
                flow[4](0,0.,dt=.001)
                latest=state.get('telemetry')['truck']
                if mode==0:
                    history,reason=simple_auto_forward_transition(state,latest,engine._simple_auto_forward_history)
                    assert not reason
                    engine._simple_auto_forward_history=history
                    state.set('simple_auto_forward_history',history)
                original(latest,pending[-1][1])
            else:original(*pending[-1])
    state.hook=publication
    monkeypatch.setattr(ap.sdk.shared_state,'get',state.get)
    flow[4](0,0.,dt=.01)  # new AP calculation, not a duplicate SDK frame
    ap.on_tick(.01)
    state.hook=None
    assert fired==[True]
    assert state.get('autopilot_active'),state.get('autopilot_intervention')
    assert not state.get('safety_hazard_active')
    assert state.get('longitudinal_command')['brake']==0.
    # Snapshot immediately: the detailed journal has its original 64 KiB
    # budget. A later export must not substitute new per-tick history here.
    from core.steering_replay import SteeringReplayBuffer,inspect_replay
    exported=SteeringReplayBuffer(2).export(tmp_path,reason='manual_disable',
        longitudinal=journal.snapshot(expanded=False,include_history=True))
    inspected=inspect_replay(exported)
    assert inspected['integrity_valid']
    rows=inspected['replay']['longitudinal']['events']
    resume_rows=[r for r in rows if (r.get('source') or {}).get('phase')=='signal_resume']
    assert resume_rows
    for row in resume_rows:
        source=row['source']
        assert source['service_hold'] is None
        assert tuple(source['launch']['request_id'])==tuple(state.get('service_brake_resume')['request_id'])
        if mode==0:
            assert source['forward_history']['launch_deadline_at'] is not None
    assert not inspected['replay']['longitudinal']['game_consumption_verified']
    for generation in range(82,88):
        signal_step(generation,'green',speed=.4,gear=4,progress=34.6)
    assert state.get('autopilot_active'),state.get('autopilot_intervention')
    assert pedal(engine,'aforward')>0. and pedal(engine,'abackward')==0.
    assert not any(ch=='parkingbrake' for _,ch,_,_ in writes)


def test_expiring_at_publication_starts_original_bounded_zero_handoff(joint,monkeypatch):
    from core.longitudinal import context, publish
    from core.navigation import longitudinal_diagnostics as diagnostics
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    timed_step(joint,[],generation=1,speed=5.,
        ego=[(2.25,10.,15.,0.,0.,1.,0.,2.5,4.,6.)])
    traffic=state.get('longitudinal_traffic')
    # Declared synthetic distant regulation makes this a required traffic leaf.
    # No acquired actor disappears across the >500ms interval: that separate
    # owner-loss negative must NOT be mistaken for a recoverable handoff.
    traffic['light']=dict(color='red',distance=130.,stop_target_kind='derived_directed_curve_entry')
    state.set('longitudinal_traffic',traffic)
    expiry=traffic['expires_at']
    # Exact historic age offsets relative to the traffic origin. Map/SDK keep
    # advancing; the independent traffic producer is delayed in this model.
    while clock[0]<expiry-.1:
        tick(speed=5.,pedals=False)
    clock[0]=expiry-.0731243-.033333
    tick(speed=5.,pedals=False)
    policy.on_tick(.033);acc.on_tick(.033)
    original=diagnostics.compact_decision
    def processing(value):
        result=original(value)
        clock[0]=expiry-.0318927
        return result
    monkeypatch.setattr(diagnostics,'compact_decision',processing)
    ap.on_tick(.033)
    monkeypatch.setattr(diagnostics,'compact_decision',original)
    command=state.get('longitudinal_command')
    assert command['expires_at']<=expiry+.1
    assert state.get('longitudinal_refresh_request'),command
    assert command['refresh_pending'] and command['throttle']==0.
    clock[0]=expiry+.0062305
    engine._flush_controls()
    assert state.get('autopilot_active'),state.get('autopilot_intervention')
    assert state.get('autopilot_control_state')!='controlled_stop'
    assert physical('aforward')==0.
    # One new source receipt, not retimestamping or rearming the old wait.
    token=state.get('longitudinal_refresh_request')['token']
    timed_step(joint,[],generation=2,speed=5.,
        ego=[(2.25,10.,15.,0.,0.,1.,0.,2.5,4.,6.)])
    assert state.get('autopilot_active'),state.get('autopilot_intervention')
    assert not state.get('longitudinal_command')['refresh_pending']
    assert state.get('longitudinal_refresh_completed')['token']==token
    assert not (physical('aforward')>0. and physical('abackward')>0.)


@pytest.mark.parametrize('failure',['missing','duplicate','teleport'])
def test_owned_crossing_is_not_cleared_by_an_unproven_replacement(joint,failure):
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    owner=crossing(at=60.,arrival=6.,aid=78)
    step(joint,[owner],1,speed=15.)
    lead=dict(id=107,x=2.25,y=10.,z=110.,yaw=math.pi,speed=5.)
    actors=[lead] if failure=='missing' else [owner,dict(owner,x=owner['x']+.1),lead] if failure=='duplicate' else [dict(owner,x=owner['x']+30.),lead]
    timed_step(joint,actors,generation=2,speed=10.,ego=[(2.25,10.,15.,0.,0.,1.,0.,2.5,4.,6.)])
    assert acc._following_fault
    assert physical('aforward')==0.


def test_owner_scope_and_independent_emergency_do_not_cancel_each_other(joint):
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    owner=crossing(at=60.,arrival=6.,aid=78)
    step(joint,[owner],1,speed=15.)
    hazard=dict(id=106,x=2.25,y=10.,z=16.,yaw=math.pi,speed=0.)
    timed_step(joint,[dict(owner,x=owner['x']+.1),hazard],generation=2,speed=10.,
        ego=[(2.25,10.,15.,0.,0.,1.,0.,2.5,4.,6.)])
    assert physical('aforward')==0. and physical('abackward')==1.


def test_atomic_manager_commit_rejects_an_epoch_change_and_regressing_result(joint):
    from core.ipc.shared_state import ControlStateManager, SharedState
    from core.longitudinal import context, packet
    state,*_=joint
    with ControlStateManager() as manager:
        raw=manager.control_dict(state.values)
        view=SharedState(raw)
        old=packet(view,view.get('telemetry')['truck'],'acc',throttle=.2,brake=0.,emergency=False)
        # The update is committed before the pending publish RPC reaches the
        # manager. It cannot pass a client-only precheck then overwrite N.
        raw.update({'autopilot_failure_epoch':context(view)[0]+1})
        new=packet(view,view.get('telemetry')['truck'],'acc',throttle=0.,brake=0.,emergency=False)
        assert view.publish_longitudinal('longitudinal_acc',new)
        assert not view.publish_longitudinal('longitudinal_acc',old)
        assert view.get('longitudinal_acc')==new
        older=dict(new,computed_at=new['computed_at']-.001)
        assert not view.publish_longitudinal('longitudinal_acc',older)
        assert view.get('longitudinal_acc')==new
        # A current producer fault is still published and rejected, not hidden
        # behind the previously good packet by the order guard.
        invalid=dict(new,valid=False,invalid_reason='producer fault')
        assert view.publish_longitudinal('longitudinal_acc',invalid)
        assert view.get('longitudinal_acc')['valid'] is False


def test_actual_manager_transport_carries_all_producers_to_backend(joint):
    from core.ipc.shared_state import ControlStateManager
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    with ControlStateManager() as manager:
        raw=manager.control_dict(state.values)
        state.values=raw
        for plugin in (ap,acc,policy,tick.publish_map.__self__):
            for view in (plugin.sdk,*plugin.sdk.__dict__.values()):
                if hasattr(view,'_state'):object.__setattr__(view,'_state',raw)
        lead=dict(id=29,x=2.25,y=10.,z=60.,yaw=math.pi,speed=5.)
        for generation in range(1,12):
            timed_step(joint,[dict(lead,z=60.+.1*generation)],generation=generation,speed=5.,
                ego=[(2.25,10.,15.,0.,0.,1.,0.,2.5,4.,6.)])
            assert not state.get('autopilot_intervention')
            assert state.get('autopilot_active')
            assert not (physical('aforward')>0. and physical('abackward')>0.)
        # Restore a local independent copy before the Manager exits, so the
        # fixture's worker shutdown cannot access a terminated proxy.
        restored=dict(raw)
        state.values=restored
        for plugin in (ap,acc,policy,tick.publish_map.__self__):
            for view in (plugin.sdk,*plugin.sdk.__dict__.values()):
                if hasattr(view,'_state'):object.__setattr__(view,'_state',restored)


def test_an_explicit_inactive_native_source_still_rejects_legacy_actor_bytes(monkeypatch):
    from core.navigation.traffic_producer import capture_traffic
    from core.acc_following import observation
    from core.sdk.traffic_snapshot import TrafficReader
    from tests.test_acc_following import capture
    from tests.lifecycle.test_longitudinal_completion import native_bytes
    from types import SimpleNamespace
    raw=capture([dict(id=29,x=1.,y=10.,z=40.,yaw=math.pi,speed=5.)],100.)
    native=TrafficReader();native.buffer=native_bytes(raw,100.,flags=0)
    reader=SimpleNamespace(_timed_traffic_reader=native,_traffic_buf=raw.moving,_parked_buf=raw.parked)
    bad=capture_traffic(reader,'session',100.)
    assert bad.source and bad.source['valid'] is False
    assert observation(bad,100.)['status']=='inactive_or_incomplete_source_capture'
    # Without a native producer the SAME explicit legacy fixture is readable,
    # but it never gains native timestamp/coverage authority.
    legacy=capture_traffic(SimpleNamespace(_traffic_buf=raw.moving,_parked_buf=raw.parked),'session',100.)
    assert observation(legacy,100.)['status']=='observed'
    assert legacy.source is None
