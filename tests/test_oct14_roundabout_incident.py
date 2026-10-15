"""Native reader -> selector -> real producers -> physical Controller; no game proof."""
import ast
import copy
import math
from pathlib import Path
from unittest.mock import Mock

import pytest

from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_oct11_joint_regressions import joint  # noqa: F401
from tests.test_oct14_completion import timed_step


def presentation(engine, perception, telemetry, traffic):
    """Execute the actual production block on both pre-fix and fixed versions."""
    if hasattr(engine, '_update_planner_presentation'):
        return engine._update_planner_presentation(perception, telemetry, .033, traffic)
    from core.engine import UltraPilotEngine
    import inspect
    source = inspect.getsource(UltraPilotEngine.run_loop)
    start=source.index('                previous_planner_state=')
    end=source.index('                # 4. Core modules',start)
    import textwrap
    import time
    exec(compile(textwrap.dedent(source[start:end]),'production-planning-block','exec'),
         dict(self=engine,time=time,perception_data=perception,telemetry_data=telemetry,
              delta_time=.033,published_traffic=traffic))


def test_distant_hypothetical_acceleration_cannot_latch_terminal_hold(joint):
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    # Recorded receipt: ~80.53 m / actor 5.32 s / hypothetical ego 4.93 s.
    # Ego's ACTUAL constant-speed arrival is 7.12 s, outside the 5 s demand.
    actor=dict(id=42,x=2.25-30.,y=10.,z=95.52834,yaw=-math.pi/2,speed=30./5.3197876)
    following=timed_step(joint,[actor],generation=1,speed=11.323)
    assert following['crossing']['brake']==0.,following['crossing']
    assert not engine._service_brake_hold
    assert state.get('autopilot_active') and not state.get('safety_hazard_active')
    assert not (physical('aforward')>0 and physical('abackward')>0)


def test_stationary_ego_does_not_emergency_for_actor_arriving_in_four_seconds(joint):
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    # Reproduces the recorded decisive distance/time, not unknown historical XYZ.
    actor=dict(id=7,x=2.25-28.,y=10.,z=15.228867,yaw=-math.pi/2,speed=28./4.66815)
    following=timed_step(joint,[actor],generation=1,speed=0.)
    assert following['crossing']['brake']==0.,following['crossing']
    assert not (state.get('autopilot_intervention') or {}).get('kind')=='emergency'
    assert physical('abackward')!=1.


def test_inactive_engine_cannot_reannounce_traffic_modes(joint):
    from core.planner import UltraPilotPlanner
    state,engine,ap,acc,policy,tick,_,n,physical,writes,clock=joint
    n();engine._flush_controls()
    engine.planner=UltraPilotPlanner();engine.voice=Mock()
    for level in (.8,0.,.5,0.,.8,0.):
        presentation(engine,dict(obstacle=dict(level=level),lane_offset=.3,nav_direction=.4),
                     state.get('telemetry'),state.get('longitudinal_traffic'))
    assert engine.planner.current_state.name=='IDLE'
    assert engine.voice.say.call_count==0
    assert physical('aforward')==0.


def test_emergency_reason_survives_large_optional_evidence(joint,tmp_path):
    from core.steering_replay import inspect_replay
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    engine._automatic_replay_directory=str(tmp_path)
    actor=dict(id=71,x=8.,y=10.,z=20.,yaw=math.pi/2,speed=5.)
    following=timed_step(joint,[actor],generation=1,speed=10.)
    fault=state.get('autopilot_intervention')
    assert fault and fault['kind']=='emergency'
    from core.navigation.longitudinal_diagnostics import expand_emergency_evidence
    evidence=expand_emergency_evidence(fault['details']['evidence'])
    assert 'snapshot_status' not in evidence,evidence
    assert evidence['traffic']['brake_basis']['decisive']['id']==71
    clock[0]+=.11;engine._flush_controls()
    result=engine._automatic_replay_writer.wait(5.)
    exported=inspect_replay(result['path'])
    assert exported['integrity_valid']
    first=exported['replay']['longitudinal']['first_intervention']
    assert first['details']['evidence']['traffic']['brake_basis']['decisive']['id']==71
    assert physical('aforward')==0.


