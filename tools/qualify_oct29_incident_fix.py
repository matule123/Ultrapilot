"""Orchestrate the EXISTING populated-traffic qualifier on frozen runtime 01."""
from pathlib import Path
import json
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
RELEASE=ROOT/'docs/steering-audit/oct29-transition/release01'
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(RELEASE/'verification-runtime'))


def main():
    from tools.qualify_oct25_traffic_capture import run_daemon_host
    from tools.assess_oct25_traffic_qualification import assess
    import tools.prepare_oct29_incident_fix as build
    manifest=build.load(RELEASE/'candidate-manifest.json');build.verify(manifest)
    out=RELEASE/'load-qualification';assert not out.exists(),'Preserve raw measurements'
    out.mkdir()
    original=ROOT/'docs/steering-audit/oct25-traffic-qualification/daemon26-release'
    for name in ('ACCEPTANCE.md','original03-identity.json','approved-budget.json','baseline-scope-approval.json'):
        source=original/name
        if not source.exists():source=original.parent/name
        shutil.copyfile(source,out/name)
    for mode,label in ((0,'simple'),(3,'real')):
        for enabled in (False,True):
            name='final-max-'+label+('-on' if enabled else '-off')
            result=run_daemon_host(dict(mode=mode,enabled=enabled,count=40,trailers=3,
                ticks=1400,directory=out/name,pace=0.,capacity_probe_mib=None,
                export_enabled=True,file_probe_mib=None,profile_export=False))
            (out/(name+'.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
            print(json.dumps(dict(mode=mode,enabled=enabled,active=result['active'],fault=result['fault'],
                whole_tick=result['whole_tick'],engine_flush=result['engine_flush'])),flush=True)
    assessment=assess(out)
    (out/'assessment.json').write_text(json.dumps(assessment,indent=2),encoding='utf-8')
    build.verify(manifest)
    record=dict(numeric_gates_passed=not assessment['failures'],verdict=assessment['verdict'],
        runtime_sha256={r['path']:r['sha256'] for r in manifest['files']},
        criteria_sha256=assessment['criteria_sha256'],assessment_sha256=build.sha((out/'assessment.json').read_bytes()),
        failures=assessment['failures'],installed_unchanged=True,game_verified=False)
    (RELEASE/'qualification-measurements.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    print(json.dumps(record,indent=2))
    if assessment['failures']:raise SystemExit(1)


if __name__=='__main__':main()
