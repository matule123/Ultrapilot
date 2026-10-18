"""Read-only lineage and actual immutable timing; never edits the installation."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from core.steering_replay import inspect_replay

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/steering-audit/oct17-systemic-longitudinal'
INSTALL=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')


def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)


def history():
    searches=(('shared pedal arbitration','core/longitudinal.py','def choose('),
        ('deadline refresh and reread','core/longitudinal.py','def refresh_handoff'),
        ('native box prediction','core/acc_body_prediction.py','def predict('),
        ('crossing completion','core/acc_following.py','def crossing_completion('),
        ('approach hold release','core/service_brake_hold.py','def profile_approach_allowed('),
        ('ending green','core/longitudinal.py','ending_green_stop'),
        ('independent SDK/output workers','core/engine.py','def _control_loop('))
    rows=[]
    for label,path,term in searches:
        lines=git('log','--reverse','--format=%H %ad %s','--date=iso-strict','-S',term,'--',path).decode().splitlines()
        rows.append(dict(feature=label,path=path,pickaxe=lines))
        for line in lines[:1]:
            sha=line.split()[0]
            (OUT/(sha[:8]+'-'+Path(path).name+'.diff')).write_bytes(git('show',sha,'--',path))
    (OUT/'history.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    # Materialize only bounded source snapshots for isolated probes. No checkout
    # reset, branch mutation, old worktree edit or historic runtime deployment.
    for ref in ('7adf8c8^','7adf8c8','9350be7','add9a19','5f96e07','a5ca5c4','7f1d5ee'):
        target=OUT/'history-sources'/ref.replace('^','-parent');target.mkdir(parents=True,exist_ok=True)
        for name in ('core/longitudinal.py','core/engine.py','core/acc_following.py',
                     'core/service_brake_hold.py','core/acc_body_prediction.py','plugins/autopilot/main.py'):
            result=subprocess.run(['git','show',ref+':'+name],cwd=ROOT,capture_output=True)
            if result.returncode==0:
                p=target/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(result.stdout)
    return rows


def incident():
    rows=[];events=[];dense=[]
    for p in sorted((INSTALL/'route-diagnostics').glob('*20261017T19*.json')):
        inspected=inspect_replay(p)
        if not inspected['integrity_valid']:raise ValueError(p.name)
        data=inspected['replay'];block=data.get('longitudinal') or {}
        h=block.get('decision_history') or {}
        rows.extend(h.get('regular_samples',[])+h.get('changes',[]))
        events.extend(block.get('events',[]))
        if data.get('sample_kind')=='dense_steering':dense.extend(data['samples'])
    unique={}
    for e in events:
        source=e.get('source') or {};inputs=source.get('inputs') or {}
        for key,value in inputs.items():
            if isinstance(value,dict) and value.get('computed_at'):
                token=(key,value.get('sdk_frame_us'),value['computed_at'])
                unique[token]=dict(source=key,sampled_write_at=e['call_started_at_s'],
                    **{k:value.get(k) for k in ('sdk_frame_us','observation_timestamp','computed_at','expires_at','deadline_basis')})
    last=[r for r in unique.values() if r['source']=='traffic' and r['computed_at']>10477.8]
    sources=sorted(dense,key=lambda r:r.get('application_monotonic_s',0.))
    seen={}
    for r in sources:
        seq=r.get('calculation_sequence')
        if seq is not None and r.get('accepted_packet_observation_timestamp',0.)>10477.6:
            seen.setdefault(seq,{k:r.get(k) for k in ('calculation_sequence','accepted_packet_observation_timestamp',
                'accepted_packet_computed_at','map_tick_started_at','map_reference_finished_at',
                'map_packet_publish_completed_at','autopilot_tick_started_at','autopilot_packet_read_finished_at',
                'application_monotonic_s')})
    result=dict(traffic_sampled_receipts=last,new_map_packets=list(seen.values()),
        limitation='Sampled reads/writes are not first delivery; no Engine main-loop phase/CPU/GC/lock spans exist in this historical export.')
    (OUT/'incident-timing.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


def main():
    OUT.mkdir(exist_ok=True)
    data=dict(history=history(),incident=incident())
    print(json.dumps(data,indent=2))


if __name__=='__main__':main()
