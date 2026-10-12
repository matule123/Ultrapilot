"""Read-only stop-reference audit; optional existing closed-plant exercise.

No producer, game mapping, controller setting or installed file is changed.
An SDK-reference gap is never promoted to a bumper/painted-line measurement.
"""
import argparse
from collections import Counter
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import subprocess
from unittest.mock import patch

from core.steering_replay import inspect_replay

ROOT = Path(__file__).resolve().parents[1]
INSTALL = Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')
INCIDENT = 'steering-replay-20261011T104936.895268Z-automatic_disable.json'
DENSE = 'steering-replay-20261011T104938.211656Z-automatic_disable.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def holds(replay):
    history = replay.get('longitudinal', {}).get('decision_history', {})
    groups = {}
    for row in history.get('regular_samples', []) + history.get('changes', []):
        target = row.get('stop_target') or {}
        distance = target.get('distance')
        if (row.get('hold_phase') != 'holding' or type(distance) not in (int, float)
                or not math.isfinite(distance)):
            continue
        key = (row.get('activation'), row.get('identity_reference'),
               row.get('signal_id'), target.get('passage_key'))
        groups.setdefault(key, []).append(row)
    result = []
    for key, rows in groups.items():
        values = [r['stop_target']['distance'] for r in rows]
        result.append(dict(activation=key[0], identity_reference=key[1], signal_id=key[2],
            passage_key=key[3], samples=len(rows),
            monotonic_range_s=[min(r['monotonic_s'] for r in rows), max(r['monotonic_s'] for r in rows)],
            sdk_reference_to_derived_target_m=[min(values), max(values)],
            target=rows[0]['stop_target'],
            original_sdk_frames=[min(r['sdk_frame_us'] for r in rows), max(r['sdk_frame_us'] for r in rows)],
            identity=history.get('identities', {}).get(str(key[1])),
            physical_bumper_to_painted_line_m=None,
            physical_gap_status='NOT VERIFIED: no bound line or body-front geometry',
            detailed_write_timing='NOT RETAINED for this hold; only bounded write aggregates',
            incomplete_rows=sum(r.get('capture_incomplete') is True for r in rows)))
    return result


def audit(installation, map_path):
    receipt_path = installation / 'manual-deployment.json'
    receipt = json.loads(receipt_path.read_text(encoding='utf-8-sig'))
    files = []
    for row in receipt['files']:
        installed, source = Path(row['target']), Path(row['source'])
        files.append(dict(path=str(installed), receipt_match=sha(installed) == row['sha256'].lower(),
            source_equal_after_lf_crlf=source.read_bytes().replace(b'\r\n', b'\n') ==
                installed.read_bytes().replace(b'\r\n', b'\n')))
    if not all(row['receipt_match'] for row in files):
        raise ValueError('installed receipt hash mismatch')
    evidence = []
    decoded = {}
    for name in (INCIDENT, DENSE):
        path = installation / 'route-diagnostics' / name
        check = inspect_replay(path)
        if not check['integrity_valid']:
            raise ValueError('replay integrity rejected: ' + name)
        decoded[name] = check['replay']
        evidence.append(dict(path=str(path), sha256=sha(path), integrity_valid=True,
            samples=check['replay'].get('sample_count'),
            execution_samples=check['replay'].get('execution_sample_count')))
    descriptions = json.loads(map_path.read_text(encoding='utf-8-sig'))
    schema = {}
    for name in ('navCurves', 'semaphores', 'mapPoints'):
        fields = Counter(key for p in descriptions for item in p.get(name, []) for key in item)
        schema[name] = dict(count=sum(len(p.get(name, [])) for p in descriptions), fields=dict(fields))
    settings = json.loads((installation / 'settings.json').read_text(encoding='utf-8-sig'))
    profiles = settings.get('vehicle_profiles')
    sections = holds(decoded[INCIDENT])
    reference = []
    for section in sections:
        low, high = section['monotonic_range_s']
        rows = [r for r in decoded[DENSE]['samples'] if low <= r.get('monotonic_s', -1) <= high]
        # Do not join the known unreliable application header to a pedal write.
        reference.append(dict(samples=len(rows), use='SDK axle-channel availability only; not write pairing',
            geometries=list({json.dumps(r.get('reference_geometry'), sort_keys=True)
                             for r in rows if r.get('reference_geometry')})[:4]))
    return dict(head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        installation_receipt_sha256=sha(receipt_path), deployed_at=receipt.get('deployed_at_utc'),
        installed_files=files, artifacts=evidence, holds=sections,
        map=dict(path=str(map_path), sha256=sha(map_path), prefabs=len(descriptions), schema=schema,
                 verified_painted_stop_line_channel=False),
        vehicle_profiles=dict(configured=isinstance(profiles, dict),
            entries=len(profiles.get('profiles', [])) if isinstance(profiles, dict) else 0),
        axle_observations=reference,
        verdict='OFFLINE VERIFIED reference audit / physical 1-2 m target NOT VERIFIED',
        runtime_changed=False, game_verified=False)


