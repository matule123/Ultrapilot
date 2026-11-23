"""Receipt/immutable incident timeline. Read-only against original evidence."""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

from core.steering_replay import inspect_replay
from tools.prepare_oct17_joint_candidate import RUNTIME

ROOT=Path(__file__).resolve().parents[1]
INSTALL=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')
OUT=ROOT/'docs/steering-audit/oct18-joint-handoffs'


def digest(raw):return hashlib.sha256(raw).hexdigest()


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    entry=OUT/'entry.json'
    if entry.exists():raise ValueError('Preserve original entry evidence')
    receipt=(INSTALL/'manual-deployment.json').read_bytes();base=json.loads(receipt.decode('utf-8-sig'))
    verified=[]
    for item in base['files']:
        target=Path(item['target']);raw=target.read_bytes()
        assert digest(raw)==item['sha256'].lower(),str(target)
        relative=item.get('relative_path') or (target.relative_to(INSTALL).as_posix()
            if target.is_relative_to(INSTALL) else 'external-ETS2/'+target.name)
        source=ROOT/relative
        verified.append(dict(path=relative,sha256=digest(raw),normalized_equal=source.exists()
            and source.read_bytes().replace(b'\r\n',b'\n')==raw.replace(b'\r\n',b'\n')))
    with zipfile.ZipFile(OUT/'entry-runtime.zip','x',zipfile.ZIP_DEFLATED) as archive:
        for name in RUNTIME:archive.writestr(name,(ROOT/name).read_bytes())
    inventories=[]
    for path in sorted((INSTALL/'route-diagnostics').glob('*20261018T11*.json')):
        result=inspect_replay(path);assert result['integrity_valid'],path.name
        data=result['replay'];block=data.get('longitudinal') or {}
        (OUT/path.name).write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
        first=block.get('first_intervention')
        events=block.get('events',[]);h=block.get('decision_history') or {}
        history=sorted(h.get('regular_samples',[])+h.get('changes',[]),key=lambda r:r.get('monotonic_s',0.))
        # Full expanded packets remain in the ignored decoded copy. The tracked
        # analytical output is a bounded original-field timeline, not inferred times.
        rows=[]
        for e in events:
            s=e.get('source') or {};request=s.get('requested') or {}
            rows.append(dict(sequence=e.get('sequence'),at=e.get('call_started_at_s'),
                returned=e.get('call_returned_at_s'),channel=e.get('channel'),value=e.get('requested_value'),
                backend=e.get('backend'),decision_sequence=s.get('decision_sequence'),
                decision_started=s.get('decision_started_at_s'),context=s.get('context'),
                sdk_frame_us=s.get('sdk_frame_us'),observation_timestamp=s.get('observation_timestamp'),
                observed_gear=s.get('observed_gear'),speed=s.get('actual_speed_mps'),
                requested={k:request.get(k) for k in ('source','computed_at','expires_at','observation_timestamp','deadline_basis','refresh_protocol','refresh_evidence')},
                selected=s.get('selected'),input_read_timing=s.get('input_read_timing'),
                forward_history=s.get('forward_history'),service_hold=s.get('service_hold'),launch=s.get('launch'),
                traffic_producer_runtime=s.get('traffic_producer_runtime')))
        summary=dict(file=path.name,sha256=digest(path.read_bytes()),integrity_valid=True,
            identity=data.get('identity'),sample_kind=data.get('sample_kind'),samples=data.get('sample_count'),
            first_intervention=first,detail_incomplete=block.get('snapshot_incomplete'),
            dropped_events=block.get('dropped_events'),history_status={k:v for k,v in h.items() if k not in ('regular_samples','changes')},
            history=history,writes=rows)
        (OUT/(path.stem+'-timeline.json')).write_text(json.dumps(summary,indent=2),encoding='utf-8')
        inventories.append({k:summary[k] for k in ('file','sha256','sample_kind','samples','first_intervention','detail_incomplete','dropped_events')})
        print(path.name,summary['sample_kind'],len(events),len(history),
            (first or {}).get('reason'),flush=True)
    entry.write_text(json.dumps(dict(head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(),
        receipt_sha256=digest(receipt),receipt=base,installed=verified,evidence=inventories),indent=2),encoding='utf-8')


if __name__=='__main__':main()
