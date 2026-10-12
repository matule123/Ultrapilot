"""Production reader/planner/ACC/AP/Engine/Controller; never live ETS2."""
import copy
from unittest.mock import patch

import pytest

from core.longitudinal import context, publish
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_oct10_signal_timing import timing_flow
from tests.test_roundabout_intervention_reporting import pedal


def reactivation(flow, tmp_path, mode=0, *, stationary=False):
    values, step = timing_flow(flow, tmp_path, mode)
    state, truck, engine, ap, tick, n, clock, writes, collector = values
    step(30, 'green', speed=2.)
    old = copy.deepcopy(state.get('longitudinal_traffic'))
    n()  # explicit manual-off; pending hold is not inherited across activation
    flow[4](0 if stationary else 4, 0. if stationary else 2., dt=.02)
    n()
    return values, step, old


@pytest.mark.parametrize('mode', [0, 3])
@pytest.mark.parametrize('stationary', [False, True])
def test_old_traffic_waits_without_power_then_new_publication_continues(flow, tmp_path, mode, stationary):
    values, step, old = reactivation(flow, tmp_path, mode, stationary=stationary)
    state, truck, engine, ap, tick, n, clock, writes, collector = values
    epoch = state.get('autopilot_failure_epoch')
    start = len(writes)
    # Fresh current Policy/ACC are not proof that Traffic has updated.
    for _ in range(3):
        flow[4](0 if stationary else 4, 0. if stationary else 2., dt=.02)
        tick.policy.on_tick(.02); tick.acc.on_tick(.02); ap.on_tick(.02)
        engine._flush_controls()
        assert state.get('autopilot_active') or state.get('auto_drive_pending'), state.get('navigation_status')
        assert state.get('autopilot_control_state') != 'controlled_stop'
        assert not state.get('autopilot_first_fault_autopilot')
        assert not state.get('autopilot_first_fault_engine')
        assert pedal(engine, 'aforward') == 0.
    assert state.get('longitudinal_traffic') == old
    assert not any(ch == 'aforward' and v > 0 for _, ch, v, _ in writes[start:])
    for gen in range(31, 40):
        # Real auto must see a D request first, then a later SDK ack.
        step(gen, 'green', gear=0 if stationary and gen==31 else 4,
             speed=2. if not stationary or gen>31 else 0.)
    assert state.get('autopilot_failure_epoch') == epoch
    assert state.get('autopilot_active'), state.get('navigation_status')
    assert pedal(engine, 'aforward') > 0. and pedal(engine, 'abackward') == 0.
    assert not any(ch == 'parkingbrake' for _, ch, v, _ in writes[start:])


def test_current_publication_during_old_traffic_read_does_not_latch_fault(flow, tmp_path):
    values, step, old = reactivation(flow, tmp_path)
    state, truck, engine, ap, tick, n, clock, writes, collector = values
    # Actual IPC copy semantics: old capture may have happened before a new
    # publication; a later tick must consume the new immutable value unchanged.
    original = state.get
    fired = []
    def read(key, default=None):
        value = original(key, default)
        if key == 'longitudinal_traffic' and not fired:
            fired.append(True)
            actual = original('telemetry')['truck']
            fresh = publish(state, actual, 'traffic', traffic_brake=0., light_brake=0.)
            assert fresh['context'][0] != old['context'][0]
        return value
    with patch.object(state, 'get', side_effect=read):
        tick.policy.on_tick(.02); tick.acc.on_tick(.02); ap.on_tick(.02); engine._flush_controls()
    assert fired
    assert state.get('autopilot_control_state') != 'controlled_stop'
    for gen in range(31, 36): step(gen, 'green', speed=2.)
    assert state.get('autopilot_active') and pedal(engine, 'aforward') > 0.


