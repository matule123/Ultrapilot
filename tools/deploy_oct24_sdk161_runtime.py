"""Explicit SDK 1.61 deployment with backups. No app/game/control startup.

Default is a read-only preflight. --apply is the user-authorized write step.
Only five app sources, the dedicated bundle, deployment metadata, and the
three SDK game targets are in scope. The diagnostic candidate is archived.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.sdk import versioned_sdk as sdk

APP=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')
GAME=Path(r'C:\Program Files (x86)\Steam\steamapps\common\Euro Truck Simulator 2')
PLUGINS=GAME/'bin/win_x64/plugins'
AUDIT=ROOT/'docs/steering-audit/oct22-sdk161'
PINS={
    'core/sdk/versioned_sdk.py':'8da36893781f89951b75f4a31dd905d496bdb6eca3228521159d3c8ff4ff10c0',
    'core/sdk/sdk_downloader.py':'a404f16aac0eef0e59c65dacbaefa1568f631b61a5cc2fa57e96163bf79fd0eb',
    'core/sdk/game_utils.py':'afe71b92e96229426e8a214d2fef1f25c14a34a2e2eda205f6b4a870a6a9e3f0',
    'core/navigation/map_data.py':'8c7e05428a5d1fb309745e01bc88b1f0bcfcc46a6398760816e67470ae6650c8',
    'ui/onboarding.py':'a70af4eef362419929788db48f3733102036a90fd2bee09e723139b9fd234e59',
}
DEPENDENCIES=('core/paths.py','core/sdk/existing_mapping.py','core/sdk/traffic_snapshot.py',
    'core/sdk/signal_snapshot.py','core/sdk/ets2la_data.py','core/navigation/road_network.py')
CANDIDATE='UltraPilot161ReadCandidate.dll'
CANDIDATE_HASH='cd5cabf8bbb55ee257c56ce9aa24442f14479bfe110207976911305e1dc5575c'


def hash_file(path):
    return sdk.sha256(path)


def require_stopped():
    import psutil
    sdk.require_game_stopped()
    for process in psutil.process_iter(['name','cmdline','cwd']):
        info=process.info;name=(info.get('name') or '').lower()
        if name.startswith('ultrapilot'):raise RuntimeError('UltraPilot is running')
        if not name.startswith(('python','pythonw','py.exe')):continue
        command=' '.join(info.get('cmdline') or []).lower()
        cwd=info.get('cwd') or ''
        if (str(APP).lower() in command or
                (cwd and Path(cwd).resolve()==APP.resolve() and
                 any(v in command for v in ('main.py','bootloader.py','-m main')))):
            raise RuntimeError('UltraPilot Python process is running')


def atomic_bytes(target,data):
    target.parent.mkdir(parents=True,exist_ok=True)
    fd,staged=tempfile.mkstemp(prefix=target.name+'.',suffix='.staging',dir=target.parent)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(data)
        os.replace(staged,target)
    finally:
        if os.path.exists(staged):os.unlink(staged)


def write_json(target,value):
    atomic_bytes(target,(json.dumps(value,indent=2,ensure_ascii=False)+'\n').encode('utf-8'))


def preflight():
    require_stopped()
    if not APP.is_dir() or not PLUGINS.is_dir():raise RuntimeError('Exact installation missing')
    folder,profile=sdk.load_bundle(str(ROOT/'assets'),'1.61')
    sdk.verify_game(str(GAME),profile)
    suite=(AUDIT/'oct24-runtime-full-suite.log').read_text(encoding='utf-8-sig')
    if '3128 passed, 1725 subtests passed' not in suite:raise RuntimeError('Full suite evidence missing')
    receipt_path=APP/'manual-deployment.json'
    receipt=json.loads(receipt_path.read_text(encoding='utf-8-sig'))
    for entry in receipt['files']:
        if hash_file(entry['target'])!=entry['sha256'].lower():
            raise RuntimeError('Previous deployment drift: '+entry['target'])
    for relative in DEPENDENCIES:
        if hash_file(APP/relative)!=hash_file(ROOT/relative):
            raise RuntimeError('Untested dependency mismatch: '+relative)
    for relative,expected in PINS.items():
        if hash_file(ROOT/relative)!=expected:raise RuntimeError('Tested source changed: '+relative)
    candidate=PLUGINS/CANDIDATE
    if not candidate.is_file() or hash_file(candidate)!=CANDIDATE_HASH:
        raise RuntimeError('Diagnostic candidate identity changed')
    bundle=Path(folder)
    if hash_file(bundle/'native-source.zip')!=profile['source_archive_sha256']:
        raise RuntimeError('Source archive changed')
    payload=list(PINS)+[p.relative_to(ROOT).as_posix() for p in sorted(bundle.iterdir()) if p.is_file()]
    if len(payload)!=15:raise RuntimeError('Unexpected runtime payload count')
    before={str(p):hash_file(p) for p in PLUGINS.glob('*.dll')}
    for relative in ('settings.json',*(f'assets/{name}' for name in sdk.FILES)):
        before[str(APP/relative)]=hash_file(APP/relative)
    return receipt,profile,payload,before


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    receipt,profile,payload,before=preflight()
    if not args.apply:
        print(json.dumps(dict(preflight_pass=True,app_files=payload,
            previous_receipt_files=len(receipt['files']),protected_files=len(before)-2,
            archive_diagnostic=CANDIDATE,keep_read_only_probe=True,
            game_dll_sha256=profile['files'],settings_and_map_unchanged=True,
            deployed=False),indent=2));return
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup=AUDIT/('runtime-deploy-'+stamp);backup.mkdir(exist_ok=False)
    original={}
    for relative in payload+['manual-deployment.json']:
        target=APP/relative
        if not target.resolve().is_relative_to(APP.resolve()):raise ValueError('Unsafe app target')
        previous=hash_file(target) if target.exists() else None
        original[relative]=previous
        if previous:
            saved=backup/'app'/relative;saved.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(target,saved)
            if hash_file(saved)!=previous:raise RuntimeError('Backup mismatch: '+relative)
    for name in sdk.FILES:
        source=PLUGINS/name;saved=backup/'game'/name;saved.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,saved)
        if hash_file(saved)!=hash_file(source):raise RuntimeError('Game backup mismatch: '+name)
    archived=backup/'diagnostics'/CANDIDATE;archived.parent.mkdir()
    shutil.copy2(PLUGINS/CANDIDATE,archived)
    if hash_file(archived)!=CANDIDATE_HASH:raise RuntimeError('Candidate backup mismatch')
    state=dict(status='backed_up',deployed=False,backup_directory=str(backup),
        original_app_sha256=original,original_game_and_settings_sha256=before,
        full_suite_log_sha256=hash_file(AUDIT/'oct24-runtime-full-suite.log'),
        controls_written=False,game_started=False,app_started=False,game_verified=False)
    write_json(backup/'receipt.json',state)
    changed=[]
    try:
        require_stopped()
        for relative in payload:
            data=(ROOT/relative).read_bytes();expected=hashlib.sha256(data).hexdigest()
            atomic_bytes(APP/relative,data);changed.append(relative)
            if hash_file(APP/relative)!=expected:raise RuntimeError('Copy mismatch: '+relative)
        require_stopped()
        # Exact single file, with verified recoverable copy outside plugins.
        (PLUGINS/CANDIDATE).unlink()
        installed=sdk.install_bundle(str(GAME),str(APP/'assets'),'1.61')
        if not installed[0]:raise RuntimeError('SDK installation failed')
        for name,expected in profile['files'].items():
            if hash_file(PLUGINS/name)!=expected:raise RuntimeError('Installed DLL mismatch: '+name)
        changed_game=str(PLUGINS/'ets2la_plugin.dll')
        for name,expected in before.items():
            if name in (str(PLUGINS/CANDIDATE),changed_game):continue
            if hash_file(name)!=expected:raise RuntimeError('Unrelated file changed: '+name)
        # Preserve unrelated receipt entries; refresh only exact deployed targets.
        entries={str(Path(e['target'])).lower():e for e in receipt['files']}
        deployed=[]
        for relative in payload:
            target=APP/relative
            entry=dict(relative_path=relative,source=str(ROOT/relative),target=str(target),
                sha256=hash_file(target),previous_sha256=original[relative],
                backup_name='app/'+relative if original[relative] else None)
            entries[str(target).lower()]=entry;deployed.append(entry)
        for name in sdk.FILES:
            target=PLUGINS/name
            entry=dict(relative_path='game-sdk/1.61/'+name,
                source=str(APP/'assets/sdk/1.61'/name),target=str(target),sha256=hash_file(target),
                previous_sha256=before[str(target)],backup_name='game/'+name)
            entries[str(target).lower()]=entry;deployed.append(entry)
        payload_id=hashlib.sha256(json.dumps([(e['target'],e['sha256']) for e in deployed],
            sort_keys=True).encode('utf-8')).hexdigest()
        receipt.update(files=list(entries.values()),prior_receipt_sha256=original['manual-deployment.json'],
            previous_backup_directory=receipt.get('backup_directory'),backup_directory=str(backup),
            deployed_at_utc=stamp,deployment_scope='sdk161-read-side-stationary-test',
            date=datetime.now(timezone.utc).date().isoformat(),changed_files=payload,
            previous_payload_content_id=receipt.get('candidate_sha256'),candidate_sha256=payload_id,
            dll_version=profile['native_version'],game_verified=False,task_complete=False,
            test_phase='standard-name stationary check pending',
            full_pytest='SDK source workspace: 3128 PASSED; 1725 SUBTESTS PASSED',
            settings_and_map_unchanged=True)
        write_json(APP/'manual-deployment.json',receipt);changed.append('manual-deployment.json')
        for entry in receipt['files']:
            if hash_file(entry['target'])!=entry['sha256'].lower():raise RuntimeError('Final receipt mismatch')
        state.update(status='deployed',deployed=True,files=deployed,
            archived_diagnostic=str(archived),read_only_probe_retained=True,
            installed_receipt_sha256=hash_file(APP/'manual-deployment.json'),
            verified_receipt_files=len(receipt['files']),settings_and_map_unchanged=True)
        write_json(backup/'receipt.json',state)
    except BaseException as error:
        # Restore only exact targets of this deployment. Never recursively delete.
        for name in sdk.FILES:
            atomic_bytes(PLUGINS/name,(backup/'game'/name).read_bytes())
        atomic_bytes(PLUGINS/CANDIDATE,archived.read_bytes())
        for relative in reversed(changed):
            if original[relative]:atomic_bytes(APP/relative,(backup/'app'/relative).read_bytes())
            elif (APP/relative).exists():(APP/relative).unlink()
        state.update(status='rolled_back',deployed=False,error=repr(error))
        write_json(backup/'receipt.json',state)
        raise
    print(json.dumps(dict(deployed=True,app_payload_files=len(payload),
        game_dll_sha256=profile['files'],verified_receipt_files=len(receipt['files']),
        backup_directory=str(backup),archived_diagnostic=str(archived),
        settings_and_map_unchanged=True,game_verified=False,
        app_started=False,game_started=False),indent=2))


if __name__=='__main__':main()
