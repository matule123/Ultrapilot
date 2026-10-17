"""Evening Oct 15 regressions through native capture and physical output."""
import math
from types import SimpleNamespace

import pytest

from tests.test_oct11_joint_regressions import joint  # noqa: F401
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_acc_following import capture
from tests.test_oct14_completion import native_bytes
from core.longitudinal import context
from core.navigation.traffic_producer import capture_traffic
from core.sdk.traffic_snapshot import TrafficReader


def step(joint, actors, generation, speed=7.6, *, pedals=True):
    state, engine, ap, acc, policy, tick, _, _, _, _, clock = joint
    tick(gear=4, speed=speed, z=15., pedals=False)
    truck = state.get('telemetry')['truck']
    raw = capture(actors, clock[0])
    reader = SimpleNamespace(_timed_traffic_reader=TrafficReader())
    reader._timed_traffic_reader.buffer = native_bytes(raw, clock[0], generation,
        truck['sdkFrameTimeUs'], anchor=(truck['x'], truck['y'], truck['z']), ego_speed=speed,
        ego=[(truck['x'], truck['y'], truck['z'], 0., 0., 1., 0., 2.5, 4., 6.)])
    consumed = capture_traffic(reader, str(context(state)[1]), clock[0])
    following, brake = engine._traffic_control_observation(consumed, truck, context(state), [])
    packet = engine._publish_traffic_control(truck, truck['_control_observation']['observed_at'],
        context(state), [], consumed, following, brake,
        dict(valid=False, candidate=None, reason='no head', coverage={}), None)
    if pedals:
        policy.on_tick(.033); acc.on_tick(.033); ap.on_tick(.033); engine._flush_controls()
    return following, packet


def crossing(at=60., arrival=7.97, aid=83):
    # Native +Z directed route. This actor would intersect if it continued
    # straight for eight seconds; no observed 3 s body contact exists.
    return dict(id=aid, x=2.25-at, y=10., z=15.+at, yaw=-math.pi/2, speed=at/arrival)


def test_passive_distant_crossing_cannot_create_an_active_speed_cap(joint):
    state, engine, ap, acc, policy, tick, _, _, physical, writes, clock = joint
    following, packet = step(joint, [crossing()], 1)
    assert following['crossing']['conflicts']
    assert following['crossing']['brake'] == 0.
    assert following['body_prediction']['brake'] == 0.
    assert packet['motion_constraint'] is None
    assert not acc._followed_target
    assert state.get('longitudinal_acc')['valid']
    assert state.get('longitudinal_acc')['brake'] == 0.
    assert state.get('autopilot_active')
    assert physical('abackward') == 0.


def test_body_brake_supersedes_ordinary_following_without_invalidating_acc(joint):
    state, engine, ap, acc, policy, tick, _, _, physical, writes, clock = joint
    lead = crossing(at=32., arrival=4.1)
    step(joint, [lead], 1)
    assert acc._followed_target
    # The same lead remains observed. A different immediate crossing body
    # removes the positive-motion scope at Engine; this is NOT source loss.
    hazard = dict(id=48, x=-9.2, y=10., z=38., yaw=-math.pi/2, speed=4.)
    following, packet = step(joint, [lead, hazard], 2)
    assert packet['traffic_brake'] > 0.
    assert state.get('longitudinal_acc')['valid'], state.get('longitudinal_acc')
    assert not acc._following_fault
    assert state.get('autopilot_control_state') != 'controlled_stop'
    assert physical('aforward') == 0. and physical('abackward') > 0.


def test_passive_second_crossing_does_not_inherit_another_actors_demand(joint):
    from tests.test_oct14_completion import timed_step
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    # Preserve the ORIGINAL two-crossing fixture too. Only 42 demands braking:
    # 43's 5.45 s intersection has zero selector urgency, not acquired ownership.
    actors=[dict(id=42,x=-20.,y=10.,z=75.,yaw=-math.pi/2,speed=5.),
            dict(id=43,x=-25.,y=10.,z=85.,yaw=-math.pi/2,speed=5.)]
    following=timed_step(joint,actors,generation=1,speed=10.,
        ego=[(2.25,10.,15.,0.,0.,1.,0.,2.5,4.,6.)])
    demands={c['id']:c['brake'] for c in following['crossing']['conflicts']}
    assert demands[42]>0. and demands[43]==0.
    assert {t['id'] for t in following['motion_constraint']['targets']}=={'42'}
    assert state.get('autopilot_active')
    assert not engine._service_brake_hold
    assert not (physical('aforward')>0. and physical('abackward')>0.)


