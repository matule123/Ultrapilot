"""Read-only October 16 evening incident/receipt audit; original files stay intact."""
import argparse
import hashlib
import json
from pathlib import Path

from core.steering_replay import inspect_replay


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    install = Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')
    receipt = json.loads((install/'manual-deployment.json').read_text(encoding='utf-8-sig'))
    installed = []
    for row in receipt['files']:
        target = Path(row['target'])
        relative = target.relative_to(install) if target.is_relative_to(install) else target
        source = root/relative if target.is_relative_to(install) else root/'__external_native_not_repo_payload__'
        installed.append(dict(path=str(relative), sha256=sha(target),
            receipt_match=sha(target)==row['sha256'].lower(),
            source_match=(source.exists() and source.read_bytes().replace(b'\r\n', b'\n')
                == target.read_bytes().replace(b'\r\n', b'\n'))))
    replays = []
    for path in sorted((install/'route-diagnostics').glob('steering-*20261016T17*.json')):
        inspected = inspect_replay(path)
        if not inspected['integrity_valid']:
            raise ValueError(str(path))
        v = inspected['replay']
        longitudinal = v.get('longitudinal') or {}
        history = longitudinal.get('decision_history') or {}
        rows = sorted(history.get('regular_samples', [])+history.get('changes', []),
                      key=lambda r:r['monotonic_s'])
        replays.append(dict(file=path.name,sha256=sha(path),identity=v['identity'],
            integrity_valid=True,first=longitudinal.get('first_intervention'),
            history={k:val for k,val in history.items() if k not in ('regular_samples','changes')},
            rows=rows,events=longitudinal.get('events'),
            sample_count=v['sample_count'],execution_count=v['execution_sample_count']))
        fault=longitudinal.get('first_intervention') or {}
        details=fault.get('details') or {}
        print(json.dumps(dict(file=path.name,rows=len(rows),first_time=fault.get('observed_at'),
            producer=fault.get('producer'),reason=fault.get('reason'),
            target=details.get('following_target_id'),fields=list(details),
            compared=details.get('traffic_comparison'),identity={k:val for k,val in v['identity'].items()
                if k not in ('control_intervention','detail')}),default=str))
    native=root/'docs/steering-audit/oct14-completion/native-candidate-c'
    native_receipt=json.loads((native/'build-receipt.json').read_text())
    native_files=[dict(path=name,sha256=sha(native/name),receipt_match=sha(native/name)==native_receipt['files'][name])
        for name in ('src\\processing\\traffic.cpp','src\\processing\\traffic.hpp','src\\up_traffic.hpp','ets2la_plugin.dll')]
    result=dict(installed=installed,replays=replays,receipt_sha256=sha(install/'manual-deployment.json'),
        native_source=native_files,native_receipt_sha256=sha(native/'build-receipt.json'),
        installed_native_matches_source_build=sha(install/'assets/ets2la_plugin.dll')==native_receipt['dll_sha256'])
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(receipt_files=len(installed),all_receipt_match=all(r['receipt_match'] for r in installed),
        source_differences=[r['path'] for r in installed if not r['source_match']]),indent=2))


if __name__=='__main__':
    main()
