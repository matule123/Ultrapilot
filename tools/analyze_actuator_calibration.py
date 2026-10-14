"""Passive operating-point identification from existing integrity-checked replay.

No controller settings, game/backend, new collector or automatic gain update.
Fit a = drive_gain*T - brake_gain*B + drift within one identity/gear/load bin.
Drift includes grade/drag: chassis pitch and cargo/unit mass are NOT road grade
or total vehicle mass. A statistical fit is not certified force/brake capacity.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def solve(rows):
    # Weighted least squares with bounded 3x3 normal equations. Fail on rank
    # deficiency instead of inventing the absent drive/brake response.
    matrix = [[sum(dt*x[i]*x[j] for x,y,dt in rows) for j in range(3)] +
              [sum(dt*x[i]*y for x,y,dt in rows)] for i in range(3)]
    scale = max(abs(v) for row in matrix for v in row[:3])
    for i in range(3):
        pivot = max(range(i, 3), key=lambda k: abs(matrix[k][i]))
        matrix[i], matrix[pivot] = matrix[pivot], matrix[i]
        if abs(matrix[i][i]) <= max(1e-10, scale*1e-8):
            return None
        divisor = matrix[i][i]
        matrix[i] = [v/divisor for v in matrix[i]]
        for k in range(3):
            if k != i:
                factor = matrix[k][i]
                matrix[k] = [a-factor*b for a,b in zip(matrix[k],matrix[i])]
    return [row[3] for row in matrix]


def analyze(history):
    counts = Counter(); groups = defaultdict(list)
    rows = sorted(history.get('regular_samples', []) + history.get('changes', []),
                  key=lambda r: r['monotonic_s'])
    previous = None; plateau_at = None
    for row in rows:
        load = row.get('load_observation') or {}
        values = [row.get(k) for k in ('observation_timestamp','speed_mps',
            'sdk_game_throttle','sdk_game_brake','written_throttle','written_brake')]
        if (row.get('observation_valid') is not True or row.get('activation') is None
                or row.get('identity_reference') is None
                or not finite(row.get('gear')) or row['gear'] <= 0
                or not finite(row.get('sdk_frame_us'))
                or row.get('phase') != 'active' or row.get('capture_incomplete')
                or row.get('command_valid') is not True
                or not finite(row.get('command_sdk_frame_us'))
                or row['command_sdk_frame_us'] > row['sdk_frame_us']
                or row.get('write_error_count',0) or row.get('write_unverified_count',0)
                or row.get('last_backend_status') != 'MAPPING_WRITE_RETURNED'
                or load.get('abi_revision') != 12
                or not all(finite(v) for v in values)
                or not all(finite(load.get(k)) for k in ('cargo_mass_kg','unit_mass_kg','chassis_pitch_rad'))):
            counts['missing_or_unqualified_evidence'] += 1; previous = None; continue
        at,speed,t,b,wt,wb = values
        written_at = row.get('write_last_returned_at_s')
        if (not finite(written_at) or not finite(row.get('monotonic_s'))
                or not finite(row.get('command_expires_at'))
                or written_at > row['monotonic_s'] or written_at > row['command_expires_at']
                or not 0 <= row['monotonic_s']-at <= .5):
            counts['write_after_history_capture_or_unbound_time'] += 1; previous=None; continue
        aggregate = row.get('aggregate') or {}
        if (aggregate.get('backend_pair_mode_changes',0) or aggregate.get('write_error_count',0)
                or any(finite(row.get('backend_'+channel+'_min'))
                       and finite(row.get('backend_'+channel+'_max'))
                       and row['backend_'+channel+'_max']-row['backend_'+channel+'_min'] > .02
                       for channel in ('throttle','brake'))):
            counts['unresolved_between_sample_actuation'] += 1; previous=None; continue
        if (not all(0 <= v <= 1 for v in (t,b,wt,wb)) or (t > 0 and b > 0)
                or abs(t-wt) > .02 or abs(b-wb) > .02
                or load.get('motor_brake') is not False or load.get('retarder_step') != 0
                or row.get('sdk_user_throttle') != 0. or row.get('sdk_user_brake') != 0.):
            counts['unmatched_response_or_other_actuator'] += 1; previous=None; continue
        # Narrow operating bins prevent treating a gear/load/speed change as a
        # force calibration. Pitch is retained as orientation only.
        key = (row['identity_reference'], row['activation'], row['gear'],
               load['cargo_mass_kg'],load['unit_mass_kg'],int(speed//5),
               round(load['chassis_pitch_rad']/.01))
        if previous is None or previous[0] != key:
            previous = (key,row); plateau_at=at; continue
        old=previous[1]; dt=at-old['observation_timestamp']
        if dt == 0 and row['sdk_frame_us'] == old['sdk_frame_us']:
            counts['duplicate_observation'] += 1; continue
        if not .05 <= dt <= .25 or row['sdk_frame_us'] <= old['sdk_frame_us']:
            counts['gap_or_regression'] += 1; previous=(key,row); plateau_at=at; continue
        # The current decision/write normally follows its SDK observation.
        # Pair with the PREVIOUS successful writer, and require the response at
        # both ends of a settled plateau to agree. Do not assign this row's new
        # write to the game response that was acquired before it.
        if old['write_last_returned_at_s'] > at:
            counts['previous_write_not_yet_returned_at_observation'] += 1
            previous=(key,row); plateau_at=at; continue
        if abs(t-old['sdk_game_throttle']) > .02 or abs(b-old['sdk_game_brake']) > .02:
            plateau_at=at
        if at-plateau_at < .7:
            counts['actuator_transient'] += 1
        else:
            acceleration=(speed-old['speed_mps'])/dt
            groups[key].append(((t,-b,1.),acceleration,dt))
        previous=(key,row)
    estimates=[]
    for key, data in groups.items():
        duration=sum(dt for _,_,dt in data)
        coefficients=solve(data) if len(data)>=30 and duration>=8. else None
        if coefficients is None or not all(0 < c < 15 for c in coefficients[:2]):
            counts['insufficient_excitation_or_invalid_gain'] += len(data); continue
        residual=math.sqrt(sum(dt*(sum(c*v for c,v in zip(coefficients,x))-y)**2
                              for x,y,dt in data)/duration)
        estimates.append(dict(operating_bin=list(key), samples=len(data), duration_s=duration,
            drive_gain_mps2=coefficients[0], brake_gain_mps2=coefficients[1],
            drift_mps2=coefficients[2], weighted_residual_rms_mps2=residual,
            status='PASSIVE_ESTIMATE_NOT_RUNTIME_CALIBRATION'))
    return dict(status='PASSIVE_ESTIMATES' if estimates else 'NOT_MEASURED',
        runtime_authorized=False, game_consumption_verified=False, estimates=estimates,
        sample_count=len(rows), excluded_counts=dict(counts),
        missing_contract='Validated per-vehicle response/capacity and operating-domain evidence before automatic use',
        method='Original observation dt, >=700 ms plateau, exclusive SDK/backend pair agreement, '
            'previous returned write -> subsequent SDK observation; '
            'same authority/gear/load/speed/pitch bin; dt-weighted 3-parameter fit. '
            'No causality certificate, grade estimate, total-mass inference or online application.')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('replay',type=Path); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT/'docs/steering-audit'):
        parser.error('Output must remain in workspace audit directory')
    from core.steering_replay import inspect_replay
    result=inspect_replay(args.replay)
    if not result['integrity_valid']: raise ValueError('Replay integrity rejected')
    analysis=analyze((result['replay'].get('longitudinal') or {}).get('decision_history') or {})
    analysis.update(input_sha256=hashlib.sha256(args.replay.read_bytes()).hexdigest(),
                    input_path=str(args.replay.resolve()))
    args.output.write_text(json.dumps(analysis,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(analysis,indent=2))
