"""A new projected candidate must not replace the current ACC owner's proof."""
import math
import pytest

from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_oct11_joint_regressions import joint  # noqa: F401
from tests.test_oct15_crossing_dev_hud import step, crossing


def test_current_crossing_continuity_survives_new_lead_during_body_braking(joint):
    state, engine, ap, acc, policy, tick, _, _, physical, writes, clock = joint
    original = crossing(at=32., arrival=4.1, aid=28)
    step(joint, [original], 1)
    assert acc._following_target_id == '28'
    # New nearer projected candidate plus a real body-path conflict. The
    # original crossing owner remains observed in its original native slot.
    lead = dict(id=29, x=2.25, y=10., z=40., yaw=math.pi, speed=3.)
    hazard = dict(id=26, x=-9.2, y=10., z=38., yaw=-math.pi/2, speed=4.)
    following, packet = step(joint, [original, lead, hazard], 2)
    assert packet['traffic_brake'] > 0.
    assert following['retained_target_continuity']['target_id'] == '28'
    assert state.get('longitudinal_acc')['valid']
    assert not acc._following_fault
    assert state.get('autopilot_active')
    assert physical('aforward') == 0.
    assert physical('abackward') > 0.


@pytest.mark.parametrize('publications',[2,4,8])
def test_original_owner_survives_independent_producer_ticks(joint,publications):
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    original=crossing(at=32.,arrival=4.1,aid=28)
    step(joint,[original],1)
    lead=dict(id=29,x=2.25,y=10.,z=40.,yaw=math.pi,speed=3.)
    hazard=dict(id=26,x=-9.2,y=10.,z=38.,yaw=-math.pi/2,speed=4.)
    for generation in range(2,2+publications):
        following,packet=step(joint,[original,lead,hazard],generation,pedals=False)
    policy.on_tick(.033);acc.on_tick(.033);ap.on_tick(.033);engine._flush_controls()
    assert state.get('longitudinal_acc')['valid'],state.get('longitudinal_acc')
    assert not acc._following_fault
    assert acc._following_target_id=='28'  # not released by someone else's brake
    assert state.get('autopilot_active')
    assert physical('aforward')==0. and physical('abackward')>0.


def test_fault_explanation_survives_bounded_details():
    from core.control_timing import fault_explanation
    from core.navigation.longitudinal_diagnostics import bounded_fault_details
    details=dict(source='acc',invalid_reason='ACC target unavailable or unconfirmed departure; driver takeover required',
        following_target_id='28',decisive_brake_actor_id='26',huge=['x'*20000]*8)
    saved=bounded_fault_details(details)
    text=fault_explanation(dict(kind='technical',reason='acc: invalid longitudinal observation',details=saved))
    assert '28' in text and '26' in text and 'unconfirmed' in text


@pytest.mark.parametrize('original_kind',['lead','crossing'])
@pytest.mark.parametrize('dev',[False,True])
def test_stronger_other_body_brake_keeps_acquired_owner(joint,original_kind,dev):
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    state.set('dev_hud_enabled',dev)
    original=(crossing(at=32.,arrival=4.1,aid=28) if original_kind=='crossing'
        else dict(id=28,x=2.25,y=10.,z=45.,yaw=math.pi,speed=3.))
    step(joint,[original],1)
    other=crossing(at=28.,arrival=4.,aid=29)
    hazard=dict(id=26,x=-9.2,y=10.,z=38.,yaw=-math.pi/2,speed=4.)
    for gen in range(2,7):step(joint,[original,other,hazard],gen,pedals=False)
    policy.on_tick(.033);acc.on_tick(.033);ap.on_tick(.033);engine._flush_controls()
    assert acc._following_target_id=='28'
    assert not acc._following_fault
    assert state.get('autopilot_active') and physical('aforward')==0. and physical('abackward')>0.
    if dev:engine._dev_hud.close()


