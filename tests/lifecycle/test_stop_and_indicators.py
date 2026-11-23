"""Oct 12 production counterexamples; no physical stop-line calibration."""
import pytest

from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.signals.test_signal_timing import timing_flow
from tests.test_roundabout_intervention_reporting import pedal
from tests.lifecycle.test_joint_regressions import joint, indicator_loop  # noqa: F401


@pytest.mark.parametrize('mode', [0,3])
def test_signal_coast_does_not_integrate_unexecuted_positive_drive(flow, tmp_path, mode):
    values, step = timing_flow(flow, tmp_path, mode)
    state, truck, engine, ap, tick, n, clock, writes, collector = values
    step(30, 'red', speed=6., progress=22.)
    step(31, 'red', speed=4., progress=24.)
    assert state.get('longitudinal_acc')['speed_control_reason'] == 'signal distance coast'
    assert state.get('longitudinal_acc')['throttle'] == 0.
    for gen in range(32,36):
        step(gen, 'red', speed=4., progress=24.+(gen-31)*.24)
        assert tick.acc._control_target > 4.*3.6
        assert state.get('longitudinal_acc')['speed_control_reason'] == 'signal distance coast'
        # Negative braking memory may unwind, but no unexecuted positive drive
        # is accumulated through zero. This is not a ban on useful unwinding.
        assert max(0.,tick.acc.speed_pid._integral) == 0.
    assert pedal(engine,'aforward') == 0.


def circulation_path(exit_number=2):
    """Actual cropped placed topology/centrelines, not a curvature-made island."""
    import json
    from pathlib import Path
    from dataclasses import replace
    from core.navigation.road_network import RoadNetwork
    from core.navigation.lane_model import LaneId, LanePoint, LaneSegment, GpsCorridorEdge
    from core.navigation.lane_trajectory import build_lane_trajectory
    from core.navigation.turn_maneuvers import components
    from types import SimpleNamespace
    f = json.loads((Path(__file__).parent.parent/'fixtures/oct12-circulation-topology.json').read_text())
    net = RoadNetwork()
    def tuples(x):
        return tuple(tuples(v) for v in x) if isinstance(x, list) else x
    for key in ('nodes','node_rot','node_alt','node_forward','node_forward_item','node_backward_item','adj'):
        setattr(net, key, {int(k): tuples(v) for k, v in f[key].items()})
    for key in ('_seg_uids','_seg_road_uids','_seg_look_tokens'):
        setattr(net, key, tuples(f[key]))
    net.road_looks = f['road_looks']
    net._prefab_desc = {k: tuples(v) for k, v in f['_prefab_desc'].items()}
    net._prefab_lane_data = f['_prefab_lane_data']
    for record in f['instances']:
        instance = tuples(record['value'])
        net._prefab_ownership[instance] = record['ownership']
        for uid in instance[1]:
            cell = net._cell(*net.nodes[uid])
            net._prefab_grid.setdefault(cell, []).append(instance)
        for a in instance[1]:
            for b in instance[1]:
                if a < b:
                    net._prefab_pairs.setdefault((a,b), []).append(instance)
    seed = SimpleNamespace(start_uid=5337536182220102206, end_uid=5337536182589199430,
                           lane_id=LaneId(5337536180303306287,1,1,'dlc_blkw_48'))
    groups, edges = components(net, [seed])
    assert len(groups) == 1 and len(groups[0]['exits']) == 4
    group = groups[0];ring = group['nodes']
    walk = [(seed.start_uid, seed.end_uid)]
    current = seed.end_uid; passed = 0
    for _ in range(32):
        if current in group['exits']:
            passed += 1
            if passed == exit_number:
                target = next(b for a,b in edges if a == current and b not in ring)
                walk.append((current,target));break
        target = next(b for a,b in edges if a == current and b in ring)
        walk.append((current,target));current=target
    else:
        raise AssertionError('selected exit absent')
    def lane_id(value):
        return LaneId(**dict(value, connector_path=tuple(value.get('connector_path', ()))))
    segments = []
    for index, (a,b) in enumerate(walk):
        edge = edges[a,b]
        if edge['kind'] == 'road':
            raw = next(s for s in f['baked_road_lanes'][str(edge['road_uid'])]
                       if s['start_uid'] == a and s['lane_index'] == 1)
            fields = dict(raw)
            fields['lane_id'] = lane_id(raw['lane_id'])
            fields['centerline'] = tuple(LanePoint(**dict(p,
                lane_id=lane_id(p['lane_id']) if p['lane_id'] else None)) for p in raw['centerline'])
            for name in ('left_neighbor','right_neighbor'):
                fields[name] = lane_id(raw[name]) if raw[name] else None
            fields.update(successors=(), connector_curve_indices=tuple(raw['connector_curve_indices']),
                          gps_uids=frozenset(raw['gps_uids']), gps_pair_index=index)
            segment = LaneSegment(**fields)
        else:
            instance = edge['instance']
            options = net._prefab_parallel_lane_options(instance,a,b)
            outputs = net._prefab_lane_data[instance[0]]['nodes'][instance[1].index(b)]['output_lanes']
            chain = next(path for path in options if path[-1] == outputs[1])
            points = net._prefab_curve_chain_3d(instance, chain)
            segment = net._make_prefab_lane_segment(GpsCorridorEdge(a,b,'prefab',index),
                                                    instance,chain,points,1)
        segments.append(segment)
    uids = (walk[0][0], *(b for _,b in walk))
    for index in range(len(segments)-1):
        connection = net._lane_connection(segments[index], segments[index+1])
        assert connection is not None
        segments[index] = replace(segments[index], successors=(connection,))
    path = build_lane_trajectory(net.connect_lane_sequence(tuple(segments), uids))
    assert path.valid, path.failure_reason
    return net, path


