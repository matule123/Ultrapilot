"""Read-only late-evening evidence extraction. Does not arm or control anything."""
import hashlib,json,zipfile
from pathlib import Path
from core.steering_replay import inspect_replay

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/steering-audit/oct16-green-restart'
INSTALL=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')


def main():
    from tools.prepare_oct16_native_owner_runtime import base
    names=tuple(dict.fromkeys((*base.RUNTIME,'plugins/autopilot/main.py',
        'core/transmission_mode.py','plugins/map/main.py','core/planner.py')))
    OUT.mkdir(parents=True,exist_ok=True)
    sha=lambda b:hashlib.sha256(b).hexdigest()
    snapshot=OUT/'entry-runtime.zip'
    if not snapshot.exists():
        with zipfile.ZipFile(snapshot,'x',zipfile.ZIP_DEFLATED) as z:
            for name in names:z.writestr(name,(ROOT/name).read_bytes())
    receipt=json.loads((INSTALL/'manual-deployment.json').read_text(encoding='utf-8-sig'))
    checked=[]
    for row in receipt['files']:
        target=Path(row['target']);data=target.read_bytes()
        checked.append(dict(path=str(target),sha256=sha(data),
            receipt_match=sha(data)==row['sha256'].lower()))
    source=[]
    for name in names:
        current=(ROOT/name).read_bytes(); deployed=(INSTALL/name).read_bytes()
        source.append(dict(path=name,source_sha256=sha(current),installed_sha256=sha(deployed),
            normalized_equal=current.replace(b'\r\n',b'\n')==deployed.replace(b'\r\n',b'\n')))
    installation_record=OUT/('installed-current.json' if (OUT/'installed.json').exists() else 'installed.json')
    installation_record.write_text(json.dumps(dict(receipt=checked,source=source,
        receipt_sha256=sha((INSTALL/'manual-deployment.json').read_bytes())),indent=2),encoding='utf-8')
    print('installed',len(checked),'receipt matches',all(r['receipt_match'] for r in checked),
          'source differences',[r['path'] for r in source if not r['normalized_equal']])
    for path in sorted((INSTALL/'route-diagnostics').glob('steering-*20261016T19*.json')):
        info=inspect_replay(path)
        if not info['integrity_valid']:raise ValueError('Corrupt original: '+str(path))
        v=info['replay']
        (OUT/path.name).write_text(json.dumps(v),encoding='utf-8')
        h=(v.get('longitudinal') or {}).get('decision_history') or {}
        rows=sorted(h.get('regular_samples',[])+h.get('changes',[]),key=lambda x:x['monotonic_s'])
        print(json.dumps(dict(file=path.name,sha256=sha(path.read_bytes()),keys=list(v),
            identity=v.get('identity'),rows=len(rows),range=[rows[0]['monotonic_s'],rows[-1]['monotonic_s']] if rows else None,
            first=(v.get('longitudinal') or {}).get('first_intervention'),
            sample_keys=list(v['samples'][0]) if v.get('samples') else None),default=str))


def summary():
    """Only immutable original/decoded evidence, no guessed longitudinal input."""
    result={}
    directory=INSTALL/'route-diagnostics'
    names=('steering-replay-20261016T193501.314781Z-automatic_disable.json',
           'steering-replay-20261016T193659.223930Z-automatic_disable.json',
           'steering-replay-20261016T193700.658891Z-automatic_disable.json')
    for name in names:
        path=directory/name;checked=inspect_replay(path)
        if not checked['integrity_valid']:raise ValueError('Invalid evidence: '+name)
        value=checked['replay'];longitudinal=value.get('longitudinal') or {}
        history=longitudinal.get('decision_history') or {}
        rows=sorted(history.get('regular_samples',[])+history.get('changes',[]),key=lambda r:r['monotonic_s'])
        entry=dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(),integrity_valid=True,
            decision_history_rows=len(rows),history_range_s=[rows[0]['monotonic_s'],rows[-1]['monotonic_s']] if rows else None,
            detailed_write_count=len(longitudinal.get('events',[])),
            first_intervention=longitudinal.get('first_intervention'))
        if rows and rows[-1]['monotonic_s']<31060.:
            keys=('monotonic_s','sdk_frame_us','observation_timestamp','speed_mps','gear',
                'signal_id','signal_color','signal_generation','signal_frame_us','signal_observed_at',
                'signal_time_left_s','stop_target','selected_source','requested_throttle','requested_brake',
                'acc_throttle','acc_brake','control_target_kmh','speed_control_reason',
                'written_throttle','written_brake','hold_phase','hold_brake')
            entry['terminal_rows']=[{k:r.get(k) for k in keys} for r in rows if r['monotonic_s']>=31058.5]
            entry['actual_write_tail']=[{k:r.get(k) for k in ('sequence','channel','requested_value',
                'call_started_at_s','call_returned_at_s','call_returned','error','last_successful_pair_after')}
                for r in longitudinal.get('events',[])]
        samples=value.get('samples',[])
        if samples:
            def distance(row):
                x,z=row['observation_xz'];return (x-34859.18)**2+(z-45366.03)**2
            usable=[r for r in samples if r.get('observation_xz')]
            point=min(usable,key=distance)
            keys=('monotonic_s','observation_xz','speed_kmh','tracking_progress_m','lane_id',
                'local_k_per_m','preview_k_per_m','navigation_intent_id','revision','route_build_id')
            entry['matching_spatial_sample']={k:point.get(k) for k in keys}
            entry['affected_sdk_rows']=[{k:r.get(k) for k in keys} for r in samples
                if 31119.<=r['monotonic_s']<=31135.]
            executions=value.get('execution_samples',[])
            entry['non_null_executor_source_packets']=sum(r.get('source_packet') is not None for r in executions)
            entry['execution_rows']=len(executions)
        result[name]=entry
    target=OUT/'evidence-summary.json'
    target.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(str(target.resolve()))


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--summary-only',action='store_true');args=parser.parse_args()
    summary() if args.summary_only else main()
