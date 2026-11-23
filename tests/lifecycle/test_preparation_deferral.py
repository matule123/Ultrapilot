"""Nov 2 clocks/frames, with explicitly modeled route/pose and tick ordering."""
from unittest.mock import patch
import pytest
from tests.test_rolling_longitudinal_authority import rolling as rolling_fixture
from tests.test_activation_observation_binding import flow  # noqa: F401


@pytest.fixture(params=[0,3])
def rolling(flow, request):
    from tests.test_longitudinal_arbitration import strict_flow
    with patch('tests.test_rolling_longitudinal_authority.strict_flow',
               side_effect=lambda raw:strict_flow(raw,mode=request.param)):
        generator=rolling_fixture.__wrapped__(flow)
        try:yield next(generator)
        finally:generator.close()

@pytest.mark.parametrize('age', [.15, .3016099])
def test_slow_unconsumed_preparation_does_not_revoke_last_fresh_calculation(rolling, age):
    state, engine, ap, acc, policy, tick, observe, n, physical, writes, clock = rolling
    tick(speed=4.37)
    mapper = tick.publish_map.__self__
    previous = state.get('nav_steering_debug')
    old_frame = previous['sdk_frame_us']
    # New real observation was captured at the start of preparation but the
    # SDK publisher has not advanced again by the final read. It must NOT be
    # calculated after exceeding the existing dynamics preparation budget.
    prepared = dict(state.get('vehicle_envelope_snapshot'), sdk_frame_us=old_frame+16666,
                    timestamp=clock[0]+.02)
    clock[0] += .02
    state.set('vehicle_envelope_snapshot', prepared)
    with patch.object(mapper, '_publish_road_type', side_effect=lambda pos: clock.__setitem__(0, clock[0]+age)):
        mapper.on_tick(.02)
    assert state.get('nav_steering_debug') == previous
    assert state.get('nav_active'), state.get('navigation_failure_reason')
    assert mapper._last_steering_sdk_frame_us == old_frame
    # Same actual Engine route projection which produced the secondary Nov 2
    # route_unavailable status. Actors here are the existing maximum-load ABI
    # model, NOT reconstructed historical actor 79 poses.
    from tools.qualify_oct25_traffic_capture import raw_capture
    from core.longitudinal import context
    capture=raw_capture(40,3,clock[0],prepared['sdk_frame_us'],1,
                        str(state.get('game_session_id')),4.37)
    projected=engine._route_lead_observation(capture,truck=state.get('telemetry')['truck'],binding=context(state))
    assert projected['status'] != 'route_unavailable_or_ambiguous', projected
    # Existing producers and actual SCS Controller still validate the ORIGINAL
    # packet and deadline; a failed new attempt is not a new control result.
    policy.on_tick(.02); acc.on_tick(.02); ap.on_tick(.02); engine._flush_controls()
    assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    assert not engine._gps_propulsion_suppressed
    tick(speed=4.37); engine._flush_controls()
    assert state.get('autopilot_active')
    assert state.get('nav_steering_debug')['sdk_frame_us'] > old_frame
    clock[0] += .501
    ap.on_tick(.02); engine._flush_controls()
    assert physical('aforward') == 0.
    assert not state.get('autopilot_active') or state.get('autopilot_control_state') == 'controlled_stop'


@pytest.mark.parametrize('fault', ['stale', 'future', 'regressed', 'incoherent', 'revision', 'activation', 'backend', 'reverse'])
def test_deferral_preserves_real_rejections(rolling, fault):
    state, engine, ap, acc, policy, tick, observe, n, physical, writes, clock = rolling
    tick(speed=4.)
    mapper=tick.publish_map.__self__
    prior=state.get('nav_steering_debug')
    observation=dict(state.get('vehicle_envelope_snapshot'),timestamp=clock[0]+.02,
        sdk_frame_us=prior['sdk_frame_us']+16666)
    clock[0]+=.02
    if fault=='future':observation['timestamp']=clock[0]+1.
    if fault=='regressed':observation['sdk_frame_us']=prior['sdk_frame_us']-16666
    state.set('vehicle_envelope_snapshot',observation)
    def prepare(pos):
        clock[0]+=.55 if fault=='stale' else .15
        if fault=='revision':state.set('lane_trajectory_revision',999)
        if fault=='incoherent':state.set('vehicle_envelope_snapshot',dict(observation,tractor_speed_ms=99.))
    with patch.object(mapper,'_publish_road_type',side_effect=prepare):mapper.on_tick(.02)
    if fault=='activation':n()
    write_start=len(writes)
    if fault=='backend':engine.controller.scs.connected=False
    if fault=='reverse':
        telemetry=state.get('telemetry');telemetry['truck']['gear']=-1
        state.set('telemetry',telemetry)
    policy.on_tick(.02);acc.on_tick(.02);ap.on_tick(.02);engine._flush_controls()
    if fault=='backend':
        # A disconnected mapping cannot attest that an attempted zero reached
        # it. Require authority removal and no new positive physical call.
        assert not state.get('autopilot_active')
        assert all(v==0 for _,channel,v in writes[write_start:] if channel=='aforward')
    else:
        assert physical('aforward')==0.
        assert not state.get('autopilot_active') or state.get('autopilot_control_state')=='controlled_stop'