@pytest.mark.parametrize('exit_number', [1,2,3,4])
def test_actual_multi_prefab_circulation_has_only_selected_exit(exit_number):
    from plugins.map.main import Plugin as Map
    net, path = circulation_path(exit_number)
    plugin = Map.__new__(Map);plugin.road_net = net
    events = plugin._turn_events_payload(path)
    assert len(events) == 1, events
    assert events[0]['kind'] == 'roundabout' and events[0]['direction'] == 'right'
    assert events[0]['indication_not_before_s_m'] >= events[0]['start_s_m']
    assert events[0]['indication_not_before_s_m'] <= events[0]['signal_s_m']


@pytest.mark.parametrize('exit_number', [1,2,3,4])
def test_actual_topology_exit_gate_reaches_physical_backend_only_after_gate(joint, monkeypatch, exit_number):
    from plugins.map.main import Plugin as Map
    net, path = circulation_path(exit_number)
    publisher = Map.__new__(Map);publisher.road_net = net
    events = publisher._turn_events_payload(path)
    assert len(events) == 1
    gate = events[0]['indication_not_before_s_m']
    # The actual PPD manoeuvre metadata is played on the existing production
    # fixture's straight progress ruler. This checks actuator chronology, not
    # lateral tracking of the physical island in ETS2.
    plugin, pump, edges = indicator_loop(joint, monkeypatch, events)
    for index in range(int(gate*3)):
        pump(z=15.+index/3.)
        assert not any(ch == 'rblinker' and value for _, ch, value in edges)
    limit = int(events[0]['end_s_m']*3)+32
    for index in range(int(gate*3), limit):
        active = any(ch == 'rblinker' and value for _, ch, value in edges)
        pump(z=15.+index/3., observed='right' if active else 'off')
    assert len([1 for _, ch, value in edges if ch == 'rblinker' and value]) == 2
    assert not any(ch == 'lblinker' and value for _, ch, value in edges)


def test_same_selected_circulation_exit_identity_survives_gps_index_shift():
    from dataclasses import replace
    from plugins.map.main import Plugin as Map
    net, path = circulation_path(3)
    publisher = Map.__new__(Map);publisher.road_net = net
    old = publisher._turn_events_payload(path)
    changed = replace(path, segments=tuple(replace(s, gps_pair_index=s.gps_pair_index+7)
                                           for s in path.segments), revision=path.revision+1)
    new = publisher._turn_events_payload(changed)
    assert old[0]['event_id'] == new[0]['event_id']


def test_incomplete_circulation_budget_does_not_restore_arc_turns(monkeypatch):
    from plugins.map.main import Plugin as Map
    net, path = circulation_path(3)
    monkeypatch.setattr('core.navigation.turn_maneuvers.MAX_NODES', 3)
    publisher = Map.__new__(Map);publisher.road_net = net
    assert publisher._turn_events_payload(path) == []


@pytest.mark.parametrize('driver', ['off','left','hazard'])
def test_actual_exit_cancellation_or_driver_side_never_rearms(joint, monkeypatch, driver):
    from plugins.map.main import Plugin as Map
    net, path = circulation_path(2)
    publisher = Map.__new__(Map);publisher.road_net = net
    events = publisher._turn_events_payload(path)
    plugin, pump, edges = indicator_loop(joint, monkeypatch, events)
    progress = max(events[0]['indication_not_before_s_m'], events[0]['signal_s_m']-35.)+1.
    for index in range(int(progress*3)+1):
        active = any(ch == 'rblinker' and value for _,ch,value in edges)
        pump(z=15.+index/3., observed='right' if active else 'off')
    pump(z=15.+progress+.3, observed='right')
    before = len([1 for _,_,value in edges if value])
    for i in range(8):pump(z=15.+progress+.6+i*.3, observed=driver)
    assert len([1 for _,_,value in edges if value]) == before
    assert joint[0].get('route_blinker') is None


