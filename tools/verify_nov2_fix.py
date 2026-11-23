"""Bind final qualification, original evidence and exact installed-base bytes."""
from pathlib import Path
import json
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import prepare_nov2_fix as build

def main():
    out=build.OUT;m=build.verify()
    assessment=json.loads((out/'load-qualification/assessment.json').read_bytes())
    identity=json.loads((out/'load-qualification/runtime-identity.json').read_bytes())
    runtime={r['path']:r['sha256'] for r in m['files']}
    assert runtime==identity['runtime_sha256']
    regression=json.loads((out/'regression-result.json').read_bytes())
    assert regression['runtime_sha256']==runtime
    selected=(out/'selected-regressions.log').read_text(encoding='utf-8')
    assert build.sha((out/'selected-regressions.log').read_bytes())==regression['log_sha256']
    # Keep the full run's four test-boundary saturation failures explicit.
    expected=[
        'tests/diagnostics/test_assembly_read_reuse.py::test_exact_assembly_decodes_each_immutable_replay_only_once',
        'tests/diagnostics/test_assembly_read_reuse.py::test_cached_decode_never_accepts_changed_file_or_foreign_request',
        'tests/diagnostics/test_assembly_read_reuse.py::test_corruption_between_attachment_and_final_readback_still_fails',
        'tests/diagnostics/test_diagnostic_window.py::test_long_related_braking_wait_and_green_remain_one_dossier']
    failures=[line.split(' - ')[0][7:].replace('\\','/') for line in selected.splitlines() if line.startswith('FAILED ')]
    assert failures==expected and '4 failed, 162 passed, 984 subtests passed' in selected
    recheck=(out/'final-order-rechecks.log').read_text(encoding='utf-8')
    assert '86 passed' in recheck and 'failed' not in recheck
    tests=json.loads((out/'test-selection.json').read_bytes())['sha256']
    assert all(build.sha((ROOT/p).read_bytes())==s for p,s in tests.items())
    before=(out.parent/'before-installed-base.log').read_text(encoding='utf-8')
    assert '4 failed' in before
    assert '1 failed' in (out.parent/'before-spawn-installed.log').read_text(encoding='utf-8')
    assert '1 failed' in (out.parent/'before-assembly-reuse.log').read_text(encoding='utf-8')
    assert '1 failed, 1 passed' in (out.parent/'before-archive.log').read_text(encoding='utf-8')
    assert json.loads((out.parent/'assembly-output-equivalence.json').read_text(encoding='utf-8-sig'))['assembly_bytes_identical']
    audit=json.loads((out.parent/'audit.json').read_bytes())
    for row in audit['originals']:assert build.sha(Path(row['path']).read_bytes())==row['sha256']
    archive=build.APP/'route-diagnostics/archive/incident-55bfc3027cad4dfd90fd37d7a4164c84-15672'
    extra=[]
    for p in archive.iterdir():
        if p.is_file():
            assert p.read_bytes()==(out.parent/'exact-assembly-profile'/p.name).read_bytes()
            extra.append(dict(path=str(p),sha256=build.sha(p.read_bytes())))
    unchanged=0
    for folder in ('core','plugins','sdk','ui'):
        for p in (build.APP/folder).rglob('*.py'):
            rel=p.relative_to(build.APP).as_posix()
            if rel not in build.RUNTIME:
                assert p.read_bytes()==(out/'verification-runtime'/rel).read_bytes(),rel
                unchanged+=1
    for rel,digest in m['unchanged_controls'].items():
        assert build.sha((out/'verification-runtime'/rel).read_bytes())==digest
    static=subprocess.run([sys.executable,'-m','compileall','-q',str(out/'verification-runtime'),
        *tests,'tests/diagnostics/conftest.py','tools/analyze_nov2_capture.py',
        'tools/preflight_nov2_capture.py','tools/profile_nov2_ap_export.py',
        'tools/profile_nov2_assembly.py','tools/prepare_nov2_fix.py','tools/qualify_nov2_fix.py',
        'tools/verify_nov2_fix.py'],cwd=ROOT)
    assert static.returncode==0
    checked=subprocess.run(['git','diff','--check'],cwd=ROOT,capture_output=True,text=True)
    assert checked.returncode==0,checked.stdout+checked.stderr
    proof=dict(build=m['build'],all_gates_passed=not assessment['failures'],
        verdict=assessment['verdict'],failures=assessment['failures'],runtime_sha256=runtime,
        base_receipt_sha256=m['base_receipt_sha256'],installed_files_verified=len(m['required_base']),
        unchanged_python_dependencies=unchanged,originals_verified=len(audit['originals'])+len(extra),
        archived_originals=extra,selected_passes=162,selected_subtests=984,
        explicit_test_isolation_failures=expected,affected_rechecks=86,
        selected_log_sha256=regression['log_sha256'],recheck_log_sha256=build.sha((out/'final-order-rechecks.log').read_bytes()),
        test_sha256=tests,test_environment_sha256={p:build.sha((ROOT/p).read_bytes())
            for p in ('tests/diagnostics/conftest.py','tests/conftest.py')},
        criteria_sha256=assessment['criteria_sha256'],assessment_sha256=build.sha((out/'load-qualification/assessment.json').read_bytes()),
        compileall_exit_code=0,git_diff_check_exit_code=0,whole_pytest_run=False,
        historical_timeout_subphase='not recorded; redundant assembly decoding reproduced and reduced',
        historical_ap_capture_failures='six aggregate failures; original exception causes not recorded',
        original_earlier_ap_part_remains_incomplete=True,installed_disk_ready_without_archival=False,
        deployed=False,game_verified=False)
    (out/'qualification-result.json').write_text(json.dumps(proof,indent=2))
    print(json.dumps({k:v for k,v in proof.items() if k not in ('test_sha256','archived_originals')},indent=2))
    if not proof['all_gates_passed']:raise SystemExit(1)

if __name__=='__main__':main()
