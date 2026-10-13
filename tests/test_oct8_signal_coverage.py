"""Real Oct 8 placed PPDs, modeled producer snapshots, physical SCS writes.

The heads/speeds below are explicit test inputs, not recovered historical raw
heads and not proof of ETS2 input consumption or painted-line geometry.
"""
import json
import math
import struct
from pathlib import Path

import pytest

from core.longitudinal import context, publish
from core.navigation.road_network import RoadNetwork, _uid
from core.navigation.lane_model import GpsCorridorEdge
from core.navigation.lane_trajectory import build_lane_trajectory
from core.navigation.prefab_signals import prepare_signal_passages
from core.sdk.signal_snapshot import LAYOUT, SIZE
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_oct8_stop_lifecycle import directed_stop
from tests.test_roundabout_intervention_reporting import pedal


def actual_path(directory, case, *, fixture='oct8-deployed-prefabs.json'):
    raw = json.loads((Path(__file__).parent/'fixtures'/fixture).read_text())
    (directory/'prefabDescriptions.json').write_text(json.dumps(raw['descriptors']))
    (directory/'prefabs.json').write_text(json.dumps(raw['prefabs']))
    network = RoadNetwork()
    for node in raw['nodes']:
        uid = _uid(node['uid'])
        network.nodes[uid] = (float(node['x']), float(node['y']))
        network.node_alt[uid] = float(node['z'])
        network.node_rot[uid] = float(node.get('rotation', 0.))
    network._load_prefabs(str(directory))
    record = raw['cases'][case]
    instances = {tuple(p) for group in network._prefab_pairs.values() for p in group
                 if p[0] == record['token'] and min(p[1]) == record['road_uid']}
    assert len(instances) == 1
    instance = instances.pop()
    indices = tuple(record['indices'])
    data = network._prefab_lane_data[record['token']]
    assert network._curve_chain_is_valid(data, indices)
    entry = next(i for i,n in enumerate(data['nodes']) if indices[0] in n['input_lanes'])
    exit = next(i for i,n in enumerate(data['nodes']) if indices[-1] in n['output_lanes'])
    points = network._prefab_curve_chain_3d(instance, indices)
    edge = GpsCorridorEdge(instance[1][entry], instance[1][exit], 'prefab', 0,
                           prefab_instance=instance)
    segment = network._make_prefab_lane_segment(edge, instance, indices, points)
    path = build_lane_trajectory(network.connect_lane_sequence((segment,), (edge.start_uid,edge.end_uid)))
    assert path.valid, path.failure_reason
    return path, prepare_signal_passages(network, path)


def signal_bytes(now, generation, frame, head, *, time_left=60.):
    payload = bytes(1920)
    heads = head if head and isinstance(head[0],tuple) else [head] if head else []
    rows = []
    for x,y,z,yaw,id,color in heads:
        tx,tz = math.floor(x/512.), math.floor(z/512.)
        row = struct.pack('<fffhhffffifii',x-tx*512.,y,z-tz*512.,tx,tz,
                          math.cos(yaw/2.),0.,math.sin(yaw/2.),0.,1,time_left,color,id)
        rows.append(row)
    packed = b''.join(rows); payload = packed+payload[len(packed):]
    sequence = 2*generation
    return bytearray(LAYOUT.pack(sequence,0x32535055,2,SIZE,99,generation,frame,
                                now,3,len(heads),payload,sequence))


