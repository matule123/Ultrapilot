"""Exact original PPD placement; native owner/colour changes are model inputs.

The recorded ID 3 pose is checked independently of ID equality. A successful
mapping write does not prove continuous SDK input consumption by ETS2.
"""
import json
import math
from pathlib import Path
from unittest.mock import patch

import pytest

from core.longitudinal import context, publish
from core.navigation.road_network import RoadNetwork, _uid
from core.sdk.signal_snapshot import LAYOUT, SCOPED_LAYOUT, OWNER_LAYOUT, SignalReader, RouteSignalSelector
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_oct8_signal_coverage import actual_path, real_flow, signal_bytes
from tests.test_roundabout_intervention_reporting import pedal

FIXTURE = 'oct10-signal-place.json'


def place(directory, case=0):
    return actual_path(directory, case, fixture=FIXTURE)


def authored_heads():
    raw = json.loads((Path(__file__).parent/'fixtures'/FIXTURE).read_text())
    net = RoadNetwork()
    for node in raw['nodes']:
        uid = _uid(node['uid'])
        net.nodes[uid] = (node['x'], node['y'])
        net.node_alt[uid] = node['z']; net.node_rot[uid] = node['rotation']
    # Use production transform, including its original descriptor ordering.
    desc = raw['descriptors'][0]
    net._prefab_desc[desc['token']] = (tuple((n['x'],n['y'],n['rotation']) for n in desc['nodes']),)
    p = raw['prefabs'][0]; uids = tuple(_uid(v) for v in p['nodeUids'])
    origin = p['originNodeIndex']; inst = (p['token'], uids, origin, True)
    ox,oz,local_rotation = net._prefab_desc[p['token']][0][origin]
    rotation = net.node_rot[uids[origin]]-local_rotation
    results = []
    for h in raw['authored_heads']:
        x,y,z = h['position_xyz']; w,qx,qy,qz = h['quaternion_wxyz']
        x,z = net._transform_prefab_points(inst, [(x,z)])[0]
        y += net.node_alt[uids[origin]]-desc['nodes'][origin]['z']
        # Rotate the source quaternion forward vector in the same world
        # transform as the curve; do not treat model yaw as lamp-facing yaw.
        dx,dz = -2*(qx*qz+w*qy), 2*(qx*qx+qy*qy)-1
        c,s = math.cos(rotation), math.sin(rotation)
        yaw = math.atan2(-(dx*c-dz*s), -(dx*s+dz*c))
        results.append(dict(id=h['authored_group'], x=x,y=y,z=z,yaw=yaw,
            instance_slot=h['instance_slot'], owner_prefab_uid=_uid(p['uid']),
            owner_node_uids=list(uids), owner_origin_index=origin, color='red'))
    return raw,results


def scoped_bytes(now, generation, frame, heads):
    tuples = [(h['x'],h['y'],h['z'],h['yaw'],h['id'],
               {'red':2,'green':8,'yellow':1}[h['color']]) for h in heads]
    fields = list(LAYOUT.unpack(signal_bytes(now,generation,frame,tuples)))
    # Enough CURRENT phase reserve; the former arbitrary 10 s did not prove
    # whole-prefab clearance after a standing restart.
    import struct
    payload = bytearray(fields[10])
    for i, h in enumerate(heads):
        struct.pack_into('<f', payload, i*48+36, h.get('time_left',60.))
    fields[10] = bytes(payload)
    fields[1:4] = [0x33535055,3,SCOPED_LAYOUT.size]
    owners = b''
    for h in heads:
        nodes=h['owner_node_uids']
        owners += OWNER_LAYOUT.pack(h['owner_prefab_uid'],*nodes,*([0]*(6-len(nodes))),
                                    h['owner_origin_index'],h['instance_slot'],1)
    return bytearray(SCOPED_LAYOUT.pack(*fields[:-1],owners+bytes(2880-len(owners)),fields[-1]))


def selection(directory, heads, *, case=0, reader=True):
    path,plan = place(directory,case); p=plan['passages'][0]; start=path.points[0]
    points=[[start.x+50*math.sin(start.heading),start.y,start.z+50*math.cos(start.heading)]]
    points += [[v.x,v.y,v.z] for v in path.points]
    for passage in plan['passages']: passage['entry_progress_m'] += 50.
    if reader:
        r=SignalReader();r.buffer=scoped_bytes(1000.,1,100,heads);r.mapping_size=SCOPED_LAYOUT.size
        with patch('core.sdk.signal_snapshot.time.monotonic',return_value=1000.02): snapshot=r.read()
    else:
        snapshot=dict(valid=True,lifecycle=1,generation=1,frame_us=100,observed_at=1000.,
                      lights=[dict(h,scope_schema=1,ownership_valid=True,
                                   id_basis='prefab_segment_instance_id') for h in heads])
    selected=RouteSignalSelector().select(snapshot,points,'place',('authority',),
        dict(x=points[0][0],y=start.y,z=points[0][2],rotation=start.heading,speed=4.),0.,plan)
    return selected,plan


