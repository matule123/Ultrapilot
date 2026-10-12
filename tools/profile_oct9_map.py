"""Read-only profile of Oct 9's directed UID window and real map cache.

Derive the original window from logged directed LaneIds and map-authored ports;
do not choose a nearby lane or synthesize missing geometry. No game/runtime I/O.
"""
import argparse
import ast
import cProfile
import gc
import json
import math
from pathlib import Path
import pstats
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.navigation.road_network import RoadNetwork
from core.navigation.lane_model import LaneLocator
from core.navigation.route import Route
from core.steering_replay import inspect_replay
import hashlib


def window(network, log, build):
    with log.open(encoding='utf-8', errors='replace') as stream:
        line = next(line for line in stream if build in line and
                    'phase=select_lane_sequence status=ok' in line)
    details = json.loads(line.split('details=', 1)[1])
    pairs = []
    for value in details['lane_ids']:
        node = ast.parse(value, mode='eval').body
        assert isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'LaneId'
        lane = {k.arg: ast.literal_eval(k.value) for k in node.keywords}
        if lane['prefab_token'] is None:
            a, b = network._seg_uids[network._road_segment_by_uid[lane['road_uid']]]
            pairs.append((a, b) if lane['direction'] > 0 else (b, a))
        else:
            instances = {tuple(instance[:3]): instance
                for group in network._prefab_pairs.values() for instance in group
                if instance[0] == lane['prefab_token'] and min(instance[1]) == lane['road_uid']}
            assert len(instances) == 1, (lane, len(instances))
            instance = next(iter(instances.values()))
            ports = network._prefab_lane_data[instance[0]]['nodes']
            chain = lane['connector_path']
            starts = [i for i, port in enumerate(ports) if chain[0] in port['input_lanes']]
            ends = [i for i, port in enumerate(ports) if chain[-1] in port['output_lanes']]
            assert len(starts) == len(ends) == 1, (lane, starts, ends)
            pairs.append((instance[1][starts[0]], instance[1][ends[0]]))
    assert all(a[1] == b[0] for a, b in zip(pairs, pairs[1:])), pairs
    return [pairs[0][0]] + [p[1] for p in pairs]


def main(args):
    network = RoadNetwork()
    assert network._try_load_cache(str(args.dataset)), 'Matching read-only cache required'
    uids = window(network, args.log, args.build)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    inspected = inspect_replay(args.replay)
    assert inspected['integrity_valid'], inspected
    replay = inspected['replay']
    rows = [r for r in replay['samples'] if r.get('packet_binding_valid')]
    assert rows and all(r['route_build_id'] == args.build for r in rows)
    print('cache nodes', len(network.nodes), 'uids', len(uids), 'rows', len(rows), flush=True)
    gc_events = []
    begin_gc = {}
    def callback(phase, info):
        if phase == 'start': begin_gc[info['generation']] = time.perf_counter()
        else: gc_events.append(dict(generation=info['generation'], duration_s=
            time.perf_counter()-begin_gc[info['generation']], collected=info['collected']))
    gc.callbacks.append(callback)
    locator = LaneLocator(network)
    profile = cProfile.Profile()
    times = []
    matches = []
    previous = None
    profile.enable()
    try:
        for _ in range(args.passes):
            for row in rows:
                x, z = row['observation_xz']
                y = network.altitude_near((x, z))
                started = time.perf_counter()
                previous = locator.locate((x, y, z), row['observation_heading_rad'], uids, previous)
                times.append(time.perf_counter()-started)
                matches.append(repr(previous.lane_id) if previous else None)
    finally:
        profile.disable()
        gc.callbacks.remove(callback)
    profile.dump_stats(str(args.output.with_suffix('.prof')))
    pstats.Stats(profile).strip_dirs().sort_stats('cumulative').print_stats(22)
    result = dict(dataset=str(args.dataset), build=args.build, gps_uids=uids,
        localization_times_s=times, gc_events=gc_events, matched=matches,
        source_replay=str(args.replay), limitations='Original window reconstructed from logged directed ports; altitude is map-derived, not original SDK altitude. cProfile overhead included.')
    result['replay_sha256'] = hashlib.sha256(args.replay.read_bytes()).hexdigest()
    result['topology_cache_accounted_bytes'] = network._prefab_topology_cache_bytes
    args.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print('max_s', max(times), 'GC', sorted(gc_events,key=lambda r:r['duration_s'],reverse=True)[:5])


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset', type=Path, required=True)
    p.add_argument('--log', type=Path, required=True)
    p.add_argument('--replay', type=Path, required=True)
    p.add_argument('--build', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--passes', type=int, default=3)
    args = p.parse_args()
    if not args.output.resolve().is_relative_to(ROOT): p.error('Output must stay in workspace')
    main(args)
