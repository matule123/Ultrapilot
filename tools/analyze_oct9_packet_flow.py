"""Read-only Oct 9 freshness audit; original packet times are never renewed."""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.steering_replay import inspect_replay


def distribution(values):
    xs = sorted(x for x in values if isinstance(x, (int, float)) and math.isfinite(x))
    if not xs:
        return dict(n=0)
    return dict(n=len(xs), minimum=xs[0], **{name: xs[int(q * (len(xs)-1))] for name, q in
                [('median', .5), ('p95', .95), ('p99', .99), ('max', 1.)]})


def analyze(directory):
    results = []
    for path in sorted(directory.glob('*20261009T19*.json')):
        checked = inspect_replay(path)
        if not checked.get('integrity_valid'):
            # Timing export has its own schema, not the dense replay schema.
            raw = json.loads(path.read_text(encoding='utf-8'))
            results.append(dict(file=path.name, status=checked.get('reason'), keys=list(raw)))
            continue
        data = checked['replay']
        rows = data['samples']
        executions = data['execution_samples']
        keys = sorted({k for r in rows for k in r})
        eligible = [r for r in rows if r.get('packet_binding_valid') is True
            or r.get('identity_matches') is True]
        unique = {r.get('calculation_sequence'):r for r in eligible if r.get('calculation_sequence') is not None}
        packets = sorted(unique.values(), key=lambda r:r['computed_at'])
        def delta(a, b):
            source = rows if a == 'autopilot_packet_read_finished_at' else packets
            return [r[a]-r[b] for r in source if isinstance(r.get(a),(int,float))
                    and isinstance(r.get(b),(int,float))]
        intervals = [b['computed_at']-a['computed_at'] for a,b in zip(packets,packets[1:])]
        worst = sorted([(dt,a.get('calculation_sequence'),b.get('calculation_sequence'))
                        for dt,a,b in zip(intervals,packets,packets[1:])],reverse=True)[:8]
        consecutive = [dt for dt,a,b in zip(intervals,packets,packets[1:])
            if b['calculation_sequence'] == a['calculation_sequence']+1]
        result = dict(file=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            integrity_valid=True,kind=data.get('sample_kind'),samples=len(rows),executions=len(executions),
            keys=keys,first=rows[0] if rows else None,last=rows[-1] if rows else None,
            sampled_unique_packet_gap_s=distribution(intervals),worst_observed_gaps=worst,
            consecutive_calculation_interval_s=distribution(consecutive),
            skipped_sequence_gaps=len(intervals)-len(consecutive),
            cadence_note='Consecutive identified calculations only; repeated/skipped sampled reads do not measure first delivery. Export tail can censor the stall.',
            phases={label:distribution(delta(a,b)) for label,a,b in [
                ('tick_to_lane','map_lane_update_finished_at','map_tick_started_at'),
                ('lane_to_presentation','map_presentation_finished_at','map_lane_update_finished_at'),
                ('presentation_to_road','map_road_type_finished_at','map_presentation_finished_at'),
                ('road_to_reference','map_reference_finished_at','map_road_type_finished_at'),
                ('observation_to_compute','computed_at','observation_timestamp'),
                ('reference_to_compute','map_calculation_started_at','map_reference_finished_at'),
                ('compute_duration','computed_at','map_calculation_started_at'),
                ('publication','map_packet_publish_completed_at','map_packet_publish_started_at'),
                ('sampled_publish_to_read','autopilot_packet_read_finished_at','map_packet_publish_completed_at') ]})
        if 'longitudinal' in data:
            journal=data['longitudinal']
            result['longitudinal_keys']=list(journal)
            result['first_intervention']=journal.get('first_intervention')
            result['last_physical_events']=journal.get('events',[])[-4:]
            result['history_last']=journal.get('decision_history',{}).get('regular_samples',[])[-3:]
        result['last_execution']=executions[-3:]
        results.append(result)
    return results


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if not args.output.resolve().is_relative_to(ROOT):p.error('Output must stay within workspace')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    result=analyze(args.directory)
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    for row in result:
        print(json.dumps({k:v for k,v in row.items() if k in ('file','integrity_valid','samples','executions','consecutive_calculation_interval_s','skipped_sequence_gaps','phases','status')},indent=2))
