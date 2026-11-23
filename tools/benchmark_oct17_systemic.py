"""Actual production operations on independent synthetic clocks and finite load.

Receipt-matching old main-loop traffic block versus the independent producer.
Passive stalls are declared injections, not identified historic inner phases.
"""
import argparse
import ast
from contextlib import contextmanager
import gc
import json
import logging
import math
from pathlib import Path
import time
from types import SimpleNamespace
import zipfile

from pytest import MonkeyPatch
from tools.benchmark_oct15_crossing_dev_hud import percentiles

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/steering-audit/oct17-systemic-longitudinal'


@contextmanager
def baseline(enabled):
    import core.longitudinal as longitudinal
    import core.engine as engine
    with MonkeyPatch.context() as patches:
        old_produce=None
        if enabled:
            with zipfile.ZipFile(OUT/'entry-runtime.zip') as archive:
                tree=ast.parse(archive.read('core/longitudinal.py').decode('utf-8-sig'))
                for n in tree.body:
                    if isinstance(n,ast.FunctionDef) and n.name in ('read','refresh_handoff','rejection_details'):
                        env={};exec(compile(ast.Module(body=[n],type_ignores=[]),'entry/longitudinal','exec'),vars(longitudinal),env)
                        patches.setattr(longitudinal,n.name,env[n.name])
                tree=ast.parse(archive.read('core/engine.py').decode('utf-8-sig'))
            cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='UltraPilotEngine')
            loop=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='run_loop')
            block=next(n for n in ast.walk(loop) if isinstance(n,ast.Try)
                and any(isinstance(a,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='traffic_binding' for t in a.targets)
                    for a in n.body))
            template=ast.parse('def produce(self,truck,telemetry_timestamp):\n published_traffic=None\n return published_traffic').body[0]
            template.body.insert(1,block);ast.fix_missing_locations(template)
            env={};exec(compile(ast.Module(body=[template],type_ignores=[]),'entry/Engine-traffic-block','exec'),vars(engine),env)
            old_produce=env['produce']
        yield old_produce


