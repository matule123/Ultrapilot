"""Offline native direction proof and same placed-prefab control model.

Original PPD positions/rotations come from the pinned fixture. Only head 3's
pose/color were historically recorded. Owner metadata, the other heads' colors,
the 100 m straight prelude and all plant responses are explicit model inputs.
No game/plugin mapping is opened. Large output belongs outside tracked data.
"""
import argparse
from dataclasses import replace
import json
import math
from pathlib import Path
import sys
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.navigation.lane_model import LanePoint, LaneId, LaneSegment, LaneConnection
from core.navigation.lane_trajectory import build_lane_trajectory
from core.navigation.road_network import RoadNetwork
from core.sdk import signal_snapshot
from tests.test_oct10_native_signal_direction import authored_heads, place, selection, scoped_bytes
from tools import run_prefab_signal_bench as bench


def placed_route(directory, reverse=False, turn=False):
    """Actual prefab chain + explicitly synthetic straight approach."""
    prefab, plan = place(directory, int(reverse))
    segment = prefab.segments[0]
    p = segment.centerline[0]
    a = LanePoint(p.x+100*math.sin(p.heading), p.y,
                  p.z+100*math.cos(p.heading), heading=p.heading)
    road_id = LaneId(100, 1, 0)
    road = LaneSegment(road_id, 10, segment.start_uid, 1, 0, 1, 4.5,
        'derived', 3, None, 'road', (a, replace(p, lane_id=road_id)),
        successors=(LaneConnection(segment.lane_id, 'prefab'),), gps_pair_index=0)
    network = RoadNetwork()
    path = build_lane_trajectory(network.connect_lane_sequence(
        (road, replace(segment, gps_pair_index=1)),
        (10, segment.start_uid, segment.end_uid)))
    assert path.valid, path.failure_reason
    for record in plan['passages']:
        record['entry_progress_m'] += 100.
    return network, path, plan


def percentile_ms(values):
    values = sorted(values)
    return {key: values[int(q*(len(values)-1))]*1000 for key,q in
        (('p50',.5),('p95',.95),('p99',.99),('maximum',1.))}


def check_original(raw, parsed):
    """Refuse a different asset, cache curve or authored fixture field."""
    assert parsed['ppd_sha256']==raw['provenance']['ppd_sha256']
    assert parsed['version']==25
    curves=raw['descriptors'][0]['navCurves']
    assert len(curves)==len(parsed['curves'])==36
    for cached,original in zip(curves,parsed['curves']):
        assert cached['semaphoreId']==original['SemaphoreId']
        for endpoint in ('start','end'):
            p=original[endpoint.title()+'Position']; c=cached[endpoint]
            assert math.dist((c['x'],c['z'],c['y']),(p['X'],p['Y'],p['Z']))<1e-5
    assert len(raw['authored_heads'])==len(parsed['semaphores'])==16
    for h,s in zip(raw['authored_heads'],parsed['semaphores']):
        assert h['authored_group']==s['SemaphoreId'] and h['type']==s['Type']
        assert h['profile']==s['Profile']['String']
        assert math.dist(h['position_xyz'],[s['Position'][k] for k in ('X','Y','Z')])<1e-6
        assert math.dist(h['quaternion_wxyz'],[s['Rotation'][k] for k in ('W','X','Y','Z')])<1e-6
    return dict(checked_curves=36,checked_authored_objects=16,
                historical_package_identity_verified=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workdir', type=Path, required=True)
    parser.add_argument('--ppd-audit', type=Path)
    args = parser.parse_args()
    args.workdir.mkdir(exist_ok=False)
    raw, heads = authored_heads()
    original = raw['recorded_head']
    opposite = heads[1]
    result = dict(limitation=__doc__, provenance=raw['provenance'],
        own_group=1, opposite_group=3,
        recorded_pose_residual_m=math.dist([opposite[k] for k in ('x','y','z')],
                                         [original[k] for k in ('x','y','z')]),
        recorded_yaw_residual_rad=math.atan2(math.sin(opposite['yaw']-original['yaw']),
                                           math.cos(opposite['yaw']-original['yaw'])),
        historical_owner_recorded=False, classifications={}, operation_ms={}, cycles={})
    if args.ppd_audit:
        result['original_asset_check']=check_original(raw,json.loads(args.ppd_audit.read_text(encoding='utf-8')))
    for name, old in (('before',True),('after',False)):
        # Exact previous scoped heading rule only; retain all distance fixes.
        heading = (lambda h: float(h['yaw'])+math.pi) if old else signal_snapshot._control_heading
        with patch.object(signal_snapshot, '_control_heading', heading):
            result['classifications'][name] = {}
            for label, incoming in (('recorded_opposite_green',[dict(opposite,color='green')]),
                                    ('own_red',[heads[3]]),
                                    ('vehicle_curve_groups',[dict(h,color='red' if h['id']==1 else 'green')
                                        for h in heads if h['id'] in (0,1,3)]),
                                    ('all_authored_as_kind1_unverified',[dict(h,color='red' if h['id']==1 else 'green')
                                        for h in heads])):
                selected,_ = selection(args.workdir, incoming)
                result['classifications'][name][label] = selected
            path,plan = place(args.workdir)
            p=path.points[0]
            points=[[p.x+100*math.sin(p.heading),p.y,p.z+100*math.cos(p.heading)]]
            points += [[q.x,q.y,q.z] for q in path.points]
            for record in plan['passages']: record['entry_progress_m'] += 100.
            snapshot=dict(valid=True,lifecycle=99,generation=1,frame_us=100,
                observed_at=1000.,lights=[dict(h,scope_schema=1,ownership_valid=True,
                    id_basis='prefab_segment_instance_id') for h in heads if h['id'] in (0,1,3)])
            truck=dict(x=points[0][0],y=p.y,z=points[0][2],rotation=p.heading,speed=35/3.6)
            selector=signal_snapshot.RouteSignalSelector(); cost=[]
            for i in range(1000):
                start=time.perf_counter()
                selector.select(dict(snapshot,generation=i+1,frame_us=i+100,
                    observed_at=1000.+i*.05),points,'actual',('authority',),truck,0.,plan)
                cost.append(time.perf_counter()-start)
            result['operation_ms'][name]=dict(samples=1000,**percentile_ms(cost))
            for mode in (0,3):
                for speed in (35.,50.):
                    def source(now,generation,frame,requested):
                        red=requested[0]['state']==2
                        # PPD semaphore objects are not all proven native
                        # kind-1 vehicle rules. The model includes only groups
                        # independently attached to original vehicle curves.
                        incoming=[dict(h,color='red' if red and h['id']==1 else 'green')
                                  for h in heads if h['id'] in (0,1,3)]
                        return scoped_bytes(now,generation,frame,incoming)
                    with patch.object(bench,'plan_for',side_effect=lambda n,p: placed_route(args.workdir)[2]):
                        try:
                            measured=bench.run(args.workdir,mode=mode,speed_kmh=speed,jitter=True,
                                path_factory=placed_route,snapshot_factory=source,observer_y=heads[3]['y'])
                            result['cycles'][f'{name}/{mode}/{speed}']={k:v for k,v in measured.items()
                                if k not in ('rows','writes','captures')}
                        except AssertionError as error:
                            if not old: raise
                            result['cycles'][f'{name}/{mode}/{speed}']=dict(
                                supported_cycle=False, rejection=str(error), completed_stop=False)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('recorded_pose_residual_m','recorded_yaw_residual_rad',
        'operation_ms','cycles')},indent=2))


if __name__=='__main__': main()
