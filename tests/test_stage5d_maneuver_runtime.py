"""Offline runtime gate regressions; no game, installation or control writes."""
import copy
from dataclasses import replace
from pathlib import Path
import unittest

from core.navigation.maneuver_runtime import (
    ManeuverRuntime, ManeuverState as State, approach_demand,
    decision_rejection_reason, execution_timing, stopping_distance,
)
from core.navigation.maneuver_integration import audit_prefab_transition
from core.swept_envelope import EnvelopeError
from tests.maneuver_runtime_cases import runtime_request, live_state, clear_traffic, actor
from tests import test_service_prefab_diagnostics as mod63


class Stage5DRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.request = runtime_request()
        cls.prepared = ManeuverRuntime(cls.request)
        assert cls.prepared.state == State.PLAN_PENDING, cls.prepared.failure_reason

    def setUp(self):
        self.runtime = copy.copy(self.prepared)
        self.runtime.transitions = list(self.prepared.transitions)

    def traffic(self, now=10., blocked=False):
        return clear_traffic(self.request.result.context.identity,now,
                             (actor(now=now),) if blocked else ())

    def test_no_maneuver_has_no_authority(self):
        decision=ManeuverRuntime().update(None,None)
        self.assertEqual(decision.state,State.NO_MANEUVER)
        self.assertFalse(decision.runtime_authorized)

    def test_geometry_rejection_and_missing_tracking_proof(self):
        result=replace(self.request.result,accepted=False,failure_reason='NO_SAFE_GEOMETRY')
        runtime=ManeuverRuntime(replace(self.request,result=result))
        self.assertEqual(runtime.state,State.GEOMETRY_REJECTED)
        self.assertEqual(runtime.failure_reason,'NO_SAFE_GEOMETRY')
        runtime=ManeuverRuntime(replace(self.request,tracking=replace(self.request.tracking,confirmed=False)))
        self.assertEqual(runtime.failure_reason,'MISSING_VALIDATED_EXECUTION_TRACKING_BOUND')

    def test_free_intersection_needs_no_wait_but_entry_requires_revalidation(self):
        live=live_state(self.runtime)
        decision=self.runtime.update(live,self.traffic())
        self.assertEqual(decision.state,State.READY_FOR_ENTRY)
        self.assertFalse(decision.runtime_authorized)
        decision=self.runtime.update(live,self.traffic(),enter=True)
        self.assertEqual(decision.state,State.EXECUTING)
        self.assertTrue(decision.runtime_authorized)
        self.assertEqual(decision_rejection_reason(decision,self.runtime,live,self.traffic()),'')
        self.assertGreater(self.runtime.timing.ramp_duration_s,0.)

    def test_traffic_change_immediately_before_entry_blocks_permission(self):
        self.runtime.update(live_state(self.runtime),self.traffic())
        decision=self.runtime.update(live_state(self.runtime,10.1),self.traffic(10.1,True),enter=True)
        self.assertEqual(decision.state,State.WAITING_FOR_TRAFFIC)
        self.assertFalse(decision.runtime_authorized)

    def test_wait_over_thirty_seconds_uses_fresh_commands_and_new_entry_timing(self):
        for now in (10.,20.,30.,40.,41.):
            decision=self.runtime.update(live_state(self.runtime,now),self.traffic(now,True))
            self.assertEqual(decision.state,State.WAITING_FOR_TRAFFIC,decision.failure_reason)
            self.assertFalse(decision.runtime_authorized)
        live=live_state(self.runtime,41.1)
        decision=self.runtime.update(live,self.traffic(41.1),enter=True)
        self.assertTrue(decision.runtime_authorized,decision.failure_reason)
        self.assertEqual(self.runtime.timing.start_s,41.1)
        self.assertEqual(self.request.ground.observed_at,10.)  # old geometric request is unchanged
        self.assertEqual(decision.computed_at_s,41.1)
        self.assertEqual(decision.sdk_frame_us,live.ground.sdk_frame_us)

    def test_wait_does_not_bypass_computed_at_staleness(self):
        live=replace(live_state(self.runtime,41.),navigation_computed_at_s=10.)
        decision=self.runtime.update(live,self.traffic(41.))
        self.assertEqual(decision.failure_reason,'STALE_NAVIGATION_COMMAND')
        self.assertEqual(decision.state,State.CANCELLED_STALE)

    def test_navigation_identity_changes_during_wait_cancel_and_latch(self):
        for key,value in (('revision',9),('navigation_intent_id','new'),('route_build_id','new'),
                          ('source_game_session_id','new'),('source_map_key','new'),
                          ('source_dataset_fingerprint','new')):
            with self.subTest(key=key):
                runtime=copy.copy(self.prepared);runtime.transitions=[]
                runtime.update(live_state(runtime),self.traffic(blocked=True))
                live=live_state(runtime,10.1)
                live=replace(live,snapshot={**live.snapshot,key:value})
                decision=runtime.update(live,self.traffic(10.1),enter=True)
                self.assertEqual(decision.state,State.CANCELLED_STALE)
                self.assertFalse(runtime.update(live_state(runtime,10.2),self.traffic(10.2),enter=True).runtime_authorized)

    def test_rolling_prefix_and_repeated_uid_occurrences_cannot_reuse_plan(self):
        for uids in ([2,3,4],[1,2,1,2,3,4]):
            with self.subTest(uids=uids):
                runtime=copy.copy(self.prepared);runtime.transitions=[]
                live=live_state(runtime)
                live=replace(live,snapshot={**live.snapshot,'covered_gps_uids':uids})
                decision=runtime.update(live,self.traffic(),enter=True)
                self.assertFalse(decision.runtime_authorized)
                self.assertEqual(decision.state,State.CANCELLED_STALE)

    def test_profile_change_and_trailer_detachment_cancel(self):
        for change in ('token','detach'):
            with self.subTest(change=change):
                runtime=copy.copy(self.prepared);runtime.transitions=[]
                live=live_state(runtime)
                prof=(replace(live.profile,token=replace(live.profile.token,generation=2))
                      if change=='token' else replace(live.profile,
                      model=replace(live.profile.model,bodies=live.profile.model.bodies[:1])))
                decision=runtime.update(replace(live,profile=prof),self.traffic(),enter=True)
                self.assertEqual(decision.failure_reason,'STALE_MANEUVER_VEHICLE_PROFILE')

    def test_ground_frame_freshness_and_sdk_identity_are_mandatory(self):
        for kind in ('sdk','time','uncertainty','elevation'):
            with self.subTest(kind=kind):
                runtime=copy.copy(self.prepared);runtime.transitions=[]
                live=live_state(runtime)
                if kind=='sdk':live=replace(live,ground=replace(live.ground,sdk_frame_us=1))
                elif kind=='time':live=replace(live,now_s=10.11)
                elif kind=='uncertainty':live=replace(live,ground=replace(live.ground,position_uncertainty_m=.1))
                else:live=replace(live,ground=replace(live.ground,frame=replace(live.ground.frame,
                    poses=tuple(replace(p,y=10.) for p in live.ground.frame.poses))))
                self.assertFalse(runtime.update(live,self.traffic(),enter=True).runtime_authorized)

    def test_reused_sdk_frame_cannot_be_retimestamped(self):
        self.runtime.update(live_state(self.runtime),self.traffic(blocked=True))
        live=live_state(self.runtime,10.1)
        live=replace(live,profile=replace(live.profile,observation=replace(live.profile.observation,sdk_frame_us=1_000_000)),
                     ground=replace(live.ground,sdk_frame_us=1_000_000))
        decision=self.runtime.update(live,self.traffic(10.1),enter=True)
        self.assertEqual(decision.failure_reason,'REUSED_SDK_FRAME_WITH_CHANGED_GROUND')

    def test_manual_disable_during_wait_or_execution_revokes_authority(self):
        for entering in (False,True):
            runtime=copy.copy(self.prepared);runtime.transitions=[]
            runtime.update(live_state(runtime),self.traffic(blocked=not entering),enter=entering)
            decision=runtime.update(live_state(runtime,10.1,enabled=False),self.traffic(10.1))
            self.assertEqual(decision.state,State.CANCELLED_STALE)
            self.assertEqual(decision.failure_reason,'MANUAL_AUTOPILOT_DISABLED')

    def test_emergency_conflict_after_entry(self):
        self.runtime.update(live_state(self.runtime),self.traffic(),enter=True)
        decision=self.runtime.update(live_state(self.runtime),
            replace(self.traffic(blocked=True),sequence=10_000_001,snapshot_id='changed'),enter=True)
        self.assertEqual(decision.state,State.EMERGENCY_ABORT)
        self.assertEqual(decision.failure_reason,'TRAFFIC_CONFLICT')

    def test_lost_traffic_after_entry_aborts(self):
        self.runtime.update(live_state(self.runtime),self.traffic(),enter=True)
        decision=self.runtime.update(live_state(self.runtime),None)
        self.assertEqual(decision.state,State.EMERGENCY_ABORT)
        self.assertEqual(decision.failure_reason,'MISSING_TRAFFIC_SNAPSHOT')

    def test_stale_traffic_before_entry_waits_without_permission(self):
        decision=self.runtime.update(live_state(self.runtime),self.traffic(9.),enter=True)
        self.assertEqual(decision.state,State.WAITING_FOR_TRAFFIC)
        self.assertEqual(decision.failure_reason,'STALE_TRAFFIC_SNAPSHOT')

    def test_changed_same_sequence_and_regressing_sequence_fail_closed(self):
        self.runtime.update(live_state(self.runtime),self.traffic(blocked=True))
        decision=self.runtime.update(live_state(self.runtime),self.traffic(),enter=True)
        self.assertEqual(decision.failure_reason,'REUSED_TRAFFIC_SEQUENCE_WITH_CHANGED_SNAPSHOT')

    def test_live_pose_must_still_be_at_entry_after_wait(self):
        self.runtime.update(live_state(self.runtime),self.traffic(blocked=True))
        live=live_state(self.runtime,10.1,sample_index=10)
        decision=self.runtime.update(live,self.traffic(10.1),enter=True)
        self.assertFalse(decision.runtime_authorized)
        self.assertEqual(decision.state,State.CANCELLED_STALE)

    def test_exit_requires_current_centerline_and_aligned_articles(self):
        self.runtime.update(live_state(self.runtime),self.traffic(),enter=True)
        end=self.runtime.timing.times_s[-1]
        # Isolated exit transition: seed the still-live lease produced by the
        # preceding execution frame. This is not an end-to-end controller replay.
        self.runtime._last_decision=replace(self.runtime._last_decision,
            computed_at_s=end-.05,valid_until_s=end+.05)
        live=live_state(self.runtime,end,speed=self.request.result.plan.speed_mps,
                        sample_index=len(self.request.result.plan.samples)-1)
        decision=self.runtime.update(live,self.traffic(end))
        self.assertEqual(decision.state,State.COMPLETED,decision.failure_reason)
        self.assertTrue(any(t[1]=='EXIT_REVALIDATION' for t in self.runtime.transitions))
        self.assertFalse(decision.runtime_authorized)

    def test_wrong_exit_article_pose_does_not_complete(self):
        self.runtime.update(live_state(self.runtime),self.traffic(),enter=True)
        end=self.runtime.timing.times_s[-1]
        self.runtime._last_decision=replace(self.runtime._last_decision,
            computed_at_s=end-.05,valid_until_s=end+.05)
        live=live_state(self.runtime,end,speed=2.,sample_index=len(self.request.result.plan.samples)-1)
        poses=live.ground.frame.poses
        live=replace(live,ground=replace(live.ground,frame=replace(live.ground.frame,
            poses=(poses[0],replace(poses[1],heading=poses[1].heading+.2)))))
        decision=self.runtime.update(live,self.traffic(end))
        self.assertEqual(decision.state,State.EMERGENCY_ABORT)

    def test_execution_cannot_resume_after_a_gap_in_live_authority(self):
        self.runtime.update(live_state(self.runtime),self.traffic(),enter=True)
        decision=self.runtime.update(live_state(self.runtime,10.2),self.traffic(10.2))
        self.assertEqual(decision.state,State.EMERGENCY_ABORT)
        self.assertEqual(decision.failure_reason,'EXECUTION_LEASE_EXPIRED_REVALIDATION_REQUIRED')

    def test_completion_does_not_skip_missing_traffic(self):
        self.runtime.update(live_state(self.runtime),self.traffic(),enter=True)
        end=self.runtime.timing.times_s[-1]
        self.runtime._last_decision=replace(self.runtime._last_decision,
            computed_at_s=end-.05,valid_until_s=end+.05)
        live=live_state(self.runtime,end,speed=2.,sample_index=len(self.request.result.plan.samples)-1)
        decision=self.runtime.update(live,None)
        self.assertEqual(decision.state,State.EMERGENCY_ABORT)
        self.assertEqual(decision.failure_reason,'MISSING_TRAFFIC_SNAPSHOT')

    def test_stale_worker_decision_cannot_be_consumed_by_new_sdk_frame_or_traffic(self):
        live=live_state(self.runtime)
        traffic=self.traffic()
        decision=self.runtime.update(live,traffic,enter=True)
        self.assertEqual(decision_rejection_reason(decision,self.runtime,live,traffic),'')
        self.assertEqual(decision_rejection_reason(replace(decision,target_speed_mps=5.),self.runtime,live,traffic),
                         'SUPERSEDED_OR_MUTATED_MANEUVER_DECISION')
        newer=live_state(self.runtime,10.01)
        self.assertEqual(decision_rejection_reason(decision,self.runtime,newer,traffic),'STALE_MANEUVER_DECISION_SDK_FRAME')

    def test_unbound_second_consumer_cannot_receive_reference(self):
        live=replace(live_state(self.runtime),consumer_binding='another-controller')
        decision=self.runtime.update(live,self.traffic(),enter=True)
        self.assertEqual(decision.failure_reason,'LOCAL_REFERENCE_CONSUMER_NOT_BOUND')

    def test_retiming_preserves_geometry_and_respects_acceleration_and_jerk(self):
        plan=self.request.result.plan
        original=plan.samples
        for speed in (0.,.5,2.):
            timing=execution_timing(plan,40.,speed,self.request.tracking)
            self.assertEqual(timing.times_s[0],40.)
            self.assertTrue(all(a<b for a,b in zip(timing.times_s,timing.times_s[1:])))
            dv=plan.speed_mps-speed
            if dv:
                self.assertLessEqual(1.5*dv/timing.ramp_duration_s,1.+1e-9)
                self.assertLessEqual(6*dv/timing.ramp_duration_s**2,.5+1e-9)
        self.assertIs(plan.samples,original)
        with self.assertRaises(EnvelopeError):
            execution_timing(plan,40.,3.,self.request.tracking)

    def test_smooth_approach_releases_throttle_and_has_bounded_jerk(self):
        speed,acceleration,distance=8.,0.,100.
        positions=[]
        for _ in range(4000):
            demand=approach_demand(speed,acceleration,distance,.02,True)
            self.assertTrue(demand.accepted,demand.failure_reason)
            self.assertTrue(demand.release_throttle)
            self.assertLessEqual(abs(demand.acceleration_mps2-acceleration),.010000001)
            acceleration=demand.acceleration_mps2
            speed=max(0.,speed+acceleration*.02)
            distance-=speed*.02
            positions.append(distance)
            if speed < .001 and abs(acceleration)<.02:break
        self.assertLess(speed,.001)
        self.assertGreater(min(positions),0.)
        self.assertLess(distance,5.)  # do not stop tens of metres prematurely
        clear=approach_demand(2.,0.,20.,.02,False)
        self.assertEqual(clear.target_speed_mps,2.)
        self.assertFalse(clear.release_throttle)

    def test_too_late_to_stop_reports_infeasibility_not_normal_braking(self):
        result=approach_demand(10.,0.,2.,.02,True)
        self.assertFalse(result.accepted)
        self.assertEqual(result.failure_reason,'INSUFFICIENT_CONFIRMED_STOPPING_DISTANCE')
        self.assertGreater(stopping_distance(10.,0.),50.)

    def test_mod_ger_63_still_requires_proven_approach_lane(self):
        fixture=mod63.ModGer63DiagnosticReplayTests(methodName='runTest');fixture.setUp()
        result=audit_prefab_transition(fixture.net,fixture.source,fixture.required)
        self.assertFalse(result.accepted)
        self.assertEqual(result.failure_reason,'PREFAB_CONNECTOR_CHANGE_REQUIRES_PROVEN_APPROACH_LANE')
        self.assertAlmostEqual(result.gap_m,4.4436471507,places=8)

    def test_core_never_writes_steering_or_replaces_global_lane_path(self):
        root=Path(__file__).resolve().parents[1]
        for name in ('maneuver_traffic.py','maneuver_runtime.py'):
            text=(root/'core/navigation'/name).read_text(encoding='utf-8')
            for forbidden in ('set_steering(', 'SteeringDynamics(', 'PID(', 'shared_state.set('):
                self.assertNotIn(forbidden,text)


if __name__ == '__main__':
    unittest.main()
