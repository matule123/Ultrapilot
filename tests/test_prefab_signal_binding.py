"""Directed prefab signal receipts, not painted-line or live SDK proof."""
import json
import math
import struct
from dataclasses import replace

import pytest

from core.navigation.road_network import RoadNetwork
from core.navigation.lane_model import LaneId, LanePoint, LaneSegment, LaneConnection, GpsCorridorEdge
from core.sdk.signal_snapshot import RouteSignalSelector
from tests.test_activation_observation_binding import flow  # noqa: F401


def parsed_path(tmp_path, reverse=False, turn=False, lane_shift=0.):
    def transform(x, z, yaw):
        return dict(x=x+lane_shift, y=z, z=0., rotationQuat=[math.cos(yaw/2),0.,math.sin(yaw/2),0.])
    end = (25., -30.) if turn else (0.,-30.)
    raw = dict(token='signal_fixture', path='fixture.ppd', nodes=[
        dict(x=0.,y=0.,z=0.,rotation=0.,inputLanes=[0],outputLanes=[1]),
        dict(x=end[0],y=end[1],z=0.,rotation=0.,inputLanes=[1],outputLanes=[0])],
        navCurves=[dict(start=transform(0.,0.,0.),end=transform(*end, -math.pi/2 if turn else 0.),
                        navNodeIndex=1,nextLines=[],prevLines=[],semaphoreId=3),
                   dict(start=transform(*end, math.pi),end=transform(0.,0.,math.pi),
                        navNodeIndex=0,nextLines=[],prevLines=[],semaphoreId=4)], navNodes=[
                dict(type='physical',endIndex=0,connections=[dict(targetNavNodeIndex=1,curveIndices=[0])]),
                dict(type='physical',endIndex=1,connections=[dict(targetNavNodeIndex=0,curveIndices=[1])])])
    (tmp_path/'prefabDescriptions.json').write_text(json.dumps([raw]),encoding='utf-8')
    (tmp_path/'prefabs.json').write_text(json.dumps([dict(token='signal_fixture',nodeUids=['b','c'],
        originNodeIndex=0,x=0.,y=-100.)]),encoding='utf-8')
    net=RoadNetwork();net.loaded=True
    net.nodes.update({11:(0.,-100.),12:(end[0],-100.+end[1])})
    net.node_alt.update({11:10.,12:10.});net.node_rot.update({11:0.,12:0.})
    net._load_prefabs(str(tmp_path))
    instance=('signal_fixture',(11,12),0,True)
    index=1 if reverse else 0
    points=net._prefab_curve_chain_3d(instance,(index,))
    edge=GpsCorridorEdge(12 if reverse else 11,11 if reverse else 12,'prefab',1,prefab_instance=instance)
    prefab=net._make_prefab_lane_segment(edge,instance,(index,),points)
    heading=points[0].heading
    p=points[0]
    a=LanePoint(p.x+100.*math.sin(heading),p.y,p.z+100.*math.cos(heading),heading=heading)
    road_id=LaneId(100,1,0)
    road=LaneSegment(road_id,10,edge.start_uid,1,0,1,4.5,'derived',3,None,'road',
        (a,replace(p,lane_id=road_id)),successors=(LaneConnection(prefab.lane_id,'prefab'),),gps_pair_index=0)
    path=net.connect_lane_sequence((road,prefab),(10,edge.start_uid,edge.end_uid))
    assert path.valid,path.failure_reason
    from core.navigation.lane_trajectory import build_lane_trajectory
    path=build_lane_trajectory(path)
    assert path.valid,path.failure_reason
    return net,path,instance


def plan_for(net,path):
    from core.navigation.prefab_signals import prepare_signal_passages
    return prepare_signal_passages(net,path)


@pytest.mark.parametrize('reverse',[False,True])
def test_parser_preserves_authored_signal_id_and_directed_entry(tmp_path,reverse):
    net,path,instance=parsed_path(tmp_path,reverse)
    assert net._prefab_lane_data['signal_fixture']['curves'][int(reverse)]['semaphore_id']==(4 if reverse else 3)
    plan=plan_for(net,path)
    assert plan['status']=='prepared' and len(plan['passages'])==1
    passage=plan['passages'][0]
    assert passage['entry_progress_m']==pytest.approx(100.)
    p=path.segments[1].centerline[0]
    assert passage['entry_xyz']==[p.x,p.y,p.z]
    assert passage['semaphore_id']==(4 if reverse else 3)


