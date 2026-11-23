"""Native owner identity, real PPD geometry and explicit modeled source heads."""
import math

import pytest

from core.sdk.signal_snapshot import RouteSignalSelector
from tests.signals.test_signal_coverage import actual_path
from tests.signals.test_signal_coverage import real_flow
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_roundabout_intervention_reporting import pedal


@pytest.mark.parametrize('case',[0,1,2])
def test_native_owned_head_above_road_is_not_a_different_deck(tmp_path,case):
    path,plan=actual_path(tmp_path,case);entry=path.points[0];p=plan['passages'][0]
    assert p['prefab_uid'] and p['native_node_uids']
    head=dict(id=p['semaphore_id'],x=entry.x,y=entry.y+4.,z=entry.z,
        yaw=p['controlled_heading_rad'],color='red',scope_schema=1,
        owner_prefab_uid=p['prefab_uid'],owner_node_uids=p['native_node_uids'],
        owner_origin_index=p['origin_node_index'],ownership_valid=True,
        id_basis='prefab_segment_instance_id')
    result=RouteSignalSelector().select(dict(valid=True,schema=3,lifecycle=1,
        generation=1,frame_us=1,observed_at=1000.,lights=[head]),
        [[q.x,q.y,q.z] for q in path.points],'route',('authority',),
        dict(x=entry.x,y=entry.y,z=entry.z,rotation=entry.heading),0.,plan)
    assert result['valid'],result
    assert result['candidate']['id']==p['semaphore_id']
    assert result['candidate']['binding_basis']=='native_prefab_owner_and_directed_group'


@pytest.mark.parametrize('case',[0,1,2])
@pytest.mark.parametrize('mode',[0,3])
def test_scoped_producer_to_backend_wait_resume_on_actual_placed_prefab(flow,tmp_path,case,mode):
    values,step=real_flow(flow,tmp_path,case,mode,scoped=True)
    state,truck,engine,ap,tick,n,clock,writes,collected=values
    for cycle in range(2):
        red=step(4,4.,progress=41.,head_shift=(0.,4.,0.))
        assert red['valid'] and red['schema']==3
        assert red['candidate']['binding_basis']=='native_prefab_owner_and_directed_group'
        assert state.get('traffic_light')['id']==red['candidate']['id']
        start=len(writes)
        for speed in (2.,.7,.2,.04,0.,0.):
            step(0 if mode==0 and speed<.05 else 4,speed,progress=41.,head_shift=(0.,4.,0.))
            assert state.get('autopilot_active'),state.get('autopilot_disable_reason')
            assert pedal(engine,'aforward')==0. and pedal(engine,'abackward')>0.
        for _ in range(5):step(0 if mode==0 else 4,0.,color=8,progress=41.,head_shift=(0.,4.,0.))
        for speed in (.001,.2,.3):step(4,speed,color=8,progress=41.,head_shift=(0.,4.,0.))
        assert state.get('autopilot_active') and pedal(engine,'aforward')>0.
        assert not any(c=='parkingbrake' for _,c,_,_ in writes[start:])


@pytest.mark.parametrize('fault',['owner','nodes','origin','direction','kind_scope','conflicting_colors'])
def test_native_owner_cannot_bypass_actual_attachment_or_direction(tmp_path,fault):
    path,plan=actual_path(tmp_path,0);entry=path.points[0];p=plan['passages'][0]
    head=dict(id=p['semaphore_id'],x=entry.x,y=entry.y+4.,z=entry.z,
        yaw=p['controlled_heading_rad'],color='red',scope_schema=1,
        owner_prefab_uid=p['prefab_uid'],owner_node_uids=p['native_node_uids'],
        owner_origin_index=p['origin_node_index'],ownership_valid=True,id_basis='prefab_segment_instance_id')
    if fault=='owner':head['owner_prefab_uid']+=1
    if fault=='nodes':head['owner_node_uids']=[1,2]
    if fault=='origin':head['owner_origin_index']+=1
    if fault=='direction':head['yaw']+=math.pi/2
    if fault=='kind_scope':head['ownership_valid']=False
    lights=[head]
    if fault=='conflicting_colors':lights.append(dict(head,x=head['x']+.2,color='green'))
    result=RouteSignalSelector().select(dict(valid=True,schema=3,lifecycle=1,
        generation=1,frame_us=1,observed_at=1000.,lights=lights),
        [[q.x,q.y,q.z] for q in path.points],'route',('authority',),
        dict(x=entry.x,y=entry.y,z=entry.z,rotation=entry.heading),0.,plan)
    assert not result['valid'] and result['candidate'] is None


