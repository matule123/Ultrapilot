"""Use the existing selected regressions and populated-traffic qualifier."""
from pathlib import Path
import json,subprocess,sys,shutil
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import prepare_reactivation_fix as build
OUT=build.OUT
sys.path.insert(0,str(OUT/'verification-runtime'))


def regressions():
    manifest=build.verify()
    prior=json.loads((ROOT/'docs/steering-audit/oct29-transition/release01/test-selection.json').read_bytes())
    migration=json.loads((ROOT/'tests/layout-migration.json').read_bytes())
    targets=[]
    for path in prior['targets']:
        name,*suffix=path.split('::')
        targets.append('::'.join([migration.get(name,name),*suffix]))
    targets+=['tests/diagnostics/test_reactivation_retention.py','tests/traffic/test_reactivation_identity.py']
    targets=list(dict.fromkeys(targets))
    test_hashes={p:build.sha((ROOT/p).read_bytes()) for p in {t.split('::')[0] for t in targets}}
    record=dict(targets=targets,test_sha256=test_hashes)
    (OUT/'test-selection.json').write_text(json.dumps(record,indent=2))
    args=('import sys;sys.path.insert(0,'+repr(str(OUT/'verification-runtime'))+');'
        'import core.engine,core.longitudinal,core.steering_replay,core.navigation.longitudinal_diagnostics,plugins.autopilot.main;'
        'print("EXACT CANDIDATE",core.steering_replay.__file__,flush=True);'
        'import pytest;raise SystemExit(pytest.main('+repr(targets+['-q'])+'))')
    path=OUT/'selected-regressions.log';assert not path.exists()
    with path.open('x',encoding='utf-8') as stream:
        result=subprocess.run([sys.executable,'-u','-c',args],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
    build.verify()
    assert all(build.sha((ROOT/p).read_bytes())==s for p,s in test_hashes.items())
    proof=dict(exit_code=result.returncode,log_sha256=build.sha(path.read_bytes()),
        runtime_sha256={r['path']:r['sha256'] for r in manifest['files']},whole_pytest_run=False)
    (OUT/'regression-result.json').write_text(json.dumps(proof,indent=2))
    print(path.read_text(encoding='utf-8')[-4500:],flush=True)
    if result.returncode:raise SystemExit(result.returncode)


def load(final=False,observer=False,observer2=False,prefix=False):
    from tools.qualify_oct25_traffic_capture import run_daemon_host
    from tools.assess_oct25_traffic_qualification import assess
    manifest=build.verify();out=OUT/('prefix-load-qualification' if prefix else 'observer2-load-qualification' if observer2 else 'observer-load-qualification' if observer else
        'final-load-qualification' if final else 'load-qualification')
    assert not out.exists();out.mkdir()
    (out/'runtime-identity.json').write_text(json.dumps(dict(build=manifest['build'],
        runtime_sha256={r['path']:r['sha256'] for r in manifest['files']},
        base_receipt_sha256=manifest['base_receipt_sha256']),indent=2))
    original=ROOT/'docs/steering-audit/oct29-transition/release01/load-qualification'
    for name in ('ACCEPTANCE.md','original03-identity.json','approved-budget.json','baseline-scope-approval.json'):
        shutil.copyfile(original/name,out/name)
    for mode,label in ((0,'simple'),(3,'real')):
        for enabled in (False,True):
            name='final-max-'+label+('-on' if enabled else '-off')
            value=run_daemon_host(dict(mode=mode,enabled=enabled,count=40,trailers=3,
                ticks=1400,directory=out/name,pace=0.,capacity_probe_mib=None,
                export_enabled=True,file_probe_mib=None,profile_export=False))
            (out/(name+'.json')).write_text(json.dumps(value,indent=2))
            print(json.dumps(dict(mode=mode,enabled=enabled,whole_tick=value['whole_tick'],
                engine_flush=value['engine_flush'],active=value['active'],fault=value['fault'])),flush=True)
    value=assess(out);(out/'assessment.json').write_text(json.dumps(value,indent=2))
    build.verify();print(json.dumps(dict(verdict=value['verdict'],failures=value['failures'])),flush=True)
    if value['failures']:raise SystemExit(1)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('action',choices=['regressions','load','load-final','load-observer','load-observer2','load-prefix'])
    dict(regressions=regressions,load=load,**{'load-final':lambda:load(final=True),
        'load-observer':lambda:load(observer=True),
        'load-observer2':lambda:load(observer2=True),
        'load-prefix':lambda:load(prefix=True)})[p.parse_args().action]()
