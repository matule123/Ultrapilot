"""Real map admissions, real producers and chronological physical pedal writes.

Backend return is not ETS2 input consumption; fixture metadata is not proof of
a installed traffic head. The bounded plant is a separate model.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from core.longitudinal import signal_stop_brake_request, context
from core.navigation.road_network import RoadNetwork, _uid
from core.navigation.lane_model import GpsCorridorEdge
from core.navigation.lane_trajectory import build_lane_trajectory
from core.navigation.prefab_signals import prepare_signal_passages
from core.sdk.signal_snapshot import RouteSignalSelector
from core.transmission_mode import read_transmission_mode, confirmed_mode
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_oct8_stop_lifecycle import directed_stop
from tests.test_roundabout_intervention_reporting import pedal


def actual_passage(tmp_path, placement=0):
    raw = json.loads((Path(__file__).parent/'fixtures/oct8-real-signal-prefabs.json').read_text())
    (tmp_path/'prefabDescriptions.json').write_text(json.dumps([raw['descriptor']]))
    (tmp_path/'prefabs.json').write_text(json.dumps(raw['prefabs']))
    net = RoadNetwork()
    for node in raw['nodes']:
        uid = _uid(node['uid'])
        net.nodes[uid] = (float(node['x']), float(node['y']))
        net.node_alt[uid] = float(node['z'])
        net.node_rot[uid] = float(node.get('rotation', 0.))
    net._load_prefabs(str(tmp_path))
    placed = raw['prefabs'][placement]
    instance = next(v for group in net._prefab_pairs.values() for v in group
        if v[0] == placed['token'] and set(v[1]) == {_uid(u) for u in placed['nodeUids']})
    data = net._prefab_lane_data[placed['token']]
    # Actual incident ID 1 entry; directed chain from the consumed PPD graph.
    indices = (30, 4, 13, 24)  # valid ID-1 chain on the recorded real placement
    assert net._curve_chain_is_valid(data, indices)
    entrances = [i for i,n in enumerate(data['nodes']) if indices[0] in n['input_lanes']]
    exits = [i for i,n in enumerate(data['nodes']) if indices[-1] in n['output_lanes']]
    points = net._prefab_curve_chain_3d(instance, indices)
    edge = GpsCorridorEdge(instance[1][entrances[0]], instance[1][exits[0]], 'prefab', 0,
                          prefab_instance=instance)
    segment = net._make_prefab_lane_segment(edge, instance, indices, points)
    path = build_lane_trajectory(net.connect_lane_sequence((segment,), (edge.start_uid, edge.end_uid)))
    assert path.valid, path.failure_reason
    return net, path, prepare_signal_passages(net, path)


@pytest.mark.parametrize('placement', [0, 1])
def test_actual_map_id_without_live_corroboration_is_not_a_red_stop(tmp_path, placement):
    net, path, plan = actual_passage(tmp_path, placement)
    p = path.points[0]
    snap = dict(valid=True, lifecycle=1, generation=1, frame_us=1, observed_at=100., lights=[])
    result = RouteSignalSelector().select(snap, [[p.x,p.y,p.z] for p in path.points],
        'p', ('a',), dict(x=p.x,y=p.y,z=p.z,rotation=p.heading), 0., plan)
    assert plan['passages'][0]['semaphore_id'] == 1  # NOT the -1 sentinel
    assert not result.get('prefab_required') and not result.get('stop_candidate')
    assert not result['valid'] and result['candidate'] is None


def test_under_profile_has_no_brake_without_an_acknowledged_stop_chain():
    light = dict(color='red', distance=80., stop_target_kind='derived_directed_curve_entry')
    assert signal_stop_brake_request(light, 1., continuing=False) == 0.
    # Only an actual admitted planned-stop chain may continue positively;
    # ordinary ACC braking cannot create that witness (integration below).
    assert signal_stop_brake_request(light, 1., continuing=True) > 0.


@pytest.mark.parametrize('mode', [0, 3])
def test_unrelated_speed_brake_does_not_latch_future_signal_as_a_wait(flow, mode):
    values, step = directed_stop(flow, mode)
    state, truck, engine, ap, tick, n, clock, writes, collected = values
    lane = state.get('lane_trajectory')
    lane['points'] = [[0.,10.,100.],[0.,10.,-50.]]
    lane['signal_passages']['passages'][0]['entry_progress_m'] = 110.
    truck['z'] = 100.
    state.set('lane_trajectory', lane); state.set('lane_trajectory_publication_token', 'far')
    # ACC's own genuine ordinary overspeed demand; no traffic following stop.
    state.set('acc_target_speed', 10.)
    signal = step(4, 10., color=2)
    assert signal['valid'] and signal['candidate']['distance'] == pytest.approx(102.)
    assert state.get('longitudinal_traffic')['light_brake'] == 0.
    assert pedal(engine, 'abackward') > 0.
    assert not state.get('simple_auto_service_hold')


def test_unobserved_nearer_map_group_cannot_hide_a_qualified_later_head(flow):
    values, step = directed_stop(flow)
    state, truck, engine, ap, tick, n, clock, writes, collected = values
    lane = state.get('lane_trajectory')
    actual = lane['signal_passages']['passages'][0]
    ghost = dict(actual, semaphore_id=77, passage_key='ghost-map-template', entry_progress_m=9.)
    lane['signal_passages']['passages'].insert(0, ghost)
    state.set('lane_trajectory', lane); state.set('lane_trajectory_publication_token', 'ghost-then-real')
    signal = step(4, 2., color=2)
    assert signal['valid'] and signal['candidate']['id'] == 19
    assert pedal(engine, 'abackward') > 0 and pedal(engine, 'aforward') == 0


@pytest.mark.parametrize('mode', [0, 3])
def test_hold_keeps_proven_decelerating_pedal_not_the_last_tiny_value(flow, mode):
    values, step = directed_stop(flow, mode)
    state, truck, engine, ap, tick, n, clock, writes, collected = values
    step(4, 2., color=2)
    peak = pedal(engine, 'abackward')
    for speed in (.7, .2, .06, .01, 0.):
        step(4 if speed > .05 or mode == 3 else 0, speed, color=2)
    assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    assert pedal(engine, 'abackward') >= peak
    assert pedal(engine, 'aforward') == 0


def profile(root, mode=0):
    encoded = 'driver'.encode().hex().upper()
    cfg = root/'steam_profiles'/encoded/'config_local.cfg'; cfg.parent.mkdir(parents=True)
    cfg.write_text(f'uset g_trans "{mode}"\n')
    log = root/'game.log.txt'
    log.write_text('************ : log created on : '+(datetime.now()-timedelta(minutes=1)).strftime('%A %B %d %Y @ %H:%M:%S')+'\n'
        f'00:00:01.000 : uset g_trans "{mode}"\n00:00:01.100 : Set profile finished: \'driver\'\n'
        f'00:00:02.000 : /steam/profiles/{encoded}/save/game.sii\n')
    return log, cfg


def test_transmission_log_append_is_a_coherent_prefix_not_a_mode_change(tmp_path, monkeypatch):
    log, cfg = profile(tmp_path)
    original_text, original_bytes = Path.read_text, Path.read_bytes
    def read_text(path, *a, **kw):
        value = original_text(path, *a, **kw)
        if path == log:
            with log.open('a') as f: f.write('00:00:03.000 : harmless running-game append\n')
        return value
    def read_bytes(path, *a, **kw):
        value = original_bytes(path, *a, **kw)
        if path == log:
            with log.open('a') as f: f.write('00:00:03.000 : harmless running-game append\n')
        return value
    monkeypatch.setattr(Path, 'read_text', read_text); monkeypatch.setattr(Path, 'read_bytes', read_bytes)
    import core.transmission_mode as module
    if hasattr(module, '_read_log_bytes'):
        read = module._read_log_bytes
        def append_read(path):
            value = read(path)
            with log.open('a') as f: f.write('00:00:03.000 : harmless running-game append\n')
            return value
        monkeypatch.setattr(module, '_read_log_bytes', append_read)
    evidence = read_transmission_mode(tmp_path)
    assert confirmed_mode(evidence) == 0, evidence


def test_immediate_n_can_revalidate_actual_fresh_authority_without_old_summary(flow):
    values, step = directed_stop(flow)
    state, truck, engine, ap, tick, n, clock, writes, collected = values
    n()  # manual disable
    flow[4](4, .3, dt=.6)  # actual new coherent SDK + steering + heartbeat
    # The producer-side readiness summary predates the reads; never renew it.
    original = state.get('autopilot_navigation_readiness')
    assert clock[0]-original['timestamp'] > .5
    n()
    assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    assert state.get('autopilot_navigation_readiness') == original


@pytest.mark.parametrize('fault', ['rewrite', 'truncate', 'replace', 'profile', 'mode', 'partial'])
def test_log_race_never_confirms_rewritten_or_unconfirmed_mode(tmp_path, monkeypatch, fault):
    import core.transmission_mode as module
    log, cfg = profile(tmp_path)
    original = module._read_log_bytes
    calls = []
    def racing_read(path):
        data = original(path)
        if not calls:
            calls.append(True)
            if fault == 'rewrite':
                log.write_bytes(data.replace(b'g_trans "0"', b'g_trans "3"'))
            elif fault == 'truncate':
                log.write_bytes(b'incomplete new session\n')
            elif fault == 'replace':
                replacement = tmp_path/'replacement.txt'
                replacement.write_bytes(data); replacement.replace(log)
            elif fault == 'profile':
                with log.open('a') as f: f.write("00:00:03.000 : Set profile finished: 'other'\n")
            elif fault == 'mode':
                cfg.write_text('uset g_trans "3"\n')
            else:
                cfg.write_text('uset g_trans "3"\n')
                with log.open('a') as f: f.write('00:00:03.000 : uset g_trans "3"')
        return data
    monkeypatch.setattr(module, '_read_log_bytes', racing_read)
    found = read_transmission_mode(tmp_path)
    # A concurrent new profile after the captured immutable prefix is detected
    # on the next bounded acquisition, never merged into the previous session.
    if fault == 'profile':
        assert confirmed_mode(read_transmission_mode(tmp_path)) is None
    else:
        assert confirmed_mode(found) is None, found


def test_same_metadata_cannot_hide_a_same_size_game_log_rewrite(tmp_path,monkeypatch):
    import core.transmission_mode as module
    log,cfg=profile(tmp_path)
    original_read=module._read_log_bytes
    original_stat=Path.stat
    captured_stat=original_stat(log)
    def stale_metadata(path,*args,**kwargs):
        return captured_stat if path==log else original_stat(path,*args,**kwargs)
    calls=[]
    def race(path):
        data=original_read(path)
        if not calls:
            calls.append(True);log.write_bytes(data.replace(b'g_trans "0"',b'g_trans "3"'))
        return data
    monkeypatch.setattr(Path,'stat',stale_metadata)
    monkeypatch.setattr(module,'_read_log_bytes',race)
    found=read_transmission_mode(tmp_path)
    assert confirmed_mode(found) is None,found
    assert found['reason']=='game log changed during read'


@pytest.mark.parametrize('mode', [0, 3])
def test_log_append_while_holding_keeps_same_evidence_and_allows_green(flow, tmp_path, monkeypatch, mode):
    import core.transmission_mode as module
    values, step = directed_stop(flow, mode, start=False)
    state, truck, engine, ap, tick, n, clock, writes, collected = values
    log, cfg = profile(tmp_path, mode)
    confirmed = read_transmission_mode(tmp_path)
    state.set('ets2_transmission_mode', confirmed)
    n()
    step(0, 0., color=8)
    for speed in (.001, .2, .3): step(4, speed, color=8)
    assert state.get('autopilot_active')
    read = module._read_log_bytes
    def append_read(path):
        value = read(path)
        with log.open('a') as f: f.write('00:00:03.000 : ordinary frame event\n')
        return value
    monkeypatch.setattr(module, '_read_log_bytes', append_read)
    for speed in (2., .7, .2, .04, 0., 0.):
        fresh = read_transmission_mode(tmp_path)
        assert confirmed_mode(fresh) == mode
        assert fresh['log_identity'] == confirmed['log_identity']
        assert fresh['generation'] == confirmed['generation']
        state.set('ets2_transmission_mode', fresh)
        step(0 if speed < .05 and mode == 0 else 4, speed)
        assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    start = len(writes)
    step(0 if mode == 0 else 4, 0., color=8)
    step(0 if mode == 0 else 4, 0., color=8, dt=.12)
    for speed in (.001, .2, .3): step(4, speed, color=8)
    assert state.get('autopilot_active') and pedal(engine, 'aforward') > 0
    assert not any(ch == 'parkingbrake' for _, ch, _, _ in writes[start:])


def test_failed_signal_read_retains_only_stop_dependency(flow):
    values, step = directed_stop(flow)
    state, truck, engine, ap, tick, n, clock, writes, collected = values
    step(4, 2., color=8)
    lane = state.get('lane_trajectory')
    result = engine._signal_selector.select(dict(valid=False, reason='mapping unavailable'),
        lane['points'], 'oct8-direct', context(state), state.get('telemetry')['truck'],
        0., lane['signal_passages'])
    assert not result['valid'] and result['candidate'] is None
    assert result['stop_candidate']['head_observed'] is False
    assert result['stop_candidate']['color'] == 'unknown'


def test_invalid_passage_key_is_rejected_without_crashing_selector(flow):
    values, step = directed_stop(flow)
    state, truck, engine, ap, tick, n, clock, writes, collected = values
    lane = state.get('lane_trajectory')
    lane['signal_passages']['passages'][0]['passage_key'] = []
    result = engine._signal_selector.select(dict(valid=True, lifecycle=1, lights=[]),
        lane['points'], 'invalid-key', context(state), truck, 0., lane['signal_passages'])
    assert not result['valid'] and result['candidate'] is None
    assert not result.get('prefab_required')


@pytest.mark.parametrize('fault', ['packet', 'alignment', 'revision', 'heartbeat'])
def test_old_summary_cannot_replace_invalid_actual_authority(flow, fault):
    values, step = directed_stop(flow)
    state, truck, engine, ap, tick, n, clock, writes, collected = values
    n(); flow[4](4, .3, dt=.6)
    if fault == 'packet':
        packet = state.get('nav_steering_debug'); packet['observation_timestamp'] -= .6
        state.set('nav_steering_debug', packet)
    elif fault == 'alignment':
        match = state.get('lane_match'); match['lateral_error_m'] = 10.
        state.set('lane_match', match)
    elif fault == 'revision':
        lane = state.get('lane_trajectory'); lane['revision'] += 1
        state.set('lane_trajectory', lane)
    else:
        state.set('lane_trajectory_heartbeat', clock[0]-.6)
    start = len(writes); n(); engine._flush_controls()
    assert not state.get('autopilot_active') and not state.get('auto_drive_pending')
    assert not any(ch == 'aforward' and v > 0 for _, ch, v, _ in writes[start:])


@pytest.mark.parametrize('load', [1.4, 2.2])
def test_documented_slope_model_uses_written_brake_and_rejects_excess_motion(flow, load):
    values, step = directed_stop(flow)
    state, truck, engine, ap, tick, n, clock, writes, collected = values
    for speed in (2., .7, .2, .06, .01, 0.):
        step(4 if speed > .05 else 0, speed)
    # Same 4 m/s² full-pedal assumption as the existing explicit plant. A
    # static grade acceleration <= pedal capacity cannot roll this model.
    # Neither its equilibrium nor a returned write proves ETS2 hill hold.
    for _ in range(30):
        rollback = -max(0., .12 - 4.*pedal(engine,'abackward')/load)*.05
        assert rollback == 0.
        step(0, rollback)
        assert state.get('autopilot_active')
        assert pedal(engine,'aforward') == 0.
    step(0, -.0523500293)  # real incident speed, unchanged .05 motion gate
    assert not state.get('autopilot_active')
    assert 'vehicle motion observed' in state.get('autopilot_disable_reason')


@pytest.mark.parametrize('mode', [0,3])
@pytest.mark.parametrize('engine_first', [False,True])
def test_unknown_mode_is_not_misreported_as_lost_gear_or_automatically_resumed(flow, mode, engine_first):
    values, step = directed_stop(flow, mode)
    state, truck, engine, ap, tick, n, clock, writes, collected = values
    step(4,2.); step(0 if mode == 0 else 4,0.)
    old = state.get('ets2_transmission_mode')
    state.set('ets2_transmission_mode',dict(old,mode=None,status='unknown',
        reason='game log changed during read'))
    start = len(writes)
    if engine_first: engine._flush_controls()
    ap.on_tick(.05); engine._flush_controls()
    assert not state.get('autopilot_active')
    assert state.get('autopilot_disable_reason') == (
        'transmission mode evidence unavailable: game log changed during read')
    state.set('ets2_transmission_mode',old)
    step(4,.3,color=8)
    assert not state.get('autopilot_active')
    assert not any(ch=='aforward' and v>0 for _,ch,v,_ in writes[start:])