@pytest.mark.parametrize('fault', ['missing','ambiguous','teleport','lifecycle','stale'])
def test_missing_or_reassigned_old_owner_is_not_continuing_braking(joint, fault):
    from core.acc_following import observed_braking_continuation
    import copy
    state, engine, ap, acc, policy, tick, _, _, physical, writes, clock = joint
    lead=crossing(at=32.,arrival=4.1)
    step(joint,[lead],1)
    hazard=dict(id=48,x=-9.2,y=10.,z=38.,yaw=-math.pi/2,speed=4.)
    actors=([hazard] if fault=='missing' else [lead,dict(lead,x=lead['x']+.1),hazard] if fault=='ambiguous'
        else [dict(lead,x=lead['x']+30.),hazard] if fault=='teleport' else [lead,hazard])
    following,packet=step(joint,actors,2,pedals=False)
    if fault in ('lifecycle','stale'):
        packet=copy.deepcopy(packet)
        proof=packet['following'].get('retained_target_continuity') or {}
        proof['lifecycle' if fault=='lifecycle' else 'observed_at']=-1
    assert not observed_braking_continuation(packet,'83',clock[0])
    if fault in ('missing','ambiguous','teleport'):
        policy.on_tick(.033);acc.on_tick(.033);ap.on_tick(.033);engine._flush_controls()
        assert physical('aforward')==0.
        assert state.get('autopilot_control_state')=='controlled_stop' or not state.get('autopilot_active')


@pytest.mark.parametrize('kind', ['interval','target','regression','future','reverse','identity'])
def test_invalid_acc_cause_survives_compact_fault_receipt(joint,kind,monkeypatch):
    from core.longitudinal import rejection_details,context
    from core.navigation.longitudinal_diagnostics import bounded_fault_details
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    step(joint,[],1)
    truck=state.get('telemetry')['truck']
    if kind=='target':state.set('acc_target_speed',float('nan'))
    elif kind=='regression':
        truck['sdkFrameTimeUs']-=1;truck['_control_observation']['sdk_frame_us']-=1
        state.set('telemetry',{'truck':truck})
    elif kind=='future':
        truck['_control_observation']['observed_at']=clock[0]+.01
        state.set('telemetry',{'truck':truck})
    elif kind=='reverse':truck['gear']=-1;state.set('telemetry',{'truck':truck})
    elif kind=='identity':
        import plugins.acc.main as module
        original=module.publish
        def changed(*args,**kwargs):
            state.set('game_session_id','foreign')
            return original(*args,**kwargs)
        monkeypatch.setattr(module,'publish',changed)
        # Force a real new producer decision, not a duplicate-frame no-op.
        tick(gear=4,speed=7.7,z=15.,pedals=False)
    acc.on_tick(.7 if kind=='interval' else .033)
    value=state.get('longitudinal_acc')
    assert value['valid'] is False
    assert value['invalid_reason']
    fault=rejection_details(value,context(state),clock[0])
    fault['huge_optional']=['x'*10000]*10
    saved=bounded_fault_details(fault)
    assert saved['invalid_reason']==value['invalid_reason']
    assert not saved.get('snapshot_status')


def test_dev_hud_contains_exact_native_geometry_and_backend_receipt(joint):
    from core.traffic_dev_hud import acquisition
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    state.set('dev_hud_enabled',True)
    lead=dict(id=29,x=2.25,y=10.,z=52.,yaw=math.pi,speed=5.)
    for gen in range(1,8):step(joint,[dict(lead,z=52.+gen*.1)],gen)
    feed=engine._dev_hud
    if feed.future:feed.future.result(timeout=3)
    snap=feed.snapshot()
    assert snap['detection'].get('actors'),snap
    assert snap['applied'].get('sequence')
    assert snap['applied']['write_stats']['write_success_count']>0
    written=next(v for at,ch,v in reversed(writes)
        if ch=='aforward' and at<=snap['applied']['recorded_at'])
    assert snap['applied']['backend_pair']['throttle']==pytest.approx(written,abs=1e-5)
    assert not snap['applied']['game_consumption_verified']
    assert len(feed.frames)<=2
    # Geometry is either exactly matched or explicitly unavailable; no old
    # same-ID pose may be relabelled as the applied source.
    if snap['consumed_geometry']:
        assert acquisition(snap['consumed_geometry']['source'])==acquisition(snap['applied']['traffic_source'])
    state.set('dev_hud_enabled',False)
    step(joint,[],9)
    assert not engine._dev_hud.active
    assert not feed.frames


def test_dev_actual_acc_brake_owner_has_exact_consumed_geometry(joint):
    from core.traffic_dev_hud import actor_style
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    state.set('dev_hud_enabled',True)
    lead=dict(id=29,x=2.25,y=10.,z=45.,yaw=math.pi,speed=3.)
    for gen in range(1,9):step(joint,[dict(lead,z=45.+gen*.1)],gen)
    snap=engine._dev_hud.snapshot()
    assert snap['attribution']=='EXACT_NATIVE_ACQUISITION_AND_ROUTE'
    actor=snap['consumed_geometry']['actors'][0]
    assert actor_style(actor,snap,clock[0])[0]=='service'
    assert snap['applied']['output_intent']['throttle']==0.
    assert snap['applied']['output_intent']['brake']>0.
    assert snap['applied']['braking_actor_ids']==['29']
    engine._dev_hud.close()


