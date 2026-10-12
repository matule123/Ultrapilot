"""Read-only receipts and decoded evidence for the Oct 11 12:46-12:50 drive."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.steering_replay import inspect_replay

REPO = Path(__file__).resolve().parents[1]
RUNTIME_FILES = (
    'core/acc_following.py','core/engine.py','core/longitudinal.py',
    'core/navigation/longitudinal_diagnostics.py','core/plugin_manager.py',
    'plugins/acc/main.py','plugins/turnsignals/main.py',
)


def longitudinal_summary(block):
    history=block.get('decision_history') or {}
    rows=history.get('regular_samples',[])+history.get('changes',[])
    groups={}
    for row in rows:
        target=row.get('stop_target') or {}
        if row.get('hold_phase')!='holding' or not isinstance(target.get('distance'),(int,float)):
            continue
        key=(row.get('activation'),row.get('identity_reference'),row.get('signal_id'),target.get('passage_key'))
        groups.setdefault(key,[]).append(row)
    holds=[]
    for key,values in groups.items():
        holds.append(dict(activation=key[0],identity_reference=key[1],signal_id=key[2],passage=key[3],
            samples=len(values),start_s=min(v['monotonic_s'] for v in values),
            end_s=max(v['monotonic_s'] for v in values),
            sdk_reference_target_distance_m=[min(v['stop_target']['distance'] for v in values),
                                            max(v['stop_target']['distance'] for v in values)],
            target=values[0]['stop_target'],
            throttle_range=[min(v['throttle'] for v in values),max(v['throttle'] for v in values)],
            brake_range=[min(v['brake'] for v in values),max(v['brake'] for v in values)]))
    lead=[r for r in rows if r.get('acc_target_id')=='29']
    return dict(first_intervention=block.get('first_intervention'),
        detail={k:block.get(k) for k in ('retained_bytes','byte_budget','dropped_events',
            'field_capture_failures','snapshot_incomplete','detail_evidence')},
        history={k:v for k,v in history.items() if k not in ('regular_samples','changes','aggregate_tail')},
        hold_sections=holds,lead_29=dict(samples=len(lead),
            start_s=min((r['monotonic_s'] for r in lead),default=None),
            end_s=max((r['monotonic_s'] for r in lead),default=None)),
        changes=[{k:r.get(k) for k in ('monotonic_s','sdk_frame_us','observation_timestamp','activation',
            'identity_reference','phase','speed_mps','gear','signal_id','signal_color','stop_target',
            'acc_target_id','acc_status','throttle','brake','reason')} for r in history.get('changes',[])])


def analyze(root, output):
    if not output.resolve().is_relative_to(REPO):
        raise ValueError('analytical output must stay in this workspace; originals are read-only')
    output.mkdir(parents=True, exist_ok=True)
    receipt = json.loads((root/'manual-deployment.json').read_text(encoding='utf-8-sig'))
    files = []
    for entry in receipt['files']:
        target, source = Path(entry['target']), Path(entry['source'])
        installed = target.read_bytes()
        normalized = lambda b: b.replace(b'\r\n', b'\n')
        files.append(dict(path=str(target), receipt_match=hashlib.sha256(installed).hexdigest().lower()==entry['sha256'].lower(),
            source_match=source.exists() and normalized(source.read_bytes())==normalized(installed)))
    names = ['steering-replay-20261011T104938.211656Z-automatic_disable.json',
             'steering-replay-20261011T104936.895268Z-automatic_disable.json',
             'steering-replay-20261011T104747.073445Z-manual_disable.json',
             'steering-timing-20261011T105004.392237Z-plugin_stop.json']
    artifacts=[]
    for index, name in enumerate(names):
        path=root/'route-diagnostics'/name
        check=inspect_replay(path)
        if not check['integrity_valid']: raise ValueError((name,check))
        replay=check['replay']
        (output/f'decoded-{index}.json').write_text(json.dumps(replay),encoding='utf-8')
        summary=dict(name=name, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            integrity_valid=True, samples=replay.get('sample_count'), execution_samples=replay.get('execution_sample_count'),
            keys=list(replay))
        long=replay.get('longitudinal') or {}
        if long:
            summary['longitudinal']=longitudinal_summary(long)
        artifacts.append(summary)
    quota=list((root/'route-diagnostics').glob('*significant_event*.json'))
    candidates=[]
    for name in RUNTIME_FILES:
        source,installed=(REPO/name).read_bytes(),(root/name).read_bytes()
        normalized=lambda b:b.replace(b'\r\n',b'\n')
        candidates.append(dict(path=name,source_sha256=hashlib.sha256(source).hexdigest(),
            installed_sha256=hashlib.sha256(installed).hexdigest(),
            source_normalized_sha256=hashlib.sha256(normalized(source)).hexdigest(),
            installed_normalized_sha256=hashlib.sha256(normalized(installed)).hexdigest(),
            content_equal=normalized(source)==normalized(installed)))
    (output/'runtime-candidate.json').write_text(json.dumps(dict(files=candidates,
        installation_written=False,dll_required=False),indent=2),encoding='utf-8')
    result=dict(deployment_at=receipt.get('deployed_at_utc'),versions={k:v for k,v in receipt.items() if k.endswith('_version')},
        files=files,artifacts=artifacts,significant_events=dict(files=len(quota),bytes=sum(p.stat().st_size for p in quota)))
    (output/'audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(deployed=result['deployment_at'], receipts=sum(f['receipt_match'] for f in files),
        mismatched_sources=[f['path'] for f in files if not f['source_match']],
        artifacts=[{k:v for k,v in a.items() if k!='longitudinal'} for a in artifacts], quota=result['significant_events']),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot'))
    p.add_argument('--output',type=Path,default=Path('docs/steering-audit/oct11-regressions'))
    a=p.parse_args();analyze(a.root,a.output)
