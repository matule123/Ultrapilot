"""Causal Engine replay; future records are used only for scoring predictions."""
import base64
import json
import math
import pickle
from pathlib import Path
from unittest.mock import patch
from core.engine import UltraPilotEngine
from core.navigation.traffic_producer import TrafficCapture
from core.acc_following import observation

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/steering-audit/nov2-roundabout'

def graph_payload():
    result=[]
    for number,instance in enumerate(json.loads((OUT/'local-prefab-topology.json').read_bytes())):
        for curve in instance['curves']:
            result.append(dict(id=str(number)+':'+str(curve['index']),points=curve['points'],
                next=[str(number)+':'+str(i) for i in curve['next']],
                prefab_token=instance['instance'][0],instance_node_uids=instance['instance'][1],curve_index=curve['index']))
    return dict(schema=1,status='prepared',curves=result,
        source='authored_directed_ppd_navigation_curves',physical_edges_verified=False,route_membership_verified=False)

def make_fixture():
    data=pickle.loads((OUT/'exact-11926.bin').read_bytes())
    rows=[r for r in data['window']['records'] if r['kind']=='traffic' and 8429.<r['at_s']<8432.8]
    frames=[]
    for row in rows:
        value=row['value'];capture=value['capture'];capture=dict(capture)
        for name in ('moving','parked'):
            capture[name]=base64.b64encode(capture[name]).decode('ascii')
        source=dict(capture['source'])
        source['ego_body_payload']=base64.b64encode(source['ego_body_payload']).decode('ascii')
        capture['source']=source
        frames.append(dict(at_s=row['at_s'],ego=value['ego'],capture=capture,original_packet=value['packet']))
    lane=json.loads((OUT/'prior-lane.json').read_bytes())
    fixture=dict(schema=1,origin='original native snapshots; static authored map; no future actor intent',
        lane=lane,graph=graph_payload(),frames=frames)
    path=ROOT/'tests/fixtures/nov2-roundabout-native.json'
    path.write_text(json.dumps(fixture,separators=(',',':')),encoding='utf-8')
    return path

def decode(frame):
    c=frame['capture'];source=dict(c['source'])
    source['ego_body_payload']=base64.b64decode(source['ego_body_payload'])
    return TrafficCapture(c['session'],c['receiver_time_s'],base64.b64decode(c['moving']),
        base64.b64decode(c['parked']),c['stable'],source)