def test_prefab_assignment_uses_route_id_not_nearest_green_head(tmp_path):
    net,path,_=parsed_path(tmp_path)
    plan=plan_for(net,path)
    lights=[dict(id=19,x=0.,y=10.,z=-40.,yaw=math.pi,color='green'),
            dict(id=3,x=2.,y=10.,z=-125.,yaw=math.pi,color='red'),
            dict(id=4,x=0.,y=10.,z=-100.,yaw=0.,color='green'),
            dict(id=3,x=2.,y=10.,z=-220.,yaw=math.pi,color='green')]
    snap=dict(valid=True,lifecycle=1,generation=1,frame_us=1,observed_at=100.,lights=lights)
    result=RouteSignalSelector().select(snap,[[p.x,p.y,p.z] for p in path.points],
        'publication',('authority',),dict(x=0.,y=10.,z=0.,rotation=0.,speed=50/3.6),0.,plan)
    assert result['valid'],result
    assert result['candidate']['id']==3
    assert result['candidate']['distance']==pytest.approx(92.)
    assert result['candidate']['stop_target_kind']=='derived_directed_curve_entry'
    assert result['candidate']['stop_line_verified'] is False
    assert result['candidate']['front_allowance_m']==6.
    assert result['candidate']['junction_standoff_m']==2.


def test_planner_uses_derived_target_not_light_head(tmp_path):
    from core.longitudinal import signal_stop_speed_limit
    cap=signal_stop_speed_limit(dict(color='red',distance=60.,
        stop_target_kind='derived_directed_curve_entry'),50/3.6)
    assert 0 < cap < 50/3.6
    # The target already includes front allowance and stand-off: no second 5 m.
    assert signal_stop_speed_limit(dict(color='red',distance=0.,
        stop_target_kind='derived_directed_curve_entry'),0.)==0.


def signal_bytes(clock,generation,frame,lights):
    from core.sdk.signal_snapshot import LAYOUT
    payload=bytearray(1920)
    for i,light in enumerate(lights):
        x,y,z=(light[k] for k in ('x','y','z'))
        tx,tz=math.floor(x/512.),math.floor(z/512.)
        yaw=light['yaw']
        struct.pack_into('<fffhhffffifii',payload,i*48,x-tx*512,y,z-tz*512,tx,tz,
            math.cos(yaw/2),math.sin(yaw/2),0.,0.,1,light.get('time_left',10.),light.get('state',2),light['id'])
    return LAYOUT.pack(generation*2,0x32535055,2,LAYOUT.size,11,generation,frame,clock,3,
                       len(lights),bytes(payload),generation*2)


@pytest.mark.parametrize('fault',['missing','ambiguous','other_height','opposite','stale'])
def test_known_control_never_uses_unrelated_green_as_clearance(tmp_path,fault):
    from core.sdk.signal_snapshot import decode
    net,path,_=parsed_path(tmp_path);plan=plan_for(net,path)
    correct=dict(id=3,x=2.,y=10.,z=-125.,yaw=math.pi,state=8)
    selector=RouteSignalSelector()
    points=[[p.x,p.y,p.z] for p in path.points]
    truck=dict(x=0.,y=10.,z=0.,rotation=0.)
    # Known control means an actual, matching producer head was observed.
    acquired=selector.select(decode(signal_bytes(99.9,1,99,[correct]),99.9),
        points,'pub',('authority',),truck,0.,plan)
    assert acquired['valid']
    lights=[correct]
    if fault=='missing':lights=[]
    if fault=='ambiguous':lights.append(dict(correct,x=3.))
    if fault=='other_height':lights=[dict(correct,y=30.)]
    if fault=='opposite':lights=[dict(correct,yaw=0.)]
    lights.append(dict(id=19,x=0.,y=10.,z=-40.,yaw=math.pi,state=8))
    snap=decode(signal_bytes(100.,1,100,lights),100.501 if fault=='stale' else 100.)
    result=selector.select(snap,points,'pub',('authority',),truck,0.,plan)
    assert not result['valid'] and result['candidate'] is None
    assert result['prefab_required'] and result['stop_candidate']['color']=='unknown'
    assert not result['stop_candidate']['head_observed']


def test_live_ids_are_prefab_local_not_globally_unique():
    from core.sdk.signal_snapshot import decode
    a=dict(id=3,x=2.,y=10.,z=-125.,yaw=math.pi)
    good=decode(signal_bytes(100.,1,100,[a,dict(a,z=-220.)]),100.)
    assert good['valid'] and len(good['lights'])==2
    assert not decode(signal_bytes(100.,1,100,[a,a]),100.)['valid']


