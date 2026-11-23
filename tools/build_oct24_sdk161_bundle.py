"""Package verified inputs under assets/sdk/1.61. Never deploys into a game."""
import hashlib
import json
from pathlib import Path
import shutil
import zipfile
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.prepare_oct24_sdk161_runtime import transform
AUDIT=ROOT/'docs/steering-audit/oct22-sdk161'
RUNTIME=AUDIT/'read-runtime-a'
OUTPUT=ROOT/'assets/sdk/1.61'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if OUTPUT.exists():raise ValueError('Bundle already exists; preserve prior evidence')
    build=json.loads((RUNTIME/'build-receipt.json').read_text())
    for name,expected in build['files'].items():
        if digest(RUNTIME/name)!=expected:raise ValueError('Runtime changed: '+name)
    candidate=AUDIT/'read-candidate-e'
    candidate_receipt=json.loads((candidate/'build-receipt.json').read_text())
    for name,expected in candidate_receipt['files'].items():
        original=candidate/name
        if digest(original)!=expected:raise ValueError('Candidate changed: '+name)
        if original.suffix in ('.cpp','.hpp'):
            if (RUNTIME/name).read_text(encoding='utf-8-sig')!=transform(original.read_text(encoding='utf-8-sig')):
                raise ValueError('Runtime acquisition logic changed: '+name)
    checked=json.loads((RUNTIME/'verification/result.json').read_text())
    if checked['candidate_dll_sha256']!=build['dll_sha256']:raise ValueError('Unchecked DLL')
    sentinel=json.loads((RUNTIME/'sentinel-regression/result.json').read_text())
    if sentinel['after_exception'] is not None or not sentinel['nonempty_rejected']:
        raise ValueError('Sentinel regression did not pass')
    inputs=json.loads((AUDIT/'inputs/receipt.json').read_text())
    evidence={}
    # Recheck the actual stationary reader captures; do not equate them with a drive.
    captures={
        'stationary':'candidate-e-live-3380-1792850918128057400.json',
        'route_changed':'candidate-e-live-3380-1792851664829228300.json',
        'route_cancelled':'candidate-e-live-3380-1792852334484744400.json',
        'profile_reloaded':'candidate-e-live-3380-1792852868218253700.json',
    }
    for event,name in captures.items():
        capture=json.loads((AUDIT/name).read_text())
        records=capture['records']
        if (not capture['read_only'] or capture['controls_written'] or len(records)<16
                or not all(r['traffic']['valid'] and r['signal']['valid'] for r in records)):
            raise ValueError('Invalid live evidence: '+name)
        evidence[event]={'file':name,'sha256':digest(AUDIT/name),'samples':len(records)}
    OUTPUT.mkdir(parents=True)
    for name in ('scs-telemetry.dll','scs_sdk_controller.dll'):
        source=AUDIT/'inputs/official161'/name
        expected=next(r['sha256'] for r in inputs['artifacts'] if Path(r['path']).name==name)
        if digest(source)!=expected:raise ValueError('Pinned SCS input changed: '+name)
        shutil.copy2(source,OUTPUT/name)
    shutil.copy2(RUNTIME/'ets2la_plugin.dll',OUTPUT/'ets2la_plugin.dll')
    for source,name in ((RUNTIME/'LICENSE.md','producer-LICENSE.md'),
            (RUNTIME/'vendor/scs_sdk/sdk_license.txt','SCS-SDK-LICENSE.txt'),
            (RUNTIME/'FMT_LICENSE','FMT-LICENSE.txt'),
            (AUDIT/'inputs/official161/sources.txt','upstream-sources.txt')):
        shutil.copy2(source,OUTPUT/name)
    # Include the modified native source, headers, licenses and a portable build
    # command with the binary; the audit directory is not part of app releases.
    with zipfile.ZipFile(OUTPUT/'native-source.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for folder in ('src','vendor/scs_sdk'):
            for path in sorted((RUNTIME/folder).rglob('*')):
                if path.is_file():archive.write(path,path.relative_to(RUNTIME).as_posix())
        for name in ('ets2la_plugin.def','LICENSE.md','FMT_LICENSE','build-receipt.json'):
            archive.write(RUNTIME/name,name)
        fmt=ROOT/'docs/steering-audit/signal-plugin-20261003/fmt/include'
        for path in sorted(fmt.rglob('*')):
            if path.is_file():archive.write(path,'fmt/include/'+path.relative_to(fmt).as_posix())
        sources=[p.relative_to(RUNTIME).as_posix() for p in (RUNTIME/'src').rglob('*.cpp')
            if p.name!='memory_utils.linux.cpp']
        archive.writestr('build.cmd','@echo off\r\nrem Run from a Visual Studio x64 Native Tools prompt.\r\n'
            +'cl /nologo /LD /O2 /MT /std:c++17 /EHsc /utf-8 /Brepro '
            +'/DFMT_HEADER_ONLY /DETS2LA_PLUGIN_EXPORTS /DUNICODE /D_UNICODE /DUP_SIGNAL_SCOPE_V3 '
            +'/Isrc /Ivendor/scs_sdk/include /Ifmt/include '+' '.join(sources)
            +' /link /DEF:ets2la_plugin.def /Brepro /OUT:ets2la_plugin.dll\r\n')
    manifest=dict(schema=1,game='ETS2',game_version='1.61',native_version=build['version'],
        game_exe_sha256=[build['game_sha256']],native_controls_enabled=False,
        control_backend='SCS_SDK',non_ai_multiplayer_motion_supported=False,
        files={p.name:digest(p) for p in OUTPUT.glob('*.dll')},
        source_archive_sha256=digest(OUTPUT/'native-source.zip'),
        provenance=dict(upstream_commit=inputs['gitlab_commit'],scs_bundle_commit=inputs['github_commit'],
            candidate_e_sha256=build['derived_from_candidate_sha256'],
            build_receipt_sha256=digest(RUNTIME/'build-receipt.json')),
        validation=dict(stationary_candidate_live_pass=True,standard_name_live_pass=False,
            autonomous_driving_verified=False,native_host_pass=True,sentinel_regression_pass=True,
            captures=evidence))
    (OUTPUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(manifest,indent=2))


if __name__=='__main__':main()