def test_dev_actual_emergency_is_red_for_its_cause(joint):
    from core.traffic_dev_hud import actor_style
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    state.set('dev_hud_enabled',True)
    following,packet=step(joint,[dict(id=77,x=2.25,y=10.,z=16.,yaw=math.pi,speed=0.)],1)
    snap=engine._dev_hud.snapshot()
    assert snap['applied']['backend_pair']['brake']==1.
    assert physical('aforward')==0.
    assert actor_style(snap['consumed_geometry']['actors'][0],snap,clock[0])[0]=='emergency'
    engine._dev_hud.close()


def test_body_prediction_capture_is_numerically_passive():
    from core.acc_body_prediction import predict
    from core.acc_following import RouteLeadSelector
    route=RouteLeadSelector();route.prepare([[0.,0.,-i] for i in range(151)],('route',))
    body=dict(x=-5.,y=0.,z=-12.,yaw=-math.pi/2,dimensions_whl=(2.,2.,4.))
    actor=dict(body,id=4,source='moving',slot=1,speed=4.,speed_source='buffer',bodies=[body])
    ego=[dict(body,x=0.,z=0.,yaw=0.,dimensions_whl=(2.5,4.,6.))]
    plain=predict(route,ego,[actor],10.,0.,(0.,0.,0.))
    debug={}
    captured=predict(route,ego,[actor],10.,0.,(0.,0.,0.),debug_geometry=debug)
    assert plain==captured
    assert debug['ego_samples']
    assert debug['actor_paths']


@pytest.mark.parametrize('style,expected', [('passive','passive'),('target','tracked'),
    ('cap','protective'),('brake','service'),('aeb','emergency'),('stale','invalid'),
    ('reused_id','passive'),('failed','protective'),('curve_brake','protective'),
    ('throttle_only','protective')])
def test_dev_colours_follow_physical_winner_not_actor_presence(style,expected):
    from core.traffic_dev_hud import actor_style
    actor=dict(id=83,source='moving',slot=3,record_fingerprint='old')
    applied=dict(target_id='83',source=dict(source='acc',brake=0.,emergency=False),
        braking_actor_ids=['83'],
        backend_pair=dict(throttle=.2,brake=0.),write_stats=dict(write_success_count=2,
            write_error_count=0,backend_brake_max=.4))
    snap=dict(applied=applied,consumed_geometry=dict(source=dict(observed_at=100.),actors=[actor]))
    if style=='passive':applied['target_id']=None
    if style in ('cap','brake','aeb','failed','curve_brake','throttle_only'):applied['targets']=[dict(id='83')]
    if style in ('brake','aeb','failed','curve_brake','throttle_only'):
        applied['backend_pair']=dict(throttle=0.,brake=.4)
        applied['source'].update(source='traffic' if style=='aeb' else 'curve' if style=='curve_brake' else 'acc')
    if style=='aeb':
        applied['source']['emergency']=True;applied['brake_basis']=dict(decisive=dict(id=83))
    if style=='failed':applied['write_stats']['write_error_count']=1
    if style=='throttle_only':applied['write_stats']['backend_brake_max']=None
    if style=='reused_id':actor=dict(actor,record_fingerprint='new')
    assert actor_style(actor,snap,100.6 if style=='stale' else 100.1)[0]==expected


@pytest.mark.parametrize('yaw', [0.,math.pi/2,-math.pi/2,2.4])
def test_dev_native_box_axes_match_control_sat(yaw):
    from core.traffic_dev_hud import body_corners
    body=dict(x=23.,y=8.,z=42.,yaw=yaw,dimensions_whl=(2.,3.,6.))
    corners=body_corners(body)
    width=(math.cos(yaw),-math.sin(yaw));forward=(-math.sin(yaw),-math.cos(yaw))
    for point in corners:
        dx,dz=point[0]-body['x'],point[2]-body['z']
        assert abs(dx*width[0]+dz*width[1])==pytest.approx(1.)
        assert abs(dx*forward[0]+dz*forward[1])==pytest.approx(3.)


