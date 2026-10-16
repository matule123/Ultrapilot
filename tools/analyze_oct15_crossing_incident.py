"""Read-only decoding of the evening Oct 15 evidence; originals are untouched."""
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.steering_replay import inspect_replay


def main():
    install = Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')
    out = ROOT / 'docs/steering-audit/oct15-crossing-dev-hud'
    out.mkdir(parents=True, exist_ok=True)
    sha = lambda b: hashlib.sha256(b).hexdigest()
    receipt = json.loads((install / 'manual-deployment.json').read_text(encoding='utf-8-sig'))
    files = []
    for row in receipt['files']:
        target = Path(row['target'])
        raw = target.read_bytes()
        assert sha(raw) == row['sha256'].lower(), str(target)
        relative = target.relative_to(install) if target.is_relative_to(install) else Path('external') / target.name
        source = ROOT / relative
        same = (source.exists() and source.read_bytes().replace(b'\r\n', b'\n')
                == raw.replace(b'\r\n', b'\n'))
        files.append(dict(path=str(relative), sha256=sha(raw), source_equal_lf=same))
    evidence = []
    incident = None
    for suffix in ('183602.361472', '183603.361416'):
        path = install / 'route-diagnostics' / f'steering-replay-20261015T{suffix}Z-automatic_disable.json'
        result = inspect_replay(path)
        assert result['integrity_valid'], str(path)
        value = result.pop('replay')
        if 'longitudinal' in value:
            journal=value['longitudinal']
            history=journal.get('decision_history') or {}
            rows=sorted(history.get('regular_samples',[])+history.get('changes',[]),
                        key=lambda row:row['monotonic_s'])
            actor83=next((r for r in rows if (r.get('traffic_cause') or {}).get('actor',{}).get('id')==83),None)
            incident=dict(first_intervention=journal.get('first_intervention'),
                detail=journal.get('detail_evidence'),history_range=history.get('observed_range_s'),
                history_capture_failures=history.get('capture_failures'),actor83_receipt=actor83)
            if actor83:
                cause=actor83['traffic_cause'];actor=cause['actor'];conflict=cause['decisive']
                incident['recomputed_old_cap_kmh']=3.6*conflict['distance_m']/(conflict['actor_arrival_s']
                    +2.+actor['dimensions_whl'][2]/(2*actor['speed']))
                incident['extrapolated_point_NOT_observed_future_xyz']=[
                    actor['x']-math.sin(actor['yaw'])*actor['speed']*conflict['actor_arrival_s'],actor['y'],
                    actor['z']-math.cos(actor['yaw'])*actor['speed']*conflict['actor_arrival_s']]
        (out / (path.stem + '-decoded.json')).write_text(json.dumps(value), encoding='utf-8')
        evidence.append(dict(path=str(path), sha256=sha(path.read_bytes()), **result))
    summary = dict(source_commit=receipt.get('source_commit'), files=files, evidence=evidence)
    (out / 'integrity-summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    (out / 'incident-analysis.json').write_text(json.dumps(incident, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
