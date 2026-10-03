"""Read-only analysis of the existing, integrity-checked combined export.

Writes are backend return evidence, never DLL/game-consumption confirmation.
Only original, coherent SDK acquisition times support speed derivatives.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.navigation.evidence_diagnostics import inspect_collection
from tools.analyze_phase6_stage1 import distribution, finite


def load_rows(path):
    checked = inspect_collection(path)
    if checked.get('integrity_valid') is not True:
        raise ValueError('COLLECTION_INTEGRITY_NOT_VERIFIED')
    manifest = json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
    document = json.loads((path / 'automatic-observations.json').read_text(encoding='utf-8'))
    if not document.get('chunked'):
        return document.get('samples', []), checked
    rows = []
    for entry in manifest['files']:
        if entry.get('role') == 'chunk' and entry['name'].startswith('automatic-observations'):
            rows.extend(json.loads((path / entry['name']).read_text(encoding='utf-8'))['records'])
    return rows, checked


def row_identity(row):
    lane = row.get('lane') or {}
    observed = (row.get('observation_identity') or {}).get('after') or {}
    return [observed.get('source_game_session_id'), observed.get('source_map_key'),
            observed.get('source_dataset_fingerprint'), lane.get('navigation_intent_id'),
            lane.get('revision'), lane.get('route_build_id')]


def source_identity(source):
    context = source.get('context')
    if isinstance(context, (tuple, list)) and len(context) == 8 and all(v is not None for v in context[:7]):
        return list(context[1:7])
    return None


def analyze_rows(rows):
    exclusions, reasons, phases = Counter(), Counter(), Counter()
    observations, writes, acceleration, jerk = [], [], [], []
    previous = previous_accel = None
    seen_writes = {}
    dropped = simultaneous = failed = unbound = 0
    for row in rows:
        block = row.get('longitudinal') or {}
        state = block.get('sampled_state') or {}
        phase = ('launch' if state.get('auto_drive_pending') else
                 'safety_stop' if state.get('control_state') == 'controlled_stop' else
                 'active' if state.get('autopilot_active') else 'inactive_unclassified')
        phases[phase] += 1
        dropped += block.get('dropped_events', 0)
        truck = row.get('truck') or {}
        metadata = truck.get('_control_observation') or {}
        t, speed, frame = metadata.get('observed_at'), truck.get('speed'), row.get('sdk_frame_us')
        identity = row_identity(row)
        key = (tuple(identity), state.get('activation'), phase)
        valid = (row.get('telemetry_valid') is True and metadata.get('valid') is True
                 and metadata.get('sdk_frame_us') == frame and finite(frame)
                 and all(v is not None for v in identity) and finite(t) and finite(speed)
                 and (row.get('observation_identity') or {}).get('reads_match') is True
                 and finite(row.get('captured_at_s')) and 0 <= row['captured_at_s']-t <= .5)
        if valid:
            obs = dict(time_s=t, sdk_frame_us=frame, identity=identity, phase=phase,
                       activation=state.get('activation'),
                       speed_mps=speed, game_throttle=truck.get('gameThrottle'),
                       game_brake=truck.get('gameBrake'))
            observations.append(obs)
            if (previous and previous[0] == key and frame > previous[1]['sdk_frame_us']
                    and 0 < t-previous[1]['time_s'] <= .5):
                dt = t-previous[1]['time_s']
                a = (speed-previous[1]['speed_mps'])/dt
                midpoint = (t+previous[1]['time_s'])/2
                acceleration.append(dict(time_s=midpoint, identity=identity, phase=phase, value_mps2=a))
                if previous_accel and previous_accel[0] == key:
                    jdt = midpoint-previous_accel[1]
                    if 0 < jdt <= .5:
                        jerk.append(dict(time_s=(midpoint+previous_accel[1])/2,
                                         identity=identity, phase=phase, value_mps3=(a-previous_accel[2])/jdt))
                previous_accel = key, midpoint, a
            else:
                previous_accel = None
                exclusions['derivative_boundary_or_gap'] += 1
            previous = key, obs
        else:
            exclusions['invalid_or_missing_original_observation_time'] += 1
            previous = previous_accel = None
        for event in block.get('events', []):
            seq = event.get('sequence')
            if seq in seen_writes:
                if seen_writes[seq] != event:
                    raise ValueError('CONFLICTING_PEDAL_WRITE_SEQUENCE')
                exclusions['duplicate_write_sequence'] += 1
                continue
            seen_writes[seq] = event
            source = event.get('source') or {}
            backend = event.get('backend') or {}
            verified = backend.get('status') == 'MAPPING_WRITE_RETURNED'
            failed += backend.get('status') in ('MAPPING_WRITE_FAILED', 'MAPPING_NOT_CONNECTED') or bool(event.get('error'))
            unbound += source_identity(source) is None
            pair = event.get('pair_after') or {}
            simultaneous += (verified and finite(pair.get('throttle')) and finite(pair.get('brake'))
                             and pair['throttle'] > 0 and pair['brake'] > 0)
            selected, inputs = source.get('selected') or {}, source.get('inputs') or {}
            acc, traffic = inputs.get('acc') or {}, inputs.get('traffic') or {}
            reason = (source.get('output_intent') or {}).get('reason') or selected.get('reason')
            if reason:
                reasons[reason] += 1
            writes.append(dict(sequence=seq, decision_sequence=source.get('decision_sequence'),
                activation=source.get('activation'), identity=source_identity(source),
                phase=source.get('phase'), sdk_frame_us=source.get('sdk_frame_us'),
                observation_timestamp=source.get('observation_timestamp'),
                write_started_s=event.get('call_started_at_s'), time_s=event.get('call_returned_at_s'),
                channel=event.get('channel'), requested_value=event.get('requested_value'),
                backend_value=backend.get('value'), backend_status=backend.get('status'),
                backend_started_at_s=backend.get('started_at_s'),
                backend_returned_at_s=backend.get('returned_at_s'),
                pair_after=pair, requested=source.get('requested'), selected=source.get('selected'),
                output_intent=source.get('output_intent'), winner=selected.get('source'), reason=reason,
                input_rejections=source.get('input_rejections'), rejected_inputs=source.get('rejected_inputs'),
                actual_speed_mps=source.get('actual_speed_mps'),
                requested_speed_kmh=acc.get('requested_speed_kmh'),
                constrained_speed_kmh=acc.get('constrained_speed_kmh'),
                control_target_kmh=acc.get('control_target_kmh'),
                regulator_mode=source.get('regulator_mode'), speed_control_reason=acc.get('speed_control_reason'),
                following=traffic.get('following'), game_consumption_verified=False))
    # An observed later frame is a response candidate, not proof that this write
    # caused it. Multiple intervening writes, input mix and lag remain unknown.
    for write in writes:
        later = next((o for o in observations if write['identity'] == o['identity']
            and write['activation'] is not None and write['activation'] == o['activation']
            and finite(write['time_s']) and finite(write['sdk_frame_us'])
            and o['sdk_frame_us'] > write['sdk_frame_us'] and 0 < o['time_s']-write['time_s'] <= .5), None)
        write['subsequent_sdk_candidate'] = later
    return dict(schema_version=1, phase_samples=dict(phases), observation_series=observations,
        write_series=writes, interventions=dict(reasons), excluded=dict(exclusions),
        returned_mapping_writes=sum(w['backend_status'] == 'MAPPING_WRITE_RETURNED' for w in writes),
        failed_backend_calls=failed, unbound_writes=unbound, dropped_journal_events=dropped,
        simultaneous_positive_pair_observations=simultaneous,
        complete_write_coverage=False, game_consumption_verified=False,
        acceleration_series=acceleration, jerk_series=jerk,
        acceleration_mps2=distribution([a['value_mps2'] for a in acceleration]),
        jerk_mps3=distribution([j['value_mps3'] for j in jerk]),
        methodology='Original SDK observed_at; increasing frames; same full identity and phase; gap <=500ms. Acceleration is delta speed/dt at interval midpoint; jerk is delta interval acceleration/midpoint dt. No filtering; derivative noise can dominate. Later-frame candidates do not prove causality. Counts cover retained writes only.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('collection', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if not output.is_relative_to(ROOT):
        parser.error('Output must remain in the workspace')
    rows, checked = load_rows(args.collection)
    result = analyze_rows(rows)
    result.update(collection=str(args.collection.resolve()), integrity=checked,
        manifest_sha256=hashlib.sha256((args.collection/'manifest.json').read_bytes()).hexdigest())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('returned_mapping_writes', 'failed_backend_calls',
        'unbound_writes', 'simultaneous_positive_pair_observations', 'dropped_journal_events')}, indent=2))


if __name__ == '__main__':
    main()