@pytest.mark.parametrize('change',['activation','route','disabled'])
def test_dev_old_authority_is_muted_not_reassigned(change):
    from core.traffic_dev_hud import actor_style,for_display
    actor=dict(id=83,source='moving',slot=3,record_fingerprint='same')
    binding=[1,'session','map','dataset','intent',7,'build',['geometry']]
    frame=dict(context=binding,source=dict(observed_at=100.),actors=[actor])
    snap=dict(detection=frame,consumed_geometry=frame,applied=dict(context=binding,target_id='83'))
    expected=list(binding)
    if change=='activation':expected[0]=2
    if change=='route':expected[6]='other'
    shown=for_display(snap,expected,change!='disabled')
    assert not shown['control_current']
    # Disengagement suppresses control attribution, not a still-fresh native
    # detection. A retired route/activation remains unverified and muted.
    assert actor_style(actor,shown,100.1)[0]==('passive' if change=='disabled' else 'invalid')
    assert shown['detection']['context']==binding


@pytest.mark.parametrize('age,expected',[(.1,'passive'),(.7,'invalid')])
def test_dev_unmatched_consumed_geometry_keeps_detection_qualification(age,expected):
    from core.traffic_dev_hud import actor_style,for_display
    binding=[1,'session','map','dataset','intent',7,'build',['geometry']]
    actor=dict(id=83,source='moving',slot=3,record_fingerprint='new')
    frame=dict(context=binding,source=dict(observed_at=100.),actors=[actor])
    # The physical receipt exists but its EXACT native generation is not in
    # the two-frame display window. Fresh detection is still a detection; it
    # cannot inherit the unmatched receipt's positive brake attribution.
    snapshot=dict(detection=frame,consumed_geometry=None,
        applied=dict(context=binding,target_id='83',source=dict(source='acc',brake=.4),
            braking_actor_ids=['83'],backend_pair=dict(throttle=0.,brake=.4)))
    shown=for_display(snapshot,binding,True)
    assert shown['control_current']
    assert actor_style(actor,shown,100.+age)[0]==expected


def test_dev_display_failure_does_not_change_control(joint,monkeypatch):
    from core.traffic_dev_hud import DevHUDFeed
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    state.set('dev_hud_enabled',True)
    def failed(*args):raise RuntimeError('display adapter failure')
    monkeypatch.setattr(DevHUDFeed,'capture',failed)
    monkeypatch.setattr(DevHUDFeed,'offer',failed)
    monkeypatch.setattr(DevHUDFeed,'written',failed)
    for gen in range(1,5):step(joint,[],gen)
    assert state.get('autopilot_active')
    assert not state.get('autopilot_intervention')
    assert physical('abackward')==0.


def test_invalid_reason_roundtrips_existing_automatic_incident(joint,tmp_path):
    from core.steering_replay import inspect_replay
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    engine._automatic_replay_directory=tmp_path
    step(joint,[],1)
    acc.on_tick(.7)
    rejected=state.get('longitudinal_acc')
    ap.on_tick(.033);engine._flush_controls()
    assert state.get('autopilot_control_state')=='controlled_stop'
    journal=engine.controller._pedal_journal
    engine._finish_automatic_longitudinal_incident(journal,shutdown=True)
    engine._automatic_replay_writer.wait(5.)
    exported=list(tmp_path.glob('*automatic_disable.json'))
    assert len(exported)==1
    result=inspect_replay(exported[0])
    assert result['integrity_valid']
    fault=result['replay']['longitudinal']['first_intervention']
    assert fault['details']['invalid_reason']==rejected['invalid_reason']
    assert fault['details']['speed_control_reason']==rejected['speed_control_reason']
    assert fault['details']['observation_timestamp']==rejected['observation_timestamp']
    assert physical('aforward')==0.


def test_invalid_reason_preserves_deadline_and_full_runtime_identity(joint):
    from core.control_timing import record_control_fault
    from core.longitudinal import rejection_details
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    step(joint,[],1)
    acc.on_tick(.7)
    rejected=state.get('longitudinal_acc')
    binding=(15769995551900,'1','promods-1.59','d6cc7936fce4e902761abb5d',
        'ebea77f0a0bd446cbcbdad9ae13f4e22',7,'f5320dcad68e4cf2b331802977dc7cb4',
        ('lane_path','f6e44b5a0a280f891ddcadaf2975d6a12dc7fd6a2dc58a166df6c0bbe895fff9',True))
    rejected=dict(rejected,context=binding)
    details=rejection_details(rejected,binding,clock[0])
    details.update(vehicle_sdk_frame_us=rejected['sdk_frame_us'],
        vehicle_observation=dict(sdk_frame_us=rejected['sdk_frame_us'],
            observed_at=rejected['observation_timestamp'],valid=True,reason=None))
    saved=record_control_fault(state,'engine','acc: invalid longitudinal observation',
        details=details)['details']
    assert saved['invalid_reason']==rejected['invalid_reason']
    assert saved['deadline_basis']==rejected['deadline_basis']
    assert saved['actual_context']==saved['expected_context']
    assert tuple(saved['actual_context'][:7])==binding[:7]
    assert saved['vehicle_sdk_frame_us']==rejected['sdk_frame_us']
