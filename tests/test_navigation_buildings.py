"""Read-only building-layer identity, spatial-query and lifecycle regressions."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import json
import math
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from UI import building_layer as layer
from UI import map_page as mod
class NavigationBuildingTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def fixture(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        folder = root / 'promods-2.84'
        folder.mkdir()
        path = folder / 'buildings.sqlite'
        c = sqlite3.connect(path)
        c.executescript('CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);CREATE TABLE building(id INTEGER PRIMARY KEY,uid TEXT,points TEXT,height REAL);CREATE VIRTUAL TABLE bounds USING rtree(id,minx,maxx,minz,maxz);')
        c.executemany('INSERT INTO metadata VALUES(?,?)', [('schema_version', '1'), ('dataset_key', 'promods-2.84'), ('dataset_fingerprint', 'a' * 24)])
        for i in range(12):
            x = i * 100
            c.execute('INSERT INTO building VALUES(?,?,?,?)', (i, str(i), json.dumps([[x, 0], [x + 10, 0], [x + 10, 10], [x, 10]]), 12 + i))
            c.execute('INSERT INTO bounds VALUES(?,?,?,?,?)', (i, x, x + 10, 0, 10))
        c.commit()
        c.close()
        return root

    def test_map_identity_must_match(self):
        root = self.fixture()
        self.assertEqual(layer.query_buildings(root, 'promods-2.84', 'b' * 24, (0, 0)), [])
        self.assertEqual(layer.query_buildings(root, '../promods-2.84', 'a' * 24, (0, 0)), [])
        self.assertEqual(layer.query_buildings(root, 'promods-2.84', 'unavailable', (0, 0)), [])

    def test_spatial_query_is_nearest_bounded_and_read_only(self):
        root = self.fixture()
        p = root / 'promods-2.84/buildings.sqlite'
        before = p.read_bytes()
        rows = layer.query_buildings(root, 'promods-2.84', 'a' * 24, (0, 0), 300, 3)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]['uid'], '0')
        self.assertEqual(rows[0]['height'], 12)
        self.assertEqual(p.read_bytes(), before)

    def test_non_finite_positions_and_missing_layer_are_empty(self):
        root = self.fixture()
        self.assertEqual(layer.query_buildings(root, 'promods-2.84', 'a' * 24, (math.nan, 0)), [])
        self.assertEqual(layer.query_buildings(root, 'ets2-1.61', 'a' * 24, (0, 0)), [])

    def test_stale_worker_result_cannot_draw_previous_map(self):
        state = {'active_map_key': 'promods-2.84', 'active_dataset_fingerprint': 'a' * 24}
        v = mod.MapView(state)
        v._building_job_pending = True
        v._accept_buildings(((('other', 'b' * 24), (0, 0), 1000), [{'bad': 'old map'}]))
        self.assertFalse(v._building_job_pending)
        self.assertEqual(v._visual_buildings, [])

    def test_background_worker_loads_layer_without_blocking_or_mutating_state(self):
        from unittest.mock import patch
        root = self.fixture()
        base = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__('shutil').rmtree(base))
        import shutil
        (base / 'assets/map_buildings').mkdir(parents=True)
        shutil.copytree(root / 'promods-2.84', base / 'assets/map_buildings/promods-2.84')
        state = {'active_map_key': 'promods-2.84', 'active_dataset_fingerprint': 'a' * 24, 'truck_world_pos': (0, 0)}
        before = dict(state)
        v = mod.MapView(state)
        with patch('core.paths.app_dir', return_value=str(base)):
            v.refresh_buildings()
            deadline = time.monotonic() + 2
            while v._building_job_pending and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(0.005)
        self.assertFalse(v._building_job_pending)
        self.assertEqual(len(v._visual_buildings), 12)
        self.assertEqual(state, before)
        v.refresh_buildings()
        self.assertFalse(v._building_job_pending)
