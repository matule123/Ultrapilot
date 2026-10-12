"""Read-only local pose comparison, not bumper/painted-line calibration.

The stationary collection has no GPS route. Project its measured chassis pose
onto independently retained historical segments; never assign it that old
session, route authority, signal color, or an invented physical line.
"""
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import median

from core.navigation.evidence_diagnostics import inspect_collection
from core.steering_replay import inspect_replay
from tools.audit_oct11_stop_geometry import holds

INSTALL = Path(r"C:\Users\PC\AppData\Local\Programs\UltraPilot")


def measured_edges(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row['tracking_segment_index']].append(row)
    edges = []
    for index, group in groups.items():
        a = min(group, key=lambda r: r['tracking_segment_fraction'])
        b = max(group, key=lambda r: r['tracking_segment_fraction'])
        fa, fb = a['tracking_segment_fraction'], b['tracking_segment_fraction']
        if fb - fa < 1e-5:
            continue  # No guessed/interpolated missing endpoints.
        delta = [(b['tracking_projection_xz'][j] - a['tracking_projection_xz'][j])
                 / (fb-fa) for j in (0, 1)]
        length = math.hypot(*delta)
        if length <= 0:
            raise ValueError('degenerate segment')
        origin = [a['tracking_projection_xz'][j] - fa*delta[j] for j in (0, 1)]
        start = a['tracking_progress_m'] - fa*length
        errors = [math.dist([origin[j]+r['tracking_segment_fraction']*delta[j]
                            for j in (0, 1)], r['tracking_projection_xz'])
                  for r in group]
        errors += [abs(start+r['tracking_segment_fraction']*length-r['tracking_progress_m'])
                   for r in group]
        if max(errors) > 1e-6:
            raise ValueError('inconsistent original segment constraints')
        edges.append((index, origin, delta, length, start, max(errors)))
    if not edges:
        raise ValueError('no measured edges')
    return edges


def project(point, edges):
    candidates = []
    for index, origin, delta, length, start, residual in edges:
        fraction = sum((point[j]-origin[j])*delta[j] for j in (0, 1))/length**2
        fraction = min(1., max(0., fraction))
        foot = [origin[j]+fraction*delta[j] for j in (0, 1)]
        candidates.append(dict(segment=index, fraction=fraction,
            lateral_distance_m=math.dist(point, foot), progress_m=start+fraction*length,
            route_heading_rad=math.atan2(-delta[0], -delta[1]),
            reconstruction_residual_m=residual))
    return min(candidates, key=lambda r: r['lateral_distance_m'])


def compare():
    root = INSTALL/'evidence-diagnostics'/'stop-calibration-20261011-stationary-01'
    check = inspect_collection(root)
    if not check['integrity_valid']:
        raise ValueError('collection integrity failed')
    rows = []
    for part in sorted(root.glob('automatic-observations.part-*.json')):
        rows.extend(json.loads(part.read_text(encoding='utf-8'))['records'])
    if len(rows) != check['sample_count'] or not all(r['truck']['pose_valid'] for r in rows):
        raise ValueError('pose samples missing')
    dense_path = INSTALL/'route-diagnostics'/'steering-replay-20261011T104938.211656Z-automatic_disable.json'
    pedal_path = INSTALL/'route-diagnostics'/'steering-replay-20261011T104936.895268Z-automatic_disable.json'
    dense, pedal = inspect_replay(dense_path), inspect_replay(pedal_path)
    if not (dense['integrity_valid'] and pedal['integrity_valid']):
        raise ValueError('historical integrity failed')
    historical_holds = holds(pedal['replay'])
    if len(historical_holds) != 1:
        raise ValueError('ambiguous historical stop')
    hold = historical_holds[0]
    context = hold['identity']['context']
    build = context[6]
    historic = [r for r in dense['replay']['samples'] if r.get('packet_binding_valid')
                and (r.get('calculation_trajectory_identity') or {}).get('route_build_id') == build]
    for row in rows:
        if row['map_key'] != context[2] or row['dataset_fingerprint'] != context[3]:
            raise ValueError('map/dataset mismatch')
    entry = hold['target']['entry_progress_m']
    local = [r for r in historic if entry-25 < r['tracking_progress_m'] < entry+15]
    edges = measured_edges(local)
    projections = [project([r['truck']['x'], r['truck']['z']], edges) for r in rows]
    errors = [abs(math.remainder(r['truck']['rotation']-p['route_heading_rad'], 2*math.pi))
              for r, p in zip(rows, projections)]
    # Comparison guards only, not authority or physical line confirmation.
    if max(p['lateral_distance_m'] for p in projections) > 2 or max(errors) > .15:
        raise ValueError('stationary pose not compatible with historical approach')
    original_gap = median(hold['sdk_reference_to_derived_target_m']) + 8
    current_gaps = [entry-p['progress_m'] for p in projections]
    return dict(collection_integrity=check, samples=len(rows),
        collection_has_route=any(r.get('route_build_id') for r in rows),
        configuration_tokens=sorted({r['vehicle_profile']['token']['configuration'] for r in rows}),
        original_route_build=build, map_key=context[2], dataset_fingerprint=context[3],
        historical_entry_xyz=hold['target']['entry_xyz'], historical_entry_progress_m=entry,
        stationary_xyz_m=[median(r['truck'][key] for r in rows) for key in ('x','y','z')],
        stationary_frame_range=[min(r['sdk_frame_us'] for r in rows), max(r['sdk_frame_us'] for r in rows)],
        stationary_spread_xz_m=math.hypot(max(r['truck']['x'] for r in rows)-min(r['truck']['x'] for r in rows),
                                        max(r['truck']['z'] for r in rows)-min(r['truck']['z'] for r in rows)),
        projected_lateral_distance_range_m=[min(p['lateral_distance_m'] for p in projections),
                                            max(p['lateral_distance_m'] for p in projections)],
        maximum_heading_difference_deg=math.degrees(max(errors)),
        historical_reference_to_entry_m=original_gap,
        stationary_reference_to_entry_range_m=[min(current_gaps),max(current_gaps)],
        stationary_progress_range_m=[min(p['progress_m'] for p in projections), max(p['progress_m'] for p in projections)],
        desired_pose_forward_of_historical_hold_m=original_gap-median(current_gaps),
        stationary_distance_to_unchanged_derived_target_m=median(current_gaps)-8,
        reconstructed_edges=len(edges), reconstruction_maximum_residual_m=max(e[-1] for e in edges),
        measured_bumper_to_line_m=None, painted_line_world_coordinates=None,
        runtime_changed=False, calibration_authorized=False,
        limitation='Manual desired pose only; no independently measured bumper/painted line. '
                   'Different sessions, no live route. Forward pose difference is NOT a universal '
                   'front allowance or a planner adjustment; stopping residual remains separate.')


if __name__ == '__main__':
    print(json.dumps(compare(), indent=2))