def real_flow(flow, directory, case, mode=0, *, scoped=False):
    values, _ = directed_stop(flow, mode, start=False)
    state, truck, engine, ap, tick, n, clock, writes, collected = values
    path, plan = actual_path(directory, case)
    p = path.points[0]; heading = p.heading
    # Keep this lifecycle scenario's initial 42 m TO ITS PLANNED TARGET.
    # The authorized 8 -> 5 m reference-policy change moves the synthetic
    # start 3 m closer to the same real authored entry. Both pose and progress
    # change together; no stop distance, recorded PPD or assertion is forged.
    # Independent Oct 13 closed-plant tests keep a fixed 100 m entry approach.
    passage = plan['passages'][0]
    approach = 42.+passage['front_allowance_m']+passage['junction_standoff_m']
    start = [p.x+approach*math.sin(heading),p.y,p.z+approach*math.cos(heading)]
    lane = state.get('lane_trajectory')
    lane['points'] = [start]+[[p.x,p.y,p.z] for p in path.points]
    plan['passages'][0]['entry_progress_m'] += approach
    lane['signal_passages'] = plan
    if scoped:
        # Production SharedState publishes small authority metadata atomically
        # with the geometry. IPCState intentionally has plain dictionary
        # semantics, so supply that same contract rather than falsely changing
        # geometry authority whenever a publication token changes.
        from dataclasses import replace
        from core.ipc.shared_state import lane_publication_batch
        from core.navigation.lane_model import LaneId, LanePoint, LaneSegment, LaneConnection
        from core.navigation.drivable_surface import lane_path_fingerprint
        segment=path.segments[0]; road_id=LaneId(11,1,0)
        road=LaneSegment(road_id,10,segment.start_uid,1,0,1,4.5,'derived',3,None,'road',
            (LanePoint(*start,heading=heading),replace(segment.centerline[0],lane_id=road_id)),
            successors=(LaneConnection(segment.lane_id,'prefab'),),gps_pair_index=0)
        full=build_lane_trajectory(RoadNetwork().connect_lane_sequence(
            (road,replace(segment,gps_pair_index=1)),(10,segment.start_uid,segment.end_uid)))
        assert full.valid,full.failure_reason
        lane['lane_path_fingerprint']=lane_path_fingerprint(full)
        state.update_batch(lane_publication_batch({'lane_trajectory':lane}))
    else:
        state.set('lane_trajectory', lane)
        state.set('lane_trajectory_publication_token', 'actual-placed-'+str(case))
    truck.update(x=start[0],y=start[1],z=start[2],rotation=heading)
    generation = [0]
    head_id = plan['passages'][0]['semaphore_id']
    # Native forward quaternion follows the regulated curve. Legacy test
    # fixtures explicitly model the old unscoped visual-facing heuristic.
    head_pose = (p.x,p.y,p.z,heading if scoped else heading+math.pi)

    def step(gear=4,speed=2.,*,color=2,id=None,head=True,progress=0.,yaw=None,side=0.,
             metadata=True,ap_first=True,flush=True,traffic_brake=0.,head_shift=(0.,0.,0.),other_head=None):
        truck.update(x=start[0]-progress*math.sin(heading)+side*math.cos(heading),
                     z=start[2]-progress*math.cos(heading)-side*math.sin(heading))
        flow[4](gear,speed,dt=.05)
        packet = state.get('nav_steering_debug'); packet['tracking_progress_m'] = progress
        state.set('nav_steering_debug',packet)
        actual = state.get('telemetry')['truck']; state.set('truck_speed_ms',speed)
        generation[0] += 1
        pose = (*(head_pose[i]+head_shift[i] for i in range(3)),head_pose[3] if yaw is None else yaw,
                head_id if id is None else id,color) if head else None
        if other_head is not None:pose = [pose,other_head] if pose else [other_head]
        engine._signal_reader.buffer = signal_bytes(clock[0],generation[0],actual['sdkFrameTimeUs'],pose)
        if scoped:
            from core.sdk.signal_snapshot import SCOPED_LAYOUT,OWNER_LAYOUT
            raw=list(LAYOUT.unpack(engine._signal_reader.buffer));raw[1:4]=[0x33535055,3,SCOPED_LAYOUT.size]
            p=plan['passages'][0];nodes=[int(u)&((1<<64)-1) for u in p['native_node_uids']]
            owner=OWNER_LAYOUT.pack(int(p['prefab_uid'])&((1<<64)-1),*nodes,
                *([0]*(6-len(nodes))),p['origin_node_index'],0,1)
            owners=owner+bytes(2880-len(owner))
            engine._signal_reader.buffer=bytearray(SCOPED_LAYOUT.pack(*raw[:-1],owners,raw[-1]))
            engine._signal_reader.mapping_size=SCOPED_LAYOUT.size
        if not metadata:
            lane = state.get('lane_trajectory'); lane['signal_passages'] = None
            state.set('lane_trajectory',lane); engine._signal_route_token = None
        signal = engine._signal_observation(actual,context(state))
        light = signal.get('candidate') if signal.get('valid') else signal.get('stop_candidate')
        state.update_batch({'traffic_light':light,'traffic_light_detected':signal.get('unassigned_candidate'),
                            'traffic_light_selection_reason':signal.get('reason')})
        publish(state,actual,'traffic',signal=signal,light=light,light_brake=engine._light_brake(light),
                traffic_brake=traffic_brake,following=None)
        tick.policy.on_tick(.05);tick.acc.on_tick(.05)
        if ap_first:ap.on_tick(.05)
        if flush:engine._flush_controls()
        return signal

    step(0,0.,color=8,head=False)
    n();step(0,0.,color=8,head=False)
    for speed in (.001,.2,.3):step(4,speed,color=8,head=False)
    assert state.get('autopilot_active'),state.get('autopilot_disable_reason')
    return values,step


