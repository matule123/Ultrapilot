"""Original placed PPD geometry plus explicit modeled native acquisition.

No native group/owner field missing from the historical fault is invented as
historical proof. Missing group correspondence stays unqualified.
"""
import math
from copy import deepcopy
import pytest
from core.sdk.signal_snapshot import RouteSignalSelector
from tests.test_oct8_signal_coverage import actual_path
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_oct8_signal_coverage import real_flow
from tests.test_roundabout_intervention_reporting import pedal
from core.longitudinal import signal_approach_speed_limit


def scene(tmp_path,distance=120.,speed=6.):
    path,plan=actual_path(tmp_path,0)
    entry=path.points[0];p=plan['passages'][0]
    start=[entry.x+distance*math.sin(entry.heading),entry.y,entry.z+distance*math.cos(entry.heading)]
    for passage in plan['passages']:passage['entry_progress_m']+=distance
    head=dict(id=999,x=entry.x,y=entry.y+4.,z=entry.z,
        yaw=p['controlled_heading_rad'],color='green',scope_schema=1,
        owner_prefab_uid=p['prefab_uid'],owner_node_uids=p['native_node_uids'],
        owner_origin_index=p['origin_node_index'],ownership_valid=True,id_basis='prefab_segment_instance_id')
    snapshot=dict(valid=True,schema=3,lifecycle=11,generation=12,frame_us=1200,observed_at=1000.,lights=[head])
    truck=dict(x=start[0],y=start[1],z=start[2],rotation=entry.heading,speed=speed)
    points=[start]+[[q.x,q.y,q.z] for q in path.points]
    return snapshot,points,plan,truck


def test_distant_native_unqualified_entry_is_planned_not_immediate_takeover(tmp_path):
    snap,points,plan,truck=scene(tmp_path)
    result=RouteSignalSelector().select(snap,points,'route',('authority',),truck,0.,plan)
    assert not result['valid'] and result['candidate'] is None
    assert not result['coverage']['requires_takeover']
    assert result['coverage']['requires_approach']
    assert result['coverage']['approach_target']['distance']==pytest.approx(115.)
    assert result['unassigned_candidate']['id']==999
    assert result['observed_at']==1000. and result['generation']==12


def test_native_owned_far_ambiguity_does_not_become_green_clearance(tmp_path):
    snap,points,plan,truck=scene(tmp_path,distance=20.,speed=6.)
    result=RouteSignalSelector().select(snap,points,'route',('authority',),truck,0.,plan)
    assert result['coverage']['requires_takeover']
    assert result['candidate'] is None and not result['valid']


def test_pending_uncertainty_retains_original_source_when_head_disappears(tmp_path):
    snap,points,plan,truck=scene(tmp_path)
    selector=RouteSignalSelector()
    first=selector.select(snap,points,'route',('authority',),truck,0.,plan)
    missing=dict(snap,generation=13,frame_us=1300,observed_at=1000.1,lights=[])
    second=selector.select(missing,points,'route',('authority',),truck,0.,plan)
    assert second['coverage']['requires_approach']
    assert second['observed_at']==first['observed_at']
    assert second['generation']==first['generation']
    assert second['unassigned_candidate']['id']==999


def test_proven_foreign_native_owner_never_falls_back_to_route_proximity(tmp_path):
    snap,points,plan,truck=scene(tmp_path,distance=10.)
    snap['lights'][0]['owner_prefab_uid']+=1
    # Explicit prepared scope proves this head belongs to another placement.
    result=RouteSignalSelector().select(snap,points,'route',('authority',),truck,0.,plan)
    assert not result['coverage']['requires_takeover']
    assert result.get('unassigned_candidate') is None


@pytest.mark.parametrize('mode',[0,3])
def test_full_unknown_approach_qualifies_then_two_red_hold_green_cycles(flow,tmp_path,mode):
    values,step=real_flow(flow,tmp_path,0,mode,scoped=True)
    state,truck,engine,ap,tick,n,clock,writes,collected=values
    unknown=step(4,4.,id=999,progress=0.)
    assert unknown['coverage']['status']=='UNASSIGNED_APPROACH_PENDING'
    assert state.get('autopilot_active') and not engine.controller.current_hazard
    cap=state.get('longitudinal_policy')['planned_speed_ms']
    assert cap<=math.sqrt(2*(42.-4.*1.5))
    packet=state.get('longitudinal_traffic')
    assert packet['expires_at']<=unknown['observed_at']+.5
    for cycle in range(2):
        red=step(4,4.,progress=41.)
        assert red['valid'] and red['candidate']['head_observed']
        assert state.get('traffic_light')['id']==red['candidate']['id']
        start=len(writes)
        for speed in (2.,.7,.2,.04,0.,0.):
            step(0 if mode==0 and speed<.05 else 4,speed,progress=41.)
            assert state.get('autopilot_active'),state.get('automatic_safety_stop_reason')
            assert pedal(engine,'aforward')==0 and pedal(engine,'abackward')>0
        for _ in range(5):step(0 if mode==0 else 4,0.,color=8,progress=41.)
        for speed in (.001,.2,.3):step(4,speed,color=8,progress=41.)
        assert state.get('autopilot_active') and pedal(engine,'aforward')>0
        assert not any(ch=='parkingbrake' for _,ch,_,_ in writes[start:])
        # The first hold contained no brake-zero edge before confirmed release.
        wait_writes=[v for _,ch,v,_ in writes[start:] if ch=='abackward']
        first_zero=next((i for i,v in enumerate(wait_writes) if v==0.),len(wait_writes))
        assert first_zero>0 and all(v>0 for v in wait_writes[:first_zero])