def test_original_ppd_object_independently_matches_recorded_foreign_id3(tmp_path):
    raw,heads=authored_heads(); h=heads[1]; original=raw['recorded_head']
    assert h['id']==3 and h['instance_slot']==1
    assert math.dist([h[k] for k in ('x','y','z')],[original[k] for k in ('x','y','z')])<.00003
    assert abs(math.atan2(math.sin(h['yaw']-original['yaw']),math.cos(h['yaw']-original['yaw'])))<1e-6
    selected,plan=selection(tmp_path,[dict(h,color='green')])
    assert plan['passages'][0]['semaphore_id']==1
    assert selected['candidate'] is None
    assert not selected['coverage']['requires_takeover']
    assert not selected['coverage'].get('requires_approach')
    assert selected.get('unassigned_candidate') is None


@pytest.mark.parametrize('case,slot,group',[(0,3,1),(1,1,3)])
def test_original_ppd_direction_qualifies_own_group_through_native_reader(tmp_path,case,slot,group):
    raw,heads=authored_heads()
    selected,plan=selection(tmp_path,[heads[slot]],case=case)
    assert selected['valid'],selected
    assert selected['candidate']['id']==group
    assert selected['candidate']['instance_slot']==slot
    assert selected['candidate']['binding_basis']=='native_prefab_owner_and_directed_group'
    assert selected['observed_at']==1000. and selected['generation']==1
    assert not selected['coverage']['requires_takeover']


@pytest.mark.parametrize('case,group',[(0,1),(1,3)])
def test_original_vehicle_groups_and_reordered_buffer_keep_directed_control(tmp_path,case,group):
    _,heads=authored_heads()
    # Other authored semaphore objects are not known native kind-1 vehicle
    # lights. Only these IDs also occur on the original vehicle navCurves.
    incoming=[dict(h,color='red' if h['id']==group else 'green') for h in heads if h['id'] in (0,1,3)]
    first,_=selection(tmp_path,incoming,case=case)
    second,_=selection(tmp_path,list(reversed(incoming)),case=case)
    for selected in (first,second):
        assert selected['valid'],selected
        assert selected['candidate']['id']==group and selected['candidate']['color']=='red'
        assert not selected['coverage']['requires_takeover']
    assert first['candidate']==second['candidate']


def test_noncurve_authored_ids_as_kind1_remain_unverified_not_invented_foreign(tmp_path):
    _,heads=authored_heads()
    incoming=[dict(h,color='red' if h['id']==1 else 'green') for h in heads]
    selected,_=selection(tmp_path,incoming)
    assert selected['candidate']['id']==1 and selected['candidate']['color']=='red'
    # A PPD object with no vehicle curve is not proof of a non-controlling
    # native rule. If modeled as kind 1 it retains the unknown entry dependency.
    assert selected['coverage']['requires_approach']
    assert selected['coverage']['clearance_confirmed'] is False


@pytest.mark.parametrize('fault',['conflict','owner','direction','height_and_owner','unknown_group'])
def test_same_place_uncertain_inputs_do_not_grant_green(tmp_path,fault):
    _,heads=authored_heads(); own=dict(heads[3],color='green'); incoming=[own]
    if fault=='conflict':incoming.append(dict(own,x=own['x']+.1,color='red'))
    if fault=='owner':own['owner_prefab_uid']+=1
    if fault=='direction':own['yaw']+=math.pi
    if fault=='height_and_owner':own['y']+=10.;own['owner_prefab_uid']+=1
    if fault=='unknown_group':own['id']=999
    selected,_=selection(tmp_path,incoming)
    assert not selected['valid'] and selected['candidate'] is None
    if fault=='unknown_group': assert selected['coverage'].get('requires_approach')


