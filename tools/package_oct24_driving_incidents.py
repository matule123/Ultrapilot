"""Preserve Oct24 evidence and produce one dossier per intervention.

Offline only: no runtime changes, no new capture, no game/controller imports.
Integrity proves stored bytes, not completeness or actual game consumption.
"""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.steering_replay import inspect_replay

APP=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')
ATTACHMENT=Path(r'C:\Users\PC\.codex\attachments\3f6f8a3b-6a18-4f8a-8b5e-e0bd38a0d279\Vložený text.txt')
OUTPUT=ROOT/'docs/steering-audit/oct24-driving-incidents'
CASES=(
    ('01-201154-gps','20:11:54',43293.0899805,'GPS cieľ/revízia',None),
    ('02-201351-acc42','20:13:51',43409.8352861,'ACC cieľ 42','42'),
    ('03-201435-hold','20:14:35',43454.0447587,'Pohyb počas držania brzdy',None),
    ('04-201522-acc39','20:15:22',43501.2854872,'ACC cieľ 39','39'),
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path,data):
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')


def case_for(time_s,cases=CASES,tolerance=.15):
    matches=[row[0] for row in cases if isinstance(time_s,(int,float)) and abs(row[2]-time_s)<=tolerance]
    if len(matches)>1:raise ValueError('Ambiguous incident assignment')
    return matches[0] if matches else None


def unique(rows):
    # Deduplicate only byte-equivalent JSON records. Same sequence with different
    # fields remains separate evidence, not an arbitrarily selected version.
    seen=set();result=[]
    for row in rows:
        key=json.dumps(row,sort_keys=True,ensure_ascii=False,separators=(',',':'))
        if key not in seen:result.append(row);seen.add(key)
    return result


