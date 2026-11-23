"""Read the incident's unchanged local prefab navigation graph offline."""
from pathlib import Path
import json
import math
from core.navigation.road_network import RoadNetwork

def main():
    import argparse,time
    parser=argparse.ArgumentParser();parser.add_argument('--verify-runtime-preparation',action='store_true')
    args=parser.parse_args()
    root=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')
    net=RoadNetwork();assert net._try_load_cache(str(root/'map-cache/promods-2.84'))
    out=Path(__file__).resolve().parents[1]/'docs/steering-audit/nov2-roundabout'
    lane=json.loads((out/'prior-lane.json').read_bytes())
    if args.verify_runtime_preparation:
        from types import SimpleNamespace
        from core.actor_motion import prepare_prefab_motion
        from core.navigation.lane_model import LaneId
        path=SimpleNamespace(segments=[SimpleNamespace(start_uid=c['start_uid'],end_uid=c['end_uid'],
            lane_id=LaneId(**c['lane_id'])) for c in lane['lane_corridor']])
        started=time.perf_counter();payload=prepare_prefab_motion(net,path);elapsed=time.perf_counter()-started
        old=json.loads((out/'local-prefab-topology.json').read_bytes())
        original={(str(r['instance'][0]),tuple(r['instance'][1]),c['index']):c['points'] for r in old for c in r['curves']}
        actual={(str(c['prefab_token']),tuple(c['instance_node_uids']),c['curve_index']):c['points'] for c in payload['curves']}
        assert original==actual and payload['status']=='prepared'
        proof=dict(exact_transformed_points=True,curves=len(actual),points=sum(map(len,actual.values())),
            preparation_ms=elapsed*1000.,payload_json_bytes=len(json.dumps(payload).encode()),
            map_key='promods-2.84',fingerprint=lane['source_dataset_fingerprint'])
        (out/'map-preparation-proof.json').write_text(json.dumps(proof,indent=2));print(json.dumps(proof));return
    instances={}
    for c in lane['lane_corridor']:
        pair=tuple(sorted((c['start_uid'],c['end_uid'])))
        for inst in net._prefab_pairs.get(pair,()):instances[repr(inst)]=inst
    results=[]
    for inst in instances.values():
        data=net._prefab_lane_data[inst[0]];curves=[]
        for i,curve in enumerate(data['curves']):
            points=net._prefab_curve_chain_3d(inst,(i,))
            curves.append(dict(index=i,next=list(curve['next_lines']),
                points=[[p.x,p.y,p.z] for p in points],
                closest_actor_m=min((math.hypot(p.x-46045.,p.z-40230.) for p in points),default=None)))
        results.append(dict(instance=inst,path=data.get('path'),curves=curves))
    (out/'local-prefab-topology.json').write_text(json.dumps(results,indent=2))
    print(json.dumps([dict(instance=r['instance'],path=r['path'],curves=len(r['curves']),
        points=sum(len(c['points']) for c in r['curves'])) for r in results],indent=2))

if __name__=='__main__':main()
