"""Compare optimization with the immutable, functionally repaired candidate.

No future actor samples. Same ordered native inputs and topology; comparison
tolerance is zero for these scalar-preserving optimizations. Release timing
and resource gates are tested by the separate existing load qualification.
"""
import importlib.util
import json
from pathlib import Path
import random
import copy
import hashlib
import pytest

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'docs/steering-audit/nov2-roundabout/release11/verification-runtime'


def old_module(name):
    path=BASE/'core'/f'{name}.py'
    manifest=json.loads((BASE.parent/'candidate-manifest.json').read_bytes())
    expected=next(r['sha256'] for r in manifest['files'] if r['path']==f'core/{name}.py')
    assert hashlib.sha256(path.read_bytes()).hexdigest()==expected
    spec=importlib.util.spec_from_file_location('before_'+name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_directed_branches_equal_repaired_baseline_for_original_and_varied_poses():
    from core.actor_motion import ActorMotionGraph
    from core.acc_following import observation
    from tools.reproduce_roundabout_prediction import decode
    data=json.loads((ROOT/'tests/fixtures/nov2-roundabout-native.json').read_bytes())
    before=old_module('actor_motion').ActorMotionGraph(data['graph'])
    after=ActorMotionGraph(data['graph']);rng=random.Random(606)
    for frame in data['frames']:
        for actor in observation(decode(frame),frame['at_s'])['actors']:
            if actor['source']!='moving':continue
            for dx,dz,dy,angle in ((0.,0.,0.,0.),(rng.uniform(-2.,2.),rng.uniform(-2.,2.),
                    rng.uniform(-2.,2.),rng.uniform(-.6,.6))):
                changed=dict(actor,x=actor['x']+dx,z=actor['z']+dz,y=actor['y']+dy,yaw=actor['yaw']+angle)
                assert after.hypotheses(changed,history_valid=True)==before.hypotheses(changed,history_valid=True)
    assert after.hypotheses(changed,history_valid=False) is None


def test_crossing_pair_prefilter_keeps_exact_original_pairs():
    import numpy as np
    from core.actor_motion import ActorMotionGraph,crossing_pairs
    from tests.traffic.test_actor_motion_contract import graph,actor
    old=old_module('actor_motion');a=actor()
    motion=ActorMotionGraph(graph()).hypotheses(a,history_valid=True)
    rng=random.Random(609)
    for _ in range(150):
        bounds=[]
        for i in range(rng.randrange(0,100)):
            x,z=rng.uniform(-50.,50.),rng.uniform(-50.,100.)
            bounds.append([x,x+rng.random()*10.,z,z+rng.random()*10.])
        edges=np.asarray(bounds,dtype=float).reshape(-1,4)
        bodies=[dict(a['bodies'][0],x=a['x']+i*2.,z=a['z']-i*5.) for i in range(4)]
        assert crossing_pairs(a,bodies,motion,edges,7)==old.crossing_pairs(a,bodies,motion,edges,7)


def test_crossing_intersection_prefilter_keeps_touches_and_intersections():
    import math
    from core.acc_following import RouteLeadSelector
    from core.actor_motion import ActorMotionGraph, crossing_pairs
    from tests.traffic.test_actor_motion_contract import graph, actor

    route = RouteLeadSelector()
    route.prepare([[-8.,10.,3.],[0.,10.,5.],[8.,10.,10.],[0.,10.,20.],[-12.,10.,26.]], 'route')
    target = actor()
    motion = ActorMotionGraph(graph()).hypotheses(target, history_valid=True)
    bodies = [target['bodies'][0], dict(target['bodies'][0], z=1.)]
    before = old_module('actor_motion').crossing_pairs(target,bodies,motion,route._crossing_bounds,0)
    after = crossing_pairs(target,bodies,motion,route._crossing_bounds,0,edge_values=route._crossing_values)
    parallel = math.sin(math.radians(20.))*target['speed']
    required = {}
    for body, candidates in before.items():
        for segment, indices in candidates:
            _,x,_,z,vx,vz,duration,_ = segment
            keep = []
            for index in indices:
                ax,_,az,dx,_,dz,_,inverse,_,_ = route.edges[index]
                denominator = vx*dz-vz*dx
                if abs(denominator)*inverse < parallel:
                    continue
                ox,oz = ax-x,az-z
                time = (ox*dz-oz*dx)/denominator
                along = (ox*vz-oz*vx)/denominator
                if 0 <= time <= duration and 0 <= along <= 1:
                    keep.append(index)
            if keep:
                required.setdefault(body, []).append((segment,keep))
    assert required
    assert after == required


@pytest.mark.parametrize('signed_speed',[0.,-.039795611,7.6])
def test_shared_body_prefix_keeps_all_contacts_and_debug_paths(signed_speed):
    from core.acc_following import RouteLeadSelector
    from core.actor_motion import ActorMotionGraph
    from core.acc_body_prediction import predict
    from tests.traffic.test_actor_motion_contract import graph,actor
    route=RouteLeadSelector();route.prepare([[0.,10.,0.],[0.,10.,100.]],'identity',actor_motion=graph())
    a=actor();a['bodies']=[dict(a['bodies'][0],z=5.-i*4.) for i in range(4)]
    motion=ActorMotionGraph(graph()).hypotheses(a,history_valid=True)
    route.actor_motion=lambda value:motion
    old=old_module('acc_body_prediction')
    for x in (0.,3.,20.):
        bodies=[dict(a['bodies'][0],x=x,z=18.-i*5.,dimensions_whl=(2.5,3.,6.)) for i in range(4)]
        args=route,bodies,[a],signed_speed,18.,(x,10.,18.)
        original={};optimized={}
        assert predict(*args,debug_geometry=optimized)==old.predict(*args,debug_geometry=original)
        assert optimized==original


def test_new_dataset_and_actor_acquisition_cannot_reuse_old_geometry():
    from core.acc_following import RouteLeadSelector
    from tests.traffic.test_actor_motion_contract import graph,actor
    route=RouteLeadSelector();points=[[0.,10.,0.],[0.,10.,100.]]
    route.prepare(points,('session','dataset1','route1'),actor_motion=graph())
    original=route._actor_motion_graph
    route._actor_motion_cache[19]={'stale':True}
    payload=copy.deepcopy(graph())
    for curve in payload['curves']:
        for point in curve['points']:point[0]+=100.
    route.prepare(points,('session','dataset2','route1'),actor_motion=payload)
    assert route._actor_motion_graph is not original and not route._actor_motion_cache
    assert route._actor_motion_graph.hypotheses(actor(),history_valid=True) is None


def test_new_acquisition_recomputes_actor_and_trailer_geometry():
    from core.acc_following import RouteLeadSelector
    from tests.traffic.test_actor_motion_contract import graph, actor

    selector = RouteLeadSelector()
    selector.prepare([[0.,10.,0.],[0.,10.,100.]], 'route', actor_motion=graph())
    original = actor()
    trailer = dict(original['bodies'][0], z=1.)
    original['bodies'] = [original['bodies'][0], trailer]
    source = dict(valid=True, lifecycle=27, generation=1, frame_us=100, observed_at=10.)
    selector.source_motion([original], source)
    selector.source_motion([original], dict(source, generation=2, frame_us=200, observed_at=10.1))
    model = selector.actor_motion(original)
    before = selector.actor_body_motion(original, model)
    assert selector.actor_body_motion(original, model) is before
    assert not before.flags.writeable
    moved = dict(original, z=5.1, speed=5.2,
        bodies=[dict(original['bodies'][0], z=5.1), dict(trailer, z=1.1)])
    selector.source_motion([moved], dict(source, generation=3, frame_us=300, observed_at=10.2))
    newer = selector.actor_motion(moved)
    after = selector.actor_body_motion(moved, newer)
    assert newer != model and after is not before
    assert after[1,0,0,2] == pytest.approx(1.1)
    assert before[1,0,0,2] == pytest.approx(1.)
    selector.source_motion([moved], dict(source, lifecycle=28, generation=4, frame_us=400, observed_at=10.3))
    assert selector.actor_motion(moved) is None