@pytest.mark.parametrize('fault',['missing','slot','teleport','reuse','stale_witness'])
def test_another_brake_cannot_repair_broken_original_owner(joint,fault):
    import copy
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    original=crossing(at=32.,arrival=4.1,aid=28)
    step(joint,[original],1)
    hazard=dict(id=26,x=-9.2,y=10.,z=38.,yaw=-math.pi/2,speed=4.)
    actors=([hazard] if fault in ('missing','reuse') else [hazard,original] if fault=='slot'
        else [dict(original,x=original['x']+30.),hazard] if fault=='teleport' else [original,hazard])
    following,packet=step(joint,actors,2,pedals=False)
    if fault=='reuse':
        # Missing acquisition breaks the original chain even if it returns to
        # the original slot and has a valid cap in subsequent acquisitions.
        step(joint,[original,hazard],3,pedals=False)
        following,packet=step(joint,[original,hazard],4,pedals=False)
    if fault=='stale_witness':
        packet=copy.deepcopy(packet)
        for proof in packet['following'].get('retained_target_continuities',[]):proof['observed_at']-=1.
        proof=packet['following'].get('retained_target_continuity')
        if proof:proof['observed_at']-=1.
        state.set('longitudinal_traffic',packet)
    policy.on_tick(.033);acc.on_tick(.033);ap.on_tick(.033);engine._flush_controls()
    assert physical('aforward')==0.
    assert acc._following_fault or not state.get('autopilot_active') or state.get('autopilot_control_state')=='controlled_stop'


def test_history_does_not_recolour_reused_id_or_technical_stop(joint):
    from core.traffic_dev_hud import for_display,actor_style
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    state.set('dev_hud_enabled',True)
    lead=dict(id=29,x=2.25,y=10.,z=45.,yaw=math.pi,speed=3.)
    for gen in range(1,9):step(joint,[dict(lead,z=45.+gen*.1)],gen)
    snap=engine._dev_hud.snapshot();history=snap['last_intervention']
    assert history['geometry']
    shown=for_display(snap,snap['applied']['context'],False)
    original=history['geometry']['actors'][0]
    assert actor_style(original,shown,clock[0]+5.,stale=True)[0]=='service'
    assert actor_style(dict(original,record_fingerprint='reused'),shown,clock[0]+5.)[0]=='passive'
    # A technical fallback may set emergency=True to remove drive immediately;
    # this is not an attributed object AEB and must never paint a red vehicle.
    shown['applied']=dict(shown['applied'],source=dict(source='engine_safety',emergency=True))
    assert actor_style(original,shown,clock[0]+5.)[0] not in ('service','emergency')
    engine._dev_hud.close()


def test_owner_fault_and_safe_writes_survive_automatic_export(joint,tmp_path):
    from core.steering_replay import inspect_replay
    from core.control_timing import first_control_fault_record
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    engine._automatic_replay_directory=tmp_path
    original=crossing(at=32.,arrival=4.1,aid=28)
    step(joint,[original],1)
    hazard=dict(id=26,x=-9.2,y=10.,z=38.,yaw=-math.pi/2,speed=4.)
    step(joint,[hazard],2)
    first=first_control_fault_record(state)
    assert first and '28' in first['explanation'] and '26' in first['explanation']
    engine.controller.release_all()
    engine._finish_automatic_longitudinal_incident(engine.controller._pedal_journal,shutdown=True)
    engine._automatic_replay_writer.wait(5.)
    exported=list(tmp_path.glob('*automatic_disable.json'))
    assert len(exported)==1
    checked=inspect_replay(exported[0]);assert checked['integrity_valid']
    saved=checked['replay']['longitudinal']['first_intervention']
    assert saved['reason']==first['reason'] and saved['explanation']==first['explanation']
    assert saved['details']['following_target_id']=='28'
    assert saved['details']['target_evidence']['decisive_brake_actor_id']==26
    assert saved['details']['observation_timestamp']==first['details']['observation_timestamp']
    assert physical('aforward')==0.


def test_continuous_hold_cause_is_orange_before_disable(joint):
    from core.traffic_dev_hud import actor_style
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    state.set('dev_hud_enabled',True)
    hazard=dict(id=26,x=-9.2,y=10.,z=38.,yaw=-math.pi/2,speed=4.)
    for gen in range(1,9):step(joint,[hazard],gen)
    snap=engine._dev_hud.snapshot()
    assert snap['applied']['source']['source']=='continuous_service_hold'
    assert snap['applied']['backend_pair']['brake']>0. and physical('aforward')==0.
    actor=next(a for a in snap['consumed_geometry']['actors'] if a['id']==26)
    assert actor_style(actor,snap,clock[0])[0]=='service'
    engine._dev_hud.close()