@pytest.mark.parametrize('case',[0,1,2])
@pytest.mark.parametrize('mode',[0,3])
def test_unassigned_live_head_is_takeover_not_implicit_clear(flow,tmp_path,case,mode):
    values,step = real_flow(flow,tmp_path,case,mode)
    state,truck,engine,ap,tick,n,clock,writes,collected = values
    start = len(writes)
    signal = step(id=999,ap_first=False)
    assert signal['candidate'] is None and not signal['valid']
    assert signal.get('coverage',{}).get('requires_takeover'), signal
    assert signal['unassigned_candidate']['id'] == 999
    assert state.get('autopilot_control_state') == 'controlled_stop'
    assert not any(ch == 'aforward' and value > 0 for _,ch,value,_ in writes[start:])
    assert not any(ch == 'parkingbrake' for _,ch,_,_ in writes[start:])
    assert 'signal regulation coverage' in state.get('automatic_safety_stop_reason','')
    assert 'Prevezmite riadenie' in state.get('navigation_status','')
    step(0 if mode == 0 else 4,0.,id=999)
    assert not state.get('autopilot_active')
    step(4,.1,color=8)
    assert not state.get('autopilot_active')  # No automatic resume after technical loss.


@pytest.mark.parametrize('mode',[0,3])
def test_missing_metadata_with_live_route_head_does_not_authorize_drive(flow,tmp_path,mode):
    values,step = real_flow(flow,tmp_path,0,mode)
    state,truck,engine,ap,tick,n,clock,writes,collected = values
    signal = step(metadata=False)
    assert signal.get('coverage',{}).get('requires_takeover')
    assert state.get('autopilot_control_state') == 'controlled_stop'
    assert pedal(engine,'aforward') == 0.


@pytest.mark.parametrize('case',[0,1,2])
def test_actual_placed_matching_head_is_qualified_not_unassigned(flow,tmp_path,case):
    values,step = real_flow(flow,tmp_path,case)
    signal = step(progress=35.,speed=4.)
    assert signal['valid'],signal
    assert signal['candidate']['head_observed'] and signal['candidate']['color'] == 'red'
    assert not signal.get('coverage',{}).get('requires_takeover')
    assert values[0].get('traffic_light') == signal['candidate']
    assert pedal(values[2],'abackward') > 0.


@pytest.mark.parametrize('case',[0,1,2])
@pytest.mark.parametrize('mode',[0,3])
def test_real_placed_red_hold_loss_green_restart(flow,tmp_path,case,mode):
    values,step = real_flow(flow,tmp_path,case,mode)
    state,truck,engine,ap,tick,n,clock,writes,collected = values
    step(4,4.,progress=41.)
    for speed in (2.,.7,.2,.04,0.,0.):
        step(0 if mode == 0 and speed < .05 else 4,speed,progress=41.)
        assert state.get('autopilot_active'),state.get('autopilot_disable_reason')
        assert pedal(engine,'aforward') == 0. and pedal(engine,'abackward') > 0.
    start = len(writes)
    lost = step(0 if mode == 0 else 4,0.,progress=41.,head=False)
    assert not lost['valid'] and lost['prefab_required']
    assert pedal(engine,'abackward') > 0. and pedal(engine,'aforward') == 0.
    assert state.get('autopilot_active')
    for _ in range(5):step(0 if mode == 0 else 4,0.,progress=41.,color=8)
    for speed in (.001,.2,.3):step(4,speed,progress=41.,color=8)
    assert state.get('autopilot_active')
    assert pedal(engine,'aforward') > 0. and pedal(engine,'abackward') == 0.
    assert not any(ch == 'parkingbrake' for _,ch,_,_ in writes[start:])


