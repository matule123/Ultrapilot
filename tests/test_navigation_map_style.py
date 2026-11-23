"""Display-only regression checks for the navigation-map renderer."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest
import math
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPainter, QImage
from UI import map_page as mod

class NavigationMapStyleTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_polygon_metadata_and_covering_viewport(self):
        view = mod.MapView({})
        view.set_scene_polygons([[[[-1000, -1000], [1000, -1000], [1000, 1000], [-1000, 1000]], 3, 0], [[[0, 0], [20, 0], [20, 15], [0, 15]], 1, 2, 'building', 18]])
        self.assertEqual(view.scene_polygons[0]['bounds'], (-1000, 1000, -1000, 1000))
        self.assertEqual(view.scene_polygons[1]['kind'], 'building')
        self.assertEqual(view.scene_polygons[1]['height'], 18)
        view.set_scene_polygons([[[[0, 0], [1, 0], [1, 1]], 1, 0, 'building', 'bad']])
        self.assertEqual(view.scene_polygons, [])

    def test_bounded_finite_geometry_and_continuous_runs(self):
        view = mod.MapView({})
        payload = [[[float(i), 0, 0], [float(i + 1), 0, 0], 'road', 2, False, True, False, False, 5, False, 'r1', i, 'local'] for i in range(1000)]
        view.set_road_segments(payload)
        self.assertEqual(len(view._road_runs), 1)
        self.assertEqual(len(view._road_runs[0][3]), 1001)
        payload[0][0][0] = math.nan
        view.set_road_segments(payload)
        self.assertEqual(len(view.road_segments), 999)

    def test_path_traversal_is_not_an_asset_token(self):
        view = mod.MapView({})
        view.set_scene_features([[0, 0, 'company', '../../private', 'bad'], [0, 0, 'company', 'test_token', 'Test']])
        self.assertNotIn('../../private', view._feature_logos)
        self.assertIn('test_token', view._feature_logos)

    def test_open_bent_roads_do_not_fill_their_enclosed_land(self):
        view = mod.MapView({'truck_world_pos': (0, 0)})
        view._perspective = False
        view.resize(500, 500)
        view.zoom_radius = 200
        view.set_road_segments([[[-130, -100, 0], [130, -100, 0], 'road', 2, False, True, False, False, 4, False, 'r', 0, 'local'], [[130, -100, 0], [130, 100, 0], 'road', 2, False, True, False, False, 4, False, 'r', 1, 'local']])
        img = QImage(view.size(), QImage.Format.Format_ARGB32)
        p = QPainter(img)
        view.render(p)
        p.end()
        self.assertEqual(img.pixelColor(300, 220).name(), view._map_palette()['land'].lower())

    def test_route_freshness_and_heading_invariant(self):
        state = {'game_gps_navigation_active': True, 'nav_path': [[0, 0], [10, 10]], 'lane_trajectory': {'valid': False}}
        self.assertEqual(mod.live_map_navigation_points(state), [])
        from PyQt6.QtCore import QPointF
        p = mod.MapView._truck_marker_polygon(QPointF(100, 100), 0)
        self.assertLess(p[0].y(), 100)

    def test_all_poi_symbols_render_both_themes_without_changing_state(self):
        state = {'truck_world_pos': (0, 0), 'truck_heading': 0.25, 'game_route_time': 900, 'game_route_distance': 15000}
        view = mod.MapView(state)
        view.resize(1100, 700)
        view.set_road_segments([[[-100, 0, 0], [100, 0, 0], 'road', 2]])
        view.set_scene_features([[i * 50 - 200, 40, 'facility', icon, icon] for i, icon in enumerate(['gas', 'parking', 'service', 'ferry', 'train', 'toll', 'viewpoint', 'recruit', 'rest'])] + [[0, -40, 'company', 'warehouse', 'Warehouse'], [0, -110, 'city', '', 'Town']])
        view.set_scene_polygons([[[[-30, -50], [30, -50], [30, -20], [-30, -20]], 1, 2, 'building', 15]])
        before = dict(state)
        for _ in range(2):
            img = QImage(view.size(), QImage.Format.Format_ARGB32)
            painter = QPainter(img)
            view.render(painter)
            painter.end()
            view.toggle_map_mode()
        self.assertEqual(state, before)

    def test_logo_cache_stays_bounded_across_scene_revisions(self):
        view = mod.MapView({})
        first = [[0, 0, "company", f"old_{i:03}", "Old"] for i in range(128)]
        second = [[0, 0, "company", f"new_{i:03}", "New"] for i in range(128)]
        view.set_scene_features(first)
        self.assertEqual(len(view._feature_logos), 128)
        view.set_scene_features(first + second)
        self.assertEqual(len(view._feature_logos), 128)
