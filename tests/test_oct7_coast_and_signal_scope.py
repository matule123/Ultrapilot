"""Production lifecycle; SDK/game response is an explicit offline model."""
import math

import pytest

from core.longitudinal import context, publish
from core.sdk.signal_snapshot import RouteSignalSelector
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_oct4_signal_lifecycle import lifecycle
from tests.test_roundabout_intervention_reporting import pedal
from tests.test_rolling_longitudinal_authority import rolling  # noqa: F401


def test_prepared_unregulated_passage_cannot_acquire_foreign_nearby_red():
    light = dict(id=99, x=2., y=10., z=-20., yaw=math.pi, color='red')
    signal = dict(valid=True, lifecycle=1, generation=1, frame_us=1,
                  observed_at=100., lights=[light])
    result = RouteSignalSelector().select(signal, [[0., 10., 0.], [0., 10., -50.]],
        'route', ('authority',), dict(x=0., y=10., z=0., rotation=0.), 0.,
        dict(schema_version=1, status='prepared', passages=[]))
    assert result['candidate'] is None
    assert result['valid'] is False
    assert result['relevance'] == 'detected_only_unassigned'


def test_real_map_unregulated_passage_does_not_feed_foreign_red_to_policy(rolling):
    import struct
    from core.sdk.signal_snapshot import SignalReader, LAYOUT
    state, engine, ap, acc, policy, map_tick, observe, n, physical, writes, clock = rolling
    map_tick(speed=2., z=20., pedals=False)
    truck = state.get('telemetry')['truck']
    assert state.get('lane_trajectory')['signal_passages']['passages'] == []
    engine._signal_reader = SignalReader()
    engine._signal_selector = RouteSignalSelector()
    engine._signal_route_token = None
    # Ego travels +Z (yaw pi); a foreign head faces the other direction.
    # The original identity quaternion faced ego and was an unassigned LIVE
    # approach head, which the later coverage contract must fail closed on.
    payload = struct.pack('<fffhhffffifii', 2.25,10.,50.,0,0,0.,0.,1.,0.,1,10.,2,99)+bytes(1920-48)
    engine._signal_reader.buffer = LAYOUT.pack(2,0x32535055,2,LAYOUT.size,11,1,
        truck['sdkFrameTimeUs'],clock[0],3,1,payload,2)
    signal = engine._signal_observation(truck, context(state))
    assert not signal['valid'] and signal['candidate'] is None
    assert not signal['coverage']['requires_takeover']
    publish(state, truck, 'traffic', light=signal['candidate'], signal=signal,
            light_brake=engine._light_brake(signal['candidate']), traffic_brake=0.)
    policy.on_tick(.033333); acc.on_tick(.033333); ap.on_tick(.033333)
    engine._flush_controls()
    assert state.get('autopilot_active')
    assert physical('abackward') == 0 and physical('aforward') > 0


def test_same_facing_unassigned_live_head_on_real_map_is_not_free_passage(rolling):
    import struct
    from core.sdk.signal_snapshot import SignalReader,LAYOUT
    state,engine,ap,acc,policy,map_tick,observe,n,physical,writes,clock=rolling
    map_tick(speed=2.,z=20.,pedals=False)
    truck=state.get('telemetry')['truck']
    engine._signal_reader=SignalReader();engine._signal_selector=RouteSignalSelector();engine._signal_route_token=None
    payload=struct.pack('<fffhhffffifii',2.25,10.,50.,0,0,1.,0.,0.,0.,1,10.,2,99)+bytes(1920-48)
    engine._signal_reader.buffer=LAYOUT.pack(2,0x32535055,2,LAYOUT.size,11,1,
        truck['sdkFrameTimeUs'],clock[0],3,1,payload,2)
    signal=engine._signal_observation(truck,context(state))
    assert signal['coverage']['requires_takeover'] and signal['candidate'] is None
    publish(state,truck,'traffic',signal=signal,light=None,light_brake=0.,traffic_brake=0.)
    policy.on_tick(.033333);acc.on_tick(.033333);ap.on_tick(.033333);engine._flush_controls()
    assert state.get('autopilot_control_state')=='controlled_stop'
    assert physical('aforward')==0. and physical('abackward')>0.


