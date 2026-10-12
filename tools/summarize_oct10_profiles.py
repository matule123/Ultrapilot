"""Summarize paired offline flow profiles without joining separate runs.

Quantiles are empirical floor(q*(n-1)); only raw within-run intervals and
confirmed mapping-write measurements are pooled. Inclusive operation quantiles
are retained per run, never averaged or summed as a whole-flow CPU duration.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.analyze_oct9_packet_flow import distribution


def overlap(events, start, end):
    return [dict(generation=e['generation'], thread_id=e.get('thread_id'),
                 duration_s=e['duration_s']) for e in events
            if e.get('started_at', end+1) < end and e.get('completed_at', start-1) > start]


def summarize(paths):
    runs = []
    intervals, ages, latency = [], [], []
    phases = {k: [] for k in ('map_wall_s', 'publication_s', 'after_publication_s',
                              'gap_before_next_map_s', 'lane_update_s', 'reference_s')}
    worst_writes, worst_intervals, gc_times = [], [], []
    for path in paths:
        data = json.loads(path.read_text(encoding='utf-8'))
        packets = data['packets']
        assert len(packets) == len({p['calculation_sequence'] for p in packets})
        assert all(b['calculation_sequence'] == a['calculation_sequence']+1
                   for a, b in zip(packets, packets[1:])), 'Not adjacent packets'
        gc_events = data['gc_events']
        gc_times.extend(e['duration_s'] for e in gc_events)
        spans = {p['calculation_sequence']: t for p, t in zip(packets, data['tick_spans'])}
        for a, b in zip(packets, packets[1:]):
            interval = b['computed_at']-a['computed_at']
            intervals.append(interval)
            worst_intervals.append(dict(run=path.name, interval_s=interval,
                previous_sequence=a['calculation_sequence'], sequence=b['calculation_sequence'],
                sdk_frame_us=b['sdk_frame_us'], span=spans[b['calculation_sequence']],
                gc_overlap=overlap(gc_events, a['computed_at'], b['computed_at'])))
        for write in data['physical_steering_writes']:
            ages.append(write['observation_age_s'])
            latency.append(write['calculation_to_write_s'])
            worst_writes.append(dict(run=path.name, **write,
                source_tick_span=spans[write['calculation_sequence']],
                gc_overlap=overlap(gc_events, write['observation_timestamp'], write['write_started_at'])))
        for p, span in zip(packets, data['tick_spans']):
            phases['map_wall_s'].append(span['map_finished_at']-span['started_at'])
            if span.get('publication_completed_at') is not None:
                phases['publication_s'].append(span['publication_completed_at']-p['map_packet_publish_started_at'])
            if span.get('map_after_publication_s') is not None:
                phases['after_publication_s'].append(span['map_after_publication_s'])
            if span.get('gap_before_map_tick_s') is not None:
                phases['gap_before_next_map_s'].append(span['gap_before_map_tick_s'])
            phases['lane_update_s'].append(p['map_lane_update_finished_at']-p['map_tick_started_at'])
            phases['reference_s'].append(p['map_reference_finished_at']-p['map_lane_update_finished_at'])
        runs.append(dict(file=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            source_replay_sha256=data['replay_sha256'], source_build=data['source_build'],
            cold_dataset_load=data['cold_dataset_load'],
            cold_map_tick=data['operation_profile']['cold_map_tick'],
            cold_steering_observation_age_s=data['cold_steering_observation_age_s'],
            packet_interval_s=data['packet_interval_s'],
            steering_observation_age_at_write_s=data['steering_observation_age_at_write_s'],
            remaining_at_pedal_write_s=data['remaining_at_pedal_write_s'],
            age_at_pedal_write_s=data['age_at_pedal_write_s'],
            topology_cache_accounted_bytes=data['topology_cache_accounted_bytes'],
            concurrent_export_load=data['concurrent_export_load'],
            modeled_evidence_job_ms=data['modeled_evidence_job_ms'],
            faults=data['faults'], producer_failures=data['producer_failures'],
            operation_profile=data['operation_profile']))
    assert len({r['source_replay_sha256'] for r in runs}) == 1
    return dict(runs=runs, packet_interval_s=distribution(intervals),
        steering_observation_age_at_write_s=distribution(ages),
        calculation_to_write_s=distribution(latency),
        phase_distributions={k: distribution(v) for k, v in phases.items()},
        writes_over_500ms=sum(a > .5 for a in ages),
        gc_duration_s=distribution(gc_times),
        worst_writes=sorted(worst_writes, key=lambda x: x['observation_age_s'], reverse=True)[:6],
        worst_intervals=sorted(worst_intervals, key=lambda x: x['interval_s'], reverse=True)[:6])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT): parser.error('Output must stay in workspace')
    result = {v: summarize([args.directory/f'profile-{v}-{i}.json' for i in (1, 2, 3)])
              for v in ('baseline', 'candidate')}
    result['method'] = __doc__
    args.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({v: {k: value for k, value in result[v].items()
                         if k not in ('runs', 'worst_writes', 'worst_intervals')}
                      for v in ('baseline', 'candidate')}, indent=2))
