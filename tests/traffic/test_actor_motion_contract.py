"""Explicit map hypotheses, not a measured vehicle/exit-intent model."""
import math
import copy
import pytest
from core.actor_motion import ActorMotionGraph
from core.acc_following import RouteLeadSelector
from core.acc_body_prediction import predict


def graph():
    return dict(schema=1,status='prepared',curves=[
        dict(id='entry',points=[[0.,10.,0.],[0.,10.,20.]],next=['ring','exit']),
        dict(id='ring',points=[[0.,10.,20.],[-3.,10.,23.],[-7.,10.,25.],[-12.,10.,25.]],next=[]),
        dict(id='exit',points=[[0.,10.,20.],[0.,10.,60.]],next=[])])


def actor():
    body=dict(x=0.,y=10.,z=5.,yaw=math.pi,dimensions_whl=(2.,2.,4.))
    return dict(body,id=19,source='moving',speed_source='buffer',speed=5.,slot=0,
        bodies=[body],record_fingerprint='original')


def test_every_compatible_exit_remains_and_invalid_history_never_gets_map_intent():
    model=ActorMotionGraph(graph());a=actor()
    result=model.hypotheses(a,history_valid=True)
    assert len(result['branches'])==2 and result['exit_intent_verified'] is False
    assert {b['curve_chain'][-1] for b in result['branches']}=={'ring','exit'}
    assert model.hypotheses(a,history_valid=False) is None
    assert model.hypotheses(dict(a,y=20.),history_valid=True) is None
    assert model.hypotheses(dict(a,yaw=0.),history_valid=True) is None
    broken=graph();broken['curves'][1]['points'][0][0]=20.
    assert ActorMotionGraph(broken).hypotheses(a,history_valid=True) is None
    overflow=graph();overflow['curves'][0]['next']=['exit']*9
    assert ActorMotionGraph(overflow).hypotheses(a,history_valid=True) is None


def test_lost_native_acquisition_cannot_reuse_cached_actor_poses():
    route=RouteLeadSelector();route.prepare([(0.,10.,0.),(0.,10.,100.)],'model',actor_motion=graph())
    a=actor();route._actor_motion_cache[a['id']]={'old':'must never be returned'}
    route.source_motion([a],None)
    assert route.actor_motion(a) is None


def test_sparse_authored_curve_middle_is_not_lost_by_point_only_index():
    model=ActorMotionGraph(dict(schema=1,status='prepared',curves=[
        dict(id='long',points=[[0.,10.,0.],[0.,10.,1000.]],next=[])]))
    a=actor();a.update(z=500.)
    assert model.hypotheses(a,history_valid=True)['branches']


@pytest.mark.parametrize('trailer',[False,True])
def test_possible_exit_contact_survives_union_and_hud_uses_same_body_poses(trailer):
    from core.actor_motion import body_poses
    route=RouteLeadSelector();route.prepare([(0.,10.,0.),(0.,10.,100.)],'model',actor_motion=graph())
    a=actor();a['z']=8.;a['bodies'][0]['z']=8.
    model=route._actor_motion_graph.hypotheses(a,history_valid=True)
    # A qualified-history model is injected at the same public prediction
    # boundary; producer/owner continuity is separately tested with raw bytes.
    route.actor_motion=lambda value:model
    ego=dict(x=0.,y=10.,z=19.,yaw=math.pi,dimensions_whl=(2.5,3.,5.))
    if trailer:
        # Tractor is safely beside it; only the measured trailer is in path.
        ego=dict(ego,x=8.)
        bodies=[ego,dict(ego,x=0.,z=19.)]
    else:bodies=[ego]
    geometry={};result=predict(route,bodies,[a],0.,19.,(0.,10.,19.),debug_geometry=geometry)
    assert result['brake']>0. and result['conflicts'][0]['id']==19
    assert result['conflicts'][0]['actor_motion_hypotheses']==2
    assert geometry['model']==result['model']
    for path in geometry['actor_paths']:
        expected=body_poses(a,a['bodies'][0],model['branches'][path['hypothesis_index']])
        assert path['points']==[[i*.25,p['x'],p['y'],p['z']] for i,p in enumerate(expected[:13])]
        assert path['exit_intent_verified'] is False


def test_unknown_topology_keeps_original_straight_collision_protection():
    route=RouteLeadSelector();route.prepare([(0.,10.,0.),(0.,10.,100.)],'without-map')
    a=actor();ego=dict(a['bodies'][0],z=12.)
    a.update(z=20.,yaw=0.);a['bodies'][0].update(z=20.,yaw=0.)
    result=predict(route,[ego],[a],0.,12.,(0.,10.,12.))
    assert result['brake']>0. and result['conflicts'][0]['actor_motion_hypotheses']==1


def test_hud_preserves_the_actual_crossing_model_and_uncertain_branch():
    from core.traffic_dev_hud import geometry
    route=RouteLeadSelector();route.prepare([(0.,10.,0.),(0.,10.,100.)],'model')
    conflict=dict(id=19,point_xyz=[0.,10.,30.],distance_m=18.,actor_arrival_s=4.,
        ego_arrival_earliest_s=4.,brake=.2,motion_model='directed_prefab_branch_hypotheses_fixed_articulation',
        branch_count=2,hypothesis_index=1,exit_intent_verified=False)
    result=dict(crossing=dict(conflicts=[conflict],brake=.2,status='protective_crossing_candidates'))
    source=dict(valid=True,lifecycle=7,generation=10,frame_us=999,observed_at=100.)
    frame=geometry(dict(actors=[actor()],source=source,status='observed',receiver_time=100.),route,
        dict(x=0.,y=10.,z=12.),12.,('epoch','session'),result,{})
    actual=frame['crossing']['conflicts'][0]
    for field in ('motion_model','branch_count','hypothesis_index','exit_intent_verified'):
        assert actual[field]==conflict[field]
