"""Read-only load through actual application code; never activates a map."""
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.navigation.road_network import RoadNetwork


class ReadOnlyRoadNetwork(RoadNetwork):
    def _try_load_cache(self,*args,**kwargs):return False
    def _save_cache(self,*args,**kwargs):pass


def main():
    data=Path(r'C:\Users\PC\Documents\GitHub\UltraPilot-MapConverter\build\UltraPilot-MapConverter-161-Progress-127-20261021\map-cache\promods-2.84')
    before={p.name:(p.stat().st_size,p.stat().st_mtime_ns) for p in data.iterdir() if p.is_file()}
    started=time.monotonic();network=ReadOnlyRoadNetwork()
    assert network.load(str(data),progress_cb=lambda value,phase:print(phase,flush=True))
    config=json.loads((data/'config.json').read_text(encoding='utf-8'))
    assert len(network.nodes)==config['counts']['nodes']
    assert len(network.segments)==config['counts']['roads']
    assert len(network._prefab_desc)==config['counts']['prefab_descriptions']
    assert len(set(network.fwd)|set(network.bwd))==config['counts']['graph_nodes']
    assert before=={p.name:(p.stat().st_size,p.stat().st_mtime_ns) for p in data.iterdir() if p.is_file()}
    result=dict(valid=True,dataset=str(data),loader='actual UltraPilot core.navigation.road_network.RoadNetwork',
        nodes=len(network.nodes),roads=len(network.segments),prefab_descriptions=len(network._prefab_desc),
        graph_nodes=len(set(network.fwd)|set(network.bwd)),dataset_modified=False,active_map_changed=False,
        game_verified=False,elapsed_s=time.monotonic()-started)
    output=ROOT/'docs/steering-audit/oct21-actual-generated-map-load.json'
    output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
