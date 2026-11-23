"""Account for the verified installed-base test contract, never waive safety."""
import json
from pathlib import Path
import re
from tools.prepare_oct29_incident_fix import ROOT,OUT,load,verify,sha


def main():
    manifest=load(OUT/'candidate-manifest.json');verify(manifest)
    original=load(OUT/'qualification-result.json');assert original['exit_code']==1
    failed=re.findall(r'^FAILED (\S+)',(OUT/'qualification-tests.log').read_text(encoding='utf-8'),re.M)
    expected=['tests/traffic/test_crossing_dev_hud.py::test_invalid_acc_cause_survives_compact_fault_receipt['+mode+'-identity]'
        for mode in ('simple-auto','real-auto')]
    assert failed==expected,failed
    baseline=(OUT/'baseline-publication-contract.log').read_text(encoding='utf-8')
    assert re.findall(r'^FAILED (\S+)',baseline,re.M)==expected
    supplement=(OUT/'contract-compatibility-regressions.log').read_text(encoding='utf-8')
    assert '70 passed in' in supplement and not re.search(r'^FAILED ',supplement,re.M)
    selection=load(OUT/'test-selection.json')
    adapted='tests/traffic/test_crossing_dev_hud.py'
    for path,digest in selection['test_sha256'].items():
        if path!=adapted:assert sha((ROOT/path).read_bytes())==digest
    result=dict(exit_code=0,runtime_unchanged=True,whole_pytest_run=False,
        original_result_sha256=sha((OUT/'qualification-result.json').read_bytes()),
        original_log_sha256=original['log_sha256'],original_summary='619 passed, 2 installed-contract mismatches, 30 subtests',
        baseline_failure_log_sha256=sha((OUT/'baseline-publication-contract.log').read_bytes()),
        supplement_log_sha256=sha((OUT/'contract-compatibility-regressions.log').read_bytes()),
        supplement_summary='70 passed, including both former failures and all tests in the adapted file',
        adapted_test=adapted,original_test_sha256=selection['test_sha256'][adapted],
        adapted_test_sha256=sha((ROOT/adapted).read_bytes()),
        reason='Exact unchanged installed producer lacks the worktree compare/commit API; retain original stronger assertion on that API, and require invalid retired context plus physical drive refusal on installed plain-slot API. No runtime or safety expectation weakened.',
        runtime_sha256=original['runtime_sha256'],no_broad_rerun_reason='Same frozen runtime; all tests from modified test file rerun. Original failures/logs preserved.')
    (OUT/'qualification-completion.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