def test_two_port_curved_connector_never_generates_physical_indicator(joint, monkeypatch):
    from types import SimpleNamespace
    from plugins.map.main import Plugin as Map
    from core.navigation.lane_model import LaneId, LanePath, LanePoint, LaneSegment
    lid = LaneId(21,1,0,'two-port-road',0,(0,))
    points = tuple(LanePoint(2.25,10.,s,s,.5*i,lane_id=lid,segment_index=0)
                   for i,s in enumerate((35.,45.,55.)))
    segment = LaneSegment(lid,1,2,1,0,1,4.,'synthetic',0,None,'prefab',points)
    path = LanePath((segment,),points,(1,2),55.,.95,True)
    publisher = Map.__new__(Map)
    publisher.road_net = SimpleNamespace(_prefab_lane_data={'two-port-road':{'nodes':[{},{}]}})
    events = publisher._turn_events_payload(path)
    plugin, pump, edges = indicator_loop(joint, monkeypatch, events)
    pump()
    assert not any(ch in ('lblinker','rblinker') and value for _,ch,value in edges)


@pytest.mark.parametrize('mode', [0, 3])
def test_positive_stop_envelope_stays_owned_by_acc_until_terminal(flow, tmp_path, mode):
    values, step = timing_flow(flow, tmp_path, mode)
    state, truck, engine, ap, tick, n, clock, writes, collector = values
    step(30, 'red', speed=5., progress=32.)  # 10 m; start actual brake in motion
    assert pedal(engine, 'abackward') > 0.
    step(31, 'red', speed=1., progress=39.)  # 3 m, positive 1.73 m/s ceiling
    assert state.get('longitudinal_traffic')['light_brake'] == 0.
    assert state.get('longitudinal_policy')['brake'] == 0.
    assert state.get('longitudinal_acc')['speed_control_reason'] != 'external braking inhibits speed drive'
    assert state.get('simple_auto_service_hold')['phase'] == 'approaching'
    step(32, 'red', speed=.48, progress=39.65)
    assert state.get('simple_auto_service_hold')['phase'] == 'approaching'
    assert state.get('autopilot_active')
    # Actual exhausted envelope commits a fresh forward-started brake chain.
    step(33, 'red', speed=.3, progress=41.8)
    assert state.get('longitudinal_traffic')['light_brake'] == 1.
    assert pedal(engine, 'abackward') > 0.
    before = len(writes)
    for i in range(34, 40):
        step(i, 'red', speed=0., gear=0 if mode == 0 else 4, progress=41.9)
        assert state.get('autopilot_active')
        assert pedal(engine, 'aforward') == 0. and pedal(engine, 'abackward') > 0.
    assert all(value > 0 for _, ch, value, _ in writes[before:] if ch == 'abackward')
    for i in range(40, 47):
        step(i, 'green', speed=0. if i < 43 else .3,
             gear=0 if mode == 0 and i < 43 else 4, progress=41.9)
    assert state.get('autopilot_active')
    assert pedal(engine, 'aforward') > 0. and pedal(engine, 'abackward') == 0.
    assert not any(ch == 'parkingbrake' for _, ch, _, _ in writes)


def test_small_roundabout_never_indicates_before_join(joint, monkeypatch):
    # Complete immutable Map event; topology owns the entry and selected exit.
    event = dict(event_id='small/first-exit', kind='roundabout', direction='right',
        start_s_m=35., end_s_m=48., signal_s_m=42., indication_not_before_s_m=35.)
    plugin, pump, edges = indicator_loop(joint, monkeypatch, [event])
    pump(z=20.)  # normal 40 m warning otherwise reaches before entry
    assert not any(ch == 'rblinker' and value for _, ch, value in edges)


def test_later_roundabout_exit_never_indicates_before_previous_fork(joint, monkeypatch):
    event = dict(event_id='small/third-exit', kind='roundabout', direction='right',
        start_s_m=5., end_s_m=65., signal_s_m=55., indication_not_before_s_m=45.)
    plugin, pump, edges = indicator_loop(joint, monkeypatch, [event])
    pump(z=35.)  # inside the ordinary warning window, before previous exit
    assert not any(ch == 'rblinker' and value for _, ch, value in edges)