def test_hud_retains_exact_intervention_after_release(joint,monkeypatch):
    from core.traffic_dev_hud import for_display
    from core.traffic_dev_hud import DevHUDFeed
    original=DevHUDFeed.written
    errors=[]
    def checked(*args,**kwargs):
        try:return original(*args,**kwargs)
        except Exception as exc:errors.append(repr(exc));raise
    monkeypatch.setattr(DevHUDFeed,'written',checked)
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    state.set('dev_hud_enabled',True)
    lead=dict(id=29,x=2.25,y=10.,z=45.,yaw=math.pi,speed=3.)
    for gen in range(1,9):step(joint,[dict(lead,z=45.+gen*.1)],gen)
    feed=engine._dev_hud
    before=feed.snapshot()
    assert not errors,errors
    assert before['consumed_geometry']
    assert before['applied']['backend_pair']['brake']>0.
    assert before['last_intervention']
    engine._automatic_safety_stop('test technical owner loss')
    # Safety/release writes and new same-ID geometry must not rebind history.
    engine._flush_controls()
    shown=for_display(feed.snapshot(),before['applied']['context'],False)
    assert shown['last_intervention']['geometry']==before['consumed_geometry']
    assert shown['last_intervention']['applied']['backend_pair']['brake']>0.
    assert shown['history_only']
    assert shown['last_fault']['kind']=='technical'
    feed.close()


def test_unused_owner_witnesses_age_out_but_actual_dependency_is_pinned(joint):
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    owner=crossing(at=32.,arrival=4.1,aid=28)
    step(joint,[owner],1)
    hazard=dict(id=26,x=-9.2,y=10.,z=38.,yaw=-math.pi/2,speed=4.)
    lead=dict(id=29,x=2.25,y=10.,z=40.,yaw=math.pi,speed=3.)
    for gen in range(2,45):step(joint,[owner,lead,hazard],gen)
    assert acc._following_target_id=='28' and not acc._following_fault
    assert state.get('autopilot_active') and physical('aforward')==0.
    assert len(engine._acc_selector._retained_owners)<=16


def test_fault_summary_budget_keeps_kind_and_ids_with_long_cause():
    from core.traffic_dev_hud import DevHUDFeed
    from core.navigation.longitudinal_diagnostics import bounded_copy
    feed=DevHUDFeed()
    feed.record_fault(dict(epoch=1,kind='technical',producer='engine',observed_at=100.,
        sdk_frame_us=123,reason='x'*512,details=dict(source='acc',invalid_reason='y'*512,
            following_target_id='28',decisive_brake_actor_id='26')))
    assert feed.last_fault['kind']=='technical'
    assert '28' in feed.last_fault['explanation'] and '26' in feed.last_fault['explanation']
    assert not bounded_copy(feed.last_fault,limit=4096)[0].get('snapshot_status')
    feed.close()


def test_departure_after_missing_and_reappearing_id_cannot_release_old_owner(joint):
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    lead=dict(id=28,x=2.25,y=10.,z=45.,yaw=math.pi,speed=3.)
    hazard=dict(id=26,x=-9.2,y=10.,z=38.,yaw=-math.pi/2,speed=4.)
    step(joint,[lead],1)
    step(joint,[hazard],2,pedals=False)  # original actually disappears
    step(joint,[lead,hazard],3,pedals=False)
    for gen,x in enumerate((2.9,3.55,4.2,4.85,5.94),4):
        following,_=step(joint,[dict(lead,x=x),hazard],gen,pedals=False)
    # A newly continuous record pair can pass the ordinary geometric departure
    # test. It must NOT certify the dependency acquired before disappearance.
    assert following['departure']['target_id']=='28'
    assert not next(w for w in following['owner_witnesses'] if w['target_id']=='28')['chain_valid']
    policy.on_tick(.033);acc.on_tick(.033);ap.on_tick(.033);engine._flush_controls()
    assert acc._following_fault
    assert not state.get('longitudinal_acc')['valid']
    assert physical('aforward')==0.
