"""Copy/verify the completed 1.61/2.84 map, then select it with app closed.

Keeps source and old map. Never launches the app/game or writes controls.
No recursive deletion; failed staging data stays outside the selected key.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
APP=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')
SOURCE=Path(r'C:\Users\PC\Documents\GitHub\UltraPilot-MapConverter\build\UltraPilot-MapConverter-161-Progress-127-20261021\map-cache\promods-2.84')
TARGET=APP/'map-cache/promods-2.84'
AUDIT=ROOT/'docs/steering-audit/oct22-sdk161'


def sha(path):
    digest=hashlib.sha256()
    with open(path,'rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def app_stopped():
    import psutil
    for process in psutil.process_iter(['name','cmdline','cwd']):
        info=process.info;name=(info.get('name') or '').lower()
        command=' '.join(info.get('cmdline') or []).lower()
        cwd=info.get('cwd') or ''
        if (name.startswith('ultrapilot') or
                (name.startswith(('python','pythonw','py.exe')) and
                 (str(APP).lower() in command or
                  (cwd and Path(cwd).resolve()==APP.resolve() and
                   any(v in command for v in ('main.py','bootloader.py','-m main')))))):
            raise RuntimeError('Close UltraPilot before map installation')


def atomic_bytes(path,data):
    fd,staged=tempfile.mkstemp(prefix=path.name+'.',suffix='.staging',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(data)
        os.replace(staged,path)
    finally:
        if os.path.exists(staged):os.unlink(staged)


def save(path,value):
    atomic_bytes(path,(json.dumps(value,indent=2,ensure_ascii=False)+'\n').encode('utf-8'))


def main():
    started=time.monotonic();app_stopped()
    if TARGET.exists():raise RuntimeError('Destination already exists; refusing overwrite')
    if TARGET.resolve().parent!=(APP/'map-cache').resolve():raise RuntimeError('Unsafe map target')
    config=json.loads((SOURCE/'config.json').read_text(encoding='utf-8'))
    if (config['dataset_key']!='promods-2.84' or config['game_version_major_minor']!='1.61'
            or config['promods_version']!='2.84' or config['map_format']!=907
            or config['generation_complete'] is not True or config['validation']['valid'] is not True):
        raise RuntimeError('Wrong or incomplete dataset')
    hashes=config['validation']['output_sha256']
    if len(hashes)!=21:raise RuntimeError('Expected 21 validated data files')
    files=sorted(SOURCE.iterdir())
    if any(not p.is_file() or p.is_symlink() for p in files):raise RuntimeError('Unexpected dataset structure')
    total=sum(p.stat().st_size for p in files)
    if shutil.disk_usage(APP).free<total+1024**3:raise RuntimeError('Insufficient free disk space')
    for name,expected in hashes.items():
        if Path(name).name!=name or sha(SOURCE/name)!=expected:
            raise RuntimeError('Source hash mismatch: '+name)
    all_hashes={p.name:sha(p) for p in files}
    settings_path=APP/'settings.json';receipt_path=APP/'manual-deployment.json'
    settings_raw=settings_path.read_bytes();metadata_raw=receipt_path.read_bytes()
    settings=json.loads(settings_raw.decode('utf-8-sig'))
    if settings.get('autopilot',{}).get('enabled') is not False:
        raise RuntimeError('Expected autopilot disabled in saved settings')
    metadata=json.loads(metadata_raw.decode('utf-8-sig'))
    for entry in metadata['files']:
        if sha(entry['target'])!=entry['sha256'].lower():raise RuntimeError('Runtime receipt drift')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup=AUDIT/('map-install-'+stamp);backup.mkdir(exist_ok=False)
    shutil.copy2(settings_path,backup/'settings.json')
    shutil.copy2(receipt_path,backup/'manual-deployment.json')
    if sha(backup/'settings.json')!=sha(settings_path):raise RuntimeError('Settings backup mismatch')
    stage=TARGET.parent/('.promods-2.84-install-'+stamp);stage.mkdir(exist_ok=False)
    info=dict(status='copying',source=str(SOURCE),target=str(TARGET),staging=str(stage),
        backup_directory=str(backup),bytes=total,source_files_sha256=all_hashes,
        prior_selected_map=settings.get('selected_map'),old_map_preserved=True,
        game_started=False,app_started=False,controls_written=False,game_verified=False)
    save(backup/'receipt.json',info)
    activated=False
    try:
        for index,source in enumerate(files,1):
            destination=stage/source.name;shutil.copy2(source,destination)
            if sha(destination)!=all_hashes[source.name]:raise RuntimeError('Copy hash mismatch: '+source.name)
            print(f'Copied and verified {index}/{len(files)}: {source.name}',flush=True)
        if sha(SOURCE/'config.json')!=all_hashes['config.json']:
            raise RuntimeError('Source changed during copy')
        app_stopped()
        # Same-directory publish; destination is absent and old map untouched.
        stage.rename(TARGET)
        sys.path.insert(0,str(APP))
        from core.navigation import map_data
        from core.navigation.road_network import RoadNetwork,_uid
        assert Path(map_data.__file__).resolve().is_relative_to(APP.resolve())
        if not map_data.is_downloaded('promods-2.84'):raise RuntimeError('Installed readiness failed')

        class ReadOnlyNetwork(RoadNetwork):
            def _try_load_cache(self,*args,**kwargs):return False
            def _save_cache(self,*args,**kwargs):pass

        network=ReadOnlyNetwork()
        if not network.load(str(TARGET),progress_cb=lambda n,p:print(p,flush=True)):
            raise RuntimeError('Actual installed map loader failed')
        observed=dict(nodes=len(network.nodes),roads=len(network.segments),
            prefab_descriptions=len(network._prefab_desc),graph_nodes=len(set(network.fwd)|set(network.bwd)))
        for name,count in observed.items():
            if count!=config['counts'][name]:raise RuntimeError('Loaded count mismatch: '+name)
        capture=json.loads((AUDIT/'runtime-a-live-33960-1792861849638686300.json').read_text())
        route=capture['records'][0]['route_untimed']
        anchors={row['uid'] for row in route['first']+route['last']}
        missing=[uid for uid in anchors if _uid(uid) not in network.nodes]
        if missing:raise RuntimeError('GPS anchors absent in copied dataset: '+str(missing))
        if {p.name:sha(p) for p in TARGET.iterdir() if p.is_file()}!=all_hashes:
            raise RuntimeError('Dataset changed during load')
        app_stopped()
        if settings_path.read_bytes()!=settings_raw or receipt_path.read_bytes()!=metadata_raw:
            raise RuntimeError('Configuration changed concurrently; do not overwrite')
        selected=dict(settings,selected_map='promods-2.84')
        save(settings_path,selected);activated=True
        metadata['selected_map']='promods-2.84'
        metadata['map_deployment_receipt']=str(backup/'receipt.json')
        metadata['map_config_sha256']=all_hashes['config.json']
        metadata['map_game_version']='1.61';metadata['map_promods_version']='2.84'
        save(receipt_path,metadata)
        actual=json.loads(settings_path.read_text(encoding='utf-8'))
        if actual!=selected or {k:v for k,v in actual.items() if k!='selected_map'}!={k:v for k,v in settings.items() if k!='selected_map'}:
            raise RuntimeError('Unexpected settings mutation')
        info.update(status='installed_and_selected',selected_map='promods-2.84',
            installed_file_count=len(files),manifest_hashes_verified=len(hashes),
            actual_installed_loader=observed,gps_sample_anchors_present=len(anchors),
            settings_sha256=sha(settings_path),installed_receipt_sha256=sha(receipt_path),
            elapsed_s=time.monotonic()-started)
        save(backup/'receipt.json',info)
    except BaseException as error:
        if activated:
            atomic_bytes(settings_path,settings_raw);atomic_bytes(receipt_path,metadata_raw)
        info.update(status='failed_not_selected',error=repr(error),active_settings_restored=activated)
        save(backup/'receipt.json',info)
        raise
    print(json.dumps({k:v for k,v in info.items() if k!='source_files_sha256'},indent=2),flush=True)


if __name__=='__main__':main()
