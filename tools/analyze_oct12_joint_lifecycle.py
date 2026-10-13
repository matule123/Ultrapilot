"""Read-only immutable incident analysis; missing geometry is not inferred."""
import argparse
import hashlib
import json
import math
from pathlib import Path

from core.steering_replay import inspect_replay

NAMES = ('steering-replay-20261012T175912.712989Z-automatic_disable.json',
    'steering-replay-20261012T175913.020683Z-automatic_disable.json',
    'steering-replay-20261012T180012.182653Z-automatic_disable.json',
    'steering-replay-20261012T180012.299925Z-automatic_disable.json',
    'steering-timing-20261012T180036.037599Z-plugin_stop.json')


def finite(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def analyze(root):
    files = []; incidents = []
    for name in NAMES:
        path = root / name; checked = inspect_replay(path)
        if not checked['integrity_valid']: raise ValueError((name, checked))
        data = checked['replay']; files.append(dict(file=name,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            samples=data['sample_count'], executions=data['execution_sample_count']))
        block = data.get('longitudinal')
        if not block: continue
        history = block['decision_history']
        rows = sorted(history['regular_samples']+history['changes'], key=lambda r: r['monotonic_s'])
        brief = [{k: row.get(k) for k in ('monotonic_s', 'activation', 'sdk_frame_us',
            'observation_timestamp', 'speed_mps', 'gear', 'signal_color', 'stop_target',
            'constrained_speed_kmh', 'control_target_kmh', 'traffic_brake', 'curve_brake',
            'curve_radius_m', 'curve_distance_m', 'selected_source', 'written_throttle',
            'written_brake', 'forward_phase', 'hold_phase', 'capture_incomplete')}
            for row in rows]
        observed = []; seen = set()
        for row in rows:
            key = (row.get('sdk_frame_us'), row.get('observation_timestamp'))
            if (key in seen or not row.get('observation_valid') or not finite(row.get('speed_mps'))
                    or not finite(row.get('observation_timestamp'))): continue
            seen.add(key); observed.append(row)
        observed.sort(key=lambda r: r['observation_timestamp'])
        # A bounded measured-speed window, not a fabricated continuous trace.
        onset = next((r for r in observed if r['speed_mps']*3.6 > 45.
            and (r.get('traffic_brake') or 0.) > .05), None)
        low = next((r for r in observed if onset and
            r['observation_timestamp'] > onset['observation_timestamp'] and r['speed_mps']*3.6 <= 20.), None)
        band = [r for r in observed if onset and low and
            onset['observation_timestamp'] <= r['observation_timestamp'] <= low['observation_timestamp']]
        acc = [(b['observation_timestamp'], (b['speed_mps']-a['speed_mps']) /
                (b['observation_timestamp']-a['observation_timestamp']))
               for a, b in zip(band, band[1:]) if 0.02 <= b['observation_timestamp']-a['observation_timestamp'] <= .2]
        jerk = [(b[1]-a[1])/(b[0]-a[0]) for a, b in zip(acc, acc[1:]) if .02 <= b[0]-a[0] <= .2]
        intervals = [(a, b, b['observation_timestamp']-a['observation_timestamp']) for a, b in zip(band, band[1:])]
        distance = (sum((a['speed_mps']+b['speed_mps'])*.5*dt for a,b,dt in intervals)
                    if intervals and all(0 < dt <= .2 for _,_,dt in intervals) else None)
        red_stops = [r for r in rows if r.get('signal_color') == 'red' and finite(r.get('speed_mps'))
                     and abs(r['speed_mps']) < .05]
        incidents.append(dict(file=name, first_intervention=block['first_intervention'],
            identity_table=history['identities'], range_s=history['observed_range_s'],
            detail=block['detail_evidence'], history_incomplete=history['incomplete'],
            red_stationary_rows=len(red_stops), painted_line_gap_m=None,
            rows=brief, retained_writes=block['events'],
            braking_band=dict(samples=len(band), from_speed_kmh=onset['speed_mps']*3.6 if onset else None,
                to_speed_kmh=low['speed_mps']*3.6 if low else None,
                started_sdk_timestamp=onset['observation_timestamp'] if onset else None,
                ended_sdk_timestamp=low['observation_timestamp'] if low else None,
                duration_s=low['observation_timestamp']-onset['observation_timestamp'] if onset and low else None,
                route_distance_m=None, integrated_sdk_forward_speed_m=distance,
                peak_sampled_deceleration_mps2=max((-a for _, a in acc), default=None),
                peak_sampled_jerk_mps3=max(map(abs, jerk), default=None),
                limitation='SDK finite differences, 20–200 ms adjacent intervals; noise/gear effects, not certified comfort jerk. Original actor poses and exact route displacement at onset not retained.')))
    return dict(files=files, incidents=incidents, game_verified_candidate=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot\route-diagnostics'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); result = analyze(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps([dict(file=r['file'], first_reason=r['first_intervention']['reason'],
        red_stationary_rows=r['red_stationary_rows'], braking_band=r['braking_band']) for r in result['incidents']], indent=2))