@pytest.mark.parametrize('case',[0,1,2])
def test_owned_high_head_with_unknown_group_requires_takeover_not_clearance(tmp_path,case):
    path,plan=actual_path(tmp_path,case);entry=path.points[0];p=plan['passages'][0]
    start=[entry.x+20.*math.sin(entry.heading),entry.y,entry.z+20.*math.cos(entry.heading)]
    for passage in plan['passages']:passage['entry_progress_m']+=20.
    head=dict(id=999,x=entry.x,y=entry.y+4.,z=entry.z,
        yaw=p['controlled_heading_rad'],color='red',scope_schema=1,
        owner_prefab_uid=p['prefab_uid'],owner_node_uids=p['native_node_uids'],
        owner_origin_index=p['origin_node_index'],ownership_valid=True,id_basis='prefab_segment_instance_id')
    result=RouteSignalSelector().select(dict(valid=True,schema=3,lifecycle=1,
        generation=1,frame_us=1,observed_at=1000.,lights=[head]),
        [start]+[[q.x,q.y,q.z] for q in path.points],'route',('authority',),
        dict(x=start[0],y=start[1],z=start[2],rotation=entry.heading),0.,plan)
    assert not result['valid'] and result['candidate'] is None
    assert result['coverage']['requires_takeover'],result
    assert result['unassigned_candidate']['y']==entry.y+4.  # No invented ground pose.
    from core.navigation.longitudinal_diagnostics import PedalJournal
    journal=PedalJournal();journal.enabled=True
    journal.significant('UNASSIGNED_SIGNAL',{'schema_version':1,'source':'traffic',
        'context':['a','session','map','data','intent',7,'build','geometry'],
        'sdk_frame_us':100,'observation_timestamp':1000.,'signal':result},1000.)
    saved=journal.expand_significant(journal.ready_significant(1000.2))
    head=saved['significant_event']['receipt']['input']['signal']['unassigned_candidate']
    assert head['owner_prefab_uid']==p['prefab_uid']
    assert head['owner_node_uids']==p['native_node_uids'] and head['id']==999


def test_same_owned_group_lamps_are_one_qualified_control(tmp_path):
    path,plan=actual_path(tmp_path,0);entry=path.points[0];p=plan['passages'][0]
    start=[entry.x+20.*math.sin(entry.heading),entry.y,entry.z+20.*math.cos(entry.heading)]
    for passage in plan['passages']:passage['entry_progress_m']+=20.
    head=dict(id=p['semaphore_id'],x=entry.x,y=entry.y+4.,z=entry.z,
        yaw=p['controlled_heading_rad'],color='red',scope_schema=1,
        owner_prefab_uid=p['prefab_uid'],owner_node_uids=p['native_node_uids'],
        owner_origin_index=p['origin_node_index'],ownership_valid=True,id_basis='prefab_segment_instance_id')
    result=RouteSignalSelector().select(dict(valid=True,schema=3,lifecycle=1,
        generation=1,frame_us=1,observed_at=1000.,lights=[head,dict(head,x=head['x']+.2)]),
        [start]+[[q.x,q.y,q.z] for q in path.points],'route',('authority',),
        dict(x=start[0],y=start[1],z=start[2],rotation=entry.heading),0.,plan)
    assert result['valid'] and not result['coverage']['requires_takeover']
