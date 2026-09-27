"""Closed-loop baseline for any future first-trailer CTE experiment.

The measured trailer placement is currently diagnostic only. Supplying it
must not alter the single Route steering command until a tested experiment
explicitly earns runtime authority.
"""

import importlib.util
import math
from pathlib import Path
import unittest
from unittest import mock

from core.navigation.maneuver_reference import ManeuverReferenceMux
from core.navigation.route import Route

_spec = importlib.util.spec_from_file_location(
    'phase4e_closed_loop_for_trailer_baseline',
    Path(__file__).with_name('test_phase4e_closed_loop_controller.py'))
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
_constant_curve_path = _module._constant_curve_path
_path_from_sections = _module._path_from_sections
_s_curve_path = _module._s_curve_path
_simulate_closed_loop = _module._simulate_closed_loop


class TrailerAwareBaselineTests(unittest.TestCase):
    def test_unauthed_planner_and_attached_trailer_preserve_global_command(self):
        """An idle offline planner cannot replace LanePath or steer the cab."""
        for direction in (-1, 1):
            points, _ = _constant_curve_path(direction, 83)
            route = Route(points)
            tractor = route.points[2]
            dx = route.points[3][0] - tractor[0]
            dz = route.points[3][1] - tractor[1]
            heading = math.atan2(-dx, -dz)
            trailer = (tractor[0] + math.sin(heading) * 10.0,
                       tractor[1] + math.cos(heading) * 10.0)
            mux = ManeuverReferenceMux()
            try:
                selected = mux.select(route, {}, {}, tractor, heading,
                                      10.0, 1000000, True)
                self.assertIs(selected.route, route)
                self.assertEqual(selected.mode, "global_lane")
                self.assertTrue(selected.authority_valid)
                kwargs = dict(cross_track_error_m=0.0, control_dt_s=0.05)
                baseline = Route(points).steering(tractor, heading, 5.0,
                                                  **kwargs)
                with mock.patch(
                        "core.navigation.trailer_guidance.plan_trailer_guidance",
                        side_effect=AssertionError("offline planner ran")):
                    attached = selected.route.steering(
                        tractor, heading, 5.0,
                        vehicle_envelope={
                            "attached": True, "position": trailer,
                            "heading": heading, "lane_width_m": 4.7,
                            "tractor_altitude_m": 45.0,
                            "trailer_altitude_m": 45.0,
                        }, **kwargs)
                self.assertEqual(attached, baseline)
                self.assertEqual(selected.route.last_steering_debug[
                    "trailer_envelope"]["applied_offset_m"], 0.0)
                self.assertFalse(selected.route.last_steering_debug[
                    "trailer_envelope"]["reference_authorized"])
            finally:
                mux.close()

    def test_existing_trailer_telemetry_does_not_change_steering(self):
        for direction in (-1, 1):
            for radius in (150, 83, 60, 35):
                points, _ = _constant_curve_path(direction, radius)
                with self.subTest(direction=direction, radius=radius):
                    cab = _simulate_closed_loop(
                        points, 5., with_trailer=False,
                        noisy_lane_match=True, delayed_ticks=True)
                    trailer = _simulate_closed_loop(
                        points, 5., with_trailer=True,
                        noisy_lane_match=True, delayed_ticks=True)
                    self.assertEqual(
                        [row['raw'] for row in cab['samples']],
                        [row['raw'] for row in trailer['samples']])
                    self.assertEqual(
                        [row['output'] for row in cab['samples']],
                        [row['output'] for row in trailer['samples']])

    def test_offline_trailer_candidate_keeps_single_controller_on_straight_and_s_curve(self):
        cases = (("straight", _path_from_sections(((0.0, 180.0),))[0]),
                 ("s_curve", _s_curve_path(83.0)[0]))
        for name, points in cases:
            for speed in (5.0, 12.0):
                for delayed in (False, True):
                    with self.subTest(path=name, speed=speed, delayed=delayed):
                        options = dict(noisy_lane_match=True,
                                       delayed_ticks=delayed)
                        cab = _simulate_closed_loop(
                            points, speed, with_trailer=False, **options)
                        trailer = _simulate_closed_loop(
                            points, speed, with_trailer=True, **options)
                        self.assertEqual(
                            [row['raw'] for row in cab['samples']],
                            [row['raw'] for row in trailer['samples']])
                        self.assertEqual(
                            [row['output'] for row in cab['samples']],
                            [row['output'] for row in trailer['samples']])

    def test_inside_trailer_cte_has_opposite_sign_to_turn(self):
        for direction in (-1, 1):
            points, _ = _constant_curve_path(direction, 83)
            result = _simulate_closed_loop(
                points, 5., with_trailer=True)
            inside = [row for row in result['samples']
                      if abs(row['curvature_per_m']) > .009
                      and abs(row['trailer_cte_m']) > .05]
            self.assertTrue(inside)
            self.assertTrue(all(
                row['curvature_per_m'] * row['trailer_cte_m'] < 0
                for row in inside), direction)


if __name__ == '__main__':
    unittest.main()