@pytest.mark.parametrize('reverse,turn',[(False,True),(True,False)])
def test_derived_entry_follows_authored_direction_on_turn_and_reverse(tmp_path,reverse,turn):
    net,path,_=parsed_path(tmp_path,reverse,turn)
    plan=plan_for(net,path);p=plan['passages'][0]
    assert p['entry_progress_m']==pytest.approx(100.)
    assert p['entry_xyz']==pytest.approx([getattr(path.segments[1].centerline[0],k) for k in ('x','y','z')])


def test_legacy_or_missing_curve_binding_is_explicitly_lower_confidence(tmp_path):
    net,path,_=parsed_path(tmp_path)
    net._prefab_lane_data['signal_fixture']['curves'][0]['semaphore_id']=None
    plan=plan_for(net,path)
    assert plan['status']=='partial' and plan['passages'][0]['semaphore_id'] is None
    assert 'authored semaphore metadata unavailable' in plan['blockers']


def test_locked_passage_green_rejects_new_build_and_stale_source(tmp_path):
    from core.sdk.signal_snapshot import decode
    net,path,_=parsed_path(tmp_path);plan=plan_for(net,path)
    points=[[p.x,p.y,p.z] for p in path.points]
    truck=dict(x=0.,y=10.,z=-92.,rotation=0.)
    light=dict(id=3,x=2.,y=10.,z=-125.,yaw=math.pi,state=2)
    selector=RouteSignalSelector()
    first=selector.select(decode(signal_bytes(100.,1,100,[light]),100.),points,'p',('a',),truck,92.,plan)
    assert first['valid']
    selector.lock=dict(candidate=first['candidate'],authority=('a',),lifecycle=11)
    green=decode(signal_bytes(100.2,2,200,[dict(light,state=8)]),100.2)
    assert selector.select(green,points,'p',('a',),truck,92.,plan)['valid']
    result=selector.select(green,points,'q',('b',),truck,92.,plan)
    assert not result['valid'] and result['candidate'] is None


@pytest.mark.parametrize('mode',[0,3])
def test_real_policy_acc_backend_stop_wait_and_green_resume(tmp_path,mode):
    from tools.run_prefab_signal_bench import run
    result=run(tmp_path,mode=mode,jitter=True)
    assert result['stop']['front_gap_to_entry_m']>=2.
    assert result['resumed_without_n'] and result['active']
    assert result['simultaneous_positive_pedals']==result['parking_writes']==result['hold_brake_zero_count']==0
    writes=result['writes']
    # Moving approach corrections may release an early brake. The terminal
    # stop must establish a NEW continuous positive chain and never release it
    # at standstill before independently confirmed green.
    terminal=next(row for row in result['rows'] if row['hold_phase'] in ('braking','holding'))
    first=terminal['write_checked_at_s']
    last_red=next(row for row in reversed(result['rows']) if row['red'])
    red_writes=[w for w in writes if w[0]<=last_red['write_checked_at_s']]
    assert all(v>0 for t,c,v in red_writes if c=='abackward' and t>=first)
    assert terminal['brake']>0
    first_approach_brake=next(row['t'] for row in result['rows'] if row['brake']>0)
    assert all(row['hold_phase']=='approaching' and row['speed_mps']>.05
               for row in result['rows'] if row['red'] and row['brake']==0
               and first_approach_brake<=row['t']<terminal['t'])
    assert all(row['throttle']==0 and row['brake']>0 for row in result['rows']
               if row['red'] and row['write_checked_at_s']>=first)
    assert any(b['brake']<a['brake'] and b['brake']>0 for a,b in zip(result['rows'],result['rows'][1:]) if a['red'] and b['red'])


def test_head_distance_counterfactual_overruns_entry_but_derived_target_does_not(tmp_path):
    from tools.run_prefab_signal_bench import run
    wrong_target=run(tmp_path,baseline=True,allow_rejection=True)
    current=run(tmp_path)
    # The wrong head-distance target crosses the actual entry. Current route
    # guards then reject it, so never describe it as a completed historical stop.
    assert wrong_target['red_entry_overrun_samples']>0
    assert not wrong_target['active'] and wrong_target['stop'] is None
    assert not wrong_target['resumed_without_n']
    assert 'signal regulation coverage unverified' in wrong_target['termination_reason']
    assert current['stop']['front_gap_to_entry_m']>=2.
    assert current['red_entry_overrun_samples']==0
    assert current['active'] and current['resumed_without_n']
    assert current['maximum_deceleration_mps2']<wrong_target['maximum_deceleration_mps2']