def test_quota_failure_keeps_pending_receipt_for_fault_and_does_not_retry(joint,tmp_path):
    from core.steering_replay import inspect_replay
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    engine._automatic_replay_directory=str(tmp_path)
    for i in range(8):
        (tmp_path/f'steering-replay-{i}-significant_event.json').write_bytes(b'original')
    journal=engine.controller._pedal_journal
    journal.significant('AVOID_OBSTACLE',dict(context=list(__import__('core.longitudinal',fromlist=['context']).context(state)),actor=dict(id=42)),clock[0])
    engine._finish_significant_longitudinal_event(journal,shutdown=True)
    result=engine._automatic_replay_writer.wait(5.)
    assert result['error_detail']=='SIGNIFICANT_EVENT_EXPORT_DISK_QUOTA'
    old_thread=engine._automatic_replay_writer._thread
    for i in range(10):
        engine._finish_significant_longitudinal_event(journal,shutdown=True)
    assert engine._automatic_replay_writer._thread is old_thread
    assert journal.ready_significant(clock[0],shutdown=True) is not None
    # The existing automatic fault path retains priority and its pending cause,
    # independently of the full normal-event quota. Original files are intact.
    actor=dict(id=71,x=8.,y=10.,z=20.,yaw=math.pi/2,speed=5.)
    timed_step(joint,[actor],generation=1,speed=10.)
    clock[0]+=.11;engine._flush_controls()
    checked=inspect_replay(engine._automatic_replay_writer.wait(5.)['path'])
    assert checked['integrity_valid']
    preceding=checked['replay']['longitudinal']['preceding_significant_event_receipt']
    assert preceding['receipt']['actor']['id']==42
    assert all(p.read_bytes()==b'original' for p in tmp_path.glob('*significant_event.json'))


def test_inactive_acc_does_not_publish_repeating_emergency_voice(joint):
    from core.longitudinal import publish
    state,engine,ap,acc,policy,tick,_,n,physical,writes,clock=joint
    n();engine._flush_controls()
    state.set('tts_message','original first intervention')
    for _ in range(5):
        publish(state,state.get('telemetry')['truck'],'traffic',traffic_brake=1.,light_brake=0.)
        acc.on_tick(.033)
    assert state.get('tts_message')=='original first intervention'
    assert state.get('longitudinal_acc')['emergency'] is False
    assert physical('aforward')==0.


@pytest.mark.parametrize('case',['empty','side','far','opposite_side','departing','crossing'])
def test_native_actor_relevance_reaches_physical_output(joint,case):
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    actor=dict(id=17,x=18.,y=10.,z=45.,yaw=math.pi,speed=8.)
    if case=='far':actor.update(x=2.25,z=400.)
    elif case=='opposite_side':actor.update(yaw=0.)
    elif case=='departing':actor.update(yaw=-math.pi/2)
    elif case=='crossing':actor.update(x=8.,z=20.,yaw=math.pi/2,speed=5.)
    actors=[] if case=='empty' else [actor]
    for generation in range(1,5):
        following=timed_step(joint,actors,generation=generation,speed=10.)
        if case=='crossing':
            assert physical('aforward')==0. and physical('abackward')==1.
        else:
            assert following['crossing']['brake']==0.,following
            assert not engine._service_brake_hold
            assert not state.get('autopilot_intervention')
        assert not (physical('aforward')>0. and physical('abackward')>0.)


@pytest.mark.parametrize('mode',[0,3])
def test_closed_distant_crossing_stays_regulation_not_terminal_stop(mode):
    from tools.compare_oct14_roundabout_incident import simulate
    result=simulate(mode,False)
    # Criteria fixed from this declared non-contact scenario: no automatic
    # intervention or terminal hold; unchanged exclusive physical pedals.
    assert result['emergency_samples']==result['inactive_samples']==0
    assert result['hold_samples']==result['standstill_samples']==0
    assert result['observed_box_overlap_samples']==result['simultaneous_pedals']==0


def test_summary_keeps_consumed_actor_before_detail_budget_exhaustion(joint):
    from core.navigation.longitudinal_diagnostics import expand_history
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    actor=dict(id=71,x=8.,y=10.,z=20.,yaw=math.pi/2,speed=5.)
    timed_step(joint,[actor],generation=1,speed=10.)
    history=expand_history(engine.controller._pedal_journal.snapshot(expanded=False,include_history=True)['decision_history'])
    rows=history['regular_samples']+history['changes']
    causes=[r['traffic_cause'] for r in rows if r.get('traffic_cause')]
    assert causes and causes[0]['actor']['id']==71
    assert causes[0]['source_acquisition']['generation']==1


def test_two_observed_crossing_caps_keep_every_current_owner(joint):
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    actors=[dict(id=42,x=-20.,y=10.,z=75.,yaw=-math.pi/2,speed=5.),
            dict(id=43,x=-25.,y=10.,z=85.,yaw=-math.pi/2,speed=5.)]
    ego=[(2.25,10.,15.,0.,0.,1.,0.,2.5,4.,6.)]
    following=timed_step(joint,actors,generation=1,speed=10.,ego=ego)
    scope=following['motion_constraint']
    assert {t['id'] for t in scope['targets']}=={'42','43'}
    assert following['body_prediction']['brake']==0.
    assert not engine._service_brake_hold
    assert state.get('longitudinal_acc')['constrained_speed_kmh']<=min(t['cap_mps'] for t in scope['targets'])*3.6
    # Losing the original object is not clearance, even if another remains.
    timed_step(joint,[dict(actors[1],x=-24.8)],generation=2,speed=10.,ego=ego)
    assert not state.get('longitudinal_acc')['valid']
    assert physical('aforward')==0.
