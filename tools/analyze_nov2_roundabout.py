"""Read original Nov 2 evening evidence without changing runtime or captures."""
import json
from collections import Counter
from pathlib import Path
from core.steering_replay import inspect_replay, inspect_incident
from core.acc_following import observation
from core.navigation.traffic_producer import TrafficCapture

ROOT = Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot\route-diagnostics')
OUT = Path(__file__).resolve().parents[1] / 'docs/steering-audit/nov2-roundabout'


def compact(value):
    return json.dumps(value, default=lambda v: '<bytes:%d>' % len(v) if isinstance(v, bytes) else str(v))


def main():
    OUT.mkdir(exist_ok=True, parents=True)
    report = []
    for suffix in ('8703', '11926'):
        mainfile = ROOT / ('incident-acc09d754db347859ee0a83944db6d9a-' + suffix + '.json')
        checked = inspect_incident(mainfile)
        meta = {k: v for k, v in checked.items() if k not in ('dossier', 'replay')}
        dossier = checked.get('dossier') or {}
        print('INCIDENT', suffix, compact(meta)[:5000])
        print('DOSSIER_KEYS', list(dossier))
        print('DOSSIER_META', compact({k: dossier.get(k) for k in ('complete', 'incomplete', 'component_completeness', 'episode', 'first_reason')})[:5000])
        files = dossier.get('files') or []
        print('FILES', compact(files)[:2500])
        replay_name = next(r['name'] for r in files if r['name'].startswith('steering-replay-') and r['name'].endswith('diagnostic_incident.json'))
        replay = inspect_replay(ROOT / replay_name)
        incident = replay['replay']['longitudinal']['diagnostic_incident']
        rows = incident['records']
        print('KINDS', compact(Counter(r['kind'] for r in rows)))
        print('WINDOW', compact({k: incident.get(k) for k in ('range_s', 'capture_failures', 'capacity_drops', 'sampling', 'autopilot_part_result')})[:5000])
        samples = []
        for row in rows:
            if not 8424 < row['at_s'] < 8447:
                continue
            if row['kind'] in ('consumer_traffic', 'consumer_acc'):
                packet = row['value'].get('packet') or {}
                if row['kind'] == 'consumer_traffic':
                    following = packet.get('following') or {}
                    crossing = following.get('crossing') or {}
                    conflicts = [c for c in crossing.get('conflicts', []) if str(c.get('id')) == '61']
                    samples.append(dict(kind=row['kind'], at_s=row['at_s'], sequence=row['sequence'],
                        following_status=following.get('status'), target=following.get('target_id'),
                        source=following.get('source_acquisition'), conflicts=conflicts,
                        body_prediction=following.get('body_prediction'),
                        owner_witnesses=following.get('owner_witnesses'),
                        constraint_completion=following.get('constraint_completion'),
                        retained_target_continuity=following.get('retained_target_continuity'),
                        motion_constraint=packet.get('motion_constraint')))
                else:
                    samples.append(dict(kind=row['kind'], at_s=row['at_s'], sequence=row['sequence'],
                        valid=packet.get('valid'), reason=packet.get('invalid_reason'),
                        target=packet.get('following_target_id'), evidence=packet.get('target_evidence')))
            if row['kind'] == 'traffic':
                value = row['value']
                capture = value.get('capture') or {}
                source = capture.get('source') or {}
                observed = observation(TrafficCapture(capture['session'], capture['receiver_time_s'],
                    capture['moving'], capture['parked'], capture['stable'], source), row['at_s'])
                samples.append(dict(kind='native_actor', at_s=row['at_s'], sequence=row['sequence'],
                    source={k:source.get(k) for k in ('lifecycle','generation','frame_us','observed_at','ego_speed_mps','ego_speed_observed_at')},
                    ego={k:(value.get('ego') or {}).get(k) for k in ('x','y','z','rotation','speed')},
                    status=observed.get('status'),
                    actors=[a for a in observed.get('actors', []) if str(a.get('id')) == '61']))
        result = dict(incident=suffix, verification=meta,
            component_completeness=dossier.get('component_completeness'),
            sampling=incident.get('sampling'), samples=samples)
        (OUT / ('analysis-' + suffix + '.json')).write_text(compact(result), encoding='utf-8')
        print('SAMPLE_COUNTS', compact(Counter(r['kind'] for r in samples)))
        native=[s for s in samples if s['kind']=='native_actor' and s['actors']]
        for t in (8428,8429,8430,8431,8431.7,8432,8432.7,8433,8434,8435,8436,8438,8440,8443):
            if native:
                sample=min(native,key=lambda s:abs(s['at_s']-t))
                if abs(sample['at_s']-t) < .2:
                    actor=sample['actors'][0]
                    print('ACTOR61', compact(dict(at_s=sample['at_s'],source=sample['source'],
                        ego=sample['ego'],actor={k:actor[k] for k in ('x','y','z','yaw','speed','slot')})))
        report.append(dict(incident=suffix, verification=meta, sample_count=len(samples)))
    (OUT / 'summary.json').write_text(compact(report), encoding='utf-8')


if __name__ == '__main__':
    main()