def main():
    OUTPUT.mkdir(exist_ok=False);raw=OUTPUT/'raw';raw.mkdir()
    shutil.copy2(ATTACHMENT,raw/'user-log.txt')
    # Preserve this full app session without copying the 243 MB historic log.
    with open(APP/'ultrapilot.log',encoding='utf-8',errors='replace') as source, \
            open(raw/'app-session.log','w',encoding='utf-8') as target:
        active=False
        for line in source:
            if line.startswith('2026-10-24 20:01:42'):active=True
            if active:target.write(line)
    for name in ('settings.json','manual-deployment.json'):
        shutil.copy2(APP/name,raw/name)
    game=Path(r'C:\Users\PC\Documents\Euro Truck Simulator 2')
    for name in ('game.log.txt','game.crash.txt'):
        shutil.copy2(game/name,raw/name)
    receipt=json.loads((raw/'manual-deployment.json').read_text(encoding='utf-8-sig'))
    installed=[]
    for entry in receipt['files']:
        target=Path(entry['target']);actual=sha(target)
        if actual!=entry['sha256'].lower():raise ValueError('Installed receipt drift: '+str(target))
        local=target.relative_to(APP).as_posix() if target.is_relative_to(APP) else 'game/'+target.name
        source=ROOT/local
        installed.append(dict(path=local,sha256=actual,
            workspace_normalized_equal=(source.is_file() and source.read_bytes().replace(b'\r\n',b'\n')
                                        ==target.read_bytes().replace(b'\r\n',b'\n'))))
    with zipfile.ZipFile(raw/'installed-runtime.zip','x',zipfile.ZIP_DEFLATED) as archive:
        for entry,checked in zip(receipt['files'],installed):
            archive.write(entry['target'],checked['path'])
        # Include dependency source that may not be listed in the manual receipt.
        seen={entry['path'].casefold() for entry in installed}
        for folder in ('core','plugins','sdk','ui'):
            for path in (APP/folder).rglob('*.py'):
                name=path.relative_to(APP).as_posix()
                if name.casefold() not in seen:archive.write(path,name);seen.add(name.casefold())
    buckets={row[0]:dict(spec=row,replays=[],blocks=[],steering=[]) for row in CASES}
    inventory=[]
    paths=sorted((APP/'route-diagnostics').glob('steering-*-20261024T18*.json'))
    for path in paths:
        saved=raw/path.name;shutil.copy2(path,saved)
        if sha(path)!=sha(saved):raise ValueError('Copy changed: '+path.name)
        check=inspect_replay(saved)
        if not check['integrity_valid']:raise ValueError('Replay integrity: '+path.name+' '+check.get('reason',''))
        replay=check['replay'];block=replay.get('longitudinal') or {}
        first=block.get('first_intervention') or (replay.get('identity') or {}).get('control_intervention') or {}
        incident=case_for(first.get('observed_at'))
        summary=dict(file=path.name,sha256=sha(saved),integrity_valid=True,
            incident_id=incident,sample_kind=replay.get('sample_kind'),
            sample_count=replay.get('sample_count'),execution_sample_count=replay.get('execution_sample_count'),
            history_incomplete=check.get('history_incomplete'),incomplete=check.get('incomplete'),
            first_intervention=first if first else None)
        inventory.append(summary)
        if incident:
            buckets[incident]['replays'].append(summary)
        blocks=[]
        if block:blocks.append(block)
        preceding=block.get('preceding_significant_event')
        if preceding:blocks.append(preceding)
        # Significant events can predate the first fault. Share by the actual
        # stored monotonic window, not by file creation timestamps.
        for key,bucket in buckets.items():
            fault=bucket['spec'][2]
            for item in blocks:
                history=item.get('decision_history') or {}
                rows=history.get('regular_samples',[])+history.get('changes',[])
                events=item.get('events',[])
                selected_rows=[r for r in rows if fault-30<=r.get('monotonic_s',-1)<=fault+5]
                selected_events=[e for e in events if fault-30<=e.get('call_started_at_s',-1)<=fault+5]
                if selected_rows or selected_events or incident==key:
                    bucket['blocks'].append(dict(file=path.name,history=selected_rows,events=selected_events,
                        first_intervention=item.get('first_intervention'),
                        history_identities=history.get('identities'),
                        capture_flags={k:item.get(k) for k in ('snapshot_incomplete','dropped_events',
                            'detail_evidence','field_capture_failures','event_capture_status')},
                        history_flags={k:v for k,v in history.items() if k not in ('regular_samples','changes','identities')}))
            for sample in replay.get('samples',[]):
                if fault-30<=sample.get('monotonic_s',-1)<=fault+5:
                    keep=('monotonic_s','sdk_frame_us','application_sdk_frame_us','observation_timestamp',
                        'observation_xz','lane_id','speed_ms','speed_mps','autopilot_active','authority_rejection',
                        'route_build_id','revision','navigation_intent_id','packet_binding_valid','packet_binding_reasons')
                    bucket['steering'].append({k:sample[k] for k in keep if k in sample})
    manifests=[]
    for key,bucket in buckets.items():
        _,wall,fault,title,target=bucket['spec']
        rows=unique([r for block in bucket['blocks'] for r in block['history']])
        rows.sort(key=lambda r:(r.get('monotonic_s',0),r.get('sequence',0)))
        events=unique([e for block in bucket['blocks'] for e in block['events']])
        events.sort(key=lambda e:e.get('call_started_at_s',0))
        firsts=unique([r['first_intervention'] for r in bucket['replays'] if r['first_intervention']])
        if not firsts:raise ValueError('No fault witness for '+key)
        speeds=[r['speed_mps']*3.6 for r in rows if isinstance(r.get('speed_mps'),(int,float))]
        packet_rejections=[dict(producer=f.get('producer'),reason=f.get('reason'),
            target_id=(f.get('details') or {}).get('following_target_id'),
            observation_age_s=(f.get('details') or {}).get('observation_age_s'),
            decision_age_s=(f.get('details') or {}).get('decision_age_s'),
            lease_overrun_s=(f.get('details') or {}).get('lease_overrun_s'),
            target_evidence=(f.get('details') or {}).get('target_evidence')) for f in firsts]
        case=dict(schema=1,incident_id=key,local_wall_time=wall,monotonic_s=fault,title=title,
            kind='technical_intervention_not_necessarily_complete_stop',target_id=target,
            requested_window_s=[fault-30,fault+5],
            actual_history_range_s=[rows[0]['monotonic_s'],rows[-1]['monotonic_s']] if rows else None,
            speed_kmh_range=[min(speeds),max(speeds)] if speeds else None,
            raw_replay_references=bucket['replays'],first_interventions=firsts,
            rejection_summary=packet_rejections,decision_history=rows,pedal_calls=events,
            steering_context=unique(bucket['steering']),capture_blocks=bucket['blocks'],
            completeness=dict(full_scene_available=False,original_full_actor_arrays_confirmed=False,
                backend_write_is_not_game_consumption=True,
                omission_flags_preserved=True,unknowns_not_reconstructed=True),
            source_state='historical_evidence_not_a_fix',game_verified=False)
        write(OUTPUT/(key+'.json'),case)
        text=f'# {wall} — {title}\n\n'
        text+='Doložený bezpečnostný zásah; presný dôvod odmietnutia nie je automaticky prvotná príčina.\n\n'
        text+='\n'.join('- '+str(f.get('producer'))+': '+str(f.get('reason')) for f in firsts)
        text+=f'\n\nHistória: {len(rows)} vzoriek; detailné pedálové volania: {len(events)}.\n'
        text+='Úplná fyzická scéna a všetky pôvodné actor polia nie sú potvrdené. Pozri JSON a príznaky neúplnosti.\n'
        (OUTPUT/(key+'.md')).write_text(text,encoding='utf-8')
        manifests.append(dict(id=key,time=wall,title=title,target=target,
            history_rows=len(rows),pedal_calls=len(events),speed_kmh_range=case['speed_kmh_range']))
    log=(raw/'user-log.txt').read_text(encoding='utf-8-sig')
    quota=[line.strip() for line in log.splitlines() if 'SIGNIFICANT_EVENT_EXPORT_DISK_QUOTA' in line]
    write(OUTPUT/'index.json',dict(schema=1,incidents=manifests,replays=inventory,
        installed=installed,quota_failure_log_entries=quota,phase='1 evidence preservation / incomplete capture audit',
        sources_modified=False,runtime_modified=False,new_capture_armed=False,
        raw_files=[dict(file=p.name,sha256=sha(p),bytes=p.stat().st_size) for p in sorted(raw.iterdir())]))
    print(json.dumps(dict(output=str(OUTPUT),incidents=manifests,replays=len(inventory),
        all_replay_integrities_valid=True,verified_receipt_files=len(installed),
        workspace_differences=[r['path'] for r in installed if not r['workspace_normalized_equal']],
        quota_log_entries=len(quota),runtime_modified=False),indent=2,ensure_ascii=False))


if __name__=='__main__':main()