def maximum_traffic(frame, *, spread=False):
    """Capacity MODEL: 40 uniquely identified copies near the turning actor,
    three fixed trailer outlines each; 40 remote parked boxes. Never game data.
    Original clocks are retained; this is a load comparison, not the incident.
    """
    import struct,copy
    from core.sdk.ets2la_data import _TRAFFIC_FMT,_PARKED_FMT
    changed=copy.deepcopy(frame);capture=decode(frame)
    fields=struct.unpack(_TRAFFIC_FMT,capture.moving)
    reference=next(list(fields[i*46:(i+1)*46]) for i in range(40) if fields[i*46+13]==61)
    moving=[]
    for i in range(40):
        row=list(reference);row[12:16]=[3,1000+i,0,0]
        if spread:
            row[0]+=(i%5)*.17;row[2]+=(i//5)*.13
        for trailer in range(3):
            body=list(row[:10])
            if spread:
                from core.sdk.ets2la_data import _yaw
                yaw=_yaw(*body[3:7]);behind=(trailer+1)*5.
                body[0]+=math.sin(yaw)*behind;body[2]+=math.cos(yaw)*behind
            row[16+trailer*10:26+trailer*10]=body
        moving.extend(row)
    parked=[]
    for i in range(40):
        row=list(reference[:10]);row[0]+=500.+i*5.;parked.extend(row+[2000+i,0])
    changed['capture']['moving']=base64.b64encode(struct.pack(_TRAFFIC_FMT,*moving)).decode('ascii')
    changed['capture']['parked']=base64.b64encode(struct.pack(_PARKED_FMT,*parked)).decode('ascii')
    return changed

def apply_frame(state,engine,frame,*,modeled_forward_gear=False):
    from core.longitudinal import context
    packet=frame['original_packet'];binding=context(state)
    # Engine's incident traffic row stored the raw SDK truck separately from
    # its published control envelope. Rebuild that transport envelope using
    # the SAME recorded frame/time, not the replay receiver time.
    truck=dict(frame['ego'],_control_observation=dict(schema_version=1,
        sdk_frame_us=packet['sdk_frame_us'],observed_at=packet['observation_timestamp'],
        valid=True,coherent=True))
    if modeled_forward_gear and truck['gear']==0:
        # Counterfactual output test only: the recording's prolonged zero ratio
        # followed the OLD emergency brake. It is not a vehicle simulation of
        # the different candidate output (nor a recording of real-auto D).
        truck['gear']=4
    # Route projection metadata comes from the original packet's route lease.
    # Native clocks are untouched; the synthetic Engine vehicle transport is
    # explicitly paired to its recorded SDK observation for this replay.
    original=packet['following']
    state.update_batch(dict(telemetry=dict(truck=truck),telemetry_valid=True,
        telemetry_timestamp=truck['_control_observation']['observed_at'],
        lane_trajectory_heartbeat=frame['at_s'],autopilot_control_heartbeat=frame['at_s']))
    debug=state.get('nav_steering_debug')
    # Steering transport/activation is modeled (the missing AP part cannot
    # supply historical calculations). Give each modeled calculation its own
    # sequence while preserving the recorded route-projection SDK timestamp.
    debug['calculation_sequence']+=1
    projection=next(d['deadline_basis'] for d in packet['lease_dependencies'] if d['source']=='route_projection')
    debug.update(observation_timestamp=projection['observation_timestamp'],
        computed_at=packet['computed_at'],sdk_frame_us=projection['sdk_frame_us'],
        tracking_progress_m=original.get('route_progress_m',debug.get('tracking_progress_m',0.)))
    # Recorded following may not repeat progress: derive ego's position on the
    # same prior immutable reference, never from future records.
    from core.acc_following import RouteLeadSelector
    route=RouteLeadSelector();route.prepare(state.get('lane_trajectory')['points'],'offline')
    position=route._project(dict(truck,yaw=truck['rotation']),0.,route.arcs[-1])
    debug['tracking_progress_m']=position[1]
    state.set('nav_steering_debug',debug)
    mode=state.get('ets2_transmission_mode');mode['observed_at']=frame['at_s']
    state.set('ets2_transmission_mode',mode)
    capture=decode(frame)
    following,brake=engine._traffic_control_observation(capture,truck,binding,[])
    return following,brake,capture

def main(*, tick_probe=None, modes=(0, 3)):
    import argparse
    p=argparse.ArgumentParser();p.add_argument('action',choices=['fixture','score']);p.add_argument('--out');p.add_argument('--repeat',type=int,default=1);p.add_argument('--maximum-traffic',action='store_true');p.add_argument('--spread',action='store_true');p.add_argument('--wall-clock',action='store_true');args=p.parse_args()
    if args.action=='fixture':print(make_fixture());return
    from contextlib import contextmanager
    from types import SimpleNamespace
    from tests.test_activation_observation_binding import flow
    from tests.lifecycle.test_joint_regressions import joint
    from tests.traffic.test_roundabout_motion import install
    from core.longitudinal import context
    import copy,time,gc
    result=[]
    from tools.benchmark_oct15_crossing_dev_hud import deep_size
    for mode in modes*args.repeat:
      with contextmanager(flow.__wrapped__)() as raw:
       with contextmanager(joint.__wrapped__)(raw,SimpleNamespace(param=mode)) as parts:
        state,engine,ap,acc,policy,tick,_,n,physical,writes,clock=parts
        data=install(parts);rows=[]
        origin=data['frames'][0]['at_s'];started=time.perf_counter()
        real_clock=patch('time.monotonic',side_effect=lambda:origin+time.perf_counter()-started)
        if args.wall_clock:real_clock.start()
        pauses=[]
        gc_started=[]
        def gc_observer(phase, info):
            if phase=='start':gc_started.append(time.perf_counter())
            elif gc_started:pauses.append((gc_started.pop(),time.perf_counter(),info['generation']))
        gc.callbacks.append(gc_observer)
        try:
          for index,frame in enumerate(data['frames']):
            if args.wall_clock:
                remaining=frame['at_s']-time.monotonic()
                if remaining>0.:time.sleep(remaining)
            if args.maximum_traffic:frame=maximum_traffic(frame,spread=args.spread)
            clock[0]=frame['at_s'];start=time.perf_counter();cpu=time.thread_time()
            following,brake,capture=apply_frame(state,engine,frame,modeled_forward_gear=True)
            projection_ms=(time.perf_counter()-start)*1000.
            projection_cpu_ms=(time.thread_time()-cpu)*1000.
            if index==0:
                state.set('autopilot_navigation_readiness',dict(ready=True,timestamp=clock[0],source='gps_lane',revision=11));n()
            truck=state.get('telemetry')['truck']
            engine._publish_traffic_control(truck,truck['_control_observation']['observed_at'],context(state),[],
                capture,following,brake,copy.deepcopy(frame['original_packet']['signal']),None)
            policy.on_tick(.05);acc.on_tick(.05);ap.on_tick(.05)
            flush_started=time.perf_counter();engine._flush_controls();end=time.perf_counter()
            whole_tick_ms=(end-start)*1000.
            checked_at=time.monotonic();command=state.get('longitudinal_command') or {}
            fault=state.get('autopilot_intervention') or {}
            selector=getattr(engine,'_acc_selector',None)
            native=getattr(selector,'_native_current',None)
            actor=native[1].get(61) if native else None
            motion=getattr(selector,'actor_motion',lambda actor:None)(actor) if actor else None
            packet=state.get('longitudinal_acc')
            rows.append(dict(at_s=clock[0],native_speed=capture.source['ego_speed_mps'],sdk_speed=truck['speed'],
                recorded_gear=frame['ego']['gear'],modeled_gear=truck['gear'],brake=brake,
                following_status=following['status'],crossing=following.get('crossing'),body=following.get('body_prediction'),
                acc_valid=packet['valid'],acc_reason=packet['invalid_reason'],active=state.get('autopilot_active'),
                disable_reason=state.get('autopilot_disable_reason'),physical_throttle=physical('aforward'),
                physical_brake=physical('abackward'),projection_ms=projection_ms,
                projection_cpu_ms=projection_cpu_ms,
                clock_basis='paced_wall_monotonic' if args.wall_clock else 'frozen_record_receiver_time',
                checked_at=checked_at,command_lease_remaining_s=(command.get('expires_at',checked_at)-checked_at) if command else None,
                command_observation_age_s=(checked_at-command['observation_timestamp']) if command else None,
                first_intervention={k:fault.get(k) for k in ('kind','reason','observed_at')},
                whole_tick_ms=whole_tick_ms,engine_flush_ms=(end-flush_started)*1000.,
                runtime_gc_ms=sum((b-a)*1000. for a,b,_ in pauses if start<=a<=b<=end),
                speed_cap_mps=following.get('speed_cap_mps'),owner_witnesses=following.get('owner_witnesses'),
                decision={k:command.get(k) for k in ('source','decision_source','reason','throttle','brake','emergency','valid')},
                _memory_snapshot=(
                    getattr(getattr(selector,'_actor_motion_graph',None),'__dict__',{}),
                    getattr(selector,'_actor_motion_cache',{}),getattr(selector,'_actor_body_cache',{}),
                    getattr(selector,'_native_pair_cache',{})),
                actor=actor,motion=motion))
            if tick_probe is not None:
                tick_probe(mode, index, start, flush_started, end, pauses, rows[-1])
            pauses.clear()
        finally:
            gc.callbacks.remove(gc_observer)
            if args.wall_clock:real_clock.stop()
        # Expensive recursive test-only heap inspection must not delay the
        # next replay acquisition. Runtime retains only its current cache;
        # this bounded 32-frame analysis owns old references for scoring only.
        for row in rows:row['motion_retained_bytes']=deep_size(row.pop('_memory_snapshot'))
        result.append(dict(mode=mode,rows=rows,writes=writes))
    Path(args.out).write_text(json.dumps(result,indent=2))
    for run in result:
        ms=sorted(r['projection_ms'] for r in run['rows'])
        print(json.dumps(dict(mode=run['mode'],frames=len(ms),p50_ms=ms[len(ms)//2],p95_ms=ms[int(.95*(len(ms)-1))],
            max_ms=max(ms),first_brake=next((r['at_s'] for r in run['rows'] if r['brake']>0),None),
            invalid_acc=sum(not r['acc_valid'] for r in run['rows']),active=run['rows'][-1]['active'])))

if __name__=='__main__':main()
