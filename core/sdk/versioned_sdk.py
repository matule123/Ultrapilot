"""Strict version-specific native data-producer bundles.

A supported bundle is not a certificate for autonomous driving. 1.61 is
restricted to the exact verified EXE and single-player read-side contract.
No default/legacy DLL fallback is permitted for a versioned bundle.
"""
import hashlib
import json
import os
import re

VERSIONED_VERSIONS=frozenset({'1.61'})
FILES=('scs-telemetry.dll','scs_sdk_controller.dll','ets2la_plugin.dll')
_SHA=re.compile(r'^[0-9a-f]{64}$')


class BundleError(ValueError):
    pass


def major_minor(version):
    return '.'.join(str(version or '').strip().split('.')[:2])


def sha256(path):
    digest=hashlib.sha256()
    with open(path,'rb') as source:
        for block in iter(lambda:source.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def load_bundle(assets_dir,version):
    version=major_minor(version)
    if version not in VERSIONED_VERSIONS:raise BundleError('not_versioned')
    folder=os.path.join(assets_dir,'sdk',version)
    manifest=os.path.join(folder,'manifest.json')
    try:
        if os.path.getsize(manifest)>65536:raise BundleError('manifest_too_large')
        with open(manifest,encoding='utf-8') as source:profile=json.load(source)
        if (not isinstance(profile,dict) or profile.get('schema')!=1
                or profile.get('game_version')!=version or profile.get('game')!='ETS2'
                or profile.get('native_controls_enabled') is not False
                or profile.get('control_backend')!='SCS_SDK'
                or profile.get('non_ai_multiplayer_motion_supported') is not False
                or profile.get('validation',{}).get('stationary_candidate_live_pass') is not True):
            raise BundleError('manifest_contract')
        if set(profile.get('files',{}))!=set(FILES):raise BundleError('manifest_files')
        images=profile.get('game_exe_sha256')
        if not isinstance(images,list) or not images or any(not _SHA.fullmatch(str(v)) for v in images):
            raise BundleError('manifest_game_hashes')
        for name,digest in profile['files'].items():
            if not _SHA.fullmatch(str(digest)) or sha256(os.path.join(folder,name))!=digest:
                raise BundleError('bundle_hash:'+name)
        return folder,profile
    except BundleError:raise
    except (OSError,ValueError,TypeError,AttributeError) as error:
        raise BundleError('bundle_unavailable') from error


def verify_game(game_path,profile):
    try:
        image=os.path.join(game_path,'bin','win_x64','eurotrucks2.exe')
        if sha256(image) not in profile['game_exe_sha256']:raise BundleError('unsupported_game_exe')
    except OSError as error:raise BundleError('game_exe_unavailable') from error


def installed_matches(game_path,profile):
    plugins=os.path.join(game_path,'bin','win_x64','plugins')
    try:
        return all(sha256(os.path.join(plugins,name))==digest for name,digest in profile['files'].items())
    except OSError:return False


def require_game_stopped():
    # A locked DLL is too late: an earlier DLL may already have been replaced.
    try:
        import psutil
    except ImportError as error:
        raise BundleError('game_state_unavailable') from error
    try:
        for process in psutil.process_iter(['name']):
            try:
                if (process.info.get('name') or '').lower() in ('eurotrucks2.exe','amtrucks.exe'):
                    raise BundleError('game_running')
            except psutil.NoSuchProcess:
                continue
    except BundleError:raise
    except (OSError,psutil.Error) as error:
        raise BundleError('game_state_unavailable') from error


def install_bundle(game_path,assets_dir,version,*,force=False,log=None):
    """Explicitly requested install; all inputs checked before the first write.

Changed files use same-directory atomic replacement and recoverable originals.
No other plugins, diagnostics, settings or map files are modified.
"""
    import shutil
    import tempfile
    folder,profile=load_bundle(assets_dir,version);verify_game(game_path,profile)
    plugins=os.path.join(game_path,'bin','win_x64','plugins')
    if os.path.exists(os.path.join(plugins,'UltraPilot161ReadCandidate.dll')):
        raise BundleError('diagnostic_candidate_present')
    if installed_matches(game_path,profile) and not force:return True,'already'
    require_game_stopped()
    os.makedirs(plugins,exist_ok=True)
    changed=[]
    try:
        for name,digest in profile['files'].items():
            target=os.path.join(plugins,name)
            if os.path.exists(target) and sha256(target)==digest:continue
            # Never silently rewrite a prior backup on repeated repair.
            backup=None
            if os.path.exists(target):
                old=sha256(target);backup=target+'.ultrapilot-backup-'+old
                if not os.path.exists(backup):shutil.copy2(target,backup)
                if sha256(backup)!=old:raise BundleError('backup_hash:'+name)
            fd,staged=tempfile.mkstemp(prefix=name+'.',suffix='.staging',dir=plugins)
            os.close(fd)
            try:
                shutil.copy2(os.path.join(folder,name),staged)
                if sha256(staged)!=digest:raise BundleError('staging_hash:'+name)
                os.replace(staged,target)
            finally:
                if os.path.exists(staged):os.remove(staged)
            changed.append((target,backup))
        if not installed_matches(game_path,profile):raise BundleError('installed_hash')
    except BaseException:
        for target,backup in reversed(changed):
            if backup:shutil.copy2(backup,target)
            elif os.path.exists(target):os.remove(target)
        raise
    if log:log('SDK '+major_minor(version)+': exact EXE and all DLL hashes verified; SCS controls unchanged.')
    return True,'installed'
