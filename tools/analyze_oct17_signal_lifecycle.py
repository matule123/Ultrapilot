"""Read-only reconstruction of the 17 October 11:12–11:13 session."""
import hashlib
import json
import csv
from pathlib import Path
import zipfile

from core.steering_replay import inspect_replay

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/steering-audit/oct17-joint-lifecycle'
INSTALL=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')


def main():
    from tools.prepare_oct16_signal_handoff_runtime import base
    OUT.mkdir(parents=True,exist_ok=True)
    sha=lambda data:hashlib.sha256(data).hexdigest()
    names=tuple(dict.fromkeys((*base.RUNTIME,'plugins/autopilot/main.py','plugins/map/main.py',
        'plugins/collision/main.py','core/planner.py','core/perception.py')))
    if not (OUT/'entry-runtime.zip').exists():
        with zipfile.ZipFile(OUT/'entry-runtime.zip','x',zipfile.ZIP_DEFLATED) as archive:
            for name in names:archive.writestr(name,(ROOT/name).read_bytes())
    receipt=json.loads((INSTALL/'manual-deployment.json').read_text(encoding='utf-8-sig'))
    checks=[dict(target=row['target'],match=sha(Path(row['target']).read_bytes())==row['sha256'].lower())
            for row in receipt['files']]
    source=[dict(path=n,sha256=sha((ROOT/n).read_bytes()),installed_sha256=sha((INSTALL/n).read_bytes()),
                 normalized_equal=(ROOT/n).read_bytes().replace(b'\r\n',b'\n')==(INSTALL/n).read_bytes().replace(b'\r\n',b'\n')) for n in names]
    record=dict(receipt_sha256=sha((INSTALL/'manual-deployment.json').read_bytes()),receipt=checks,source=source)
    if not (OUT/'entry-installation.json').exists():
        (OUT/'entry-installation.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    print('Receipt:',len(checks),all(r['match'] for r in checks),'source:',len(source),[r['path'] for r in source if not r['normalized_equal']])
    summary=[]
    for path in sorted((INSTALL/'route-diagnostics').glob('steering-*20261017T09*.json')):
        checked=inspect_replay(path)
        if not checked['integrity_valid']:raise ValueError((path.name,checked))
        data=checked['replay'];block=data.get('longitudinal') or {};history=block.get('decision_history') or {}
        (OUT/path.name).write_text(json.dumps(data),encoding='utf-8')
        rows=sorted(history.get('regular_samples',[])+history.get('changes',[]),key=lambda r:r['monotonic_s'])
        item=dict(file=path.name,sha256=sha(path.read_bytes()),kind=data.get('sample_kind'),integrity_valid=True,
            identity=data.get('identity'),rows=len(rows),row_range=[rows[0]['monotonic_s'],rows[-1]['monotonic_s']] if rows else None,
            event_count=len(block.get('events',[])),sample_count=len(data.get('samples',[])),
            first_intervention=block.get('first_intervention'),significant_event=block.get('significant_event'),
            history_keys=list(rows[-1]) if rows else None,detail_keys=list(block['events'][-1]) if block.get('events') else None,
            sample_keys=list(data['samples'][-1]) if data.get('samples') else None)
        summary.append(item)
        print(path.name,'rows',item['rows'],item['row_range'],'detail',item['event_count'],'dense',item['sample_count'])
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    rows={}; writes={}; sources=[]
    for item in summary:
        data=json.loads((OUT/item['file']).read_text());block=data.get('longitudinal') or {}
        history=block.get('decision_history') or {};identities=history.get('identities',{})
        for row in history.get('regular_samples',[])+history.get('changes',[]):
            rows[row['monotonic_s']]=dict(row,identity=identities.get(row['identity_reference']))
        for event in block.get('events',[]):
            key=(event['sequence'],event['call_started_at_s']);writes[key]=event
            sources.append(dict(file=item['file'],time=event['call_started_at_s'],source=event['source']))
    ordered=sorted(rows.values(),key=lambda r:r['monotonic_s'])
    (OUT/'rows.json').write_text(json.dumps(ordered),encoding='utf-8')
    (OUT/'writes.json').write_text(json.dumps(sorted(writes.values(),key=lambda e:e['call_started_at_s'])),encoding='utf-8')
    (OUT/'sources.json').write_text(json.dumps(sources),encoding='utf-8')
    dense=next(json.loads((OUT/i['file']).read_text()) for i in summary if i['sample_count']>900)
    transitions=[];previous=None
    for row in dense['samples']:
        lane=row.get('lane_id')
        if lane!=previous:
            transitions.append({k:row.get(k) for k in ('monotonic_s','observation_xz','tracking_progress_m','speed_kmh','lane_id','sdk_frame_us','observation_timestamp')})
            previous=lane
    (OUT/'lane-transitions.json').write_text(json.dumps(transitions,indent=2),encoding='utf-8')
    keys=('monotonic_s','sdk_frame_us','speed_mps','gear','signal_color','signal_time_left_s',
        'selected_source','requested_throttle','requested_brake','acc_throttle','acc_brake',
        'control_target_kmh','speed_control_reason','hold_phase','hold_brake','written_throttle','written_brake',
        'sdk_game_throttle','sdk_game_brake','sdk_user_throttle','sdk_user_brake','traffic_target_status')
    with (OUT/'timeline.csv').open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=(*keys,'stop_distance_m'))
        writer.writeheader()
        for row in ordered:
            writer.writerow(dict({k:row.get(k) for k in keys},stop_distance_m=(row.get('stop_target') or {}).get('distance')))
    last=-1
    for row in ordered:
        if int(row['monotonic_s'])==last:continue
        last=int(row['monotonic_s']);target=row.get('stop_target') or {}
        print('t %.3f v %.2f gear %s %s d %s target %s pedal %s/%s game %s/%s hold %s ctrl %s'%(
            row['monotonic_s'],row.get('speed_mps') or 0,row.get('gear'),row.get('signal_color'),
            target.get('distance'),row.get('control_target_kmh'),row.get('written_throttle'),row.get('written_brake'),
            row.get('sdk_game_throttle'),row.get('sdk_game_brake'),row.get('hold_phase'),row.get('speed_control_reason')))


if __name__=='__main__':main()
