"""Read-only reconstruction of recorded placed PPD signal curves (Oct 5).

Uses the real parser and exact LaneIds; never writes map caches or diagnostic
inputs. A standalone recorded prefab is not the missing historical LanePath.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.navigation.road_network import RoadNetwork, _loadf, _uid
from core.navigation.lane_model import GpsCorridorEdge
from core.navigation.lane_trajectory import build_lane_trajectory
from core.navigation.prefab_signals import prepare_signal_passages


def audit(cache,replays):
    records=[]
    identities=[]
    for p in replays:
        raw=p.read_bytes();r=json.loads(raw)
        identities.append(dict(path=str(p),sha256=hashlib.sha256(raw).hexdigest(),identity=r['identity']))
        for sample in r['samples']:
            lane=sample['lane_id']
            key=(lane['prefab_token'],lane['road_uid'],tuple(lane['connector_path']))
            if lane['prefab_token'] and key not in records:records.append(key)
    prefabs=_loadf(str(cache/'europe-prefabs.json'))
    needed=set()
    for p in prefabs:
        uids=tuple(_uid(v) for v in p['nodeUids'])
        if any(p['token']==token and min(uids)==uid for token,uid,indices in records):needed.update(uids)
    net=RoadNetwork()
    for node in _loadf(str(cache/'europe-nodes.json')):
        uid=_uid(node['uid'])
        if uid in needed:
            net.nodes[uid]=(float(node['x']),float(node['y']))
            net.node_alt[uid]=float(node['z']);net.node_rot[uid]=float(node.get('rotation',0.) or 0.)
    t=time.perf_counter();net._load_prefabs(str(cache));load_ms=(time.perf_counter()-t)*1000
    result=dict(records=identities,parser_prefab_load_ms=load_ms,cases=[],
        limitation='Only recorded placed prefab chains. No historical head observation, stop line or vehicle-front measurement.')
    for token,uid,indices in records:
        instances={tuple(p) for group in net._prefab_pairs.values() for p in group if p[0]==token and min(p[1])==uid}
        data=net._prefab_lane_data.get(token) or {}
        if len(instances)!=1 or not indices or not net._curve_chain_is_valid(data,indices):continue
        curves=data['curves'];controls=[(i,curves[i].get('semaphore_id')) for i in indices if curves[i].get('semaphore_id',-1)>=0]
        if not controls:continue
        instance=next(iter(instances));nodes=data['nodes']
        entrances=[i for i,n in enumerate(nodes) if indices[0] in n['input_lanes']]
        exits=[i for i,n in enumerate(nodes) if indices[-1] in n['output_lanes']]
        if len(entrances)!=1 or len(exits)!=1:continue
        pts=net._prefab_curve_chain_3d(instance,indices)
        edge=GpsCorridorEdge(instance[1][entrances[0]],instance[1][exits[0]],'prefab',0,prefab_instance=instance)
        segment=net._make_prefab_lane_segment(edge,instance,indices,pts)
        path=build_lane_trajectory(net.connect_lane_sequence((segment,),(edge.start_uid,edge.end_uid)))
        t=time.perf_counter();plan=prepare_signal_passages(net,path);prepare_ms=(time.perf_counter()-t)*1000
        result['cases'].append(dict(token=token,road_uid=uid,indices=list(indices),ppd_path=data['path'],
            controlled_curves=controls,descriptor_node_uids=list(instance[1]),
            origin_node_index=instance[2],path_valid=path.valid,path_failure=path.failure_reason,
            prepare_ms=prepare_ms,signal_passages=plan,
            raw_curve_chain=[[p.x,p.y,p.z] for p in pts]))
    result['source_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (cache/'europe-prefabs.json',cache/'europe-prefabDescriptions.json',cache/'europe-nodes.json')}
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--installation',type=Path,default=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot'))
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    replays=[a.installation/'route-diagnostics'/n for n in (
        'steering-replay-20261005T182758.414089Z-manual_disable.json',
        'steering-replay-20261005T182906.053563Z-automatic_disable.json')]
    result=audit(a.installation/'map-cache/promods-1.59',replays)
    a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({**result,'cases':[{k:v for k,v in c.items() if k!='raw_curve_chain'} for c in result['cases']]},indent=2))
