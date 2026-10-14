"""Candidate follow-up: actual-box protection, never a game safety certificate."""
import math
import struct
from types import SimpleNamespace

import pytest

from tests.test_oct11_joint_regressions import joint  # noqa: F401
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_oct14_completion import native_bytes
from tests.test_acc_following import capture


def test_current_body_overlap_does_not_require_future_route_segment():
    from core.acc_body_prediction import predict
    from core.acc_following import RouteLeadSelector
    route = RouteLeadSelector()
    route.prepare([[0., 10., 0.], [0., 10., 1.]], ('short',))
    ego = dict(x=0., y=10., z=.5, yaw=math.pi, dimensions_whl=(2.5, 4., 6.))
    actor = dict(id=17, source='moving', temporary=False, speed_source='buffer',
                 speed=10., bodies=[dict(ego, x=1.)])
    result = predict(route, [ego], [actor], 10., .5, (0., 10., .5))
    assert result['brake'] == 1.
    assert result['conflicts'][0]['contact_basis'] == 'observed_overlap_at_source_frame'
    assert not result['complete_envelope_verified']


def test_parked_box_conflict_reaches_real_emergency_backend(joint):
    from core.sdk.ets2la_data import _PARKED_FMT
    from core.sdk.traffic_snapshot import TrafficReader
    from core.navigation.traffic_producer import capture_traffic, TrafficCapture
    from core.longitudinal import context
    state, engine, ap, acc, policy, tick, _, _, physical, writes, clock = joint
    tick(gear=4, speed=10., z=15., pedals=False)
    truck = state.get('telemetry')['truck']
    # Parked body's actual box intersects the measured trailer but its centre
    # lies outside the old centreline candidate gate. No invented moving speed.
    raw = capture([], clock[0])
    parked = list(struct.unpack(_PARKED_FMT, raw.parked))
    parked[:12] = [5., 10., 17., 0., 0., 1., 0., 2., 2., 4., 77, 0]
    raw = TrafficCapture(raw.session, raw.observed_at, raw.moving,
                         struct.pack(_PARKED_FMT, *parked), True)
    ego = [(2.25, 10., 15., 0., 0., 1., 0., 2.5, 4., 6.),
           (2.25, 10., 6., 0., 0., 1., 0., 4., 4., 12.)]
    reader = TrafficReader()
    reader.buffer = native_bytes(raw, clock[0], frame=truck['sdkFrameTimeUs'],
        ego=ego, anchor=(truck['x'], truck['y'], truck['z']))
    observed = capture_traffic(SimpleNamespace(_timed_traffic_reader=reader),
                               str(context(state)[1]), clock[0])
    following, brake = engine._traffic_control_observation(observed, truck, context(state), [])
    engine._publish_traffic_control(truck, truck['_control_observation']['observed_at'],
        context(state), [], observed, following, brake,
        dict(valid=False, candidate=None, reason='no head', coverage={}), None)
    policy.on_tick(.033); acc.on_tick(.033); ap.on_tick(.033); engine._flush_controls()
    body = following['body_prediction']
    assert body['brake'] == 1., body
    assert body['conflicts'][0]['actor_motion_basis'] == 'native_parked_classification_static_model'
    assert physical('aforward') == 0. and physical('abackward') == 1.


@pytest.mark.parametrize('fault', ['height', 'missing_dimensions', 'TMP', 'unknown_motion'])
def test_body_prediction_does_not_invent_geometry_or_motion(fault):
    from core.acc_body_prediction import predict
    from core.acc_following import RouteLeadSelector
    route = RouteLeadSelector(); route.prepare([[0.,10.,0.],[0.,10.,100.]], ('route',))
    ego = dict(x=0., y=10., z=10., yaw=math.pi, dimensions_whl=(2., 4., 6.))
    actor = dict(id=1, source='moving', temporary=False, speed_source='buffer',
                 speed=0., bodies=[dict(ego)])
    if fault == 'height': actor['bodies'][0]['y'] = 20.
    elif fault == 'missing_dimensions': actor['bodies'][0]['dimensions_whl'] = ()
    elif fault == 'TMP': actor['temporary'] = True
    else: actor['speed_source'] = 'unknown'
    assert predict(route,[ego],[actor],10.,10.,(0.,10.,10.))['brake'] == 0.


def test_actual_sdk_response_and_load_fields_survive_normalization_and_codec():
    from core.sdk.scs_sdk import SCSTelemetry
    from core.telemetry import Telemetry
    from core.navigation.longitudinal_diagnostics import local_source_snapshot, pack_source, unpack_source
    reader = SCSTelemetry(); reader.mm = bytearray(reader.mmap_size)
    struct.pack_into('<I', reader.mm, 40, 12)
    struct.pack_into('<Q', reader.mm, 8, 123456)
    for offset, value in ((948, 10.), (976, .25), (980, .0), (964, 0.),
                          (748, 22000.), (944, 11000.)):
        struct.pack_into('<f', reader.mm, offset, value)
    struct.pack_into('<d', reader.mm, 2232, .01)
    raw = reader._decode_control_snapshot()
    raw['controlRead'] = dict(stable=True, observed_at=100., sdk_frame_us=123456)
    telemetry = Telemetry.__new__(Telemetry)
    normalized = telemetry._normalize_sdk(raw)['truck']
    normalized['_control_observation'] = dict(valid=True, observed_at=100., sdk_frame_us=123456)
    assert normalized['gameThrottle'] == .25 and normalized['gameBrake'] == 0.
    restored = unpack_source(pack_source(local_source_snapshot(normalized)))
    assert restored['sdk_response']['gameThrottle'] == .25
    load = restored['load_observation']
    assert load['cargo_mass_kg'] == 22000. and load['unit_mass_kg'] == 11000.
    assert load['chassis_pitch_rad'] == pytest.approx(.01*math.tau)
    assert load['total_mass_verified'] is False


