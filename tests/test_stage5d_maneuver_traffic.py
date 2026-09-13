"""Deterministic continuous traffic occupancy and adversarial evidence tests."""
from dataclasses import replace
import math
import unittest

from core.navigation.maneuver_traffic import (
    OccupancyInterval, check_traffic_window, polygon_distance,
)
from core.swept_envelope import Identity
from core.navigation.lane_model import LaneId
from tests.maneuver_runtime_cases import actor, clear_traffic


class Stage5DTrafficTests(unittest.TestCase):
    identity = Identity('intent', 8, 'build', 'session', 'map', 'dataset',
                        'level', (LaneId(1,1,0),), ((1,2),))
    square = ((-1.,-1.), (1.,-1.), (1.,1.), (-1.,1.))

    def check(self, actors=(), *, intervals=None, snapshot=None, now=10.):
        intervals = intervals or (OccupancyInterval(now,now+2.,(self.square,)),)
        snapshot = snapshot or clear_traffic(self.identity,now,actors)
        return check_traffic_window(intervals,snapshot,self.identity,now)

    def test_confirmed_empty_intersection_is_clear_immediately(self):
        result = self.check()
        self.assertTrue(result.accepted, result.failure_reason)
        self.assertIsNone(result.minimum_clearance_m)
        self.assertEqual(result.temporal_margin_s,1.)

    def test_crossing_between_endpoints_is_detected(self):
        result = self.check((actor(x=-10.,vx=10.),))
        self.assertFalse(result.accepted)
        self.assertEqual(result.failure_reason,'TRAFFIC_CONFLICT')
        self.assertEqual(result.conflicts[0].actor_id,'car')
        self.assertEqual((result.conflicts[0].start_s,result.conflicts[0].end_s),(10.,12.))

    def test_oncoming_and_rear_approaching_vehicle(self):
        for z,vz in ((-10.,10.),(10.,-10.)):
            with self.subTest(z=z):
                self.assertFalse(self.check((actor(z=z,vz=vz),)).accepted)

    def test_stopped_vehicle_blocks_zone(self):
        self.assertFalse(self.check((actor(),)).accepted)

    def test_vehicle_outside_the_corridor_does_not_block(self):
        result=self.check((actor(x=10.),))
        self.assertTrue(result.accepted,result.failure_reason)
        self.assertGreater(result.minimum_clearance_m,7.)

    def test_complete_body_including_trailer_not_only_center_is_checked(self):
        car=actor(x=20.)
        trailer=((-2.,-2.),(2.,-2.),(2.,2.),(-2.,2.))
        car=replace(car,polygons_xz=car.polygons_xz+(trailer,),
            history=tuple(replace(o,polygons_xz=o.polygons_xz+(trailer,)) for o in car.history))
        self.assertFalse(self.check((car,)).accepted)

    def test_ego_trailer_not_only_cab_is_checked(self):
        far=tuple((x+20.,z) for x,z in self.square)
        occupancy=(OccupancyInterval(10.,12.,(far,self.square)),)
        self.assertFalse(self.check((actor(),),intervals=occupancy).accepted)

    def test_long_time_window_is_safe_but_short_gap_is_not(self):
        safe=self.check((actor(x=-50.,vx=10.),))
        short=self.check((actor(x=-25.,vx=10.),))
        self.assertTrue(safe.accepted,safe.failure_reason)
        self.assertFalse(short.accepted)  # crosses after exit, within the time reserve

    def test_new_window_after_conflict_does_not_reuse_old_prediction(self):
        self.assertFalse(self.check((actor(),)).accepted)
        self.assertTrue(self.check((actor(x=40.,now=40.),),now=40.).accepted)

    def test_prediction_uncertainty_expands_every_corner(self):
        car=replace(actor(x=10.),corner_acceleration_bound_mps2=3.)
        self.assertFalse(self.check((car,)).accepted)

    def test_multiple_vehicles_preserve_distinct_conflicts(self):
        result=self.check((actor('a'),actor('b',x=-10.,vx=10.),actor('clear',x=50.)))
        self.assertEqual({c.actor_id for c in result.conflicts},{'a','b'})

    def test_contiguous_conflicts_merge_without_bridging_clear_gap(self):
        far=tuple((x+50.,z) for x,z in self.square)
        steps=tuple(OccupancyInterval(10.+i,11.+i,(poly,))
                    for i,poly in enumerate((self.square,self.square,far,self.square)))
        result=self.check((actor(),),intervals=steps)
        self.assertEqual([(c.start_s,c.end_s) for c in result.conflicts],[(10.,12.),(13.,14.)])

    def test_touching_edges_and_containment_are_collisions(self):
        self.assertEqual(polygon_distance(self.square,self.square),0.)
        adjacent=tuple((x+2.,z) for x,z in self.square)
        self.assertEqual(polygon_distance(self.square,adjacent),0.)
        big=tuple((x*2,z*2) for x,z in self.square)
        self.assertEqual(polygon_distance(big,self.square),0.)

    def test_missing_dimensions_confidence_and_motion_bounds_fail_closed(self):
        for change in ({'dimensions_confirmed':False},{'confidence':.98},
                       {'position_error_m':0.},{'corner_velocity_error_mps':math.nan},
                       {'corner_acceleration_bound_mps2':-1.}, {'polygons_xz':()},
                       {'history':()}, {'evidence_sha256':'made up'}):
            with self.subTest(change=change):
                self.assertFalse(self.check((replace(actor(x=100.),**change),)).accepted)

    def test_stale_observation_and_stale_snapshot_are_distinct(self):
        self.assertEqual(self.check((actor(now=9.),)).failure_reason,'STALE_TRAFFIC_OBSERVATION')
        snap=clear_traffic(self.identity,9.)
        self.assertEqual(self.check(snapshot=snap).failure_reason,'STALE_TRAFFIC_SNAPSHOT')

    def test_future_and_nan_timestamps_reject(self):
        for t in (10.01,math.nan,math.inf):
            with self.subTest(t=t):
                snap=replace(clear_traffic(self.identity),observed_at_s=t)
                self.assertFalse(self.check(snapshot=snap).accepted)

    def test_unavailable_or_truncated_coverage_is_never_empty_clear(self):
        for change in ({'complete':False},{'source':''}, {'coverage_xz':self.square},
                       {'unseen_speed_bound_mps':0.}):
            with self.subTest(change=change):
                self.assertFalse(self.check(snapshot=replace(clear_traffic(self.identity),**change)).accepted)
        result=check_traffic_window((OccupancyInterval(10.,12.,(self.square,)),),[],self.identity,10.)
        self.assertEqual(result.failure_reason,'MISSING_TRAFFIC_SNAPSHOT')

    def test_unseen_vehicle_can_enter_from_outside_observation_region(self):
        snap=replace(clear_traffic(self.identity),coverage_xz=
                     ((-20.,-20.),(20.,-20.),(20.,20.),(-20.,20.)))
        self.assertEqual(self.check(snapshot=snap).failure_reason,'TRAFFIC_COVERAGE_HORIZON_INCOMPLETE')

    def test_snapshot_and_actor_must_cover_whole_horizon_and_time_margin(self):
        snap=replace(clear_traffic(self.identity),valid_until_s=12.9)
        self.assertEqual(self.check(snapshot=snap).failure_reason,'TRAFFIC_PREDICTION_HORIZON_INCOMPLETE')
        car=replace(actor(x=100.),valid_until_s=12.9)
        self.assertEqual(self.check((car,)).failure_reason,'TRAFFIC_PREDICTION_HORIZON_INCOMPLETE')

    def test_identity_session_dataset_and_occurrence_order_are_not_interchangeable(self):
        for change in ({'intent':'new'},{'revision':9},{'build':'new'},{'session':'new'},
                       {'map_key':'new'},{'dataset':'new'}, {'gps_pairs':((2,1),)}):
            with self.subTest(change=change):
                snap=replace(clear_traffic(self.identity),identity=replace(self.identity,**change))
                self.assertEqual(self.check(snapshot=snap).failure_reason,'STALE_TRAFFIC_IDENTITY')

    def test_duplicate_actor_or_observation_ids_reject(self):
        car=actor()
        self.assertEqual(self.check((car,car)).failure_reason,'AMBIGUOUS_TRAFFIC_ACTOR_ID')
        duplicate=replace(car,history=car.history[:-1]+(replace(car.history[-1],
                               observation_id=car.history[0].observation_id),))
        self.assertEqual(self.check((duplicate,)).failure_reason,'INVALID_TRAFFIC_OBSERVATION_ID')

    def test_observed_motion_must_agree_with_declared_bound(self):
        car=actor()
        bad=replace(car,history=car.history[:-1]+(replace(car.history[-1],x_m=10.),))
        self.assertEqual(self.check((bad,)).failure_reason,'TRAFFIC_HISTORY_EXCEEDS_MOTION_BOUND')

    def test_speed_and_velocity_must_agree(self):
        car=actor()
        bad=replace(car,history=car.history[:-1]+(replace(car.history[-1],speed_mps=4.),))
        self.assertEqual(self.check((bad,)).failure_reason,'TRAFFIC_SPEED_VECTOR_MISMATCH')

    def test_gap_in_ego_time_or_reduced_safety_margin_rejects(self):
        steps=(OccupancyInterval(10.,11.,(self.square,)),OccupancyInterval(12.,13.,(self.square,)))
        self.assertEqual(self.check(intervals=steps).failure_reason,'EGO_OCCUPANCY_TIME_GAP')
        result=check_traffic_window(steps,clear_traffic(self.identity),self.identity,10.,.1,.1)
        self.assertEqual(result.failure_reason,'INVALID_TRAFFIC_SAFETY_MARGIN')

    def test_vehicle_that_just_cleared_still_violates_time_reserve(self):
        # At now the car is already at x=10, but crossed only 0.5 s ago.
        result=self.check((actor(x=10.,vx=20.),))
        self.assertFalse(result.accepted)
        self.assertEqual(result.failure_reason,'TRAFFIC_CONFLICT')

    def test_temporal_history_cannot_be_clipped_at_now(self):
        car=actor(x=100.)
        self.assertEqual(self.check((replace(car,history=car.history[-2:]),)).failure_reason,
                         'TRAFFIC_PREDICTION_HORIZON_INCOMPLETE')
        snap=replace(clear_traffic(self.identity),coverage_since_s=10.)
        self.assertEqual(self.check(snapshot=snap).failure_reason,'TRAFFIC_TEMPORAL_HISTORY_INCOMPLETE')


if __name__ == '__main__':
    unittest.main()
