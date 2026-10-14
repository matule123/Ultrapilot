"""Read-only receipt/codec analysis of the Oct 13 evening follow-up drive."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.steering_replay import inspect_replay


def analyze(installation, source_ref=None):
    receipt = json.loads((installation / 'manual-deployment.json').read_text(encoding='utf-8-sig'))
    installed = []
    for row in receipt['files']:
        target, source = Path(row['target']), Path(row['source'])
        content = target.read_bytes()
        source_content = None
        comparison_basis = 'working-tree'
        if source_ref:
            try:
                relative = source.relative_to(ROOT).as_posix()
                historical = subprocess.run(['git', 'show', f'{source_ref}:{relative}'],
                    cwd=ROOT, capture_output=True)
            except ValueError:
                historical = None
            if historical and historical.returncode == 0:
                source_content = historical.stdout
                comparison_basis = 'git:' + source_ref
            else:
                comparison_basis = 'WORKSPACE_ARTIFACT_NOT_IN_GIT'
        if source_content is None and source.is_file():
            source_content = source.read_bytes()
        installed.append(dict(path=row.get('relative_path', target.name),
            receipt_match=hashlib.sha256(content).hexdigest() == row['sha256'].lower(),
            comparison_basis=comparison_basis,
            source_comparison='raw_binary' if target.suffix.lower()=='.dll' else 'LF_CRLF_normalized_text',
            normalized_source_match=((content == source_content) if target.suffix.lower()=='.dll' else
                (content.replace(b'\r\n', b'\n') == source_content.replace(b'\r\n', b'\n')))
                if source_content is not None else None))
    exports = []
    paths = sorted((installation / 'route-diagnostics').glob('steering-replay-20261013T17*.json'))
    paths += sorted((installation / 'route-diagnostics').glob('steering-replay-20261013T18*.json'))
    for path in paths:
        result = inspect_replay(path)
        if not result['integrity_valid']:
            raise ValueError((path.name, 'integrity rejected'))
        data = result['replay']
        longitudinal = data.get('longitudinal') or {}
        history = longitudinal.get('decision_history') or {}
        rows = sorted(history.get('regular_samples', []) + history.get('changes', []),
                      key=lambda row: row['monotonic_s'])
        exports.append(dict(name=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            samples=data['sample_count'], executions=data['execution_sample_count'],
            first_intervention=longitudinal.get('first_intervention'),
            detail_evidence=longitudinal.get('detail_evidence'),
            detail_events=longitudinal.get('events'),
            decision_history=history, decoded_longitudinal=longitudinal,
            history_range=[rows[0]['monotonic_s'], rows[-1]['monotonic_s']] if rows else None))
    # Keep multiline native diagnostic records, only in these actual sessions.
    records, buffer = [], []
    with (installation / 'ultrapilot.log').open(encoding='utf-8', errors='replace') as log:
        for line in log:
            if line.startswith('2026-'):
                if buffer:
                    records.append(''.join(buffer))
                buffer = [line] if line.startswith('2026-10-13 ') and line[11:16] >= '19:49' else []
            elif buffer:
                buffer.append(line)
    if buffer:
        records.append(''.join(buffer))
    return dict(source_ref=source_ref or 'working-tree', installed=installed,
                receipt=receipt, exports=exports, session_records=records)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ref', help='Compare deployed content to this Git source ref; never change checkout')
    parser.add_argument('--installation', type=Path,
        default=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot'))
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(Path.cwd() / 'docs/steering-audit'):
        raise ValueError('Analysis output must remain in workspace audit directory')
    result = analyze(args.installation, args.ref)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(receipt_matches=sum(x['receipt_match'] for x in result['installed']),
        source_matches=sum(x['normalized_source_match'] is True for x in result['installed']),
        git_source_matches=sum(x['normalized_source_match'] is True
            and x['comparison_basis'].startswith('git:') for x in result['installed']),
        files=len(result['installed']), exports=[dict(name=x['name'], samples=x['samples'],
        intervention=x['first_intervention'], history_range=x['history_range'])
        for x in result['exports']]), indent=2))