@pytest.mark.parametrize('revision', [0, 11, 13])
def test_unknown_sdk_abi_does_not_invent_load_or_response(revision):
    from core.sdk.scs_sdk import SCSTelemetry
    reader = SCSTelemetry(); reader.mm = bytearray(reader.mmap_size)
    struct.pack_into('<I', reader.mm, 40, revision)
    raw=reader._decode_control_snapshot()
    assert raw.get('loadObservation') is None
    assert raw['truckFloat'].get('gameThrottle') is None


def test_incomplete_original_stop_ownership_never_recovers_from_a_smaller_list(joint):
    from tests.test_oct14_completion import timed_step
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    actor=dict(id=91,x=-15.,y=10.,z=50.,yaw=-math.pi/2,speed=5.)
    timed_step(joint,[actor],generation=1,speed=10.)
    # Real bounded ownership: the next observed stop adds 17 unique conflicts,
    # so the complete original cause set cannot be retained in 16 owner slots.
    timed_step(joint,[dict(actor,id=91+i,z=50.+i*.1) for i in range(17)],
               generation=2,speed=10.)
    hold=state.get('simple_auto_service_hold')
    assert hold and (not hold['traffic_lock']['complete']
                     or 'unqualified_traffic' in hold['other_stop_sources']),hold
    timed_step(joint,[actor],generation=3,speed=10.)
    hold=state.get('simple_auto_service_hold')
    assert not hold['traffic_lock']['complete'] or 'unqualified_traffic' in hold['other_stop_sources']
    assert physical('aforward')==0.


def calibration_history(drive=2.2, brake=4., drift=-.1):
    rows=[]; speed=10.; at=100.; sequence=1
    # Fixed explicit local plant, no ETS2/cargo-force measurement claim.
    for t,b in [(0.,0.),(.15,0.),(0.,.08),(.2,0.),(0.,.12)]*3:
        for _ in range(32):
            speed+=(drive*t-brake*b+drift)*.1
            rows.append(dict(monotonic_s=at+.03,observation_timestamp=at,sdk_frame_us=sequence,
                activation=1,identity_reference='1',gear=4,phase='active',speed_mps=speed,
                command_valid=True,command_sdk_frame_us=sequence,command_expires_at=at+.3,
                observation_valid=True,sdk_game_throttle=t,sdk_game_brake=b,
                sdk_user_throttle=0.,sdk_user_brake=0.,written_throttle=t,written_brake=b,
                last_backend_status='MAPPING_WRITE_RETURNED',write_last_returned_at_s=at+.02,
                load_observation=dict(abi_revision=12,cargo_mass_kg=22000.,unit_mass_kg=11000.,
                    chassis_pitch_rad=0.,motor_brake=False,retarder_step=0)))
            at+=.1;sequence+=1
    return dict(regular_samples=rows)


def test_passive_calibration_recovers_distinct_load_response_without_changing_controller():
    from tools.analyze_actuator_calibration import analyze
    for drive,brake in ((2.2,4.),(1.2,3.)):
        result=analyze(calibration_history(drive,brake))
        assert result['status']=='PASSIVE_ESTIMATES',result
        assert not result['runtime_authorized'] and not result['game_consumption_verified']
        for estimate in result['estimates']:
            assert estimate['drive_gain_mps2']==pytest.approx(drive)
            assert estimate['brake_gain_mps2']==pytest.approx(brake)
            assert estimate['drift_mps2']==pytest.approx(-.1)


@pytest.mark.parametrize('fault', ['missing', 'manual', 'retarder', 'future_write', 'unexcited', 'unknown',
                                 'expired', 'ahead', 'pulse'])
def test_passive_calibration_cannot_authorize_unqualified_or_unobservable_gain(fault):
    from tools.analyze_actuator_calibration import analyze
    history=calibration_history()
    for row in history['regular_samples']:
        if fault=='missing':row['sdk_game_brake']=None
        elif fault=='manual':row['sdk_user_throttle']=.1
        elif fault=='retarder':row['load_observation']['retarder_step']=1
        elif fault=='future_write':row['write_last_returned_at_s']=row['monotonic_s']+.01
        elif fault=='unexcited':row.update(sdk_game_brake=0.,sdk_game_throttle=0.,written_brake=0.,written_throttle=0.)
        elif fault=='expired':row['command_expires_at']=row['observation_timestamp']-.01
        elif fault=='ahead':row['command_sdk_frame_us']=row['sdk_frame_us']+1
        elif fault=='pulse':row['aggregate']=dict(backend_pair_mode_changes=2)
        else:row['gear']=None
    result=analyze(history)
    assert result['status']=='NOT_MEASURED' and not result['estimates']
    assert not result['runtime_authorized']


def test_computed_lane_endpoint_is_not_a_unique_gps_destination(joint, flow):
    """Contract boundary, not a claimed new repair of automatic GPS removal."""
    from core.longitudinal import destination_stop_control
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    state.set('game_gps_navigation_active',True)
    endpoints=[]
    for remaining in (100.,200.):
        flow[1]['routeDistance']=remaining
        tick(gear=4,speed=4.,pedals=False)
        lane=state.get('lane_trajectory')
        assert lane['route_horizon_complete']
        endpoints.append(lane['points'][-1])
        actual=state.get('telemetry')['truck']
        assert destination_stop_control(state,actual)['distance_m']==remaining
    # Real Map processing resolved the same full UID window, while the live
    # GPS remainder changed: lane geometry does not encode an exact user goal.
    assert endpoints[0]==endpoints[1]
