"""Read-only Oct 11 receipt, immutable export and low-speed coverage inventory."""
import argparse
import hashlib
import json
from pathlib import Path

from core.steering_replay import inspect_replay


def analyze(root):
    receipt = json.loads((root/'manual-deployment.json').read_text(encoding='utf-8-sig'))
    checks = []
    for item in receipt['files']:
        installed = Path(item['target']).read_bytes()
        source = Path(item['source']).read_bytes()
        checks.append(dict(path=item.get('relative_path', item['target']),
            installed_sha256=hashlib.sha256(installed).hexdigest(),
            source_sha256=hashlib.sha256(source).hexdigest(),
            receipt_matches=hashlib.sha256(installed).hexdigest() == item['sha256'].lower(),
            normalized_source_matches=installed.replace(b'\r\n', b'\n') == source.replace(b'\r\n', b'\n')))
    result = dict(receipt=receipt, checks=checks, exports=[])
    for path in sorted((root/'route-diagnostics').glob('*20261011T*.json')):
        checked = inspect_replay(path)
        if not checked['integrity_valid']:
            raise ValueError((path.name, checked))
        replay = checked['replay']; history = (replay.get('longitudinal') or {}).get('decision_history') or {}
        rows = replay.get('samples') or []
        # Only original accepted steering/SDK samples; never infer pedals or
        # colors from a dense steering header. Split identity/gaps explicitly.
        bands = []; current = None
        for row in rows:
            if row.get('sample_kind') == 'passive_timing' or not isinstance(row.get('speed_kmh'), (float,int)):
                continue
            t = row.get('application_monotonic_s')
            identity = row.get('application_trajectory_identity')
            if not isinstance(t, (float,int)) or not identity:
                continue
            low = row.get('autopilot_active') is True and row['speed_kmh'] < 5.
            if not low:
                current = None; continue
            if current is None or current['identity'] != identity or t-current['end_s'] > .5:
                current = dict(identity=identity, start_s=t, end_s=t, samples=0,
                    start_progress_m=row.get('tracking_progress_m'), end_progress_m=None,
                    min_speed_kmh=row['speed_kmh'], max_speed_kmh=row['speed_kmh'])
                bands.append(current)
            current.update(end_s=t, end_progress_m=row.get('tracking_progress_m'),
                samples=current['samples']+1,
                min_speed_kmh=min(current['min_speed_kmh'], row['speed_kmh']),
                max_speed_kmh=max(current['max_speed_kmh'], row['speed_kmh']))
        for band in bands: band['duration_s'] = band['end_s']-band['start_s']
        result['exports'].append(dict(file=path.name,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(), integrity_valid=True,
            samples=replay.get('sample_count'), executions=replay.get('execution_sample_count'),
            identity=replay.get('identity'), low_speed_bands=bands,
            history_range=history.get('observed_range_s'), history_incomplete=history.get('incomplete'),
            history_capture_failures=history.get('capture_failures'),
            signal_rows=sum(r.get('signal_id') is not None for r in
                history.get('regular_samples', [])+history.get('changes', [])),
            first_intervention=(replay.get('longitudinal') or {}).get('first_intervention')))
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot'))
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); result = analyze(a.root)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k != 'receipt'}, indent=2))


if __name__ == '__main__': main()
