"""Read-only immutable incident audit. No capture, game control or deployment."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess

from core.steering_replay import inspect_replay
from tools.prepare_oct16_crossing_hud import ROOT, RUNTIME


def body_brake_review(rows,events):
    """Recorded native poses plus an explicit, separately labelled model probe."""
    from core.acc_body_prediction import contact_interval
    poses={};probes={}
    for row in rows:
        cause=row.get('traffic_cause') or {}
        actor=cause.get('actor') or {};source=cause.get('source_acquisition') or {}
        if actor.get('id') is None or not source.get('observed_at'):continue
        poses[(actor['id'],source['observed_at'])]=dict(actor=actor,source=source,
            predicted_contact_s=(cause.get('decisive') or {}).get('predicted_contact_s'))
    for event in events or ():
        traffic=((event.get('source') or {}).get('inputs') or {}).get('traffic') or {}
        basis=traffic.get('brake_basis') or {};d=basis.get('decisive') or {};actor=d.get('actor') or {}
        if not d.get('ego_bodies') or actor.get('id') is None:continue
        body={k:actor[k] for k in ('x','y','z','yaw','dimensions_whl')}
        v=actor['speed'];vb=(-math.sin(body['yaw'])*v,-math.cos(body['yaw'])*v)
        ego_speed=d['ego_observed_speed_mps'];root=d['ego_bodies'][0]
        va=(-math.sin(root['yaw'])*ego_speed,-math.cos(root['yaw'])*ego_speed)
        source=basis.get('source_acquisition') or {}
        contacts=[contact_interval(e,body,va,vb,3.) for e in d['ego_bodies']]
        probes[(actor['id'],source.get('observed_at'))]=dict(actor_id=actor['id'],source=source,
            actor_record=actor,ego_bodies=d['ego_bodies'],ego_observed_speed_mps=ego_speed,
            measured_heading_difference_rad=math.remainder(body['yaw']-root['yaw'],2*math.pi),
            recorded_contact_from_source_s=d.get('contact_from_source_observation_s'),
            counterfactual_fixed_heading_contacts_s=contacts,
            limitation='Reuses measured boxes; BOTH ego and actor velocities held at source heading. '
                'NOT the unretained actual directed-reference prediction, lane proof or future vehicle motion.')
    motion=[]
    for aid in sorted({key[0] for key in poses}):
        values=sorted([v for (i,_),v in poses.items() if i==aid],key=lambda v:v['source']['observed_at'])
        for before,after in zip(values,values[1:]):
            dt=after['source']['observed_at']-before['source']['observed_at']
            if (not 0<dt<=.5 or any(before['actor'].get(k)!=after['actor'].get(k) for k in ('source','slot'))
                    or before['source'].get('lifecycle')!=after['source'].get('lifecycle')):continue
            a,b=before['actor'],after['actor']
            motion.append(dict(actor_id=aid,previous_at=before['source']['observed_at'],
                observed_at=after['source']['observed_at'],dt_s=dt,
                observed_position_step_m=math.hypot(b['x']-a['x'],b['z']-a['z']),
                observed_heading_step_rad=math.remainder(b['yaw']-a['yaw'],2*math.pi),
                basis='Consecutive retained native reference poses; no certified incarnation/lane/intent'))
    return dict(original_poses=list(poses.values()),observed_pose_changes=motion,
        explicitly_counterfactual_fixed_heading_box_probes=list(probes.values()))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    installed=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')
    sha=lambda b:hashlib.sha256(b).hexdigest()
    receipt=json.loads((installed/'manual-deployment.json').read_text(encoding='utf-8-sig'))
    files=[dict(path=r['target'],match=sha(Path(r['target']).read_bytes())==r['sha256'].lower())
        for r in receipt['files']]
    norm=lambda b:b.replace(b'\r\n',b'\n')
    controls=Path(r'C:\Users\PC\Documents\Euro Truck Simulator 2\steam_profiles\65726767726D617475736B727532\controls.sii')
    # Exact profile is identified by this session's Engine transmission record
    # and game.log selected-profile path, not guessed from newest mtime.
    configuration=dict(path=str(controls),sha256=sha(controls.read_bytes()),
        mtime_ns=controls.stat().st_mtime_ns,
        relevant_lines=[line.strip() for line in controls.read_text(encoding='utf-8').splitlines()
            if any(token in line for token in ('constant c_brake_dz ','mix abackward ','mix backward ',
                'mix geardrive ','mix gearreverse '))],
        limitation='Current on-disk profile; no controller callback/mixing/gear-transition acknowledgement')
    comparisons=[dict(path=r,source_match=norm((installed/r).read_bytes())==norm((ROOT/r).read_bytes()),
        head_match=norm((installed/r).read_bytes())==norm(subprocess.check_output(['git','show','HEAD:'+r],cwd=ROOT)))
        for r in RUNTIME if (installed/r).exists()]
    results=[]
    for path in sorted((installed/'route-diagnostics').glob('*20261016T13*.json')):
        if not path.name.startswith(('steering-replay-','steering-timing-')):continue
        result=inspect_replay(path)
        if not result['integrity_valid']:raise ValueError((path,result))
        v=result['replay'];l=v.get('longitudinal') or {};h=l.get('decision_history') or {}
        rows=sorted(h.get('regular_samples',[])+h.get('changes',[]),key=lambda r:r['monotonic_s'])
        fields=('monotonic_s','activation','sdk_frame_us','observation_timestamp','gear','speed_mps',
            'acc_target_id','acc_status','traffic_target_id','traffic_target_status','traffic_cause',
            'motion_constraint','traffic_brake','light_brake','acc_brake','acc_throttle','written_brake',
            'written_throttle','selected_source','hold_phase','hold_chain','signal_id','signal_color',
            'signal_valid','signal_lock','stop_target','first_reason')
        results.append(dict(path=str(path),sha256=sha(path.read_bytes()),integrity_valid=True,
            identity=v['identity'],sample_count=v['sample_count'],executions=v['execution_sample_count'],
            kind=v.get('sample_kind'),first=l.get('first_intervention'),
            history={k:h.get(k) for k in ('observed_range_s','incomplete','capture_failures')},
            rows=[{k:r.get(k) for k in fields} for r in rows],events=l.get('events'),
            sample_fields=sorted({k for row in v['samples'] if isinstance(row,dict) for k in row}),
            exact_source_packets=sum(isinstance((e.get('executor') or {}).get('source_packet'),dict)
                for e in v['execution_samples']),body_brake_review=body_brake_review(rows,l.get('events'))))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(dict(head=subprocess.check_output(['git','rev-parse','HEAD']).decode().strip(),
        installed=files,comparisons=comparisons,control_configuration=configuration,replays=results),indent=2),encoding='utf-8')
    print(json.dumps(dict(receipt_files=len(files),all_receipt_matches=all(f['match'] for f in files),
        differences=[r['path'] for r in comparisons if not r['head_match']],
        replays=[dict(path=Path(r['path']).name,rows=len(r['rows']),samples=r['sample_count'],
            first=r['first']) for r in results if r['first']]),indent=2))


if __name__=='__main__':main()
