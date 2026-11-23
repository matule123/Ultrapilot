"""Replay original native acquisitions against their own captured Map path."""
from pathlib import Path
import json
import pickle
import math
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/steering-audit/oct29-transition'


def main():
    # Only this task's local exact primitive analysis cache, never an external
    # diagnostic file or runtime deserializer.
    rows=pickle.loads((OUT/'native-analysis-cache.bin').read_bytes())
    ap=pickle.loads((OUT/'ap-analysis-cache.bin').read_bytes())
    packets=[]
    for row in ap['records']:
        for item in row['value']['inputs']:
            v=item['value'];snapshot=v.get('snapshot')
            if item['source']=='consumer_control_locals' and snapshot and snapshot.get('points'):
                packets.append((item['at_s'],snapshot,v))
    from core.acc_following import RouteLeadSelector, observation
    from core.acc_body_prediction import predict
    from core.navigation.traffic_producer import TrafficCapture
    selector=RouteLeadSelector();out=[];previous_binding=None
    for row in rows:
        if row['kind']!='traffic':continue
        value=row['value'];packet=value['packet'];capt=value['capture'];truck=value['ego']
        source=capt.get('source') or {};at=row['at_s']
        binding=packet['context']
        matching=[p for p in packets if p[1].get('route_build_id')==binding[6]
            and p[1].get('revision')==binding[5]]
        if not matching:continue
        nearest=min(matching,key=lambda p:abs(p[0]-at))
        snapshot=nearest[1]
        with patch('time.monotonic',return_value=at):
            raw=TrafficCapture(capt['session'],capt['receiver_time_s'],capt['moving'],capt['parked'],capt['stable'],source)
            observed=observation(raw,at)
            if observed['status'] not in ('observed','empty_unproven_coverage'):continue
            if previous_binding!=binding:
                selector.prepare(snapshot['points'],binding);previous_binding=binding
            saved=packet['following'];progress=(packet.get('signal') or {}).get('route_progress_m')
            if progress is None:continue
            selected=selector.select(observed['actors'],truck,progress,
                receiver_time=observed['receiver_time'],source=observed.get('source'))
            crossing=selector.crossing(observed['actors'],truck,progress)
            body=predict(selector,observed['ego_bodies'],observed['actors'],source['ego_speed_mps'],progress,
                source['ego_anchor'],source_age=at-source['observed_at']) if observed.get('ego_bodies') else None
        out.append(dict(sequence=row['sequence'],at_s=at,source_acquisition=saved.get('source_acquisition'),
            speed_mps=truck['speed'],gear=truck['gear'],ego={k:truck[k] for k in ('x','y','z','rotation')},
            route_build=binding[6],revision=binding[5],progress_m=progress,
            route_snapshot_at=nearest[0],route_snapshot_match='same build/revision; nearest AP consumption, not first Map publication',
            actor_bodies=[a for a in observed['actors'] if a['id'] in (39,51,66)],ego_bodies=observed.get('ego_bodies'),
            original_crossing=saved.get('crossing'),replayed_crossing=crossing,
            original_body=saved.get('body_prediction'),replayed_body=body,
            original_scope=packet.get('motion_constraint'),original_brake=packet['traffic_brake']))
        # Preserve the original actually selected constraint owner between the
        # captured acquisitions; this is not an inferred new ACC acquisition.
        if packet.get('motion_constraint'):
            selector.retain_crossing_target(packet['motion_constraint']['targets'],raw.observed_at)
    (OUT/'prediction-reconstruction.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
    print(json.dumps(dict(rows=len(out),body_contact_rows=sum(bool((r['original_body'] or {}).get('conflicts')) for r in out),
        replay_body_contact_rows=sum(bool((r['replayed_body'] or {}).get('conflicts')) for r in out),
        route_binding_count=len({(r['revision'],r['route_build']) for r in out}))))


if __name__=='__main__':main()