@pytest.mark.parametrize('mode', [0,3])
def test_cancellation_and_repeated_n_cannot_restore_previous_power(flow, tmp_path, mode):
    values, step, old = reactivation(flow, tmp_path, mode)
    state, truck, engine, ap, tick, n, clock, writes, collector = values
    epoch = state.get('autopilot_failure_epoch')
    for _ in range(3):
        tick.policy.on_tick(.02); tick.acc.on_tick(.02); ap.on_tick(.02); engine._flush_controls()
        assert pedal(engine,'aforward') == 0.
        n(); engine._flush_controls()
        assert not state.get('autopilot_active') and not state.get('auto_drive_pending')
        assert state.get('longitudinal_initialization') is None
        assert pedal(engine,'aforward') == pedal(engine,'abackward') == 0.
        flow[4](4,2.,dt=.02); n()
        assert state.get('autopilot_failure_epoch') != epoch
        epoch = state.get('autopilot_failure_epoch')
    for gen in range(31,36):step(gen,'green',speed=2.)
    assert state.get('autopilot_active') and pedal(engine,'aforward') > 0.


@pytest.mark.parametrize('mode', [0,3])
@pytest.mark.parametrize('fault', ['session','dataset','intent','build','revision','future','stale','invalid','reverse','backend'])
def test_initial_wait_does_not_mask_real_faults(flow, tmp_path, mode, fault):
    values, step, old = reactivation(flow, tmp_path, mode)
    state, truck, engine, ap, tick, n, clock, writes, collector = values
    engine._automatic_replay_directory = str(tmp_path)
    if fault in ('session','dataset','intent'):
        state.set({'session':'game_session_id','dataset':'active_dataset_fingerprint',
                   'intent':'navigation_intent_id'}[fault], 'foreign')
    elif fault in ('build','revision'):
        lane=state.get('lane_trajectory')
        lane['route_build_id' if fault=='build' else 'revision']='foreign' if fault=='build' else lane['revision']+1
        from core.ipc.shared_state import lane_publication_batch
        state.update_batch(lane_publication_batch({'lane_trajectory':lane}))
    elif fault=='invalid':
        state.set('longitudinal_traffic',dict(old,valid=False))
    elif fault in ('future','stale'):
        bad = copy.deepcopy(old)
        stamp = clock[0]+.1 if fault=='future' else clock[0]-.501
        bad.update(observation_timestamp=stamp, computed_at=stamp, expires_at=stamp+.5)
        state.set('longitudinal_traffic',bad)
    elif fault=='reverse':flow[4](-1,-.3,dt=.02)
    else:engine.controller.scs.connected=False
    start = len(writes)
    tick.policy.on_tick(.02); tick.acc.on_tick(.02); ap.on_tick(.02); engine._flush_controls()
    assert not any(ch=='aforward' and v>0 for _,ch,v,_ in writes[start:])
    assert state.get('autopilot_control_state') == 'controlled_stop' or not state.get('autopilot_active')
    first = state.get('autopilot_intervention')
    if first:
        from core.steering_replay import inspect_replay
        # A cleanup is not a new cause and the incident is immutable.
        engine.controller.release_all()
        engine._finish_automatic_longitudinal_incident(engine.controller._pedal_journal,shutdown=True)
        status = engine._automatic_replay_writer.wait(5.)
        assert not status['error'] and status['path']
        checked = inspect_replay(status['path'])
        assert checked['integrity_valid'] and not checked['confirmed']
        assert checked['replay']['longitudinal']['first_intervention']['reason'] == first['reason']


@pytest.mark.parametrize('stationary', [False,True])
def test_fixed_initialization_deadline_is_not_renewed_by_ticks(flow, tmp_path, stationary):
    values, step, old = reactivation(flow, tmp_path, stationary=stationary)
    state, truck, engine, ap, tick, n, clock, writes, collector = values
    request = state.get('longitudinal_initialization')
    assert request['expires_at']-request['started_at'] == pytest.approx(2.5 if stationary else .5)
    for _ in range(3):
        flow[4](0 if stationary else 4,0. if stationary else 2.,dt=.02)
        tick.policy.on_tick(.02); tick.acc.on_tick(.02); ap.on_tick(.02); engine._flush_controls()
        assert state.get('longitudinal_initialization') == request
    flow[4](0 if stationary else 4,0. if stationary else 2.,dt=request['expires_at']-clock[0]+.001)
    tick.policy.on_tick(.02); tick.acc.on_tick(.02); ap.on_tick(.02); engine._flush_controls()
    assert pedal(engine,'aforward') == 0.
    assert ('initialization timed out waiting for traffic' in str(state.get('navigation_status'))
            or 'initialization timed out waiting for traffic' in str(state.get('autopilot_intervention')))


