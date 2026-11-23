"""Check exact replay outputs and summarize the unchanged latency gates."""

import argparse
from collections import defaultdict
import json
import math
from pathlib import Path


CONTROL_FIELDS = (
    'at_s', 'native_speed', 'sdk_speed', 'recorded_gear', 'modeled_gear', 'brake',
    'following_status', 'crossing', 'body', 'acc_valid', 'acc_reason', 'active',
    'disable_reason', 'physical_throttle', 'physical_brake', 'first_intervention',
    'speed_cap_mps', 'owner_witnesses', 'decision', 'actor', 'motion',
)
MODES = (0, 3)


def load(path):
    return json.loads(path.read_bytes())


def control_bytes(run):
    control = dict(mode=run['mode'], writes=run['writes'],
                   rows=[{field: row[field] for field in CONTROL_FIELDS} for row in run['rows']])
    return json.dumps(control, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def exact(reference, candidate):
    """Compare numbers at zero tolerance and lists in their emitted order."""
    before, after = load(reference), load(candidate)
    old_probe, new_probe = (load(path.with_suffix('.probe.json')) for path in (reference, candidate))
    if old_probe['fixture_sha256'] != new_probe['fixture_sha256']:
        raise AssertionError('Replay input changed')
    frames = 0
    writes = {}
    for left, right in zip(before, after, strict=True):
        mode = left['mode']
        if mode != right['mode'] or left['writes'] != right['writes']:
            raise AssertionError(f'Mode or chronological Controller writes changed in mode {mode}')
        writes[mode] = len(left['writes'])
        if len(left['rows']) != 32:
            raise AssertionError(f'Expected 32 frames in mode {mode}')
        for first, second in zip(left['rows'], right['rows'], strict=True):
            for field in CONTROL_FIELDS:
                if first[field] != second[field]:
                    raise AssertionError(f'Mode {mode}, time {first["at_s"]}: {field} differs')
            frames += 1
        if control_bytes(left) != control_bytes(right):
            raise AssertionError(f'Mode {mode}: canonical control bytes changed')
    if set(writes) != set(MODES) or frames != 64:
        raise AssertionError('Expected both automatic modes')
    if len(old_probe['records']) != frames or len(new_probe['records']) != frames:
        raise AssertionError('Per-actor branch audit missing')
    actors = 0
    for index, (left, right) in enumerate(zip(old_probe['records'], new_probe['records'], strict=True)):
        if left['branches'] != right['branches']:
            raise AssertionError(f'Per-actor branch results changed at acquisition {index}')
        actors += len(left['branches'])
    return dict(frames=frames, ordered_writes_by_mode=writes, actor_branch_observations=actors,
                numeric_tolerance=0, checked_native_actors=new_probe['checked_actors'])


def stats(values):
    values = sorted(values)
    if not values:
        return None
    return dict(n=len(values), p50=values[math.ceil(len(values) * .50) - 1],
                p95=values[math.ceil(len(values) * .95) - 1],
                p99=values[math.ceil(len(values) * .99) - 1], max=values[-1])


def timings(path):
    runs = load(path)
    results = {}
    for mode in MODES:
        rows = [row for run in runs if run['mode'] == mode for row in run['rows']]
        fields = ('whole_tick_ms', 'projection_ms', 'projection_cpu_ms', 'engine_flush_ms',
                  'runtime_gc_ms', 'motion_retained_bytes')
        if len(rows) != 96 or any(row['clock_basis'] != 'frozen_record_receiver_time' for row in rows):
            raise AssertionError(f'Mode {mode} did not replay three 32-frame runs at the original clock')
        result = {field: stats(row[field] for row in rows) for field in fields}
        result['whole_minus_projection_and_flush_ms'] = stats(
            row['whole_tick_ms'] - row['projection_ms'] - row['engine_flush_ms'] for row in rows)
        result['worst_ticks'] = [{field: row[field] for field in ('at_s', *fields[:-1])}
                                 for row in sorted(rows, key=lambda row: row['whole_tick_ms'])[-3:][::-1]]
        result['gates'] = dict(whole_p99=result['whole_tick_ms']['p99'] < 50.,
                               whole_max=result['whole_tick_ms']['max'] < 100.,
                               flush_p99=result['engine_flush_ms']['p99'] <= 16.67,
                               flush_max=result['engine_flush_ms']['max'] < 50.)
        results[mode] = result
    return results


def phases(path):
    runs = load(path)
    probe = load(path.with_suffix('.probe.json'))
    rows = [(run['mode'], row) for run in runs for row in run['rows']]
    grouped = {mode: defaultdict(list) for mode in MODES}
    worst = {}
    for (mode, row), record in zip(rows, probe['records'], strict=True):
        if mode not in worst or row['whole_tick_ms'] > worst[mode]['whole_tick_ms']:
            worst[mode] = {name: row[name] for name in ('at_s', 'whole_tick_ms', 'projection_ms',
                           'projection_cpu_ms', 'engine_flush_ms', 'runtime_gc_ms')}
            worst[mode]['phases_ms'] = {name: seconds * 1000.
                                        for name, (seconds, _) in record['phases'].items()}
            worst[mode]['native_ms'] = {name: seconds * 1000.
                                        for name, seconds in record.get('native_seconds', {}).items()}
        values = grouped[mode]
        for name, (seconds, count) in record['phases'].items():
            if count:
                values[name].append(seconds * 1000.)
        native = record.get('native_seconds')
        if native:
            for name, seconds in native.items():
                values['native_' + name].append(seconds * 1000.)
            values['native_boundary_total'].append(sum(native.values()) * 1000.)
            values['native_arrays_bytes'].append(record['native_arrays_bytes'])
    return dict(native_calls=probe['native_calls'], peak_arrays_bytes=probe['peak_arrays_bytes'],
                worst_ticks_by_mode=worst,
                per_mode={mode: {phase: stats(values) for phase, values in phases.items()}
                          for mode, phases in grouped.items()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    audit = commands.add_parser('exact')
    audit.add_argument('reference', type=Path)
    audit.add_argument('candidate', type=Path)
    for command in ('timings', 'phases'):
        commands.add_parser(command).add_argument('replay', type=Path)
    args = parser.parse_args()
    if args.command == 'exact':
        result = exact(args.reference, args.candidate)
    else:
        result = (timings if args.command == 'timings' else phases)(args.replay)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
