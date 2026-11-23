"""Qualify one installed-base candidate using existing scenarios and gates."""
from pathlib import Path
import json
import shutil
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import prepare_nov2_fix as build
OUT=build.OUT
sys.path.insert(0,str(OUT/'verification-runtime'))

TARGETS=[
 'tests/lifecycle/test_preparation_deferral.py',
 'tests/test_steering_fresh_handoff.py',
 'tests/test_post_localization_freshness.py',
 'tests/diagnostics/test_standalone_archive.py',
 'tests/diagnostics/test_assembly_read_reuse.py',
 'tests/diagnostics/test_preparation_episode.py',
 'tests/diagnostics/test_diagnostic_window.py',
 'tests/diagnostics/test_late_assembly.py',
 'tests/diagnostics/test_reactivation_retention.py',
 'tests/diagnostics/test_export_service_crash.py',
 'tests/diagnostics/test_incident_assembly_failures.py',
 'tests/diagnostics/test_populated_capture.py',
 'tests/diagnostics/test_daemon_incident_export.py::test_live_red_wait_green_in_daemon_host',
 'tests/traffic/test_native_owner_contract.py',
 'tests/test_phase4_steering_dynamics.py',
]

def regressions():
    manifest=build.verify()
    test_hashes={p:build.sha((ROOT/p).read_bytes()) for p in {t.split('::')[0] for t in TARGETS}}
    (OUT/'test-selection.json').write_text(json.dumps(dict(targets=TARGETS,sha256=test_hashes),indent=2))
    script=('import sys;sys.path.insert(0,'+repr(str(OUT/'verification-runtime'))+');'
        'import core.steering_replay,plugins.map.main;'
        'print("FROZEN",core.steering_replay.__file__,plugins.map.main.__file__,flush=True);'
        'import pytest;raise SystemExit(pytest.main('+repr(TARGETS+['-q'])+'))')
    log=OUT/'selected-regressions.log';assert not log.exists()
    with log.open('x',encoding='utf-8') as stream:
        done=subprocess.run([sys.executable,'-u','-c',script],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
    build.verify()
    assert all(build.sha((ROOT/p).read_bytes())==s for p,s in test_hashes.items())
    (OUT/'regression-result.json').write_text(json.dumps(dict(exit_code=done.returncode,
        log_sha256=build.sha(log.read_bytes()),runtime_sha256={r['path']:r['sha256'] for r in manifest['files']}),indent=2))
    print(log.read_text(encoding='utf-8')[-4500:])
    raise SystemExit(done.returncode)

def load():
    from tools.qualify_oct25_traffic_capture import run_daemon_host
    from tools.assess_oct25_traffic_qualification import assess
    manifest=build.verify();directory=OUT/'load-qualification'
    assert not directory.exists();directory.mkdir()
    (directory/'runtime-identity.json').write_text(json.dumps(dict(
        runtime_sha256={r['path']:r['sha256'] for r in manifest['files']},
        base_receipt_sha256=manifest['base_receipt_sha256']),indent=2))
    original=ROOT/'docs/steering-audit/oct29-reactivation/release02/prefix-load-qualification'
    for name in ('ACCEPTANCE.md','original03-identity.json','approved-budget.json','baseline-scope-approval.json'):
        shutil.copyfile(original/name,directory/name)
    for mode,label in ((0,'simple'),(3,'real')):
        for enabled in (False,True):
            name='final-max-'+label+('-on' if enabled else '-off')
            value=run_daemon_host(dict(mode=mode,enabled=enabled,count=40,trailers=3,
                ticks=1400,directory=directory/name,pace=0.,capacity_probe_mib=None,
                export_enabled=True,file_probe_mib=None,profile_export=False))
            (directory/(name+'.json')).write_text(json.dumps(value,indent=2))
            print(json.dumps(dict(mode=mode,enabled=enabled,whole_tick=value['whole_tick'],
                engine_flush=value['engine_flush'],active=value['active'],fault=value['fault'])),flush=True)
    value=assess(directory);(directory/'assessment.json').write_text(json.dumps(value,indent=2))
    build.verify();print(json.dumps(dict(verdict=value['verdict'],failures=value['failures'])),flush=True)
    if value['failures']:raise SystemExit(1)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('action',choices=['regressions','load'])
    {'regressions':regressions,'load':load}[p.parse_args().action]()