@pytest.mark.parametrize('mode', [0,3])
def test_reactivated_red_wait_then_green_and_moving_green_releases(flow, tmp_path, mode):
    values, step, old = reactivation(flow, tmp_path, mode)
    state, truck, engine, ap, tick, n, clock, writes, collector = values
    tick.policy.on_tick(.02); tick.acc.on_tick(.02); ap.on_tick(.02); engine._flush_controls()
    for gen in range(31,34): step(gen,'red',speed=2.,progress=48.)
    start=len(writes)
    for gen in range(34,40): step(gen,'red',speed=0.,progress=48.,gear=0 if mode==0 else 4)
    assert state.get('autopilot_active') and pedal(engine,'abackward') > 0.
    assert all(v>0 for _,ch,v,_ in writes[start:] if ch=='abackward')
    for gen in range(40,50): step(gen,'green',speed=0. if gen<43 else .3,progress=48.,gear=0 if mode==0 and gen<43 else 4)
    assert state.get('autopilot_active') and pedal(engine,'aforward') > 0., state.get('navigation_status')
    for gen in range(50,53):step(gen,'red',speed=1.,progress=48.)
    for gen in range(53,60):step(gen,'green',speed=.92,progress=48.)
    assert state.get('simple_auto_service_hold') is None
    assert state.get('autopilot_active') and pedal(engine,'aforward') > 0.
    assert not any(ch=='parkingbrake' for _,ch,v,_ in writes[start:])


@pytest.mark.parametrize('source', ['policy','acc'])
def test_missing_required_producer_is_not_disguised_as_old_activation_wait(flow,tmp_path,source):
    values,step,old=reactivation(flow,tmp_path)
    state,truck,engine,ap,tick,n,clock,writes,collector=values
    # Resolve Traffic first so its earlier bounded wait cannot short-circuit
    # this independent required-producer loss (the established source contract).
    publish(state,state.get('telemetry')['truck'],'traffic',traffic_brake=0.,light_brake=0.)
    state.set('longitudinal_'+source,None)
    flow[4](4,2.,dt=.02)
    getattr(tick,'acc' if source=='policy' else 'policy').on_tick(.02)
    ap.on_tick(.02);engine._flush_controls()
    assert state.get('autopilot_control_state') == 'controlled_stop'
    assert pedal(engine,'aforward') == 0.
    assert 'missing or unsupported longitudinal packet' in str(state.get('autopilot_intervention'))


def test_current_emergency_bypasses_wait_for_older_policy(flow,tmp_path):
    values,step,old=reactivation(flow,tmp_path)
    state,truck,engine,ap,tick,n,clock,writes,collector=values
    actual=state.get('telemetry')['truck']
    publish(state,actual,'traffic',traffic_brake=1.,light_brake=0.)
    ap.on_tick(.02);engine._flush_controls()
    assert pedal(engine,'aforward')==0. and pedal(engine,'abackward')==1.
    assert state.get('longitudinal_applied')['emergency']


def test_old_activation_is_not_tolerated_after_first_real_output(flow,tmp_path):
    values,step,old=reactivation(flow,tmp_path)
    state,truck,engine,ap,tick,n,clock,writes,collector=values
    for gen in range(31,35):step(gen,'green',speed=2.)
    assert state.get('longitudinal_initialization') is None
    assert pedal(engine,'aforward')>0.
    state.set('longitudinal_traffic',old)
    ap.on_tick(.02);engine._flush_controls()
    assert state.get('autopilot_control_state')=='controlled_stop'
    assert pedal(engine,'aforward')==0.
