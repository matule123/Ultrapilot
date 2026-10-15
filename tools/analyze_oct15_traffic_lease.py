"""Read-only native traffic lease incident decoding; no installed writes."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from core.steering_replay import inspect_replay

def analyze():
    install=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')
    output=ROOT/'docs/steering-audit/oct15-traffic-lease';output.mkdir(parents=True,exist_ok=True)
    sha=lambda b:hashlib.sha256(b).hexdigest()
    receipt=json.loads((install/'manual-deployment.json').read_text(encoding='utf-8-sig'))
    checks=[]
    for row in receipt['files']:
        p=Path(row['target']);actual=p.read_bytes()
        name=str(p.relative_to(install)).replace('\\','/') if p.is_relative_to(install) else 'game-plugin/ets2la_plugin.dll'
        source=ROOT/name
        committed = subprocess.run(['git','show','HEAD:'+name],cwd=ROOT,capture_output=True)
        checks.append(dict(path=name,receipt_matches=sha(actual)==row['sha256'].lower(),
            source_head_normalized_matches=(committed.stdout.replace(b'\r\n',b'\n')==actual.replace(b'\r\n',b'\n')
                                            if committed.returncode==0 else None),
            source_normalized_matches=source.read_bytes().replace(b'\r\n',b'\n')==actual.replace(b'\r\n',b'\n') if source.exists() else None))
    package=ROOT/'docs/steering-audit/oct14-roundabout/ultrapilot-oct14-roundabout-candidate-v5.zip'
    with zipfile.ZipFile(package) as archive:
        manifest=json.loads(archive.read('candidate-manifest.json'))
        for row in manifest['files']:
            if row['path'].startswith('game-plugin/'):
                p=next(Path(r['target']) for r in receipt['files'] if Path(r['target']).name=='ets2la_plugin.dll' and not Path(r['target']).is_relative_to(install))
            else:p=install/row['path'].removeprefix('runtime/')
            assert sha(p.read_bytes())==row['sha256']==sha(archive.read(row['path'])),row['path']
    records=[]; decoded=[]
    for name in ('steering-replay-20261015T043038.167087Z-automatic_disable.json',
                 'steering-replay-20261015T043039.383315Z-automatic_disable.json'):
        path=install/'route-diagnostics'/name;checked=inspect_replay(path)
        replay=checked.pop('replay');assert checked['integrity_valid']
        decoded.append(replay)
        (output/(path.stem+'-decoded.json')).write_text(json.dumps(replay),encoding='utf-8')
        records.append(dict(path=str(path),sha256=sha(path.read_bytes()),**checked,
            identity=replay.get('identity'),first=(replay.get('longitudinal') or {}).get('first_intervention')))
    pedal, dense = decoded
    block = pedal['longitudinal']; fault = block['first_intervention']; detail = fault['details']
    check = detail['checked_at']; basis = detail['deadline_basis']
    history = block['decision_history']
    recent = sorted((r for r in history['regular_samples']+history['changes']
                     if check-.9 <= r['monotonic_s'] <= check+.2), key=lambda r:r['monotonic_s'])
    map_ticks = {}
    for sample in dense['samples']:
        tick = sample.get('previous_map_tick_timing') or {}
        if tick.get('started_at') is not None and check-.25 <= tick['started_at'] <= check:
            map_ticks[tick['tick_sequence']] = tick
    timeline = dict(first_fault=fault,
        deadline_budget_ms=dict(traffic_observation_to_command_observation=1000*(detail['observation_timestamp']-basis['observation_timestamp']),
            command_observation_to_computation=1000*(detail['computed_at']-detail['observation_timestamp']),
            remaining_at_computation=1000*(detail['expires_at']-detail['computed_at']),
            computation_to_final_check=1000*(check-detail['computed_at']),
            overrun=1000*(check-detail['expires_at'])),
        evidence_limits=['Original traffic packet/capture, its generation, publication and first receipt not retained at this fault',
            'Summary timestamps are decision completion samples, not physical-write timestamps',
            'Map timing records are sampled completed ticks, not an exhaustive packet delivery stream',
            'Fault top-level vehicle is later than the rejected command; not used to establish comparison freshness'],
        recent_summary=[{k:r.get(k) for k in ('monotonic_s','command_sdk_frame_us','command_observation_timestamp',
            'command_computed_at','command_expires_at','selected_source','reason','throttle','brake','control_state')}
            for r in recent],
        completed_map_ticks=sorted(map_ticks.values(),key=lambda t:t['started_at']),
        safety_writes=[{k:e.get(k) for k in ('sequence','channel','requested_value','call_started_at_s','call_returned_at_s','backend')}
                       for e in block['events']],
        detail_evidence=block['detail_evidence'],history_evidence={k:history[k] for k in
            ('observed_range_s','incomplete','capture_failures','regular_dropped_capacity','change_dropped_capacity')})
    (output/'timeline.json').write_text(json.dumps(timeline,indent=2),encoding='utf-8')
    summary=dict(head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(),
        receipt={k:v for k,v in receipt.items() if k not in ('files','changed_files')},
        installed_checks=checks,package_sha256=sha(package.read_bytes()),records=records)
    (output/'incident-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))

if __name__=='__main__':analyze()