def model_case(directory, *, speed=35., mode=0, approach_curvature=0., program=None, other_stop=False,
               plant_options=None):
    """Actual PPD/selector/control path; explicit uncalibrated model geometry.

    Curved approach is a synthetic arc tangent to the same authored entrance.
    It tests arc-distance plumbing, NOT that entrance's painted-line placement.
    """
    from core.acc_following import RouteLeadSelector
    from core.navigation.lane_model import LanePoint
    from core.navigation.lane_trajectory import build_lane_trajectory
    from tools.audit_oct10_native_signal import placed_route
    from tools.run_oct10_signal_timing_bench import snapshot
    from tools import run_prefab_signal_bench as bench

    prepared = {}

    def geometry(folder, reverse, turn):
        net, path, plan = placed_route(folder, reverse, turn)
        if approach_curvature:
            road, *remaining = path.segments
            end = road.centerline[-1]
            k = approach_curvature
            points = []
            for s in range(101):
                theta = end.heading + k * (s-100.)
                points.append(LanePoint(end.x+(math.cos(theta)-math.cos(end.heading))/k,
                    end.y, end.z-(math.sin(theta)-math.sin(end.heading))/k,
                    heading=theta, lane_id=road.lane_id))
            road = replace(road, centerline=tuple(points))
            path = build_lane_trajectory(net.connect_lane_sequence((road, *remaining), path.source_gps_uids))
            if not path.valid:
                raise ValueError(path.failure_reason)
            projection = RouteLeadSelector()
            projection.prepare([[p.x, p.y, p.z] for p in path.points], 'offline-curved-approach')
            for passage in plan['passages']:
                entry = passage['entry_xyz']
                match = projection._project(dict(x=entry[0], y=entry[1], z=entry[2],
                    yaw=passage['entry_heading_rad']), 0., projection.arcs[-1])
                if match is None or match[0] > .5:
                    raise ValueError('authored entrance lost on modeled arc')
                passage['entry_progress_m'] = match[1]
        prepared['plan'] = plan
        return net, path, plan

    with patch.object(bench, 'plan_for', side_effect=lambda net, path: prepared['plan']):
        result = bench.run(directory, speed_kmh=speed, mode=mode, jitter=True,
            path_factory=geometry, snapshot_factory=snapshot, observer_y=6.90234375,
            phase_program=program, other_stop=other_stop, duration_limit_s=70. if program else None,
            **(plant_options or {}))
    return result


def model_metrics(result):
    stopped = result['stop']
    entry = (stopped['progress_m'] + stopped['reference_gap_to_target_m'] + 8.) if stopped else None
    # Different fronts are a geometry sensitivity analysis, NOT different
    # calibrated vehicle response plants. The controller has no such input.
    fronts = {str(front): entry-stopped['progress_m']-front for front in (3., 4., 6.)} if stopped else None
    far = [r for r in result['rows'] if r['red'] and r.get('light_distance') is not None
           and r['light_distance'] > 10. and r['speed_mps']*3.6 < 5.]
    return dict(samples=result['samples'], duration_s=result['duration_s'],
        sdk_reference_to_derived_target_m=stopped['reference_gap_to_target_m'] if stopped else None,
        assumed_front_to_authored_entry_m=fronts, painted_line_gap_m=None,
        maximum_deceleration_mps2=result['maximum_deceleration_mps2'],
        maximum_abs_model_jerk_mps3=result['maximum_abs_model_jerk_mps3'],
        brake_onset_reference_distance_to_entry_m=result['brake_start_distance_to_entry_m'],
        far_low_speed_s=sum(r['dt'] for r in far),
        pedal_transitions=result['drive_brake_transitions'],
        positive_pedal_overlap=result['simultaneous_positive_physical_writes'],
        hold_zero_samples=result['hold_brake_zero_count'], parking_writes=result['parking_writes'],
        red_entry_overrun_samples=result['red_entry_overrun_samples'],
        resumed_without_n=result['resumed_without_n'], active=result['active'])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--installation', type=Path, default=INSTALL)
    p.add_argument('--map', type=Path, default=ROOT/'map-cache/promods-1.59/europe-prefabDescriptions.json')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--models', action='store_true')
    args = p.parse_args()
    if not args.output.resolve().is_relative_to(ROOT / 'docs/steering-audit'):
        raise ValueError('write analysis only beneath the workspace steering-audit directory')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = audit(args.installation, args.map)
    if args.models:
        rows = {}
        for k in (0., 1./60., -1./60.):
            for speed in (20., 35., 50.):
                for mode in (0, 3):
                    name = f'{k:.5f}-{speed:g}-{mode}'
                    directory = args.output.parent / name
                    directory.mkdir(exist_ok=True)
                    rows[name] = model_metrics(model_case(directory, speed=speed, mode=mode, approach_curvature=k))
                    print(name, json.dumps(rows[name]), flush=True)
        result['unchanged_runtime_models'] = rows
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n', encoding='utf-8')
    print(json.dumps(dict(verdict=result['verdict'], holds=result['holds'], runtime_changed=False), indent=2))


if __name__ == '__main__':
    main()
