"""Read-only stage 2 analysis of source-bound control and diagnostic timing.

No backend, game control, collector arm or deployment. Detailed outputs must
remain in the workspace. A sampled read is never labelled first delivery.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.analyze_phase6_stage1 import (distribution, finite, identity,
    sha, source_measurement, summarize, collection_report, replay_report)
from core.navigation.evidence_diagnostics import inspect_collection


def phase(source, start, stop):
    t = source.get('observation_timestamp')
    if not finite(t) or t < start:
        return 'launch_or_inactive'
    if t >= stop:
        return 'controlled_stop_or_manual'
    lane = (source.get('lane_match_snapshot') or {}).get('active_lane_id') or {}
    uid = lane.get('road_uid')
    if uid in (5337536178973708447, 5337536093791584855):
        return 'approach'
    if uid == 5337536180190062103 and lane.get('connector_path') == [2, 5, 6]:
        return 'entry'
    if uid in (5337536095347671845, 5337536092906588896,
               5337536180898893020, 5337536096723407576):
        return 'circulation'
    if uid in (5337536179565107919, 5337536096979258520):
        return 'exit_approach_only'
    if (uid == 5337536179162457633 and lane.get('direction') == 1
            and lane.get('lane_index') == 1 and lane.get('connector_path') == [4, 6, 2, 5]):
        return 'exit_connector'
    if uid in (5337536093846112063, 5337536179200201307, 5337536093166633263,
               5337536111176974397, 5337536110279393342, 5337536092877246909,
               5337536093137294876, 5337536095175708374, 5337536182924768567):
        return 'after_exit'
    return 'unclassified'


def analyze(collection, replay_path, timing_path, build, start, stop):
    checked = inspect_collection(collection)
    if checked.get('integrity_valid') is not True:
        raise ValueError('INVALID_COLLECTION_INTEGRITY')
    manifest = json.loads((collection/'manifest.json').read_text(encoding='utf-8'))
    root_doc = json.loads((collection/'automatic-observations.json').read_text(encoding='utf-8'))
    rows = root_doc.get('samples', [])
    if root_doc.get('chunked'):
        rows = []
        for entry in manifest['files']:
            if entry.get('role') == 'chunk' and entry['name'].startswith('automatic-observations'):
                rows.extend(json.loads((collection/entry['name']).read_text(encoding='utf-8'))['records'])
    replay = json.loads(replay_path.read_text(encoding='utf-8'))
    timing = json.loads(timing_path.read_text(encoding='utf-8'))
    packets = {}; excluded_sources = Counter()
    for e in replay.get('execution_samples', []):
        s = e.get('source_packet')
        execution_at = e.get('execution_monotonic_s')
        if (not isinstance(s, dict) or s.get('route_build_id') != build
                or not e.get('executor_active') or not finite(execution_at)
                or not start <= execution_at < stop):
            continue
        if (s.get('authority_valid') is False or s.get('valid') is False
                or any(v is None for v in identity(s).values())
                or not finite(s.get('observation_timestamp'))
                or not finite(s.get('computed_at'))
                or type(s.get('calculation_sequence')) is not int
                or type(s.get('sdk_frame_us')) is not int or s['sdk_frame_us'] <= 0):
            excluded_sources['invalid_or_incomplete_source'] += 1
            continue
        key = (json.dumps(identity(s), sort_keys=True), s.get('calculation_sequence'))
        if key in packets and packets[key] != s:
            raise ValueError('CONFLICTING_IMMUTABLE_SOURCE')
        packets[key] = s
    observations = {}; speed = {}; phase_counts = Counter()
    selected = []
    ordered = sorted(packets.values(), key=lambda s:s['computed_at'])
    exit_connector_seen = False
    completed_exit = False
    for s in ordered:
        ph = phase(s, start, stop)
        exit_connector_seen |= ph == 'exit_connector'
        lane = (s.get('lane_match_snapshot') or {}).get('active_lane_id') or {}
        if (exit_connector_seen and lane.get('road_uid') == 5337536093846112063
                and lane.get('direction') == 1 and lane.get('lane_index') == 1):
            completed_exit = True
    def classified(s):
        ph = phase(s, start, stop)
        if completed_exit and ph in ('exit_approach_only', 'exit_connector'):
            return 'exit'
        return ph
    for s in ordered:
        ph = classified(s)
        phase_counts[ph] += 1
        if ph in ('launch_or_inactive', 'controlled_stop_or_manual'):
            continue
        selected.append(s)
        observations.setdefault(ph, []).append(source_measurement(s, ph))
        speed.setdefault(ph, []).append(s.get('observation_speed_ms'))
    active_identities = {json.dumps(identity(s), sort_keys=True) for s in selected}
    if len(active_identities) > 1:
        raise ValueError('AMBIGUOUS_ACTIVE_ROUTE_IDENTITY')
    intervals = []
    for a, b in zip(selected, selected[1:]):
        dt = b['computed_at'] - a['computed_at']
        if identity(a) == identity(b) and dt > 0:
            intervals.append(dt*1000)  # Include long gaps; never censor >500 ms.
    phases = {ph: dict(measurement=summarize(v), speed_mps=distribution(speed[ph]))
              for ph, v in observations.items()}
    all_observations = [source_measurement(s, 'active') for s in selected]
    writes = []; ages = []; latencies = []; excluded = Counter(); write_phases = {}
    for r in rows:
        e = r.get('executor') or {}; s = e.get('source_packet') or {}
        if (s.get('route_build_id') != build or not r.get('autopilot_active')
                or not start <= r['captured_at_s'] < stop):
            excluded['outside_active_build_or_window'] += 1; continue
        t = (r.get('steering_boundary') or {}).get('steering_write_returned_at_s')
        value = r.get('engine_steer')
        if (not r.get('backend_sent') or not r.get('command_binding_proven')
                or not finite(t) or not finite(value) or not finite(e.get('output'))
                or abs(value-e['output']) > 1e-12
                or json.dumps(identity(s), sort_keys=True) not in active_identities):
            excluded['unbound_physical_write'] += 1; continue
        age = t-s['observation_timestamp']
        ages.append(age*1000); latencies.append((t-s['computed_at'])*1000)
        if not 0 <= age <= .5:
            excluded['stale_write_source'] += 1; continue
        w = dict(time_s=t, identity=identity(s), phase='active',
            reference='sampled confirmed backend steering', steer=value,
            progress_m=s.get('tracking_progress_m'), cte_m=None, heading_rad=None)
        writes.append(w)
        write_phases.setdefault(classified(s), []).append(w)
    phase_times = {}; read_ages = []; receipt_count = 0; read_count = 0
    fields = {
        'lane_update_ms': ('map_tick_started_at','map_lane_update_finished_at'),
        'presentation_ms': ('map_lane_update_finished_at','map_presentation_finished_at'),
        'road_type_ms': ('map_presentation_finished_at','map_road_type_finished_at'),
        'reference_ms': ('map_road_type_finished_at','map_reference_finished_at'),
        'controller_ms': ('map_calculation_started_at','computed_at'),
        'publish_ms': ('map_packet_publish_started_at','map_packet_publish_completed_at')}
    seen = set()
    for r in timing['samples']:
        if (not r.get('identity_matches') or r.get('route_build_id') != build
                or not r.get('packet_available')):
            continue
        key = r.get('calculation_sequence')
        if not start <= r['monotonic_s'] < stop:
            continue
        read_count += 1
        t = r.get('autopilot_packet_read_finished_at')
        if finite(t) and finite(r.get('observation_timestamp')):
            read_ages.append(1000*(t-r['observation_timestamp']))
        if finite(r.get('map_packet_publish_completed_at')):
            receipt_count += 1
            phase_times.setdefault('publish_to_sampled_read_ms', []).append(
                1000*(t-r['map_packet_publish_completed_at']))
        if key in seen:
            continue
        seen.add(key)
        for name, (a,b) in fields.items():
            if finite(r.get(a)) and finite(r.get(b)) and r[b] >= r[a]:
                phase_times.setdefault(name, []).append(1000*(r[b]-r[a]))
    return dict(integrity=checked, manifest_sha256=sha(collection/'manifest.json'),
        replay_sha256=sha(replay_path), timing_sha256=sha(timing_path),
        build=build, active_handoff_at_s=start, first_fault_at_s=stop,
        dropped_samples=manifest.get('dropped_samples'), packet_phase_counts=dict(phase_counts),
        excluded_sources=dict(excluded_sources),
        active_source_packets=len(selected), active_measurements=summarize(all_observations),
        phases=phases, sampled_writes=summarize(writes), sampled_write_count=len(writes),
        sampled_writes_by_phase={k:summarize(v) for k,v in write_phases.items()},
        excluded_writes=dict(excluded), submitted_intervals_ms=distribution(intervals),
        submitted_intervals_above_500ms=sum(x>500 for x in intervals),
        sdk_age_at_confirmed_write_ms=distribution(ages),
        sdk_age_at_confirmed_write_above_500ms=sum(x>500 for x in ages),
        computation_to_confirmed_write_ms=distribution(latencies),
        timing_phases={k:distribution(v) for k,v in phase_times.items()},
        timing_sampled_reads=read_count, timing_receipts=receipt_count,
        age_at_sampled_read_ms=distribution(read_ages),
        completed_exit=('MEASURED_NAVIGATED_EXIT_TO_FOLLOWING_ROAD' if completed_exit else 'NOT MEASURED'),
        limitation='Sparse writes do not establish full 60 Hz maxima. Timing reads are sampled, not first delivery. Phases are specific to these proven LaneIds. Paused/manual samples do not count as active CTE; no obstacle clearance is measured.',
        stage1_collection=collection_report(collection), stage1_replay=replay_report(replay_path))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--collection', type=Path, required=True)
    p.add_argument('--replay', type=Path, required=True)
    p.add_argument('--timing', type=Path, required=True)
    p.add_argument('--build', required=True)
    p.add_argument('--handoff-at', type=float, required=True)
    p.add_argument('--fault-at', type=float, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if not a.output.resolve().is_relative_to(ROOT):
        p.error('Output must remain in the workspace')
    result = analyze(a.collection, a.replay, a.timing, a.build, a.handoff_at, a.fault_at)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('stage1_collection','stage1_replay')},indent=2))


if __name__ == '__main__':
    main()