def test_new_positive_brake_can_reduce_while_moving_but_not_release_hold(tmp_path):
    # Same production composition as the simulation; no standalone fake hold.
    from tools.run_prefab_signal_bench import run
    result=run(tmp_path,other_stop=True)
    assert result['active'] and not result['resumed_without_n']
    assert result['rows'][-1]['throttle']==0 and result['rows'][-1]['brake']>0


@pytest.mark.parametrize('mode',[0,3])
def test_launch_without_manual_throttle_then_signal_cycle(tmp_path,mode):
    from tools.run_prefab_signal_bench import run
    # Initially green at the start point; red arrives during actual forward
    # movement. This does not claim autonomous stationary red-light holding.
    result=run(tmp_path,mode=mode,speed_kmh=0.,jitter=True)
    assert result['active'] and result['resumed_without_n']
    assert result['stop']['front_gap_to_entry_m']>=2.
    assert result['simultaneous_positive_pedals']==0


def test_insufficient_short_approach_cannot_resume_after_entry_overrun(tmp_path):
    from tools.run_prefab_signal_bench import run
    result=run(tmp_path,speed_kmh=50.,approach=30.,jitter=True)
    assert result['stop']['front_gap_to_entry_m']<0.  # insufficient model brake distance
    assert not result['resumed_without_n']
    assert result['rows'][-1]['throttle']==0
    assert 'entry passed' in result['restart_blocker']


def test_derived_stop_receipt_survives_existing_combined_export(tmp_path,monkeypatch):
    import copy
    from core.navigation.evidence_diagnostics import EvidenceDiagnosticCollector
    from tests.test_real_evidence_diagnostics import capture,command
    from tools.analyze_longitudinal_evidence import load_rows
    from tools.run_prefab_signal_bench import run
    import core.navigation.evidence_diagnostics as diagnostics_module
    original=diagnostics_module._export_failure_reason
    def explain(error):
        print('Isolated export failure:',repr(error))
        return original(error)
    monkeypatch.setattr(diagnostics_module,'_export_failure_reason',explain)
    result=run(tmp_path,speed_kmh=35.,diagnostics=True)
    root=tmp_path/'evidence-diagnostics'
    exporter=EvidenceDiagnosticCollector(root,capacity=1200)
    exporter.apply_command(command(1,collection_id='prefab-signal'))
    for i,saved in enumerate(result['captures']):
        profile=copy.deepcopy(capture(i,when=1000.).profile)
        profile['observation'].update(sdk_frame_us=saved.truck['sdkFrameTimeUs'],captured_at=saved.captured_at_s)
        profile['observation']['articles'][0]['position_m']=[saved.truck[k] for k in ('x','y','z')]
        exporter._ingest(replace(saved,profile=profile))
    exporter.finalize()
    assert exporter.status()['state']=='READY_FOR_OFFLINE_REVIEW',exporter.status()
    rows,receipt=load_rows(root/'prefab-signal')
    assert receipt['integrity_valid'] and not receipt['confirmed'] and not receipt['runtime_authorized']
    events=[e for row in rows for e in row['longitudinal']['events']]
    signals=[e['source']['inputs']['traffic']['signal'] for e in events
        if isinstance(e['source'].get('inputs'),dict) and isinstance(e['source']['inputs'].get('traffic'),dict)
        and isinstance(e['source']['inputs']['traffic'].get('signal'),dict)]
    assigned=[s for s in signals if (s.get('candidate') or {}).get('passage_key')]
    assert assigned, 'bounded journal discarded the derived target receipt'
    assert all(s['candidate']['stop_line_verified'] is False for s in assigned)
    assert all(s['candidate']['front_allowance_m']==6. for s in assigned)
    assert any(e['source'].get('phase')=='signal_resume' and e['pair_after']['throttle']>0 for e in events)


