"""Exact broad phases must retain collisions and separate native identities."""
import math,random
from core.acc_following import RouteLeadSelector


def test_indexed_route_segments_cover_every_intersecting_aabb():
    route=RouteLeadSelector()
    points=[[i*1.7,10.,12.*math.sin(i*.1)] for i in range(120)]
    route.prepare(points,'same-geometry')
    source=random.Random(17)
    for _ in range(300):
        x=source.uniform(-20.,220.);z=source.uniform(-20.,20.)
        xmin,xmax=x,x+source.uniform(0.,50.)
        zmin,zmax=z,z+source.uniform(0.,25.)
        actual=set(route.crossing_edges(xmin,xmax,zmin,zmax,0,len(route.edges)))
        required=set()
        for i,(a,b) in enumerate(zip(points,points[1:])):
            if (max(a[0],b[0])>=xmin and min(a[0],b[0])<=xmax
                    and max(a[2],b[2])>=zmin and min(a[2],b[2])<=zmax):required.add(i)
        assert required<=actual
    # Long unsampled edges use the exact fallback rather than a partial grid.
    route.prepare([[0.,10.,0.],[1e6,10.,1e6]],'long-edge')
    assert list(route.crossing_edges(99.,101.,99.,101.,0,1))==[0]


def test_geometry_replacement_cannot_keep_previous_query_indices():
    route=RouteLeadSelector();route.prepare([[0.,10.,0.],[0.,10.,100.]],'first')
    route._crossing_query_cache={}
    assert list(route.crossing_edges(-1.,1.,1.,2.,0,1))==[0]
    route.prepare([[100.,10.,0.],[100.,10.,100.]],'changed')
    assert list(route.crossing_edges(-1.,1.,1.,2.,0,1))==[]


def test_equal_geometry_never_merges_actors_or_their_trailer_records():
    route=RouteLeadSelector();route.prepare([[0.,10.,0.],[0.,10.,100.]],'model')
    body=dict(x=-10.,y=10.,z=20.,yaw=-math.pi/2,dimensions_whl=(2.,2.,4.))
    actors=[dict(body,id=aid,speed=5.,source='moving',slot=aid,record_fingerprint=str(aid),
        bodies=[dict(body),dict(body)]) for aid in (7,8)]
    truck=dict(x=0.,y=10.,z=0.,rotation=math.pi,speed=5.)
    result=route.crossing(actors,truck,0.)
    assert len(result['conflicts'])==4 and result['brake']>0.
    assert {(c['id'],c['body_index'],c['actor']['slot'],c['actor']['record_fingerprint'])
        for c in result['conflicts']}=={(aid,i,aid,str(aid)) for aid in (7,8) for i in (0,1)}
    actors[1].update(x=-1000.)
    actors[1]['bodies']=[dict(body,x=-1000.)]
    result=route.crossing(actors,truck,0.)
    assert all(c['id']==7 for c in result['conflicts'])


def test_batched_body_pairs_equal_scalar_transform_and_all_edge_checks():
    from core.actor_motion import crossing_pairs,body_poses,ActorMotionGraph
    from tests.traffic.test_actor_motion_contract import graph,actor
    route=RouteLeadSelector();route.prepare([[0.,10.,0.],[0.,10.,20.],[-10.,10.,30.]],'model')
    a=actor();motion=ActorMotionGraph(graph()).hypotheses(a,history_valid=True)
    bodies=[dict(a['bodies'][0]),dict(a['bodies'][0],x=2.,z=1.,yaw=2.8)]
    actual=crossing_pairs(a,bodies,motion,route._crossing_bounds,0)
    expected={}
    for body_index,body in enumerate(bodies):
        for branch_index,branch in enumerate(motion['branches']):
            poses=body_poses(a,body,branch)
            for index,(p,q) in enumerate(zip(poses,poses[1:])):
                vx=(q['x']-p['x'])/.25;vz=(q['z']-p['z'])/.25
                ex=p['x']+vx*.25;ez=p['z']+vz*.25
                edges=[i for i,(xmin,xmax,zmin,zmax) in enumerate(route._crossing_bounds)
                    if min(p['x'],ex)<=xmax and max(p['x'],ex)>=xmin
                    and min(p['z'],ez)<=zmax and max(p['z'],ez)>=zmin]
                if edges:
                    expected.setdefault(body_index,[]).append(((index*.25,p['x'],p['y'],p['z'],vx,vz,.25,branch_index),edges))
    assert actual==expected
