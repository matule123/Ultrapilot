"""Read-only Oct 8 evidence audit; decoded incidents, exact times, no game I/O.

Pedal events are physical backend-return witnesses, not game consumption.
Timing is sampled consumer reading, not first packet delivery. Dense speed and
progress come from distinct application/calculation frames and stay labelled.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.steering_replay import inspect_replay

NAMES = (
    'steering-replay-20261008T175542.756248Z-automatic_disable.json',
    'steering-replay-20261008T175542.842441Z-automatic_disable.json',
    'steering-replay-20261008T180328.669987Z-manual_disable.json',
    'steering-replay-20261008T180632.932802Z-automatic_disable.json',
    'steering-replay-20261008T180633.064412Z-automatic_disable.json',
    'steering-timing-20261008T175745.836124Z-plugin_stop.json',
    'steering-timing-20261008T180708.035308Z-plugin_stop.json')


def distribution(values):
    a=sorted(v for v in values if isinstance(v,(int,float)) and math.isfinite(v))
    if not a:return dict(count=0)
    def percentile(p):
        i=(len(a)-1)*p; low=int(i); high=min(low+1,len(a)-1)
        return a[low]+(a[high]-a[low])*(i-low)
    return dict(count=len(a),median=statistics.median(a),p95=percentile(.95),maximum=a[-1])


def analyze(installation, names=NAMES, log_from=None):
    out=dict(records=[],clock='original Windows monotonic seconds',methodology=__doc__)
    for name in names:
        path=installation/'route-diagnostics'/name
        checked=inspect_replay(path)
        if checked.get('integrity_valid') is not True:raise ValueError(f'invalid integrity: {name}')
        r=checked['replay'];record=dict(name=name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            integrity_valid=True,identity=r['identity'],samples=len(r['samples']),
            execution_samples=len(r['execution_samples']))
        l=r.get('longitudinal')
        if l:
            h=l['decision_history'];rows=sorted(h['regular_samples']+h['changes'],key=lambda r:r['sequence'])
            record.update(first_intervention=l.get('first_intervention'),
                history_metadata={k:v for k,v in h.items() if k not in ('regular_samples','changes','identities')},
                detailed_metadata={k:l.get(k) for k in ('dropped_events','snapshot_incomplete','retained_bytes')},
                history_last_decisions=rows[-10:],detailed_events=l['events'])
            record['history_first_decision'] = rows[0] if rows else None
        elif 'timing-' in name:
            rows=[x for x in r['samples'] if x.get('identity_matches') and x.get('computed_at')
                  and x.get('map_packet_publish_completed_at') and x.get('sdk_frame_us')]
            def delta(a,b):return distribution([(x[a]-x[b])*1000 for x in rows
                if x.get(a) is not None and x.get(b) is not None])
            record.update(paired_samples=len(rows),observation_age_ms=delta('autopilot_packet_read_finished_at','observation_timestamp'),
                map_precalculation_ms=delta('map_calculation_started_at','map_lane_update_finished_at'),
                publish_to_sampled_read_ms=delta('autopilot_packet_read_finished_at','map_packet_publish_completed_at'))
        else:
            record['immutable_execution_source_packets']=sum(bool(x.get('source_packet')) for x in r['execution_samples'])
            record['sampled_range_s'] = [r['samples'][0].get('application_monotonic_s'),
                                        r['samples'][-1].get('application_monotonic_s')] if r['samples'] else []
            runs=[];run=[]
            for row in r['samples']:
                valid=(row.get('autopilot_active') and row.get('packet_binding_valid')
                    and row.get('application_trajectory_identity')==row.get('calculation_trajectory_identity')
                    and 3. <= row.get('speed_kmh',float('nan')) <= 4.)
                if run and (not valid or row['monotonic_s']-run[-1]['monotonic_s']>.5
                    or row.get('application_trajectory_identity')!=run[-1].get('application_trajectory_identity')):
                    runs.append(run);run=[]
                if valid:run.append(row)
            if run:runs.append(run)
            record['crawl_sampled_sections']=[dict(count=len(run),
                application_started_at=run[0]['application_monotonic_s'],
                application_ended_at=run[-1]['application_monotonic_s'],
                application_duration_s=run[-1]['application_monotonic_s']-run[0]['application_monotonic_s'],
                calculation_progress_delta_m=run[-1]['tracking_progress_m']-run[0]['tracking_progress_m'],
                original_calculation_frames=[run[0]['calculation_sdk_frame_us'],run[-1]['calculation_sdk_frame_us']],
                application_frames=[run[0]['application_sdk_frame_us'],run[-1]['application_sdk_frame_us']],
                reference_point='recorded LanePath tracking progress, not front/painted stop line')
                for run in runs if len(run)>1]
        out['records'].append(record)
    # Search only this day's preserved log; previous crashes are not evidence.
    path=installation/'ultrapilot.log';oct8=False;crash=[];events=[]
    with path.open(encoding='utf-8',errors='replace') as stream:
        for line in stream:
            if line.startswith('2026-10-08 '):oct8=not log_from or line[:19]>=log_from
            elif line.startswith('2026-') and not line.startswith('2026-10-08 '):oct8=False
            if not oct8:continue
            if any(x in line for x in ('Traceback','Fatal Python','crashed','Unhandled')):crash.append(line.rstrip())
            if any(x in line for x in ('Hotkey N ->','game log changed during read','simple_auto_handoff_complete',
                                       'cancel_drive_engagement','automatically disabled')):events.append(line.rstrip())
    out.update(oct8_crash_lines=crash,log_events=events,log_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    return out


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installation',type=Path,default=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot'))
    parser.add_argument('--record',nargs='+',help='Exact identity-checked capture filenames; defaults to the earlier evening incident')
    parser.add_argument('--log-from',help='Earliest local ISO log timestamp, e.g. 2026-10-08 21:31:00')
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT):parser.error('Output must remain in workspace')
    out=analyze(args.installation,args.record or NAMES,args.log_from)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
    print(json.dumps([dict(name=r['name'],samples=r['samples'],integrity_valid=r['integrity_valid'],
        crawl=r.get('crawl_sampled_sections'),paired=r.get('paired_samples')) for r in out['records']],indent=2))
