"""Tie qualification to exact candidate, raw logs, original evidence and base."""
from pathlib import Path
import json,subprocess,sys,difflib
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import prepare_reactivation_fix as build
OUT=build.OUT


def main():
    manifest=build.verify()
    result=json.loads((OUT/'regression-result.json').read_bytes())
    original=(OUT/'selected-regressions.log').read_text(encoding='utf-8')
    assert build.sha((OUT/'selected-regressions.log').read_bytes())==result['log_sha256']
    expected=['tests/diagnostics/test_diagnostic_window.py::test_long_related_braking_wait_and_green_remain_one_dossier',
        'tests/diagnostics/test_export_overhead.py::test_part_available_after_admission_wait_is_fully_validated_not_declared_missing']
    failures=[line.split(' - ')[0][len('FAILED '):].replace('\\','/')
        for line in original.splitlines() if line.startswith('FAILED ')]
    assert failures==expected and '2 failed, 630 passed, 30 subtests passed' in original
    recheck=(OUT/'final-contract-regressions.log').read_text(encoding='utf-8')
    assert '48 passed' in recheck and 'failed' not in recheck
    final_tests=(OUT/'final-prefix-regressions.log').read_text(encoding='utf-8')
    assert '73 passed' in final_tests and 'failed' not in final_tests
    selected=json.loads((OUT/'test-selection.json').read_bytes())
    changed={p for p,sha in selected['test_sha256'].items() if build.sha((ROOT/p).read_bytes())!=sha}
    assert changed=={p.split('::')[0] for p in expected}|{'tests/diagnostics/test_reactivation_retention.py'}
    assert '4 failed' in (OUT.parent/'frozen-before-tests.log').read_text(encoding='utf-8')
    assert '1 failed' in (OUT.parent/'frozen-before-spawn.log').read_text(encoding='utf-8')
    assessed=OUT/'prefix-load-qualification'
    assessment=json.loads((assessed/'assessment.json').read_bytes())
    identity=json.loads((assessed/'runtime-identity.json').read_bytes())
    assert identity['runtime_sha256']=={r['path']:r['sha256'] for r in manifest['files']}
    observer=(OUT/'observer2-contract-tests.log').read_text(encoding='utf-8')
    assert '11 passed' in observer and 'failed' not in observer
    for pair in assessment['pairs']:
        for variant in (pair['off'],pair['on']):
            assert variant['host_local_memory']['export_children_observed_by']=='external Manager-family supervisor'
            assert variant['host_local_memory']['sample_period_s']==variant['memory']['sample_period_s']==.02
            assert variant['host_local_memory']['parent_peak_rss']>0
        assert pair['on']['memory']['simultaneous_children_max']==1
        assert pair['on']['memory']['children_combined_peak_rss']>0
    audit=json.loads((OUT.parent/'stream-audit.json').read_bytes())
    for row in audit['originals']:assert build.sha(Path(row['path']).read_bytes())==row['sha256']
    baseline=ROOT/'docs/steering-audit/oct29-transition/release01/verification-runtime'
    for name in build.RUNTIME:
        assert build.sha((baseline/name).read_bytes())==build.sha((build.APP/name).read_bytes())
    diffs=[]
    for name in build.RUNTIME:
        a=(build.APP/name).read_text(encoding='utf-8-sig').splitlines(True)
        b=(OUT/'verification-runtime'/name).read_text(encoding='utf-8-sig').splitlines(True)
        diffs.extend(difflib.unified_diff(a,b,fromfile='installed/'+name,tofile='candidate/'+name))
    (OUT/'installed-to-candidate.diff').write_text(''.join(diffs),encoding='utf-8')
    static=subprocess.run([sys.executable,'-m','compileall','-q',str(OUT/'verification-runtime'),
        'tests/diagnostics/test_reactivation_retention.py','tests/traffic/test_reactivation_identity.py',
        'tools/analyze_reactivation_capture.py','tools/prepare_reactivation_fix.py',
        'tools/qualify_reactivation_fix.py','tools/verify_reactivation_fix.py',
        'tools/qualify_oct25_traffic_capture.py','tools/profile_reactivation_baseline.py',
        'tests/diagnostics/test_qualification_observer.py'],cwd=ROOT)
    assert static.returncode==0
    diff=subprocess.run(['git','diff','--check'],cwd=ROOT,capture_output=True,text=True)
    assert diff.returncode==0,diff.stdout+diff.stderr
    proof=dict(all_gates_passed=not assessment['failures'],verdict=assessment['verdict'],
        failures=assessment['failures'],build=manifest['build'],
        runtime_sha256={r['path']:r['sha256'] for r in manifest['files']},
        selected_run=dict(passed=630,subtests=30,contract_rechecks=48,original_expected_failures=expected,
            original_log_sha256=result['log_sha256'],recheck_log_sha256=build.sha((OUT/'final-contract-regressions.log').read_bytes()),
            final_diagnostic_refinement_regressions=73,
            final_log_sha256=build.sha((OUT/'final-prefix-regressions.log').read_bytes()),
            original_runtime_sha256=result['runtime_sha256']),
        final_test_sha256={p:build.sha((ROOT/p).read_bytes()) for p in
            [*selected['test_sha256'],'tests/diagnostics/test_qualification_observer.py']},
        qualifier_sha256=build.sha((ROOT/'tools/qualify_oct25_traffic_capture.py').read_bytes()),
        criteria_sha256=assessment['criteria_sha256'],assessment_sha256=build.sha((assessed/'assessment.json').read_bytes()),
        originals_verified=len(audit['originals']),installed_files_verified=len(manifest['required_base']),
        compileall_exit_code=0,git_diff_check_exit_code=0,whole_pytest_run=False,
        qualifier_observer_regressions=11,observer_scope='local host RSS plus external complete Manager/child family, both 20 ms; non-allocating lock probe',
        controls_unchanged=True,installed_unchanged=True,deployed=False,game_verified=False,
        historical_lock_owner='not recorded',actor85_fault_pose='missing original acquisition')
    proof_path=OUT/'qualification-result.json'
    if proof_path.exists():
        old=json.loads(proof_path.read_bytes())
        if not old.get('all_gates_passed') and proof['all_gates_passed']:
            retained=OUT/'qualification-result-before-observer.json'
            assert not retained.exists()
            retained.write_bytes(proof_path.read_bytes())
    proof_path.write_text(json.dumps(proof,indent=2))
    print(json.dumps(proof,indent=2))


if __name__=='__main__':main()
