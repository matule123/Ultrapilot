"""Prepare and rehash a coherent candidate ZIP; never write an installation."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
RUNTIME=(
    'core/acc_acceleration.py', 'core/acc_body_prediction.py', 'core/acc_following.py',
    'core/engine.py', 'core/control_timing.py', 'core/longitudinal.py', 'core/pid.py', 'core/service_brake_hold.py',
    'core/navigation/traffic_producer.py', 'core/navigation/longitudinal_diagnostics.py',
    'core/sdk/traffic_snapshot.py', 'core/sdk/scs_sdk.py', 'core/telemetry.py',
    'plugins/acc/main.py', 'plugins/drivepolicy/main.py',
    'PLUGIN_CHANGELOG.md',
)


def prepare(output, test_log):
    if not output.resolve().is_relative_to(ROOT/'docs/steering-audit'):
        raise ValueError('Candidate must remain in workspace audit directory')
    if output.exists():raise ValueError('Use a new ZIP; never overwrite a candidate')
    native=ROOT/'docs/steering-audit/oct14-completion/native-candidate-c'
    receipt=json.loads((native/'build-receipt.json').read_text())
    dll=(native/'ets2la_plugin.dll').read_bytes()
    sha=lambda data:hashlib.sha256(data).hexdigest()
    if sha(dll)!=receipt['dll_sha256']:raise ValueError('Native build receipt mismatch')
    for path,digest in receipt['files'].items():
        if sha((native/path).read_bytes())!=digest:raise ValueError('Native source/artifact mismatch: '+path)
    log=test_log.read_text(errors='replace')
    if 'failed' in log.lower() or 'passed' not in log or '[100%]' not in log:
        raise ValueError('Final complete pytest PASS is required before packaging')
    verified=json.loads(test_log.with_suffix('.verified.json').read_text())
    if verified.get('exit_code') != 0 or verified.get('log_sha256') != sha(test_log.read_bytes()):
        raise ValueError('Complete verification receipt does not match the test log')
    for name in RUNTIME:
        if verified.get('runtime_sha256',{}).get(name) != sha((ROOT/name).read_bytes()):
            raise ValueError('Runtime changed after full verification: '+name)
    installation=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')
    deployed_receipt=(installation/'manual-deployment.json').read_bytes()
    deployed=json.loads(deployed_receipt.decode('utf-8-sig'))
    for row in deployed['files']:
        if sha(Path(row['target']).read_bytes()) != row['sha256'].lower():
            raise ValueError('Base installation changed since its receipt: '+row['target'])
    from core.app_release import plugin_versions
    versions=plugin_versions(ROOT)
    payload={'runtime/'+name:(ROOT/name).read_bytes() for name in RUNTIME}
    payload['runtime/assets/ets2la_plugin.dll']=dll
    payload['game-plugin/ets2la_plugin.dll']=dll
    manifest=dict(schema=1,kind='candidate_not_deployment',runtime_authorized=False,
        scope='oct14-roundabout-traffic-intervention',
        supersedes_candidate='oct14-v4',native_changed=False,
        source_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(),
        working_tree_uncommitted=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT)),
        versions=dict(acc=versions['acc'],drivepolicy=versions['drivepolicy'],native='1.59.4-up-traffic-timed'),
        verified_base_receipt_sha256=sha(deployed_receipt),
        verified_base_installed_files=len(deployed['files']),
        native_build_recipe_sha256=sha((ROOT/'tools/build_signal_plugin.py').read_bytes()),
        full_pytest_log_sha256=sha(test_log.read_bytes()),native_build_receipt=receipt,
        files=[dict(path=name,sha256=sha(content),size=len(content)) for name,content in payload.items()],
        deployment_requirements=['Separate user approval, both applications off, whole-set rollback backup',
            'Install runtime payload and the same DLL into the already receipt-identified game plugin location',
            'Preserve settings/map-cache/diagnostic records/commit marker; verify every installed hash'],
        blockers=['Historical first emergency actor poses/bodies were not retained; synthetic reproduction is not that source frame',
            'New behavior has no ETS2 game verification; requires separately approved deployment',
            'Normal significant-event quota is full; old originals require approved archival, automatic fault export remains available',
            'Certified coverage/full swept envelope and calibrated load mapping are not claimed',
            'Native GPS-arrival work remains unavailable and cancelled; it is outside this candidate task'],
        game_verified=False)
    with zipfile.ZipFile(output,'x',zipfile.ZIP_DEFLATED) as archive:
        for name,content in payload.items():archive.writestr(name,content)
        archive.writestr('candidate-manifest.json',json.dumps(manifest,indent=2)+'\n')
        for name in ('LICENSE.md','FMT_LICENSE'):
            archive.writestr('licenses/native-'+name,(native/name).read_bytes())
    with zipfile.ZipFile(output) as archive:
        for row in manifest['files']:
            if sha(archive.read(row['path']))!=row['sha256']:raise ValueError('ZIP readback hash mismatch')
    output.with_suffix('.manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(zip=str(output),sha256=sha(output.read_bytes()),runtime_files=len(payload),
        source_head=manifest['source_head'],uncommitted=True,installed=False),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--verification-log',type=Path,required=True)
    args=p.parse_args();prepare(args.output.resolve(),args.verification_log.resolve())
