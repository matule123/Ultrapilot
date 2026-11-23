"""Version-bound native integration. All installation writes use fake games."""
import hashlib
import json
from pathlib import Path
from unittest import mock
import zipfile

import pefile
import pytest

from core.sdk import game_utils, sdk_downloader, versioned_sdk as sdk

ROOT=Path(__file__).resolve().parents[2]


def digest(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def bundle(tmp_path,monkeypatch):
    assets=tmp_path/'assets';folder=assets/'sdk/1.61';folder.mkdir(parents=True)
    game=tmp_path/'ETS2';binary=game/'bin/win_x64';plugins=binary/'plugins';plugins.mkdir(parents=True)
    (binary/'eurotrucks2.exe').write_bytes(b'verified game fixture')
    files={}
    for name in sdk.FILES:
        data=('new '+name).encode();(folder/name).write_bytes(data);files[name]=digest(data)
        (assets/name).write_bytes(b'WRONG LEGACY DLL')
        (plugins/name).write_bytes(('old '+name).encode())
    profile=dict(schema=1,game='ETS2',game_version='1.61',native_controls_enabled=False,
        control_backend='SCS_SDK',non_ai_multiplayer_motion_supported=False,
        game_exe_sha256=[digest(b'verified game fixture')],files=files,
        validation=dict(stationary_candidate_live_pass=True))
    (folder/'manifest.json').write_text(json.dumps(profile))
    monkeypatch.setattr(sdk_downloader,'_dll_source_dir',lambda:str(assets))
    monkeypatch.setattr(game_utils,'get_version_for_game',lambda _: '1.61')
    monkeypatch.setattr(sdk,'require_game_stopped',lambda:None)
    return assets,folder,game,plugins,profile


def test_versioned_install_verifies_replaces_backs_up_and_leaves_other_files(bundle):
    assets,folder,game,plugins,profile=bundle
    (plugins/'other.dll').write_bytes(b'untouched')
    assert not sdk_downloader.is_sdk_installed(str(game))
    assert sdk_downloader.ensure_installed(str(game),'1.61.1.9')==(True,'installed')
    assert sdk_downloader.is_sdk_installed(str(game))
    assert sdk_downloader.ensure_installed(str(game),'1.61')==(True,'already')
    for name in sdk.FILES:
        old=('old '+name).encode()
        assert (plugins/name).read_bytes()==(folder/name).read_bytes()
        assert (plugins/(name+'.ultrapilot-backup-'+digest(old))).read_bytes()==old
    assert (plugins/'other.dll').read_bytes()==b'untouched'
    assert not list(plugins.glob('*.staging'))


@pytest.mark.parametrize('mutation,reason',[
    ('missing_manifest','unsupported:'),('wrong_dll','unsupported:'),
    ('wrong_game','failed:unsupported_game_exe'),('candidate','failed:diagnostic_candidate_present'),
    ('wrong_version','failed:game_version_mismatch'),('running','failed:game_running'),
])
@pytest.mark.parametrize('force',[False,True])
def test_invalid_inputs_never_write_or_fall_back(bundle,monkeypatch,mutation,reason,force):
    assets,folder,game,plugins,profile=bundle
    before={n:(plugins/n).read_bytes() for n in sdk.FILES}
    if mutation=='missing_manifest':(folder/'manifest.json').unlink()
    if mutation=='wrong_dll':(folder/'ets2la_plugin.dll').write_bytes(b'corrupted')
    if mutation=='wrong_game':(game/'bin/win_x64/eurotrucks2.exe').write_bytes(b'other patch')
    if mutation=='candidate':(plugins/'UltraPilot161ReadCandidate.dll').write_bytes(b'diagnostic')
    if mutation=='wrong_version':monkeypatch.setattr(game_utils,'get_version_for_game',lambda _: '1.59')
    if mutation=='running':
        def running():raise sdk.BundleError('game_running')
        monkeypatch.setattr(sdk,'require_game_stopped',running)
    with mock.patch.object(sdk_downloader,'_ensure_dlls_local') as legacy:
        ok,message=sdk_downloader.ensure_installed(str(game),'1.61.1.9',force=force)
        assert not ok and message.startswith(reason),message
        legacy.assert_not_called()
    assert before=={n:(plugins/n).read_bytes() for n in sdk.FILES}
    assert not list(plugins.glob('*.staging'))
    assert not list(plugins.glob('*.ultrapilot-backup-*'))


@pytest.mark.parametrize('field,value',[
    ('native_controls_enabled',True),('game','ATS'),('game_version','1.59'),
    ('non_ai_multiplayer_motion_supported',True),('control_backend','native'),
    ('validation',{}),('files',{'../escape.dll':'a'*64}),('game_exe_sha256',[]),
])
def test_bad_manifest_contract_rejected(bundle,field,value):
    assets,folder,game,plugins,profile=bundle
    profile[field]=value;(folder/'manifest.json').write_text(json.dumps(profile))
    with pytest.raises(sdk.BundleError):sdk.load_bundle(str(assets),'1.61')


def test_boot_uses_versioned_bundle_not_legacy_root(bundle,monkeypatch):
    assets,folder,game,plugins,profile=bundle
    monkeypatch.setattr(game_utils,'find_scs_games',lambda:[str(game)])
    assert game_utils.install_game_dlls(str(assets))==[str(plugins)]
    assert sdk.installed_matches(str(game),profile)
    # Subsequent boots are no-ops, not timestamp rewrites.
    with mock.patch('shutil.copy2') as copy:
        assert game_utils.install_game_dlls(str(assets))==[str(plugins)]
        copy.assert_not_called()


def test_boot_and_legacy_helper_cannot_downgrade_161(bundle,monkeypatch):
    assets,folder,game,plugins,profile=bundle
    monkeypatch.setattr(game_utils,'find_scs_games',lambda:[str(game)])
    before={n:(plugins/n).read_bytes() for n in sdk.FILES}
    assert game_utils.install_game_dlls(str(assets),names=['ets2la_plugin.dll'])==[]
    assert game_utils.install_telemetry_dll(str(assets/'scs-telemetry.dll'))==[]
    assert sdk_downloader.ensure_installed(str(game),'1.59')==(False,'failed:game_version_mismatch')
    (folder/'manifest.json').unlink()
    assert game_utils.install_game_dlls(str(assets))==[]
    assert before=={n:(plugins/n).read_bytes() for n in sdk.FILES}


def test_partial_failure_rolls_back_prior_replacements(bundle,monkeypatch):
    assets,folder,game,plugins,profile=bundle
    before={n:(plugins/n).read_bytes() for n in sdk.FILES}
    replace=sdk.os.replace;calls=[]
    def fail_second(source,target):
        calls.append(target)
        if len(calls)==2:raise PermissionError('fixture locked DLL')
        return replace(source,target)
    monkeypatch.setattr(sdk.os,'replace',fail_second)
    result=sdk_downloader.ensure_installed(str(game),'1.61')
    assert not result[0] and 'fixture locked DLL' in result[1]
    assert before=={n:(plugins/n).read_bytes() for n in sdk.FILES}
    assert not list(plugins.glob('*.staging'))


def test_game_process_guard_is_read_only_and_refuses_running_game():
    import psutil
    process=mock.Mock(info={'name':'eurotrucks2.exe'})
    with mock.patch.object(psutil,'process_iter',return_value=[process]):
        with pytest.raises(sdk.BundleError,match='game_running'):sdk.require_game_stopped()
    with mock.patch.object(psutil,'process_iter',side_effect=psutil.AccessDenied()):
        with pytest.raises(sdk.BundleError,match='game_state_unavailable'):sdk.require_game_stopped()


def test_shipped_bundle_hashes_sources_exports_and_honest_validation():
    folder,profile=sdk.load_bundle(str(ROOT/'assets'),'1.61.1.9')
    folder=Path(folder)
    assert sdk_downloader.is_supported('1.61.1.9')
    assert not sdk_downloader._resolve('1.62')
    assert not sdk_downloader._ensure_dlls_local('1.61',str(folder))
    assert 'alias' not in sdk_downloader.SOURCES['1.61']
    assert not profile['validation']['standard_name_live_pass']
    assert not profile['validation']['autonomous_driving_verified']
    assert sdk.sha256(folder/'native-source.zip')==profile['source_archive_sha256']
    with zipfile.ZipFile(folder/'native-source.zip') as source:
        assert 'build.cmd' in source.namelist()
        core=source.read('src/core.cpp').decode('utf-8-sig')
        assert 'void CCore::override_inputs() const {}' in core
        assert 'this->override_inputs();' not in core
        assert 'UltraPilot161Candidate' not in core
    data=(folder/'ets2la_plugin.dll').read_bytes()
    exports=pefile.PE(data=data).DIRECTORY_ENTRY_EXPORT.symbols
    assert {e.name for e in exports}=={b'scs_telemetry_init',b'scs_telemetry_shutdown'}
    for name in ('Local\\UltraPilotTrafficV1','Local\\UltraPilotSemaphoreV3','ETS2LARoute'):
        assert (name+'\0').encode('utf-16le') in data
    assert b'UltraPilot161Candidate' not in data
