"""Dataset availability does NOT certify native SDK support for that game."""
import json
from pathlib import Path
import shutil
import unittest
import uuid
from unittest import mock

from core.navigation import map_data
from core.sdk import sdk_downloader


class Version161MapSupportTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(__file__).resolve().parent/'.tmp-map-compat'/('161-'+uuid.uuid4().hex)
        self.root.mkdir(parents=True)
        self.addCleanup(lambda:shutil.rmtree(self.root,ignore_errors=True))
        self.app=mock.patch.object(map_data,'app_dir',return_value=str(self.root));self.app.start();self.addCleanup(self.app.stop)
        self.index=mock.patch.object(map_data,'_index_cache',{k:dict(v) for k,v in map_data.COMPATIBILITY_DATASETS.items()})
        self.index.start();self.addCleanup(self.index.stop)

    def dataset(self,key='promods-2.84'):
        folder=self.root/'map-cache'/key;folder.mkdir(parents=True)
        for name in ('nodes','roads','prefabs','roadLooks','prefabDescriptions','graph'):
            (folder/('europe-'+name+'.json')).write_text('[]',encoding='utf-8')
        config=dict(schema_version=1,dataset_key=key,map_format=907,game_version_major_minor='1.61',
            generator=dict(library='TruckLib',trucklib_version='0.5.1'),generation_complete=True,
            validation=dict(valid=True),packages=[dict(sha256='a'*64)])
        if key.startswith('promods'):config['promods_version']='2.84'
        self.write(folder,config)
        return folder,config

    def write(self,folder,config):
        (folder/'config.json').write_text(json.dumps(config),encoding='utf-8')

    def test_distinct_game_mod_pairs_and_offline_selection(self):
        rows={r['key']:r for r in map_data.list_datasets()}
        self.assertEqual(rows['ets2-1.61']['game_version'],'1.61')
        self.assertEqual(rows['promods-2.84']['mod_version'],'2.84')
        self.assertEqual(map_data.suggest_key('1.61'),'ets2-1.61')
        self.assertEqual(map_data.suggest_key('1.61',prefer_promods=True),'promods-2.84')

    def test_complete_transactionally_validated_base_and_promods_accepted(self):
        for key in ('ets2-1.61','promods-2.84'):
            with self.subTest(key=key):
                self.dataset(key);self.assertTrue(map_data.is_downloaded(key))

    def test_wrong_game_or_promods_or_validation_rejected(self):
        folder,config=self.dataset()
        changes=(('game_version_major_minor','1.60'),('promods_version','2.83'),
            ('map_format',906),('generation_complete',False),('validation',{'valid':False}),
            ('packages',[{'sha256':'bad'}]),('dataset_key','promods-1.59'))
        for field,value in changes:
            with self.subTest(field=field):
                self.write(folder,dict(config,**{field:value}))
                self.assertFalse(map_data.is_downloaded('promods-2.84'))

    def test_missing_graph_and_partial_copy_never_ready(self):
        folder,_=self.dataset();(folder/'europe-graph.json').unlink()
        self.assertFalse(map_data.is_downloaded('promods-2.84'))

    def test_switch_preserves_promods_preference_without_crossing_versions(self):
        for key in ('ets2-1.61','promods-2.84'):self.dataset(key)
        rows=map_data.list_datasets()
        self.assertEqual(map_data.choose_downloaded_for_game(rows,'1.61','promods-1.59')['key'],'promods-2.84')
        self.assertIsNone(map_data.choose_downloaded_for_game(rows,'1.60','promods-2.84'))
        with mock.patch.object(map_data,'installed_ets2',return_value=('ETS2','1.60')):
            self.assertFalse(map_data.compatible_with_installed_game('promods-2.84')[0])

    def test_generator_is_separate_and_no_legacy_download_fallback(self):
        with mock.patch.object(map_data.requests,'get') as download:
            self.assertFalse(map_data.download('promods-2.84'))
            download.assert_not_called()

    def test_new_map_entry_does_not_whitelist_unsupported_native_dll(self):
        # Adding a dataset/source entry alone must not bypass the native gate.
        with mock.patch.object(sdk_downloader,'_dll_source_dir',return_value=str(self.root)):
            self.assertFalse(sdk_downloader.is_supported('1.61.1.9'))
        self.assertNotIn('alias',sdk_downloader.SOURCES['1.61'])

    def test_existing_dlls_do_not_falsely_confirm_161_support_or_get_overwritten(self):
        game=self.root/'ETS2';plugins=game/'bin/win_x64/plugins';plugins.mkdir(parents=True)
        for name in sdk_downloader.SDK_FILES:(plugins/name).write_bytes(b'original fixture')
        with mock.patch.object(sdk_downloader,'_dll_source_dir',return_value=str(self.root)), \
                mock.patch.object(sdk_downloader,'_ensure_dlls_local') as install:
            for force in (False,True):
                self.assertEqual(sdk_downloader.ensure_installed(str(game),'1.61.1.9',force=force),
                    (False,'unsupported:1.61.1.9'))
            install.assert_not_called()
        for name in sdk_downloader.SDK_FILES:self.assertEqual((plugins/name).read_bytes(),b'original fixture')


if __name__=='__main__':unittest.main()