def test_unresolved_entry_does_not_expire_by_new_buffer_reads_or_clear_on_reroute(tmp_path):
    snap,points,plan,truck=scene(tmp_path)
    selector=RouteSignalSelector()
    first=selector.select(snap,points,'route',('activation','session'),truck,0.,plan)
    assert first['coverage']['requires_approach']
    for generation in range(13,18):
        missing=dict(snap,generation=generation,frame_us=generation*100,observed_at=1000.1*generation,lights=[])
        still=selector.select(missing,points,'route',('activation','session'),truck,0.,plan)
        assert still['observed_at']==1000. and still['generation']==12
    changed=selector.select(dict(snap,lights=[]),points,'new-route',('new-activation','session'),truck,0.,plan)
    assert not changed['coverage'].get('requires_approach')
    assert selector._uncertain_approach is None


def test_actual_progress_and_speed_decide_uncertainty_reserve(tmp_path):
    snap,points,plan,truck=scene(tmp_path,distance=120.,speed=6.)
    selector=RouteSignalSelector()
    # The unchanged 27 m reserve is crossed 3 m later with a 5 m target.
    # Keep the old 85 m pose as a negative case and exercise the new boundary.
    for progress,speed,takeover in ((0.,6.,False),(50.,6.,False),(75.,6.,False),
                                    (85.,6.,False),(88.,6.,True)):
        moved=dict(truck,x=truck['x']-progress*math.sin(truck['rotation']),
                   z=truck['z']-progress*math.cos(truck['rotation']),speed=speed)
        current=dict(snap,generation=12+int(progress),observed_at=1000.+progress*.05)
        result=selector.select(current,points,'route',('authority',),moved,progress,plan)
        assert result['coverage']['requires_takeover']==takeover
        assert result['coverage']['stopping_reserve_m']==pytest.approx(27.)
        assert result['coverage']['approach_target']['distance']==pytest.approx(115.-progress)
        assert signal_approach_speed_limit({'signal':result},speed)==pytest.approx(
            math.sqrt(2*max(0.,115.-progress-9.)))
        assert not result['coverage']['clearance_confirmed']


@pytest.mark.parametrize('distance',[20.,120.])
def test_compact_rejected_owner_and_entry_survive_fault_budget(tmp_path,distance):
    from core.navigation.longitudinal_diagnostics import bounded_fault_details, _expand_fault_details
    snap,points,plan,truck=scene(tmp_path,distance=distance)
    signal=RouteSignalSelector().select(snap,points,'route',('authority',),truck,0.,plan)
    signal.update(authority_lane_id=[11,1,0,'',-1,[]],route_progress_m=0.,route_publication_token='actual')
    details=dict(signal=signal,traffic_comparison={'following_status':'ambiguous_actor_id'},
                 sdk_frame_us=100,observation_timestamp=1000.,unrelated='x'*20000)
    packed=bounded_fault_details(details,packed=True)
    assert packed['capture_incomplete']
    recovered=_expand_fault_details(packed)
    head=recovered['signal']['unassigned_candidate']
    assert head['owner_prefab_uid']==snap['lights'][0]['owner_prefab_uid']
    assert head['owner_node_uids']==snap['lights'][0]['owner_node_uids']
    assert recovered['signal']['coverage']['approach_target']==signal['coverage']['approach_target']
    assert recovered['signal']['observed_at']==1000.
    assert recovered['signal']['generation']==12
    assert recovered['signal']['route_publication_token']=='actual'
    assert recovered['signal']['route_progress_m']==0.


def test_hud_does_not_promote_pending_unknown_green(tmp_path):
    from unittest.mock import patch
    from ui.visualization import traffic_light_presentation
    snap,points,plan,truck=scene(tmp_path)
    signal=RouteSignalSelector().select(snap,points,'route',('authority',),truck,0.,plan)
    with patch('time.monotonic',return_value=1000.1):
        head,color,label,only=traffic_light_presentation(None,signal['unassigned_candidate'],signal['coverage'])
    assert only and color=='green' and head['id']==999
    assert 'nepotvrdená' in label and 'priblíženie' in label
