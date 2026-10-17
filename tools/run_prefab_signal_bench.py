"""Same-path stop/green simulation through real policy and physical SCS writes.

Uncalibrated along-path model; no ETS2 mapping/input is opened. Front extent
and transmission consumption are model assumptions, never SDK proof.
"""
import argparse
from collections import deque
import io
import json
import math
from pathlib import Path
import random
import struct
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.longitudinal import context, publish
from core.sdk.signal_snapshot import SignalReader, RouteSignalSelector
from core.navigation.route import Route
from sdk.plugin_sdk import PluginSDK
from plugins.drivepolicy.main import Plugin as Policy
from tests.test_activation_observation_binding import flow
from tests.test_longitudinal_arbitration import strict_flow
from tests.test_longitudinal_evidence_diagnostics import memory_controller
from tests.test_acc_following import route_input
from tests.test_prefab_signal_binding import parsed_path, plan_for, signal_bytes


def run(directory,*,speed_kmh=50.,mode=0,turn=False,reverse=False,jitter=False,
        baseline=False,approach=100.,front_m=4.,other_stop=False,diagnostics=False,
        head_missing_during_approach=False,allow_rejection=False,
        path_factory=None,snapshot_factory=None,observer_y=10.,phase_program=None,
        duration_limit_s=None, low_speed_disturbance=False, idle_speed_mps=None,
        brake_response_s=.35, input_delay_s=.12, mass_ratio=1.4,
        coherent_processing_clock=False):
    # Optional offline fixtures preserve actual placed geometry/native bytes;
    # the existing plant and production control sequence are unchanged.
    if (not all(math.isfinite(v) for v in (brake_response_s,input_delay_s,mass_ratio))
            or brake_response_s <= 0 or input_delay_s < 0 or mass_ratio <= 0):
        raise ValueError('invalid explicit offline plant parameters')
    net,path,_=(path_factory or parsed_path)(directory,reverse,turn)
    points=[[p.x,p.y,p.z] for p in path.points]
    plan=plan_for(net,path)
    if approach!=100.:
        # Move the starting SDK pose along the same validated approach, without
        # pretending to gain more road distance or alter the derived target.
        initial_progress=100.-approach
    else:initial_progress=0.
    r=Route([(p[0],p[2]) for p in points])
    gen=flow.__wrapped__();harness=next(gen)
    state,truck,engine,ap,update,n,clock,acc=strict_flow(harness,mode=mode)
    collected=None
    if diagnostics:
        from tests.test_longitudinal_evidence_diagnostics import attach
        collected=attach(engine)
    else:engine.controller=memory_controller()
    policy=Policy(PluginSDK(state.values,'drivepolicy'));policy.on_start()
    state.set('acc_target_speed',speed_kmh if speed_kmh>0 else 35.)
    pose=points[0]; binding=route_input(state,engine,truck,points)
    lane=state.get('lane_trajectory');lane['signal_passages']=plan
    state.set('lane_trajectory',lane)
    engine._signal_reader=SignalReader()
    engine._signal_selector=RouteSignalSelector();engine._signal_route_token=None
    # The model includes all backend writes in order, not final tick scalars.
    writes=[];writer=engine.controller.scs
    class Buffer(io.BytesIO):
        def write(self,data):
            channel=next((k for k in ('aforward','abackward','parkingbrake') if writer._offsets[k]==self.tell()),None)
            if channel:writes.append((clock[0],channel,struct.unpack('f',data)[0] if len(data)==4 else bytes(data)))
            return super().write(data)
    writer._buf=Buffer(writer._buf.getvalue())
    def pedal(name):return struct.unpack_from('f',writer._buf.getvalue(),writer._offsets[name])[0]
    def pose_at(s):
        p=r._point_at_progress(s);q=r._point_at_progress(min(s+.1,r._cumulative_m[-1]))
        heading=math.atan2(-(q[0]-p[0]),-(q[1]-p[1])) if q!=p else truck['rotation']
        truck.update(x=p[0],y=observer_y,z=p[1],rotation=heading)
    v=speed_kmh/3.6;s=initial_progress;t=0.;gear=8 if v else 0
    act_t=act_b=held_t=held_b=0.;queue=deque();rng=random.Random(7610)
    # Legacy reports excluded the simulated 30 ms processing/IPC interval from
    # vehicle time while including it in leases. New comparisons explicitly
    # integrate that interval too, and date the physical write after it.
    pipeline_s=0.
    entry=plan['passages'][0]['entry_progress_m'];first_stop=None;green_at=None;rows=[];red=speed_kmh>0
    reference_offset = (plan['passages'][0]['front_allowance_m']
                        + plan['passages'][0]['junction_standoff_m'])
    previous_phase=None
    disturbance_done=False
    moved=v>.5
    red_started=red;drive_selected=gear>0
    # Signal head is 25 m after entry, intentionally unlike the stop target.
    p=plan['passages'][0];head=dict(id=p['semaphore_id'],x=p['entry_xyz'][0]+2.,y=10.,
        z=p['entry_xyz'][2]-25. if not reverse else p['entry_xyz'][2]+25.,
        yaw=p['entry_heading_rad']+math.pi,state=2)
    if turn:head['x']=p['entry_xyz'][0]+2.;head['z']=p['entry_xyz'][2]-5.
    try:
        pose_at(s);update(gear,v);n()
        for sequence in range(1,1900):
            dt=rng.choice((.033,.05,.08)) if jitter else .05
            old_v=v
            disturbed = bool(low_speed_disturbance and not disturbance_done
                and rows and rows[-1]['brake']>.02)
            if disturbed:
                v=.92;old_v=v;disturbance_done=True
            elapsed=dt+pipeline_s if coherent_processing_clock else dt
            for j in range(math.ceil(elapsed/.01)):
                h=elapsed/math.ceil(elapsed/.01)
                while queue and queue[0][0]<=t+j*h:
                    _,held_t,held_b=queue.popleft()
                alpha=1.-math.exp(-h/brake_response_s)
                act_t+=alpha*(held_t-act_t);act_b+=alpha*(held_b-act_b)
                a=(2.2*act_t-4.*act_b)/mass_ratio-.12-.004*v*v
                if idle_speed_mps is not None:
                    # Optional, explicitly uncalibrated creep-load stress.
                    # It is not an inferred ETS2 clutch/idle measurement.
                    a += .9*max(0.,idle_speed_mps-v)
                v=max(0.,v+a*h);s+=v*h
            t+=elapsed
            moved=moved or v>.5
            phase = phase_program(t, first_stop) if phase_program else None
            if phase is not None:
                red = phase['state'] != 8
                # A green at time zero is not a restart. Match the first green
                # after a non-green phase, rather than an unrelated drive row.
                if not red and previous_phase is not None and previous_phase != 8:
                    green_at = t
                previous_phase=phase['state']
            if not red_started and moved:
                red=red_started=True
            if v<.01 and moved and red_started and first_stop is None and (phase is None or red):
                first_stop=dict(t=t,progress_m=s,model_front_progress_m=s+front_m,
                    front_gap_to_entry_m=entry-s-front_m,
                    reference_offset_m=reference_offset,
                    reference_gap_to_target_m=entry-s-reference_offset)
                if phase is None: green_at=t+1.
            if phase is None and green_at and t>=green_at:red=False
            if duration_limit_s is not None and (t>=duration_limit_s or s>=r._cumulative_m[-1]-1.):
                break
            # Mode 3 only acknowledges an actually written D selector in a
            # later SDK frame; it does not succeed simply because mode==3.
            drive_write=bool(writer._buf.getvalue()[writer._offsets['geardrive']])
            drive_selected=drive_selected or drive_write
            gear=8 if (v>.01 or (mode==0 and held_t>0) or (mode==3 and drive_selected)) else 0
            pose_at(s);update(gear,v,dt=dt)
            packet=state.get('nav_steering_debug');packet['tracking_progress_m']=s
            packet['trajectory_identity']=state.get('lane_trajectory_identity')
            lane_id=path.segments[0 if s<entry else 1].lane_id
            from core.navigation.route_diagnostics import lane_id_payload
            match=state.get('lane_match');match.update(valid=True,active_lane_id=lane_id_payload(lane_id))
            state.set('lane_match',match);packet['authority_lane_id']=lane_id.sort_key()
            state.set('nav_steering_debug',packet)
            # Acquisition timestamp is before transport delay and preserved.
            # Optional Oct 8 source-loss model: a new valid producer image has
            # no matching authored head until standstill. It is not a stale
            # image and never supplies synthetic green to clear a stop.
            engine._signal_reader.buffer=(snapshot_factory or signal_bytes)(clock[0],sequence,truck['sdkFrameTimeUs'],
                [dict(head,id=-99 if head_missing_during_approach and sequence > 1 and first_stop is None else head['id'],
                      state=phase['state'] if phase else 2 if red else 8,
                      time_left=phase['remaining_s'] if phase else 60.)])
            engine._signal_reader.mapping_size=len(engine._signal_reader.buffer)
            signal=engine._signal_observation(state.get('telemetry')['truck'],context(state))
            light=signal.get('candidate') if signal.get('valid') else signal.get('stop_candidate')
            if baseline and light:
                # Geometry-only head-distance counterfactual, NOT a frozen
                # historical controller. Keep the qualified target identical
                # for every producer so the current distance controller is not
                # mixed with a metadata-free legacy brake request.
                light = dict(light, distance=entry+25.-s)
                signal = dict(signal)
                signal['candidate' if signal.get('valid') else 'stop_candidate'] = light
            if not light and not baseline and (phase_program is None or s<entry-.5):raise AssertionError(signal)
            state.set('truck_speed_ms',v)
            traffic_brake=.4 if other_stop and not red else 0.
            publish(state,state.get('telemetry')['truck'],'traffic',traffic_brake=traffic_brake,
                light_brake=engine._light_brake(light),light=light,signal=signal,following=None)
            clock[0]+=.012
            policy.on_tick(dt)
            clock[0]+=.008
            acc.on_tick(dt)
            clock[0]+=.01
            ap.on_tick(dt);engine._flush_controls()
            if not state.get('autopilot_active') and not state.get('auto_drive_pending'):
                if not allow_rejection:
                    raise AssertionError(state.get('autopilot_disable_reason') or state.get('auto_drive_phase'))
            throttle,brake=pedal('aforward'),pedal('abackward')
            assert not(throttle>0 and brake>0)
            pipeline_s=.03
            queue.append((t+(pipeline_s if coherent_processing_clock else 0.)+input_delay_s,throttle,brake))
            rows.append(dict(t=t,dt=elapsed,s=s,speed_mps=v,throttle=throttle,brake=brake,
                model_write_at_s=t+(pipeline_s if coherent_processing_clock else 0.),
                acceleration_mps2=(v-old_v)/elapsed,disturbed=disturbed,
                red=red,phase=state.get('autopilot_control_state'),
                write_checked_at_s=clock[0],sdk_frame_us=truck['sdkFrameTimeUs'],
                observation_timestamp=state.get('telemetry')['truck']['_control_observation']['observed_at'],
                context=list(context(state)),signal_generation=signal.get('generation'),
                signal_observed_at=signal.get('observed_at'),
                light_distance=light['distance'] if light else None,target=state.get('longitudinal_acc')['constrained_speed_kmh'],
                signal_phase_plan=light.get('phase_plan') if light else None,
                hold_phase=(state.get('simple_auto_service_hold') or {}).get('phase'),
                selected_source=(state.get('longitudinal_command') or {}).get('decision_source'),
                native_state=phase['state'] if phase else 2 if red else 8))
            if allow_rejection and not state.get('autopilot_active') and not state.get('auto_drive_pending'):
                break  # partial failed baseline is never passed off as a completed stop
            hold=state.get('simple_auto_service_hold') or {}
            if first_stop and not red and ((not other_stop and v>.4) or
                    ((other_stop or hold.get('entry_overrun')) and t>green_at+2.)):
                break
        if first_stop is None and not allow_rejection and phase_program is None:raise AssertionError('no observed model stop')
        start=next((row for row in rows if row['brake']>.02),None)
        jerks=[(b['acceleration_mps2']-a['acceleration_mps2'])/b['dt'] for a,b in zip(rows,rows[1:])]
        nonzero=['brake' if row['brake']>0 else 'drive' for row in rows if row['brake']>0 or row['throttle']>0]
        approaching=['brake' if row['brake']>0 else 'drive' for row in rows
            if row['red'] and (row['brake']>0 or row['throttle']>0)]
        if coherent_processing_clock:
            for previous,current in zip(rows,rows[1:]):
                assert abs((current['write_checked_at_s']-previous['write_checked_at_s'])
                           -(current['t']-previous['t'])) < 1e-8
        physical_pair={'aforward':0.,'abackward':0.};physical_overlap=0
        for _,channel,value in writes:
            if channel in physical_pair:
                physical_pair[channel]=value
                physical_overlap += physical_pair['aforward']>0 and physical_pair['abackward']>0
        return dict(samples=len(rows),duration_s=t,stop=first_stop,
            coherent_processing_clock=coherent_processing_clock,
            brake_start_progress_m=start['s'] if start else None,
            brake_start_distance_to_entry_m=entry-start['s'] if start else None,
            maximum_deceleration_mps2=max(-row['acceleration_mps2'] for row in rows),
            maximum_abs_model_jerk_mps3=max(map(abs,jerks)),
            resumed_without_n=bool(not other_stop and first_stop and green_at is not None
                and state.get('autopilot_active') and v>.4
                and any(row['t']>=green_at and row['throttle']>0 for row in rows)),
            active=state.get('autopilot_active'),
            termination_reason=state.get('autopilot_disable_reason'),
            drive_brake_transitions=sum(a!=b for a,b in zip(nonzero,nonzero[1:])),
            red_drive_brake_transitions=sum(a!=b for a,b in zip(approaching,approaching[1:])),
            far_low_speed_s=sum(row['dt'] for row in rows if row['red']
                and row['light_distance'] is not None and row['light_distance']>10.
                and row['speed_mps']<5./3.6),
            red_target_overrun_samples=sum(row['red'] and row['light_distance'] is not None
                and row['light_distance']<0. for row in rows),
            restart_blocker=(state.get('simple_auto_service_hold') or {}).get('restart_blocker'),
            simultaneous_positive_pedals=sum(row['throttle']>0 and row['brake']>0 for row in rows),
            simultaneous_positive_physical_writes=physical_overlap,
            red_entry_overrun_samples=sum(row['red'] and row['s']+front_m>=entry for row in rows),
            parking_writes=sum(channel=='parkingbrake' for _,channel,_ in writes),
            hold_brake_zero_count=sum(row['brake']==0 for row in rows if first_stop and first_stop['t']<=row['t']<green_at),
            green_first_at_s=green_at,
            green_drive_return_s=next((row['t']-green_at for row in rows
                if green_at is not None and row['t']>=green_at and row['throttle']>0.),None),
            rows=rows,writes=writes,captures=collected.samples if collected else [])
    finally:gen.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--workdir',type=Path,required=True);args=parser.parse_args();args.workdir.mkdir(exist_ok=False)
    results={}
    for speed in (20.,35.,50.):
        for reverse,turn in ((False,False),(True,False),(False,True)):
            for old in (True,False):
                name=f'{speed:g}/{reverse}/{turn}/{"head_distance_counterfactual" if old else "derived_target"}'
                result=run(args.workdir,speed_kmh=speed,mode=0,reverse=reverse,turn=turn,jitter=True,
                           baseline=old,allow_rejection=old)
                results[name]={k:v for k,v in result.items() if k not in ('rows','writes','captures')}
    args.output.write_text(json.dumps(results,indent=2)+'\n',encoding='utf-8');print(json.dumps(results,indent=2))


if __name__=='__main__':main()