def test_actual_map_build_publishes_parser_binding_then_physical_brake(flow,tmp_path):
    from plugins.map.main import Plugin as Map
    from plugins.drivepolicy.main import Plugin as Policy
    from sdk.plugin_sdk import PluginSDK
    from core.longitudinal import context,publish
    from core.sdk.signal_snapshot import SignalReader,RouteSignalSelector
    from tests.test_lane_route_builder import SyntheticMap
    from tests.test_longitudinal_arbitration import strict_flow
    from tests.test_longitudinal_evidence_diagnostics import memory_controller
    net,_,_=parsed_path(tmp_path,reverse=True,lane_shift=-2.25)
    synthetic=SyntheticMap();synthetic.net=net
    synthetic.node(10,0.,-230.,10.);synthetic.node(12,0.,-130.,10.);synthetic.node(11,0.,-100.,10.)
    synthetic.road(10,12,1)
    state,truck,engine,ap,update,n,clock,acc=strict_flow(flow)
    plugin=Map(PluginSDK(state.values,'map'));plugin.on_start();plugin.road_net=net;plugin._net_attempted=True
    engine.controller=memory_controller();engine._signal_reader=SignalReader()
    engine._signal_selector=RouteSignalSelector();engine._signal_route_token=None
    policy=Policy(PluginSDK(state.values,'drivepolicy'));policy.on_start()
    state.set('game_route_node_uids',[10,12,11]);state.set('acc_target_speed',35.)
    def tick(z,generation):
        truck.update(x=-2.25,y=10.,z=z,rotation=math.pi)
        dt=update(8,5.,dt=.1)
        obs=state.get('telemetry')['truck']['_control_observation']
        state.update_batch({'truck_world_pos':(-2.25,z),'truck_altitude':10.,'truck_heading':math.pi,
            'truck_speed_ms':5.,'vehicle_envelope_snapshot':dict(valid=True,timestamp=obs['observed_at'],
                sdk_frame_us=truck['sdkFrameTimeUs'],tractor_position=(-2.25,10.,z),
                tractor_heading=math.pi,tractor_speed_ms=5.,tractor_reference_geometry=dict(
                    valid=True,source='synthetic_4x2',wheelbase_m=3.8,reference_ahead_m=2.1))})
        plugin.on_tick(dt)
        assert state.get('lane_trajectory')['valid'],state.get('navigation_failure_reason')
        engine._signal_reader.buffer=signal_bytes(clock[0],generation,truck['sdkFrameTimeUs'],
            [dict(id=4,x=-5.,y=10.,z=-110.,yaw=0.,state=2)])
        signal=engine._signal_observation(state.get('telemetry')['truck'],context(state))
        assert signal['valid'],dict(signal=signal,match=state.get('lane_match'),
            packet=state.get('nav_steering_debug'),binding=context(state))
        publish(state,state.get('telemetry')['truck'],'traffic',traffic_brake=0.,
            light_brake=engine._light_brake(signal['candidate']),light=signal['candidate'],signal=signal)
        policy.on_tick(dt);acc.on_tick(dt);ap.on_tick(dt);engine._flush_controls()
    try:
        tick(-220.,1)
        prepared=state.get('lane_trajectory')['signal_passages']
        assert prepared['status']=='prepared' and prepared['passages'][0]['semaphore_id']==4
        n()
        for i in range(1,151):
            tick(-220.+i*.5,i+1)
        assert state.get('autopilot_active'),state.get('autopilot_disable_reason')
        from tests.test_signal_stop_resume import pedal
        assert pedal(engine,'abackward')>0 and pedal(engine,'aforward')==0
    finally:
        plugin._maneuver_evidence_worker.close();plugin._maneuver_reference_mux.close()


def test_signal_on_inner_curve_stops_before_whole_directed_passage(tmp_path):
    import copy
    from core.navigation.lane_trajectory import build_lane_trajectory
    net,path,instance=parsed_path(tmp_path)
    filename=tmp_path/'prefabDescriptions.json';raw=json.loads(filename.read_text())[0]
    second=copy.deepcopy(raw['navCurves'][0])
    second.update(start=copy.deepcopy(second['end']),prevLines=[0],nextLines=[],semaphoreId=3)
    second['end']['y']=-60.
    raw['navCurves'][0].update(semaphoreId=-1,nextLines=[1])
    raw['navCurves'][1]=second;raw['nodes'][1].update(y=-60.,outputLanes=[1])
    raw['navNodes'][0]['connections'][0]['curveIndices']=[0,1]
    raw['navNodes'][1]['connections']=[]
    filename.write_text(json.dumps([raw]),encoding='utf-8');net.nodes[12]=(0.,-160.)
    net._load_prefabs(str(tmp_path))
    pts=net._prefab_curve_chain_3d(instance,(0,1))
    segment=net._make_prefab_lane_segment(GpsCorridorEdge(11,12,'prefab',1),instance,(0,1),pts)
    road=replace(path.segments[0],successors=(LaneConnection(segment.lane_id,'prefab'),))
    directed=build_lane_trajectory(net.connect_lane_sequence((road,segment),(10,11,12)))
    plan=plan_for(net,directed)
    assert plan['status']=='prepared'
    assert plan['passages'][0]['controlled_curve_index']==1
    assert plan['passages'][0]['entry_progress_m']==pytest.approx(100.)


