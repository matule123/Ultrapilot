"""Recover uniquely measured planar vertices, never synthesize missing geometry.

Uses an integrity-checked existing dense replay. Curve queries call production
Route on the recovered geometry and original cached projection. Calculation
speed/cruise target are not exported: application speed is an explicit proxy
and requested-speed variants are scenario inputs, not historical measurements.
"""
import argparse
import collections
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.navigation.route import Route
from core.longitudinal import curve_preview_horizon_m,curve_constraint_speed
from core.steering_replay import inspect_replay


def recover(rows):
    identities={json.dumps(r['calculation_trajectory_identity'],sort_keys=True) for r in rows}
    if len(identities)!=1:raise ValueError('mixed calculation identities')
    groups=collections.defaultdict(list)
    for row in rows:
        i,f,p=row['tracking_segment_index'],row['tracking_segment_fraction'],row['tracking_projection_xz']
        if (type(i) is not int or not 0<=i<20000 or not 0<=f<=1
                or len(p)!=2 or not all(math.isfinite(v) for v in (*p,f))):
            raise ValueError('invalid original projection')
        groups[i].append(row)
    vertices={};overlaps=[];solved=0
    for index,g in groups.items():
        a=min(g,key=lambda r:r['tracking_segment_fraction']);b=max(g,key=lambda r:r['tracking_segment_fraction'])
        fa,fb=a['tracking_segment_fraction'],b['tracking_segment_fraction']
        if fb-fa<1e-5:continue
        delta=[(b['tracking_projection_xz'][j]-a['tracking_projection_xz'][j])/(fb-fa) for j in (0,1)]
        first=[a['tracking_projection_xz'][j]-fa*delta[j] for j in (0,1)]
        for key,point in ((index,first),(index+1,[first[j]+delta[j] for j in (0,1)])):
            if key in vertices:overlaps.append(math.dist(vertices[key],point))
            vertices[key]=point
        solved+=1
    for _ in range(4):
        for index,g in groups.items():
            if index in vertices and index+1 in vertices:continue
            row=g[0];f=row['tracking_segment_fraction'];p=row['tracking_projection_xz']
            if index in vertices and f>1e-5:
                vertices[index+1]=[(p[j]-(1-f)*vertices[index][j])/f for j in (0,1)]
            elif index+1 in vertices and f<1.-1e-5:
                vertices[index]=[(p[j]-f*vertices[index+1][j])/(1-f) for j in (0,1)]
    if not vertices or any(i not in vertices for i in range(max(vertices)+1)):
        raise ValueError('unmeasured route vertices; no interpolation allowed')
    residuals=[]
    for row in rows:
        i,f=row['tracking_segment_index'],row['tracking_segment_fraction']
        if i not in vertices or i+1 not in vertices:raise ValueError('unmeasured edge endpoint')
        p=[(1-f)*vertices[i][j]+f*vertices[i+1][j] for j in (0,1)]
        residuals.append(math.dist(p,row['tracking_projection_xz']))
    # Numerical consistency of the linear constraints, not a driving criterion.
    if max(overlaps+residuals,default=0.)>1e-6:raise ValueError('inconsistent endpoint constraints')
    return dict(points=[vertices[i] for i in range(len(vertices))],directly_solved_edges=solved,
                maximum_overlap_residual_m=max(overlaps,default=0.),
                maximum_projection_residual_m=max(residuals,default=0.))


def profiles(rows,geometry,requested_speed_kmh):
    route=Route(geometry['points']);result=[]
    for row in rows:
        speed=row['speed_kmh']/3.6
        if not math.isfinite(speed) or speed<0:continue
        pos=row['observation_xz'];heading=row['observation_heading_rad']
        route._tracking_state=(tuple(pos),heading,row['tracking_segment_index'],
                               row['tracking_segment_fraction'],row['tracking_progress_m'])
        profile=route.curve_profile_ahead(pos,heading,
            curve_preview_horizon_m(speed,requested_speed_kmh),speed)
        result.append(dict(application_at=row['application_monotonic_s'],
            calculation_frame=row['calculation_sdk_frame_us'],application_frame=row['application_sdk_frame_us'],
            original_observation_timestamp=row['observation_timestamp'],
            application_speed_kmh_proxy=row['speed_kmh'],progress_m=row['tracking_progress_m'],
            lane_id=row['lane_id'],**profile,curve_only_target_kmh=curve_constraint_speed(profile,speed)*3.6))
    return dict(route_length_m=route._cumulative_m[-1],rows=result)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('replay',type=Path);p.add_argument('--build',required=True)
    p.add_argument('--requested-speed',nargs='+',type=float,default=[20.,35.,50.,60.,90.,160.])
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    if not args.output.resolve().is_relative_to(ROOT):p.error('Output must remain in workspace')
    checked=inspect_replay(args.replay)
    if not checked.get('integrity_valid'):raise ValueError('replay integrity not verified')
    all_rows=checked['replay']['samples']
    rows=[r for r in all_rows if r.get('packet_binding_valid') and
          (r.get('calculation_trajectory_identity')or{}).get('route_build_id')==args.build]
    geometry=recover(rows)
    result=dict(source_sha256=hashlib.sha256(args.replay.read_bytes()).hexdigest(),
        identity=rows[0]['calculation_trajectory_identity'],samples=len(rows),excluded=len(all_rows)-len(rows),
        limitations=__doc__,geometry=geometry,
        scenarios={str(v):profiles(rows,geometry,v) for v in args.requested_speed})
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('geometry','scenarios','limitations')},indent=2))
    print(json.dumps({k:v for k,v in geometry.items() if k!='points'},indent=2))