@pytest.mark.parametrize('foreign',['direction','height','lateral'])
def test_foreign_head_and_map_id_alone_do_not_invent_a_stop(flow,tmp_path,foreign):
    values,step = real_flow(flow,tmp_path,0)
    state,truck,engine,ap,tick,n,clock,writes,collected = values
    p = state.get('lane_trajectory')['signal_passages']['passages'][0]
    options = dict(id=999)
    if foreign == 'direction':options['yaw'] = p['entry_heading_rad']+1.5*math.pi
    if foreign == 'height':options['head_shift'] = (0.,8.,0.)
    if foreign == 'lateral':
        options['head_shift'] = (12.*math.cos(p['entry_heading_rad']),0.,-12.*math.sin(p['entry_heading_rad']))
    signal = step(**options)
    assert not signal.get('coverage',{}).get('requires_takeover')
    assert signal['candidate'] is None and not signal.get('prefab_required')
    assert state.get('autopilot_active') and pedal(engine,'abackward') == 0.
    assert not state.get('simple_auto_service_hold')
    absent = step(head=False)
    assert not absent.get('prefab_required') and state.get('autopilot_active')


def test_unassigned_green_is_not_clearance_and_does_not_downgrade_emergency(flow,tmp_path):
    values,step = real_flow(flow,tmp_path,0)
    state,truck,engine,ap,tick,n,clock,writes,collected = values
    signal = step(id=999,color=8,traffic_brake=1.)
    assert signal['coverage']['requires_takeover']
    assert state.get('autopilot_control_state') == 'controlled_stop'
    assert pedal(engine,'aforward') == 0. and pedal(engine,'abackward') == 1.
    from core.control_timing import first_control_fault_record
    record = first_control_fault_record(state) or {}
    assert record.get('details',{}).get('signal',{}).get('unassigned_candidate',{}).get('id') == 999


def test_later_qualified_head_cannot_hide_an_earlier_unassigned_conflict(flow,tmp_path):
    values,step = real_flow(flow,tmp_path,0)
    state,truck,engine,ap,tick,n,clock,writes,collected = values
    h = truck['rotation']
    head = (truck['x']-10.*math.sin(h),truck['y'],truck['z']-10.*math.cos(h),h+math.pi,999,2)
    signal = step(color=8,other_head=head)
    assert signal.get('coverage',{}).get('requires_takeover')
    # Keep the separately qualified later head, but it cannot clear the
    # earlier unassigned conflict or authorize a physical throttle write.
    assert signal['candidate']['id'] != 999
    assert signal['unassigned_candidate']['id'] == 999
    assert pedal(engine,'aforward') == 0.


@pytest.mark.parametrize('mode',[0,3])
def test_measured_approach_curve_values_do_not_create_a_technical_pulse(flow,mode):
    values,step=directed_stop(flow,mode)
    state,truck,engine,ap,tick,n,clock,writes,collected=values
    state.set('acc_target_speed',50.)
    # Recorded geometry-query outputs; speeds are marked application proxies.
    # This is a supplied-SDK integration, not historical pedal reconstruction.
    samples=((18.729,112.,42.99),(19.062,104.,31.63),(21.063,96.,23.67),
             (20.559,84.,33.38),(18.823,80.,31.22),(20.293,72.,20.39))
    for radius,distance,speed in samples:
        packet=state.get('nav_steering_debug')
        packet['longitudinal_curve_profile']=dict(radius_m=radius,distance_m=distance)
        state.set('nav_steering_debug',packet)
        for _ in range(3):step(4,speed/3.6,color=8)
        assert state.get('autopilot_active'),state.get('autopilot_disable_reason')
        assert pedal(engine,'abackward') == 0.
        assert state.get('autopilot_control_state') != 'controlled_stop'


def test_signal_fault_encoding_rejects_incomplete_vectors():
    from core.navigation.longitudinal_diagnostics import _expand_fault_details
    for values in ([],[None]*9):
        with pytest.raises(ValueError,match='INVALID_SIGNAL_COMPARISON'):
            _expand_fault_details({'signal_comparison':{'schema':1,'values':values}})
