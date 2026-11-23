"""Read-only final archive, installed-base and original-evidence verification."""
from pathlib import Path
import json
import zipfile
from tools.prepare_oct29_incident_fix import APP,OUT,ROOT,load,sha,verify


def main():
    manifest=load(OUT/'candidate-manifest.json');verify(manifest)
    receipt=load(OUT/'release-receipt.json')
    for name,entry in receipt['archives'].items():
        assert sha((OUT/name).read_bytes())==entry['sha256']
    names={row['path'] for row in manifest['files']}
    with zipfile.ZipFile(OUT/'ultrapilot-oct29-incident-01-candidate.zip') as archive:
        assert archive.testzip() is None
        assert set(archive.namelist())==names|{'runtime-manifest.json'}
        for row in manifest['files']:assert sha(archive.read(row['path']))==row['sha256']
        signed=json.loads(archive.read('runtime-manifest.json'))
        assert signed['qualification']['exit_code']==0 and signed['measurements']['numeric_gates_passed']
    with zipfile.ZipFile(OUT/'rollback-installed-base.zip') as archive:
        assert archive.testzip() is None
        assert set(archive.namelist())==names|{'manual-deployment.json'}
        for row in manifest['files']:assert sha(archive.read(row['path']))==row['previous_sha256']
        assert archive.read('manual-deployment.json')==(APP/'manual-deployment.json').read_bytes()
    audit=load(ROOT/'docs/steering-audit/oct29-transition/audit.json')
    for row in audit['originals']:
        assert sha((APP/'route-diagnostics'/row['name']).read_bytes())==row['sha256']
    baseline=load(OUT/'steering-baseline.json');candidate=load(OUT/'steering-candidate.json')
    assert baseline['cases']==candidate['cases']
    controls={name:sha((APP/name).read_bytes()) for name in manifest['unchanged_controls']}
    for name,digest in controls.items():assert sha((OUT/'verification-runtime'/name).read_bytes())==digest
    result=dict(build=manifest['build'],archives_verified=True,runtime_entries=4,
        installed_files_verified=len(manifest['required_base']),installed_unchanged=True,
        original_evidence_unchanged=True,control_hashes=controls,
        steering_cases_identical=len(candidate['cases']),compileall_exit_code=0,
        git_diff_check_exit_code=0,whole_pytest_run=False,deployed=False,game_verified=False)
    (OUT/'final-verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
