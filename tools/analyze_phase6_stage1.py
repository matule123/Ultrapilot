"""Offline metrics for existing simulations, evidence exports and replay files.

Never opens an input backend, arms a collector or starts the game. Raw outputs
belong in an ignored audit directory. Legacy execution headers are NOT bindings.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def finite(value):
    return type(value) in (float, int) and math.isfinite(value)


def distribution(values):
    good = sorted(float(x) for x in values if finite(x))
    if not good:
        return dict(n=0, mean=None, rms=None, median=None, p95=None, p99=None, maximum=None)
    def percentile(fraction):
        i = (len(good) - 1) * fraction
        lo, hi = math.floor(i), math.ceil(i)
        return good[lo] + (good[hi] - good[lo]) * (i - lo)
    return dict(n=len(good), mean=sum(good)/len(good),
                rms=math.sqrt(sum(x*x for x in good)/len(good)),
                median=percentile(.5), p95=percentile(.95), p99=percentile(.99),
                maximum=good[-1])


def segments(rows, *, gap_s=.5):
    """Input order matters. Never reorder across identity/state/time changes."""
    result = []
    previous = None
    for row in rows:
        if not finite(row.get('time_s')):
            previous = None
            continue
        key = (json.dumps(row.get('identity'), sort_keys=True), row.get('phase'),
               row.get('reference'))
        if (previous is None or key != previous[0]
                or not 0 < row['time_s'] - previous[1] <= gap_s):
            result.append([])
        result[-1].append(row)
        previous = key, row['time_s']
    return result


def summarize(rows, *, gap_s=.5):
    groups = segments(rows, gap_s=gap_s)
    values = [r.get('cte_m') for r in rows]
    valid = [v for v in values if finite(v)]
    weights = []
    rates, steps, accelerations = [], [], []
    saturation_time = 0.0
    sign_changes = 0
    duration = 0.0
    covered_length = 0.0
    for group in groups:
        last_rate = None
        last_sign = 0
        if len(group) > 1:
            duration += group[-1]['time_s'] - group[0]['time_s']
            if all(finite(r.get('progress_m')) for r in (group[0], group[-1])):
                covered_length += max(0., group[-1]['progress_m'] - group[0]['progress_m'])
        for row in group:
            out = row.get('steer')
            sign = 1 if finite(out) and out > .02 else -1 if finite(out) and out < -.02 else 0
            if sign and last_sign and sign != last_sign:
                sign_changes += 1
            if sign:
                last_sign = sign
        for a, b in zip(group, group[1:]):
            dt = b['time_s'] - a['time_s']
            # Left-hold CTE quadrature until the next sample. No terminal weight
            # and no interpolation over a missing observation or gap.
            if finite(a.get('cte_m')) and finite(b.get('cte_m')):
                weights.append((a['cte_m'], dt))
            if a.get('saturated') is True:
                saturation_time += dt
            if finite(a.get('steer')) and finite(b.get('steer')):
                delta = b['steer'] - a['steer']
                rate = delta/dt
                steps.append(abs(delta)); rates.append(abs(rate))
                # Derivatives are located at interval midpoints.
                midpoint = (a['time_s']+b['time_s'])/2
                if last_rate is not None:
                    accelerations.append(abs((rate-last_rate[0])/(midpoint-last_rate[1])))
                last_rate = rate, midpoint
            else:
                last_rate = None
    weighted_seconds = sum(w for _, w in weights)
    return dict(samples=len(rows), segments=len(groups), duration_s=duration,
        covered_progress_m=covered_length,
        cte_reference=sorted({str(r.get('reference')) for r in rows}),
        cte_abs=distribution(abs(v) for v in valid), cte_rms_m=distribution(valid)['rms'],
        cte_missing_or_invalid=len(values)-len(valid),
        cte_time_weighted_rms_m=(math.sqrt(sum(v*v*w for v,w in weights)/weighted_seconds)
                                 if weighted_seconds else None),
        cte_weighted_duration_s=weighted_seconds,
        heading_abs_rad=distribution(abs(r['heading_rad']) for r in rows if finite(r.get('heading_rad'))),
        heading_missing_or_invalid=sum(not finite(r.get('heading_rad')) for r in rows),
        steering_step=distribution(steps), steering_rate_abs_per_s=distribution(rates),
        steering_acceleration_abs_per_s2=distribution(accelerations),
        known_saturation_time_s=(saturation_time if any(type(r.get('saturated')) is bool for r in rows) else None),
        output_sign_changes_at_002=sign_changes,
        sign_change_limitation='Includes intended S/entry/exit reversals; not automatically an oscillation count.')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def identity(source):
    return {k: source.get(k) for k in ('navigation_intent_id', 'authority_revision',
        'route_build_id','source_game_session_id','source_map_key','source_dataset_fingerprint')}


def source_measurement(source, phase):
    match = source.get('lane_match_snapshot') or {}
    return dict(time_s=source.get('observation_timestamp'), identity=identity(source), phase=phase,
        reference='SDK chassis-origin LaneMatch CTE', cte_m=match.get('lateral_error_m'),
        heading_rad=source.get('body_tracking_error_rad'), progress_m=source.get('tracking_progress_m'),
        # Error measurement is not a physical execution measurement.
        steer=None, saturated=source.get('saturated'))


def timing_summary(rows):
    pairs = {
        'lane_update_ms': ('map_tick_started_at', 'map_lane_update_finished_at'),
        'presentation_ms': ('map_lane_update_finished_at', 'map_presentation_finished_at'),
        'road_type_ms': ('map_presentation_finished_at', 'map_road_type_finished_at'),
        'reference_ms': ('map_road_type_finished_at', 'map_reference_finished_at'),
        'calculation_ms': ('map_calculation_started_at', 'computed_at'),
        'IPC_publish_ms': ('map_packet_publish_started_at', 'map_packet_publish_completed_at'),
        'publish_to_read_ms': ('map_packet_publish_completed_at', 'autopilot_packet_read_finished_at'),
        'compute_to_read_ms': ('computed_at', 'autopilot_packet_read_finished_at')}
    result = {name:distribution(1000*(r[b]-r[a]) for r in rows
              if finite(r.get(a)) and finite(r.get(b)) and r[b] >= r[a])
              for name,(a,b) in pairs.items()}
    result['observation_age_at_read_ms'] = distribution(
        1000*r['observation_age_at_read_s'] for r in rows
        if finite(r.get('observation_age_at_read_s')) and r['observation_age_at_read_s'] >= 0)
    return result


def collection_report(path):
    from core.navigation.evidence_diagnostics import inspect_collection
    checked = inspect_collection(path)
    if checked.get('integrity_valid') is not True:
        raise ValueError('COLLECTION_INTEGRITY_NOT_VERIFIED')
    manifest_path = path/'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    document = json.loads((path/'automatic-observations.json').read_text(encoding='utf-8'))
    rows = document.get('samples', [])
    if document.get('chunked'):
        rows = []
        for entry in manifest['files']:
            if entry.get('role') == 'chunk' and entry['name'].startswith('automatic-observations'):
                rows.extend(json.loads((path/entry['name']).read_text(encoding='utf-8'))['records'])
    observations, writes = [], []
    phases = Counter(); excluded = Counter(); packets = {}; intervals = []
    ages, latencies = [], []
    last_packet = None
    for row in rows:
        # Inactive data lack gear/throttle: launch/manual/stop cannot be guessed.
        phase = 'active' if row.get('autopilot_active') else 'inactive_unclassified'
        phases[phase] += 1
        source = (row.get('executor') or {}).get('source_packet')
        if not isinstance(source, dict):
            excluded['no_immutable_source'] += 1; continue
        packet_key = json.dumps(identity(source), sort_keys=True), source.get('calculation_sequence')
        if packet_key not in packets:
            packets[packet_key] = source
            observations.append(source_measurement(source, phase))
            now = source.get('computed_at')
            if last_packet and packet_key[0] == last_packet[0] and finite(now) and finite(last_packet[1]):
                dt = now-last_packet[1]
                if 0 < dt <= .5:
                    intervals.append(dt*1000)
            last_packet = packet_key[0], now
        elif packets[packet_key] != source:
            raise ValueError('CONFLICTING_IMMUTABLE_SOURCE_PACKET')
        ex = row['executor']; boundary = row.get('steering_boundary') or {}
        t = boundary.get('steering_write_returned_at_s')
        value = row.get('engine_steer')
        if (not row.get('backend_sent') or row.get('command_binding_proven') is not True
                or not finite(t) or not finite(value) or not finite(ex.get('output'))
                or abs(value-ex['output']) > 1e-12):
            excluded['no_confirmed_source_bound_write'] += 1; continue
        if not finite(source.get('observation_timestamp')) or not 0 <= t-source['observation_timestamp'] <= .5:
            excluded['stale_or_unknown_source_at_write'] += 1; continue
        ages.append((t-source['observation_timestamp'])*1000)
        if finite(source.get('computed_at')) and t >= source['computed_at']:
            latencies.append((t-source['computed_at'])*1000)
        writes.append(dict(time_s=t, identity=identity(source), phase=phase,
            reference='physical normalized backend steering', steer=value,
            progress_m=source.get('tracking_progress_m'), cte_m=None, heading_rad=None,
            saturated=source.get('saturated')))
    return dict(path=str(path), manifest_sha256=sha(manifest_path), integrity=checked,
        dropped_samples=manifest['dropped_samples'], phase_rows=dict(phases), excluded=dict(excluded),
        measurements_by_segment=[summarize(g) for g in segments(observations)],
        # Sparse source-bound writes are not the full 60 Hz executor trace.
        writes_by_segment=[summarize(g) for g in segments(writes)], confirmed_writes=len(writes),
        sampled_distinct_packet_intervals_ms=distribution(intervals),
        SDK_age_at_confirmed_write_ms=distribution(ages), computation_to_confirmed_write_ms=distribution(latencies),
        first_N_success=None, activation_time_s=None, launch_time_s=None,
        limitation='No hotkey/gear/throttle timeline in this schema; sparse writes cannot certify full execution maxima.')


def replay_report(path):
    doc = json.loads(path.read_text(encoding='utf-8'))
    rows = doc.get('samples', []); reasons = Counter(); missing = 0; observations = []
    if doc.get('sample_kind') == 'passive_phase_timing':
        usable = [r for r in rows if r.get('identity_matches') and r.get('packet_available')]
        normalized = [dict(time_s=r.get('monotonic_s'),
            identity=dict(identity(r), authority_revision=r.get('revision')),
            phase='active' if r.get('autopilot_active') else 'inactive_unclassified',
            reference='passive timing', original=r) for r in usable]
        return dict(path=str(path), sha256=sha(path), kind='passive_phase_timing', samples=len(rows),
            identity=doc.get('identity'), usable_identity_bound_packets=len(usable),
            packet_missing_rows=sum(not r.get('packet_available') for r in rows),
            excluded_identity_or_packet_rows=len(rows)-len(usable),
            timing_gap_limit_s=1.0,
            timing_by_segment=[dict(identity=g[0]['identity'], phase=g[0]['phase'],
                samples=len(g), duration_s=g[-1]['time_s']-g[0]['time_s'],
                metrics=timing_summary([r['original'] for r in g]))
                for g in segments(normalized, gap_s=1.0)],
            active_rows=sum(bool(r.get('autopilot_active')) for r in rows),
            verdict='NOT VERIFIED' if not usable else 'MEASUREMENT_ONLY')
    for r in rows:
        if r.get('authority_rejection'):
            reasons[r['authority_rejection']] += 1
        missing += bool(r.get('autopilot_active') and not r.get('packet_binding_valid'))
    executions = doc.get('execution_samples', [])
    unique = {}; bound_execution = []; execution_trace = []; packet_intervals = []; last_packet = None
    invalid_source_rows = 0
    for e in executions:
        s = e.get('source_packet')
        if not isinstance(s, dict) or not e.get('executor_active'):
            execution_trace.append(dict(time_s=None))
            continue
        if s.get('authority_valid') is False or s.get('valid') is False:
            invalid_source_rows += 1
            execution_trace.append(dict(time_s=None))
            observations.append(dict(time_s=None))
            last_packet = None
            continue
        key = json.dumps(identity(s), sort_keys=True), s.get('calculation_sequence')
        if key not in unique:
            unique[key] = s
            observations.append(source_measurement(s, 'active'))
            now = s.get('computed_at')
            if last_packet and key[0] == last_packet[0] and finite(now) and finite(last_packet[1]):
                dt = now-last_packet[1]
                if 0 < dt <= .5:
                    packet_intervals.append(dt*1000)
            last_packet = key[0], now
        elif unique[key] != s:
            raise ValueError('CONFLICTING_IMMUTABLE_SOURCE_PACKET')
        bound_execution.append(dict(time_s=e.get('execution_monotonic_s'), identity=identity(s),
            phase='active', reference='executor output (backend write unverified)',
            steer=e.get('output'), cte_m=None, heading_rad=None, saturated=None,
            progress_m=s.get('tracking_progress_m')))
        execution_trace.append(bound_execution[-1])
    return dict(path=str(path), sha256=sha(path), identity=doc.get('identity'), samples=len(rows),
        immutable_execution_samples=len(bound_execution), legacy_unbound_execution_samples=len(executions)-len(bound_execution),
        invalid_immutable_source_rows=invalid_source_rows,
        execution_segments=[summarize(g) for g in segments(execution_trace)],
        source_measurement_segments=[summarize(g) for g in segments(observations)],
        distinct_submitted_packet_intervals_ms=distribution(packet_intervals),
        rejection_rows=dict(reasons), active_invalid_binding_rows=missing,
        automatic_disable_artifacts=int(doc.get('reason') == 'automatic_disable'),
        automatic_disable_reason=(doc.get('identity') or {}).get('detail') if doc.get('reason') == 'automatic_disable' else None,
        first_N_success=None, activation_time_s=None, launch_time_s=None,
        limitation='Executor trace is not physical write confirmation. Submission intervals omit unsubmitted packets and gaps >500ms. Empty rejection fields do not prove absence of faults. Legacy mutable headers never bind an applied command.')


def log_report(path, start, end, build):
    """Extract only control-boundary fields from a caller-selected log window."""
    fields = ('sequence', 'monotonic_s', 'sdk_frame_us', 'observed_gear',
              'observed_speed_mps', 'autopilot_active', 'action', 'reason',
              'selector_write', 'backend_mode', 'steering_command',
            'throttle_command', 'brake_command', 'route_revision',
              'route_build_id', 'vehicle_observation_at',
              'vehicle_observation_valid', 'vehicle_observation_age_s')
    boundaries, events = [], []
    with path.open(encoding='utf-8', errors='replace') as handle:
        for line in handle:
            if len(line) > 65536:
                continue
            try:
                wall = datetime.strptime(line[:23], '%Y-%m-%d %H:%M:%S,%f')
            except ValueError:
                continue
            if not start <= wall <= end:
                continue
            if 'Drive boundary: ' in line:
                try:
                    value = ast.literal_eval(line.split('Drive boundary: ', 1)[1].strip())
                except (ValueError, SyntaxError):
                    continue
                if isinstance(value, dict) and value.get('route_build_id') == build:
                    boundaries.append(dict(wall_time=wall.isoformat(),
                        **{k:value.get(k) for k in fields}))
            elif 'Hotkey N ->' in line or 'Autopilot automatically disabled:' in line:
                events.append(dict(wall_time=wall.isoformat(), message=line.split('] ', 1)[-1].strip()))
    return dict(path=str(path), sha256=sha(path), window_start=start.isoformat(),
        window_end=end.isoformat(), route_build_id=build, boundaries=boundaries, events=events,
        limitation='Hotkey messages have no route identity: association is only the selected wall-time window. SDK gear is not selector position; missing manual pedal data cannot be inferred.')


def simulation_reports(matrix=False):
    from tools.run_steering_bench import cases, independent_matrix_cases
    from tests.steering_bench import path, run
    reports = {}
    scenarios = list(cases())
    scenarios += [(f'turn90_{sign}',path([(0.,40.),(sign/35,35*math.pi/2),(0.,80.)]),
                   dict(speed=7.4,noisy=True,jitter=True)) for sign in (-1,1)]
    if matrix:
        scenarios += list(independent_matrix_cases(False))
    for name,data,options in scenarios:
        existing, rows = run(data, **options)
        normalized = [dict(time_s=r['t'], phase='active_simulated', identity=name,
            reference='plant rear axle (observation_ahead_m=0)', cte_m=r['cte'],
            heading_rad=r['h'], steer=r['out'], progress_m=r['s'],
            saturated=abs(r['raw'])>=1.) for r in rows]
        reports[name] = dict(metrics=summarize(normalized), existing_benchmark=existing,
            trailer_metrics=(summarize([dict(time_s=r['t'], identity=name,
                phase='active_simulated', reference='synthetic trailer point (8 m model)',
                cte_m=r['trailer_cte'], heading_rad=None, steer=None, progress_m=r['s'])
                for r in rows]) if options.get('trailer') else None),
            simulation_parameters={k: ({'callable':v.__qualname__,
                'source':'tests/fixtures/steering-20260816.json'} if callable(v) else v)
                for k,v in options.items()}, geometry=dict(sections_boundaries_m=data['boundaries'],
            total_length_m=data['distance'][-1], points=len(data['points'])),
            missing_telemetry_packet_latencies=True,
            control_rejected_samples=sum(r.get('authority_valid') is False for r in rows))
    return reports


def environment():
    versions = {}
    for p in sorted((ROOT/'plugins').glob('*/main.py')):
        tree = ast.parse(p.read_text(encoding='utf-8-sig'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(isinstance(t,ast.Name) and t.id=='VERSION' for t in node.targets):
                if isinstance(node.value,ast.Constant): versions[p.parent.name]=node.value.value
    paths = ['core/navigation/route.py','core/lateral_controller.py','core/engine.py',
             'core/steering_dynamics.py','plugins/map/main.py','plugins/autopilot/main.py',
             'tests/steering_bench.py','tests/fixtures/steering-20260816.json']
    settings = ROOT/'settings.json'
    config = json.loads(settings.read_text(encoding='utf-8')) if settings.exists() else {}
    # Record only control-specific config, not profile paths/other user data.
    allowed = ('steering_lock_rad','steering_smoothness','transmission_mode',
               'transmission_mode_override','navigation_source','target_speed','fps')
    return dict(commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        plugin_versions=versions, source_sha256={p:sha(ROOT/p) for p in paths},
        repository_settings_sha256=sha(settings) if settings.exists() else None,
        selected_repository_settings={section:{k:v for k,v in value.items() if k in allowed}
            for section,value in config.items() if isinstance(value,dict)},
        repository_transmission_preference=config.get('transmission_mode_preference'),
        config_limitation='Repository settings do not prove installed or historical configuration.',
        SDK_freshness_limit_s=.5)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--simulate',action='store_true')
    parser.add_argument('--matrix',action='store_true')
    parser.add_argument('--collection',action='append',type=Path,default=[])
    parser.add_argument('--replay',action='append',type=Path,default=[])
    parser.add_argument('--log',type=Path)
    parser.add_argument('--log-start',type=datetime.fromisoformat)
    parser.add_argument('--log-end',type=datetime.fromisoformat)
    parser.add_argument('--log-build')
    args=parser.parse_args(argv)
    if args.log and not (args.log_start and args.log_end and args.log_build):
        parser.error('--log requires explicit --log-start, --log-end and --log-build')
    output=args.output.resolve()
    if not output.is_relative_to(ROOT): parser.error('Output must remain in the workspace')
    result=dict(schema_version=1,environment=environment(),
        methodology='Per-identity/per-state/per-reference segments; gap>500ms or non-monotonic time splits. Missing channels remain null.',
        simulations=simulation_reports(args.matrix) if args.simulate else {},
        collections=[collection_report(p) for p in args.collection],
        replays=[replay_report(p) for p in args.replay],
        log=log_report(args.log,args.log_start,args.log_end,args.log_build) if args.log else None)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(output=str(output),simulations=len(result['simulations']),
        collections=len(result['collections']),replays=len(result['replays'])),indent=2))


if __name__=='__main__':
    main()
