"""Read-only latest Oct 11 lifecycle evidence; no inferred pedal/stop-line data."""
import argparse
import hashlib
import json
from pathlib import Path
from core.steering_replay import inspect_replay
from tools.recover_steering_route import recover, profiles


def analyze(root):
    names = ('steering-replay-20261011T071453.485201Z-automatic_disable.json',
        'steering-replay-20261011T071453.034423Z-automatic_disable.json',
        'steering-timing-20261011T071505.960559Z-plugin_stop.json')
    receipts = []; decoded=[]
    for name in names:
        path=root/'route-diagnostics'/name
        check=inspect_replay(path)
        if not check['integrity_valid']: raise ValueError((name,check))
        replay=check['replay'];decoded.append(replay)
        receipts.append(dict(file=name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            integrity_valid=True,samples=replay['sample_count'],executions=replay['execution_sample_count']))
    dense,pedal,timing=decoded
    rows=[r for r in dense['samples'] if r.get('packet_binding_valid')]
    geometry=recover(rows)
    curve=profiles(rows,geometry,80.)['rows']
    # Analysis windows selected by actual speed trace, not by invented source
    # chronology. Calculation speed is an explicitly named application proxy.
    braking=[r for r in rows if 2734.5<r['application_monotonic_s']<2735.2]
    forecast=[r for r in curve if 2734.5<r['application_at']<2735.2]
    stopped=[r for r in rows if 2650<r['application_monotonic_s']<2710 and r['speed_kmh']<.2]
    history=pedal['longitudinal']['decision_history']
    return dict(artifacts=receipts,calculation_identity=rows[0]['calculation_trajectory_identity'],
        measured_geometry=dict(points=len(geometry['points']),
            maximum_projection_residual_m=geometry['maximum_projection_residual_m'],
            warning='Measured contiguous prefix only; no unseen final vertices or painted line.'),
        stopped_band=dict(samples=len(stopped),start_s=stopped[0]['application_monotonic_s'],
            end_s=stopped[-1]['application_monotonic_s'],
            progress_min_m=min(r['tracking_progress_m'] for r in stopped),
            progress_max_m=max(r['tracking_progress_m'] for r in stopped),
            controlling_head_and_stop_target='NOT_RETAINED'),
        braking_band=dict(samples=len(braking),start_s=braking[0]['application_monotonic_s'],
            end_s=braking[-1]['application_monotonic_s'],
            first_speed_kmh=braking[0]['speed_kmh'],last_speed_kmh=braking[-1]['speed_kmh'],
            first_progress_m=braking[0]['tracking_progress_m'],last_progress_m=braking[-1]['tracking_progress_m'],
            lane_id=braking[0]['lane_id'],
            reconstructed_curve_cap_min_kmh=min(r['curve_only_target_kmh'] for r in forecast),
            speed_provenance='Application speed proxy; not substituted as proven calculation-frame speed',
            physical_brake_producer='NOT_RETAINED'),
        pedal_history_range=history['observed_range_s'],
        first_intervention=pedal['longitudinal']['first_intervention'],
        gps_distance_at_removal='NOT_RETAINED; log does not distinguish zero from <=25m branch',
        last_row={k:rows[-1][k] for k in ('application_monotonic_s','application_sdk_frame_us',
            'calculation_sdk_frame_us','tracking_progress_m','speed_kmh')},
        exported_success_verification=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot'))
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=analyze(a.root)
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