@pytest.mark.parametrize('mode',[0,3])
def test_actual_place_foreign_green_then_own_red_hold_green_backend(flow,tmp_path,mode):
    # Full native publication -> reader -> planner/ACC -> AP -> Engine ->
    # real Controller/test mapping. Fresh SDK response is an explicit model.
    with patch('tests.test_oct8_signal_coverage.actual_path',side_effect=place):
        values,_=real_flow(flow,tmp_path,0,mode,scoped=True)
    state,truck,engine,ap,tick,n,clock,writes,collected=values
    raw,heads=authored_heads(); path,plan=place(tmp_path); entry=path.points[0]
    generation=[20]
    def step(gear,speed,*,green=False,foreign_only=False,traffic_brake=0.,missing=False):
        # Same one-metre terminal gap under the current reference convention.
        distance = state.get('lane_trajectory')['signal_passages']['passages'][0]['entry_progress_m']-41.
        truck.update(x=entry.x+distance*math.sin(entry.heading),z=entry.z+distance*math.cos(entry.heading))
        flow[4](gear,speed,dt=.05)
        packet=state.get('nav_steering_debug');packet['tracking_progress_m']=41.
        state.set('nav_steering_debug',packet)
        actual=state.get('telemetry')['truck'];state.set('truck_speed_ms',speed)
        generation[0]+=1
        lights=[] if missing else [dict(heads[1],color='green')]
        if not foreign_only and not missing:lights.append(dict(heads[3],color='green' if green else 'red'))
        engine._signal_reader.buffer=scoped_bytes(clock[0],generation[0],actual['sdkFrameTimeUs'],lights)
        engine._signal_reader.mapping_size=SCOPED_LAYOUT.size
        signal=engine._signal_observation(actual,context(state))
        light=signal.get('candidate') if signal.get('valid') else signal.get('stop_candidate')
        publish(state,actual,'traffic',signal=signal,light=light,
            light_brake=engine._light_brake(light),traffic_brake=traffic_brake,following=None)
        tick.policy.on_tick(.05);tick.acc.on_tick(.05);ap.on_tick(.05);engine._flush_controls()
        return signal
    foreign=step(4,4.,foreign_only=True)
    assert not foreign['coverage']['requires_takeover'] and not foreign['coverage'].get('requires_approach')
    assert state.get('autopilot_active') and pedal(engine,'abackward')==0.
    for cycle in range(2):
        red=step(4,4.)
        assert red['valid'] and red['candidate']['id']==1
        assert red['candidate']['color']=='red'
        start=len(writes)
        for speed in (2.,.7,.2,.04,0.,0.):
            step(0 if mode==0 and speed<.05 else 4,speed)
            assert state.get('autopilot_active'),state.get('automatic_safety_stop_reason')
            assert pedal(engine,'aforward')==0. and pedal(engine,'abackward')>0.
        # Loss of the locked native head must not clear its original stop.
        step(0 if mode==0 else 4,0.,missing=True)
        assert pedal(engine,'aforward')==0. and pedal(engine,'abackward')>0.
        # Republish the same placed geometry under a new window token; the
        # exact passage/authority and original lock must survive this refresh.
        lock=dict(state.get('simple_auto_service_hold')['signal_lock'])
        from core.ipc.shared_state import lane_publication_batch
        before=context(state)
        state.update_batch(lane_publication_batch({'lane_trajectory':state.get('lane_trajectory')}))
        assert context(state)==before
        assert all(v>0. for _,ch,v,_ in writes[start:] if ch=='abackward')
        step(0 if mode==0 else 4,0.)
        assert state.get('simple_auto_service_hold')['signal_lock']==lock
        for _ in range(5): step(0 if mode==0 else 4,0.,green=True)
        for speed in (.001,.2,.3):step(4,speed,green=True)
        assert state.get('autopilot_active') and pedal(engine,'aforward')>0.
        assert not any(ch=='parkingbrake' for _,ch,_,_ in writes[start:])
        assert not engine.controller.current_hazard
    # A different stopping reason is a separate immutable dependency. Its
    # disappearance is not verified clearance and must not fake a happy cycle.
    step(4,4.)
    for speed in (2.,.7,.2,.04,0.):
        step(0 if mode==0 and speed<.05 else 4,speed)
    step(0 if mode==0 else 4,0.,green=True,traffic_brake=.3)
    for _ in range(5):
        step(0 if mode==0 else 4,0.,green=True)
        assert state.get('autopilot_active')
        assert pedal(engine,'aforward')==0. and pedal(engine,'abackward')>0.
    n();engine._flush_controls()
    assert not state.get('autopilot_active') and pedal(engine,'aforward')==0.