def test_distinct_control_groups_at_same_entry_do_not_choose_arbitrary_green(tmp_path):
    import copy
    from core.sdk.signal_snapshot import decode
    net,path,_=parsed_path(tmp_path);plan=plan_for(net,path)
    selector=RouteSignalSelector()
    points=[[p.x,p.y,p.z] for p in path.points]
    truck=dict(x=0.,y=10.,z=0.,rotation=0.)
    acquired=selector.select(decode(signal_bytes(99.9,1,99,[
        dict(id=3,x=2.,y=10.,z=-125.,yaw=math.pi,state=2)]),99.9),
        points,'p',('a',),truck,0.,plan)
    assert acquired['valid']
    other=copy.deepcopy(plan['passages'][0]);other.update(semaphore_id=4,passage_key='other-control-group')
    plan['passages'].append(other)
    snap=decode(signal_bytes(100.,1,100,[dict(id=3,x=2.,y=10.,z=-125.,yaw=math.pi,state=8),
        dict(id=4,x=3.,y=10.,z=-125.,yaw=math.pi,state=2)]),100.)
    result=selector.select(snap,points,'p',('a',),truck,0.,plan)
    assert not result['valid'] and result['candidate'] is None
    assert result['reason']=='ambiguous regulated prefab passages'
    assert result['stop_candidate']['color']=='unknown' and result['stop_candidate']['distance']==92.


def test_missing_authored_id_cannot_be_replaced_by_geometric_green(tmp_path):
    from core.sdk.signal_snapshot import decode
    net,path,_=parsed_path(tmp_path)
    net._prefab_lane_data['signal_fixture']['curves'][0]['semaphore_id']=None
    plan=plan_for(net,path)
    snap=decode(signal_bytes(100.,1,100,[dict(id=3,x=2.,y=10.,z=-125.,yaw=math.pi,state=8)]),100.)
    result=RouteSignalSelector().select(snap,[[p.x,p.y,p.z] for p in path.points],'p',('a',),
        dict(x=0.,y=10.,z=-20.,rotation=0.),20.,plan)
    assert not result['valid']
    # A missing authored ID cannot qualify a control or an unknown stop; a
    # nearby green is still refused as clearance, never inferred as our head.
    assert result['candidate'] is None and not result.get('prefab_required')
    assert not result.get('stop_candidate')


def test_dedicated_tollgate_control_is_not_a_required_traffic_light(tmp_path):
    net,path,_=parsed_path(tmp_path)
    net._prefab_lane_data['signal_fixture']['path']='prefab2/tollgate/tollgate_fixture.ppd'
    plan=plan_for(net,path)
    assert not plan['passages']
    assert 'dedicated tollgate delegated to existing toll flow' in plan['blockers']


def test_traffic_command_cannot_outlive_original_signal_acquisition(flow):
    from core.longitudinal import publish
    from tests.test_longitudinal_arbitration import strict_flow
    from tests.test_longitudinal_evidence_diagnostics import memory_controller
    from tests.test_signal_stop_resume import pedal
    state,truck,engine,ap,update,n,clock,acc=strict_flow(flow)
    engine.controller=memory_controller();update(8,5.);n()
    observed=clock[0]-.3
    light=dict(id=3,color='green',distance=80.,stop_target_kind='derived_directed_curve_entry')
    signal=dict(valid=True,observed_at=observed,frame_us=123,generation=2,candidate=light)
    traffic=publish(state,state.get('telemetry')['truck'],'traffic',traffic_brake=0.,light_brake=0.,
        light=light,signal=signal,following=None)
    acc.on_tick(.033);ap.on_tick(.033);engine._flush_controls()
    assert pedal(engine,'aforward')>0
    clock[0]+=.201  # SDK/steering remain under 500 ms, signal exceeds it.
    engine._flush_controls()
    assert pedal(engine,'aforward')==0
    assert traffic['expires_at']==pytest.approx(observed+.5)
    assert traffic['deadline_basis']['source']=='traffic_signal'