def run(mode,before,seconds=65.,rpc=.00005):
    from tests.test_activation_observation_binding import flow
    from tests.lifecycle.test_joint_regressions import joint
    from tests.lifecycle.test_systemic_longitudinal import native_producer
    from tests.test_longitudinal_handoff_cadence import Mapping
    from core.navigation.longitudinal_diagnostics import PedalJournal
    import core.longitudinal as longitudinal
    generator=flow.__wrapped__();f=next(generator)
    source=joint.__wrapped__(f,SimpleNamespace(param=mode));values=next(source)
    state,engine,ap,acc,policy,tick,observe,n,physical,writes,clock=values
    truck=f[1];start=clock[0]
    actors=[dict(id=100+i,x=20.+i%8*2.,y=10.,z=25.+i*3.,yaw=math.pi,speed=2.) for i in range(35)]
    acquire=native_producer(values,actors=actors)
    def signal(truck,binding):
        # Declared synthetic QUALIFIED source, not a recovered native head.
        # Actual native signal selection/red/green is covered separately with
        # the real placed prefab. This distant red keeps traffic required while
        # it does not yet request braking at this modeled speed.
        at=truck['_control_observation']['observed_at']
        return dict(valid=True,authority=binding,lifecycle=73,generation=truck['sdkFrameTimeUs'],
            frame_us=truck['sdkFrameTimeUs'],observed_at=at,coverage={},candidate=dict(id=1,
                color='red',distance=130.,stop_required=True,passage_key='synthetic-far-red',
                stop_target_kind='derived_directed_curve_entry',stop_line_verified=False))
    engine._signal_observation=signal
    original_store=engine._store_telemetry_sample
    # Real Manager-like serialization/RPC cost on every consumed state read.
    state.hook=lambda key:clock.__setitem__(0,clock[0]+rpc)
    proxy=Mapping(state,clock,rpc)
    for plugin in (ap,acc,policy,tick.publish_map.__self__):
        for view in (plugin.sdk,*plugin.sdk.__dict__.values()):
            if hasattr(view,'_state'):object.__setattr__(view,'_state',proxy)
    journal=engine.controller._pedal_journal=PedalJournal();journal.enabled=True
    engine._automatic_replay_directory=str(OUT/'model-exports'/f'{mode}-{before}')
    Path(engine._automatic_replay_directory).mkdir(parents=True,exist_ok=True)
    periods=dict(sdk=.027,map=.041,traffic=.05,policy=.061,acc=.031,ap=.038,engine=.021)
    due={k:start+i*.001 for i,k in enumerate(periods)}
    due['sdk']+=periods['sdk']  # the fixture already published the initial frame
    counts=dict.fromkeys(periods,0);sampled=[];wall=[];cpu=[];gc_spans=[];gc_start=[]
    def gc_tick(phase,info):
        if phase=='start':gc_start.append(time.perf_counter())
        elif gc_start:gc_spans.append(time.perf_counter()-gc_start.pop())
    gc.callbacks.append(gc_tick)
    fault=None;last_sdk=start;produced=[];read_margins=[];write_ages=[];write_margins=[]
    try:
        with baseline(before) as old:
            while clock[0]-start<seconds:
                key=min(due,key=due.get);clock[0]=max(clock[0],due[key]);counts[key]+=1
                dt=periods[key]*(1.+(.17 if counts[key]%7==0 else -.08 if counts[key]%11==0 else 0.))
                due[key]=clock[0]+dt
                if key=='sdk':
                    elapsed=clock[0]-last_sdk;last_sdk=clock[0]
                    truck.update(gear=4,speed=3.,x=2.25,y=10.,z=15.+3.*(clock[0]-start),rotation=math.pi,
                        sdkFrameTimeUs=truck['sdkFrameTimeUs']+max(1,int(elapsed*1e6)))
                    original_store(True,dict(truck=truck,raw=dict(sdkActive=True)),clock[0])
                    state.update_batch(engine._vehicle_telemetry_payload(
                        dict(truck=truck,raw=dict(sdkActive=True)),clock[0]))
                    actual=state.get('telemetry')['truck'];evidence=state.get('ets2_transmission_mode')
                    evidence['observed_at']=clock[0];state.set('ets2_transmission_mode',evidence)
                    state.update_batch(dict(truck_world_pos=(truck['x'],truck['z']),truck_altitude=10.,
                        truck_heading=math.pi,truck_speed_ms=3.,vehicle_envelope_snapshot=dict(
                            timestamp=actual['_control_observation']['observed_at'],sdk_frame_us=truck['sdkFrameTimeUs'],
                            tractor_position=(truck['x'],10.,truck['z']),tractor_heading=math.pi,tractor_speed_ms=3.,
                            tractor_reference_geometry=dict(valid=True,source='synthetic_4x2',wheelbase_m=3.8,reference_ahead_m=2.1))))
                elif key=='map':tick.publish_map(dt)
                elif key=='traffic':
                    # The same 440ms passive main-loop pause every 5s. Source
                    # SDK/native/Map keep advancing, as in the recorded class.
                    if before and 2.<(clock[0]-start)%5.<2.44:continue
                    acquire(counts[key]);at=time.perf_counter();cp=time.thread_time()
                    if old:
                        actual=state.get('telemetry')['truck'];packet=old(engine,actual,actual['_control_observation']['observed_at'])
                    else:packet=engine._traffic_tick()
                    wall.append((time.perf_counter()-at)*1000);cpu.append((time.thread_time()-cp)*1000)
                    if packet:produced.append((clock[0],packet['observation_timestamp'],packet['expires_at']))
                elif key=='policy':policy.on_tick(dt)
                elif key=='acc':acc.on_tick(dt)
                elif key=='ap':
                    value=state.get('longitudinal_traffic')
                    if value:read_margins.append(value['expires_at']-clock[0])
                    ap.on_tick(dt)
                else:
                    engine._flush_controls()
                    value=state.get('longitudinal_applied')
                    if value and value.get('write_started_at'):
                        write_ages.append(value['write_started_at']-value['source_observation_timestamp'])
                        write_margins.append(value['expires_at']-value['write_started_at'])
                    assert physical('aforward')==0. or physical('abackward')==0.
                fault=state.get('autopilot_intervention')
                if fault:break
                # Fixture histories are not runtime allocation evidence.
                writes.clear()
                if hasattr(time.monotonic,'reset_mock'):time.monotonic.reset_mock()
        intervals=[(b[0]-a[0])*1000 for a,b in zip(produced,produced[1:])]
        memory=journal.snapshot(include_history=True)
        return dict(mode=mode,baseline=before,duration_s=clock[0]-start,actor_count=35,counts=counts,
            fault=fault,packet_interval_ms=percentiles(intervals) if intervals else None,
            traffic_margin_at_sampled_ap_read_ms=percentiles([v*1000 for v in read_margins]) if read_margins else None,
            age_at_confirmed_write_ms=percentiles([v*1000 for v in write_ages]) if write_ages else None,
            margin_at_confirmed_write_ms=percentiles([v*1000 for v in write_margins]) if write_margins else None,
            producer_wall_ms=percentiles(wall) if wall else None,producer_thread_cpu_ms=percentiles(cpu) if cpu else None,
            gc_ms=percentiles([v*1000 for v in gc_spans]) if gc_spans else None,
            source_bytes=journal._bytes,history_bytes=memory['decision_history']['retained_bytes'],
            over_500ms_writes=sum(v>.5 for v in write_ages),negative_lease_writes=sum(v<0 for v in write_margins),
            model='fixed synthetic poses/speed and explicitly qualified synthetic distant red; no ETS2 dynamics, native head association or first-delivery claim')
    finally:
        gc.callbacks.remove(gc_tick)
        writer=getattr(engine,'_automatic_replay_writer',None)
        if writer:writer.wait(5.)
        source.close();generator.close()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--seconds',type=float,default=65.)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    logging.disable(logging.WARNING)
    if args.output.exists():raise ValueError('Do not overwrite measurement')
    result=[]
    for mode in (0,3):
        for before in (True,False):
            row=run(mode,before,args.seconds);result.append(row);print(json.dumps(row),flush=True)
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')


if __name__=='__main__':main()
