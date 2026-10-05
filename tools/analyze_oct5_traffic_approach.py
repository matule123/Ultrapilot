"""Read-only Oct 5 evidence/cache audit. No game or runtime mapping is opened.

Replay application headers are NOT pedal receipts or immutable calculation
bindings. Reconstructed cache geometry is identified by exact recorded LaneId;
it is not the missing original complete LanePath or a physical road boundary.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.navigation.road_network import RoadNetwork
from core.navigation.lane_model import LaneId
from core.navigation.route import Route
from core.longitudinal import curve_speed_envelope, curve_preview_horizon_m

NAMES = ('steering-replay-20261005T182758.414089Z-manual_disable.json',
         'steering-replay-20261005T182906.053563Z-automatic_disable.json')
RUNTIME = ('core/engine.py', 'core/controller.py', 'core/longitudinal.py',
           'core/acc_following.py', 'core/service_brake_hold.py',
           'core/sdk/signal_snapshot.py', 'core/navigation/route.py',
           'plugins/map/main.py', 'plugins/autopilot/main.py',
           'plugins/acc/main.py', 'plugins/drivepolicy/main.py')


def audit(installation, baseline='HEAD', geometry=False):
    output = dict(baseline=subprocess.check_output(['git', 'rev-parse', baseline],
        cwd=ROOT, text=True).strip(), files=[], replays=[])
    for name in RUNTIME:
        source = subprocess.check_output(['git', 'show', f'{baseline}:{name}'], cwd=ROOT)
        installed = (installation/name).read_bytes()
        output['files'].append(dict(path=name, source_sha256=hashlib.sha256(source).hexdigest(),
            installed_sha256=hashlib.sha256(installed).hexdigest(), bytes_equal=source == installed,
            content_equal=source.replace(b'\r\n', b'\n') == installed.replace(b'\r\n', b'\n')))
    samples = []
    for name in NAMES:
        raw = (installation/'route-diagnostics'/name).read_bytes()
        replay = json.loads(raw)
        rows = replay['samples']; executions = replay['execution_samples']
        samples.extend(rows)
        output['replays'].append(dict(file=name, sha256=hashlib.sha256(raw).hexdigest(),
            identity=replay['identity'], sample_count=len(rows), executions=len(executions),
            immutable_source_count=sum(isinstance(e.get('source_packet'), dict) for e in executions),
            progress_range_m=[min(s['tracking_progress_m'] for s in rows),
                              max(s['tracking_progress_m'] for s in rows)],
            speed_reference='application SDK header; NOT a calculation-frame or pedal binding'))
    if not geometry:
        return output
    net = RoadNetwork()
    if not net._try_load_cache(str(installation/'map-cache/promods-1.59')):
        raise ValueError('existing cache unavailable')
    # Exact placed instance ID plus token, not a nearby display polygon.
    instances = {}
    for group in net._prefab_pairs.values():
        for instance in group:
            instances.setdefault((instance[0], min(instance[1])), instance)
    lanes, seen = [], set()
    for sample in samples:
        key = dict(sample['lane_id']); key['connector_path'] = tuple(key['connector_path'])
        lane_id = LaneId(**key)
        if lane_id in seen:
            continue
        seen.add(lane_id)
        token = lane_id.prefab_token
        if token:
            instance = instances.get((token, lane_id.road_uid))
            data = net._prefab_lane_data.get(token) or {}
            if not instance or not net._curve_chain_is_valid(data, lane_id.connector_path):
                raise ValueError(f'no proven recorded prefab chain: {lane_id}')
            points = net._prefab_curve_chain_3d(instance, lane_id.connector_path)
            path = data.get('path')
        else:
            candidates = net.lane_segments_near(tuple(sample['observation_xz']), radius=28.)
            matches = [c for c in candidates if c.lane_id == lane_id]
            if len(matches) != 1:
                raise ValueError(f'no unique recorded road lane: {lane_id}')
            points, path = matches[0].centerline, None
        lanes.append(dict(lane_id=sample['lane_id'], prefab_path=path,
            first_sample_progress_m=sample['tracking_progress_m'],
            points=[[p.x, p.y, p.z] for p in points]))
    output['recorded_lanes'] = lanes
    # Independent local lane chains; reject unproven bridges. This is a static
    # envelope comparison, not a closed-loop reconstruction of the driven car.
    points, joins, chains, members = [], [], [], []
    for lane in lanes:
        current = lane['points']
        if points:
            gap = math.dist(points[-1], current[0]); joins.append(gap)
            if gap > .5:
                chains.append((Route([(p[0], p[2]) for p in points]), members))
                points, members = [], []  # Never synthesize the unrecorded bridge.
        points.extend(current[1:] if points else current)
        members.append(lane['lane_id'])
    if points:
        chains.append((Route([(p[0], p[2]) for p in points]), members))
    comparisons = []
    for sample in samples:
        if sample['speed_kmh'] < 5.:
            continue
        matched = [r for r, ids in chains if sample['lane_id'] in ids]
        if len(matched) != 1:
            raise ValueError('ambiguous recorded lane occurrence')
        route = matched[0]
        pos, heading = tuple(sample['observation_xz']), sample['observation_heading_rad']
        speed = sample['speed_kmh']/3.6
        horizon = curve_preview_horizon_m(speed, 50.)
        profile = route.curve_profile_ahead(pos, heading, horizon, speed)
        # The optional-speed API preserves the exact legacy sample positions
        # (including the final horizon sample) and maximum-curvature ranking.
        old = route.curve_profile_ahead(pos, heading, horizon)
        distance = old['distance_m']
        before = curve_speed_envelope(old['radius_m'], distance, speed)[0]
        after = curve_speed_envelope(profile['radius_m'], profile['distance_m'], speed)[0]
        comparisons.append(dict(recorded_progress_m=sample['tracking_progress_m'],
            lane_id=sample['lane_id'],
            before_kmh=before*3.6, after_kmh=after*3.6,
            before_distance_m=distance, after_distance_m=profile['distance_m']))
    output.update(join_gaps_m=joins, coherent_chain_count=len(chains),
                  geometry_comparison='STATIC EXACT-LANE CACHE CHAINS; UNRECORDED GAPS NOT BRIDGED',
                  envelope_comparison=comparisons)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installation', type=Path,
        default=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot'))
    parser.add_argument('--baseline', default='HEAD')
    parser.add_argument('--geometry', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.installation, args.baseline, args.geometry)
    args.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items()
                     if k not in ('recorded_lanes', 'envelope_comparison')}, indent=2))
