"""Read-only Oct16 immutable evidence/installed content audit; no new capture."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from core.steering_replay import inspect_replay
from tools.prepare_oct16_crossing_hud import RUNTIME,ROOT


def sha(data):return hashlib.sha256(data).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();installation=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')
    receipt_raw=(installation/'manual-deployment.json').read_bytes()
    receipt=json.loads(receipt_raw.decode('utf-8-sig'))
    installed=[]
    for row in receipt['files']:
        installed.append(dict(target=row['target'],sha256=sha(Path(row['target']).read_bytes()),
            receipt_match=sha(Path(row['target']).read_bytes())==row['sha256'].lower()))
    comparisons=[]
    for relative in RUNTIME:
        path=installation/relative
        if not path.exists():continue
        deployed=path.read_bytes();current=(ROOT/relative).read_bytes()
        baseline=subprocess.check_output(['git','show','0ed435f:'+relative],cwd=ROOT)
        norm=lambda b:b.replace(b'\r\n',b'\n')
        comparisons.append(dict(path=relative,installed_sha256=sha(deployed),
            matches_starting_head_normalized=norm(deployed)==norm(baseline),
            matches_candidate_normalized=norm(deployed)==norm(current)))
    files=[];incident=None
    directory=installation/'route-diagnostics'
    paths=list(directory.glob('steering-replay-20261016T*.json'))+list(directory.glob('steering-timing-20261016T*.json'))
    for path in sorted(paths):
        inspected=inspect_replay(path)
        if not inspected['integrity_valid']:raise ValueError((str(path),inspected))
        value=inspected['replay'];longitudinal=value.get('longitudinal') or {}
        history=longitudinal.get('decision_history') or {}
        rows=sorted(history.get('regular_samples',[])+history.get('changes',[]),key=lambda r:r['monotonic_s'])
        item=dict(path=str(path),sha256=sha(path.read_bytes()),integrity_valid=True,
            confirmed=False,runtime_authorized=False,samples=value['sample_count'],
            execution_samples=value['execution_sample_count'],identity=value['identity'],
            exact_execution_source_packets=sum(isinstance((e.get('executor') or {}).get('source_packet'),dict)
                for e in value['execution_samples']),history_rows=len(rows),
            history_range=history.get('observed_range_s'),history_incomplete=history.get('incomplete'),
            history_capture_failures=history.get('capture_failures'),
            qualified_signal_history_rows=sum(r.get('signal_valid') is True for r in rows),
            sample_kind=value.get('sample_kind'),
            sample_field_names=sorted({key for r in value['samples'] if isinstance(r,dict) for key in r}),
            original_actor_array_retained=False)
        files.append(item)
        if longitudinal:
            keys=('monotonic_s','sequence','sdk_frame_us','observation_timestamp','speed_mps','gear',
                'activation','command_sequence','selected_source','speed_control_reason','constrained_speed_kmh',
                'traffic_brake','acc_brake','acc_throttle','written_brake','written_throttle',
                'traffic_target_id','traffic_target_status','motion_constraint','traffic_cause',
                'signal_id','signal_valid','signal_color','stop_target','hold_phase')
            incident=dict(first_intervention=longitudinal.get('first_intervention'),
                preceding_significant_event_receipt=longitudinal.get('preceding_significant_event_receipt'),
                last_4s_rows=[{k:r.get(k) for k in keys} for r in rows
                    if r['monotonic_s']>=rows[-1]['monotonic_s']-4.],
                confirmed_backend_events=[dict(sequence=e['sequence'],channel=e.get('channel'),
                    backend=e.get('backend'),source=e.get('source'),
                    game_consumption_verified=False) for e in longitudinal.get('events',[])])
    result=dict(installed_receipt_sha256=sha(receipt_raw),installed_files=installed,
        content_comparison=comparisons,replays=files,incident=incident,
        limitation='No rejected original actor array, no earlier exact red pedal chain; no historical cause inferred from reconstructed model')
    a.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(receipt_files=len(installed),all_receipt_hashes_match=all(r['receipt_match'] for r in installed),
        replays=[{k:v for k,v in f.items() if k not in ('identity','path','sha256')} for f in files]),indent=2))


if __name__=='__main__':main()
