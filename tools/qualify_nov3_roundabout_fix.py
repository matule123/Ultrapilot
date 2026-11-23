"""Qualify the exact installed-base frozen candidate, not a deployment."""
from pathlib import Path
import json,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import prepare_nov3_roundabout_fix as build
OUT=build.OUT

TARGETS=['tests/traffic','tests/test_acc_following.py',
 'tests/lifecycle/test_joint_regressions.py','tests/lifecycle/test_longitudinal_completion.py',
 'tests/signals/test_signal_lifecycle.py','tests/signals/test_green_restart.py',
 'tests/diagnostics/test_late_ap_continuation.py','tests/diagnostics/test_stop_episode_capture.py',
 'tests/diagnostics/test_reactivation_retention.py','tests/diagnostics/test_daemon_incident_export.py',
 'tests/diagnostics/test_late_assembly.py','tests/diagnostics/test_capture_failures.py',
 'tests/diagnostics/test_incident_assembly_failures.py',
 'tests/test_phase4_steering_dynamics.py','tests/test_service_hold_comfort.py']


def invoke(source,log):
    script='import sys;sys.path.insert(0,'+repr(str(OUT/'verification-runtime'))+');'+source
    with (OUT/log).open('x',encoding='utf-8') as stream:
        result=subprocess.run([sys.executable,'-u','-c',script],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
    build.verify();print((OUT/log).read_text(encoding='utf-8')[-3500:]);return result.returncode


def regressions():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('group',choices=['control','diagnostic'])
    args=parser.parse_args()
    groups=dict(control=['tests/traffic','tests/test_acc_following.py',
        'tests/lifecycle/test_joint_regressions.py','tests/lifecycle/test_longitudinal_completion.py',
        'tests/signals/test_signal_lifecycle.py','tests/signals/test_green_restart.py',
        'tests/test_phase4_steering_dynamics.py'],
      diagnostic=['tests/diagnostics/test_late_ap_continuation.py','tests/diagnostics/test_resolved_predecessor.py',
        'tests/diagnostics/test_stop_episode_capture.py','tests/diagnostics/test_late_assembly.py',
        'tests/diagnostics/test_capture_failures.py','tests/diagnostics/test_assembly_read_reuse.py',
        'tests/diagnostics/test_incident_assembly_failures.py','tests/diagnostics/test_standalone_archive.py',
        'tests/diagnostics/test_daemon_incident_export.py::test_spawned_daemon_exports_through_existing_manager',
        'tests/diagnostics/test_daemon_incident_export.py::test_manager_admission_is_bounded_and_failed_part_releases_ticket',
        'tests/diagnostics/test_daemon_incident_export.py::test_daemon_episode_finishes_without_application_shutdown[0-long-wait]',
        'tests/diagnostics/test_daemon_incident_export.py::test_daemon_episode_finishes_without_application_shutdown[3-long-wait]'])
    targets=groups[args.group]
    m=build.verify()
    log=args.group+'-regressions.log'
    source='import core.engine,core.actor_motion,plugins.map.main;print("FROZEN",core.engine.__file__,core.actor_motion.__file__,plugins.map.main.__file__,flush=True);import pytest;raise SystemExit(pytest.main('+repr(targets+['-q','-x','--tb=short'])+'))'
    code=invoke(source,log)
    paths=set()
    for target in targets:
        path=ROOT/target.split('::')[0]
        paths.update(path.glob('test_*.py') if path.is_dir() else [path])
    (OUT/(args.group+'-result.json')).write_text(json.dumps(dict(exit_code=code,
        targets=targets,log_sha256=build.sha((OUT/log).read_bytes()),
        test_sha256={str(p.relative_to(ROOT)):build.sha(p.read_bytes()) for p in paths},
        runtime_sha256={r['path']:r['sha256'] for r in m['files']}),indent=2))
    raise SystemExit(code)


def benchmarks():
    build.verify()
    common='import core.engine;print("FROZEN",core.engine.__file__,flush=True);'
    jobs=[('captured-score.log',common+"from tools.reproduce_roundabout_prediction import main;sys.argv=['replay','score','--repeat','3','--out',"+repr(str(OUT/'captured-score.json'))+"];main()"),
      ('maximum-spread-score.log',common+"from tools.reproduce_roundabout_prediction import main;sys.argv=['replay','score','--maximum-traffic','--spread','--out',"+repr(str(OUT/'maximum-spread-score.json'))+"];main()"),
      ('hud-benchmark.log',common+"from tools.benchmark_oct15_crossing_dev_hud import main;sys.argv=['bench','--ticks','160','--output',"+repr(str(OUT/'hud-benchmark.json'))+"];main()"),
      ('longitudinal-benchmark.log',common+"from tools.benchmark_automatic_longitudinal import main;sys.argv=['bench','--samples','180','--output',"+repr(str(OUT/'longitudinal-benchmark.json'))+"];raise SystemExit(main())"),
      ('steering-benchmark.log',common+"import runpy;sys.argv=['bench','--quiet','--output',"+repr(str(OUT/'steering-benchmark.json'))+"];runpy.run_module('tools.run_steering_bench',run_name='__main__')")]
    codes={}
    for log,source in jobs:
        codes[log]=invoke(source,log)
        if codes[log]:break
    (OUT/'benchmark-result.json').write_text(json.dumps(dict(exit_codes=codes,
        runtime_sha256={r['path']:r['sha256'] for r in build.verify()['files']}),indent=2))
    raise SystemExit(int(any(codes.values())))


if __name__=='__main__':
    benchmarks() if len(sys.argv)>1 and sys.argv[1]=='benchmarks' else regressions()