def test_actual_map_with_independent_executor_coasts_on_zero_ratio(rolling):
    state, engine, ap, acc, policy, tick, observe, n, physical, writes, clock = rolling
    state.set('acc_target_speed', .47177308797836304*3.6)
    for _ in range(18):
        tick(speed=.47177308797836304, z=15.)
    tick(gear=0, speed=.47177308797836304, z=15.)
    engine._flush_controls()
    assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    assert physical('aforward') == physical('abackward') == 0


@pytest.mark.parametrize('engine_first', [False, True])
def test_zero_pedal_coast_does_not_require_propulsion_or_old_confirmation(flow, engine_first):
    state, truck, engine, ap, tick, n, clock, writes, collected = lifecycle(flow)
    # The real producers are independently scheduled while Engine confirmation
    # is older than .5 s. This is a fresh forward COAST, never neutral drive.
    state.set('acc_target_speed', .47177308797836304*3.6)
    for _ in range(6):
        tick(4, .47177308797836304, dt=.09, flush=False)
    before = len(writes)
    tick(0, .47177308797836304, engine_first=engine_first)
    assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    assert pedal(engine, 'aforward') == pedal(engine, 'abackward') == 0
    assert state.get('simple_auto_forward_history')['phase'] == 'zero_ratio_transition'
    for _ in range(3):
        tick(0, .45)
        assert state.get('autopilot_active')
    assert not any(ch == 'aforward' and value > 0 for _, ch, value, _ in writes[before:])
    tick(4, .45)
    assert state.get('autopilot_active')


@pytest.mark.parametrize('fault', ['expired_coast', 'stale', 'identity', 'reverse', 'manual'])
def test_coast_cannot_renew_forever_or_bypass_real_safety(flow, fault):
    state, truck, engine, ap, tick, n, clock, writes, collected = lifecycle(flow)
    state.set('acc_target_speed', .47177308797836304*3.6)
    for _ in range(6):
        tick(4, .47177308797836304, dt=.09, flush=False)
    tick(0, .47177308797836304)
    assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    count = len(writes)
    if fault == 'expired_coast':
        for _ in range(6):
            tick(0, .4, dt=.09)
    elif fault == 'stale':
        clock[0] += .501
        engine._flush_controls()
    elif fault == 'identity':
        state.set('active_dataset_fingerprint', 'other')
        engine._flush_controls()
    elif fault == 'reverse':
        tick(-1, -.2)
    else:
        n()
        engine._flush_controls()
    assert not any(ch == 'aforward' and value > 0 for _, ch, value, _ in writes[count:])
    assert (not state.get('autopilot_active')
            or state.get('autopilot_control_state') == 'controlled_stop')


@pytest.mark.parametrize('fault', ['missing', 'old', 'future_frame', 'future_time', 'foreign'])
def test_coast_receipt_cannot_be_invented_from_old_or_foreign_ratio(flow, fault):
    state, truck, engine, ap, tick, n, clock, writes, collected = lifecycle(flow)
    state.set('acc_target_speed', .47177308797836304*3.6)
    for _ in range(6):
        tick(4, .47177308797836304, dt=.09, flush=False)
    value = state.get('simple_auto_forward_observation')
    if fault == 'missing':
        value = None
    elif fault == 'old':
        value['observation_timestamp'] -= .501
    elif fault == 'future_frame':
        value['sdk_frame_us'] += 10000000
    elif fault == 'future_time':
        value['observation_timestamp'] += 1.
    else:
        value['context'] = ('another-activation',)
    state.set('simple_auto_forward_observation', value)
    count = len(writes)
    tick(0, .47177308797836304)
    assert not state.get('autopilot_active')
    assert not any(ch == 'aforward' and v > 0 for _,ch,v,_ in writes[count:])
