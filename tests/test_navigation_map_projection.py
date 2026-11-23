"""Regression tests for display-only map perspective, clipping and interaction."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import math
import unittest
from PyQt6.QtWidgets import QApplication
from UI import map_page as mod
from UI import map_projection as proj

class NavigationMapProjectionTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_near_roads_are_wider_than_far_roads(self):
        c = proj.MapCamera(1000, 700, (0, 0), 0, 600)
        near = c.project((-5, 100))
        near2 = c.project((5, 100))
        far = c.project((-5, -600))
        far2 = c.project((5, -600))
        self.assertGreater(near2[0] - near[0], far2[0] - far[0])

    def test_project_ground_inverse_under_heading_and_pan(self):
        for heading in [0, 0.6, math.pi / 2, math.pi, -2.2]:
            c = proj.MapCamera(1300, 800, (200, -500), heading, 650)
            for point in [(200, -500), (100, -600), (250, -300)]:
                screen = c.project(point)
                back = c.ground(screen)
                self.assertAlmostEqual(back[0], point[0], places=6)
                self.assertAlmostEqual(back[1], point[1], places=6)

    def test_roof_has_world_height_and_correct_perspective(self):
        c = proj.MapCamera(1000, 700, (0, 0), 0, 600)
        base = c.project((100, -100))
        roof = c.project((100, -100), 20)
        self.assertLess(roof[1], base[1])
        self.assertGreater(roof[0], base[0])

    def test_heading_rotates_map_not_the_vehicle_marker(self):
        c = proj.MapCamera(1000, 700, (0, 0), math.pi / 2, 600)
        a = c.project((0, 0))
        forward = c.project((-100, 0))
        self.assertAlmostEqual(a[0], forward[0])
        self.assertLess(forward[1], a[1])

    def test_clip_behind_camera(self):
        c = proj.MapCamera(1000, 700, (0, 0), 0, 600)
        self.assertIsNone(c.project((0, 10000)))
        self.assertIsNone(c.segment((0, 10000), (10, 10000)))
        self.assertEqual(c.polygon([(0, 10000), (10, 10000), (0, 11000)]), [])
        for x, y in c.polygon([(-100, 0), (100, 0), (100, 10000), (-100, 10000)]):
            self.assertTrue(math.isfinite(x) and math.isfinite(y))

    def test_default_and_2d_switch(self):
        v = mod.MapView({})
        self.assertTrue(v._perspective)
        v.toggle_perspective()
        self.assertFalse(v._perspective)
        v.toggle_perspective()
        self.assertTrue(v._perspective)

    def test_curved_roads_are_cached_world_surfaces(self):
        v = mod.MapView({})
        v.set_road_segments([[[-20, 0, 0], [0, 0, 0], 'road', 2, False, True, False, False, 6, False, 'r', 0, 'local'], [[0, 0, 0], [20, 0, -20], 'road', 2, False, True, False, False, 6, False, 'r', 1, 'local']])
        self.assertEqual(len(v._road_ribbons), 1)
        self.assertGreater(sum((len(p) for p in v._road_ribbons[0][1])), 4)

    def test_qt_homography_matches_explicit_3d_projection(self):
        from PyQt6.QtGui import QTransform
        from PyQt6.QtCore import QPointF
        for heading in [0, 0.6, 2.4]:
            c = proj.MapCamera(1300, 800, (24800, 14300), heading, 550)
            transform = QTransform(*c.ground_matrix())
            for point in [(24800, 14300), (24900, 14200), (24600, 14150)]:
                expected = c.project(point)
                actual = transform.map(QPointF(*point))
                self.assertAlmostEqual(actual.x(), expected[0], places=6)
                self.assertAlmostEqual(actual.y(), expected[1], places=6)

    def test_ground_tile_reuses_cache_and_rebuilds_on_scene_change(self):
        from PyQt6.QtGui import QImage, QPainter
        view = mod.MapView({"truck_world_pos": (0, 0), "truck_heading": .2})
        view.resize(700, 500)
        view.set_road_segments([[[-50, 0, 0], [50, 0, 0], "road", 2]])
        def paint():
            image = QImage(view.size(), QImage.Format.Format_ARGB32)
            p = QPainter(image)
            view.render(p)
            p.end()
        paint()
        cached = view._ground_tile
        self.assertIsNotNone(cached)
        self.assertLessEqual(cached[1].width(), 2049)
        self.assertLessEqual(cached[1].height(), 2049)
        paint()
        self.assertIs(view._ground_tile, cached)
        view.set_scene_polygons([[[[-20, -20], [20, -20], [20, 20], [-20, 20]], 3, 0]])
        paint()
        self.assertIsNot(view._ground_tile, cached)
