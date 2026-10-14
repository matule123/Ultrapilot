"""Paired stop-ownership production model and wall/CPU/GC profile, no game I/O.

Entry add9a19 is frozen in memory. The explicit plant (2.2 drive, 4.0 brake,
0.35 s response, 0.10 s output delay, drag 0.12+0.004*v^2) is not ETS2.
The criterion is semantic: a continuously observed positive moving constraint
must not force standstill. No bumper/coverage certificate or comfort threshold.
"""
import argparse
from contextlib import contextmanager
import ctypes
from collections import deque
import gc
import json
import math
from pathlib import Path
import statistics
import sys
import threading
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import pytest
from tests.test_oct14_stop_completion import committed_stop_baseline
from tests.test_oct14_completion import timed_step
from tests.test_activation_observation_binding import flow, IPCState
from tests.test_oct11_joint_regressions import joint
from tools.compare_oct14_completion import native_pipeline_cost
from tools.run_longitudinal_comfort_bench import percentile


def distribution(values):
    return dict(n=len(values),p50=statistics.median(values),p95=percentile(values,.95),
                p99=percentile(values,.99),maximum=max(values)) if values else dict(n=0)


@contextmanager
def frozen(before):
    with pytest.MonkeyPatch.context() as m:
        if before:
            m.setenv('ULTRAPILOT_OCT14_STOP_BASELINE','1')
            committed_stop_baseline.__wrapped__(m)
        yield


def moving_model(mode,before,duration=20.):
    from types import SimpleNamespace
    with frozen(before):
        f=flow.__wrapped__(); source=next(f)
        g=joint.__wrapped__(source,SimpleNamespace(param=mode)); values=next(g)
        state,engine,ap,acc,policy,tick,observe,n,physical,writes,clock=values
        state.set('acc_target_speed',50.)
        speed,ego_z,actor_z=10.,15.,44.
        drive=brake=act_drive=act_brake=0.
        queue=deque(); rows=[]; dt=1./30.
        try:
            for generation in range(1,round(duration/dt)+1):
                t=generation*dt
                while queue and queue[0][0]<=t:
                    _,drive,brake=queue.popleft()
                old_speed=speed
                for _ in range(4):
                    h=dt/4.; alpha=1.-math.exp(-h/.35)
                    act_drive+=alpha*(drive-act_drive);act_brake+=alpha*(brake-act_brake)
                    speed=max(0.,speed+h*(2.2*act_drive-4.*act_brake-.12-.004*speed*speed))
                    ego_z+=speed*h;actor_z+=10.*h
                gear=0 if mode==0 and speed<.05 else 4
                actor=dict(id=31,x=4.,y=10.,z=actor_z,yaw=math.pi,speed=10.)
                timed_step(values,[actor],generation=generation,speed=speed,gear=gear,z=ego_z)
                throttle,brake_command=physical('aforward'),physical('abackward')
                assert not(throttle>0. and brake_command>0.)
                queue.append((t+.10,throttle,brake_command))
                rows.append(dict(t=t,speed_mps=speed,ego_progress_m=ego_z-15.,
                    reference_gap_m=actor_z-ego_z,throttle=throttle,brake=brake_command,
                    model_acceleration_ms2=(speed-old_speed)/dt,
                    active=state.get('autopilot_active'),
                    phase=(state.get('simple_auto_service_hold') or {}).get('phase'),
                    motion_contract=(state.get('longitudinal_traffic') or {}).get('motion_constraint'),
                    brake_basis=(state.get('longitudinal_traffic') or {}).get('brake_basis'),
                    acc=(state.get('longitudinal_acc') or {}).get('speed_control_reason'),
                    other_sources=(state.get('simple_auto_service_hold') or {}).get('other_stop_sources')))
                writes.clear()
            final=rows[-1]
            result=dict(mode=mode,samples=len(rows),duration_s=duration,final_speed_mps=final['speed_mps'],
                minimum_speed_mps=min(r['speed_mps'] for r in rows),
                stopped_samples=sum(r['speed_mps']<.05 for r in rows),
                terminal_hold_samples=sum(r['phase']=='holding' for r in rows),
                final_brake=final['brake'],final_throttle=final['throttle'],
                min_reference_gap_m=min(r['reference_gap_m'] for r in rows),
                settled_speed_rms_kmh=math.sqrt(sum(((r['speed_mps']-10.)*3.6)**2
                    for r in rows[-150:])/len(rows[-150:])),
                max_model_deceleration_ms2=-min(r['model_acceleration_ms2'] for r in rows),
                p95_abs_model_jerk_ms3=percentile([abs(b['model_acceleration_ms2']-
                    a['model_acceleration_ms2'])/dt for a,b in zip(rows,rows[1:])],.95),
                max_abs_model_jerk_ms3=max(abs(b['model_acceleration_ms2']-
                    a['model_acceleration_ms2'])/dt for a,b in zip(rows,rows[1:])),
                pedal_reversals=sum(a!=b for a,b in zip(
                    [1 if r['throttle']>0. else -1 for r in rows if r['throttle']>0. or r['brake']>0.],
                    [1 if r['throttle']>0. else -1 for r in rows if r['throttle']>0. or r['brake']>0.][1:])),
                trace=rows)
            return result
        finally:g.close();f.close()


def thread_cpu():
    # Windows thread_time is quantized on this host. Retain native thread
    # cycles as CPU-work evidence, never divide by an assumed clock frequency.
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetCurrentThread.restype=ctypes.c_void_p
    handle=kernel.GetCurrentThread()
    cycles=ctypes.c_ulonglong()
    kernel.QueryThreadCycleTime.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_ulonglong)]
    if not kernel.QueryThreadCycleTime(handle,ctypes.byref(cycles)):
        raise ctypes.WinError(ctypes.get_last_error())
    return cycles.value


def profile(before,exports,run):
    from plugins.map.main import Plugin as Map
    from plugins.drivepolicy.main import Plugin as Policy
    from plugins.acc.main import Plugin as ACC
    from plugins.autopilot.main import Plugin as AP
    from core.engine import UltraPilotEngine as Engine
    from core.steering_replay import AsyncReplayExporter,SteeringReplayBuffer,inspect_replay
    phases={}; collections=[]; active={}; ipc=[]; export_paths=[]; tick_number=[0]
    exporter=AsyncReplayExporter()
    def callback(phase,info):
        key=(threading.get_ident(),info['generation'])
        if phase=='start':active[key]=time.perf_counter()
        elif key in active:collections.append(dict(start=active.pop(key),end=time.perf_counter(),
            generation=info['generation'],thread=key[0]))
    def tracked(name,operation):
        def call(*args,**kwargs):
            cycles=thread_cpu();cpu=time.thread_time();start=time.perf_counter()
            try:return operation(*args,**kwargs)
            finally:
                end=time.perf_counter(); elapsed_cpu=time.thread_time()-cpu
                row=dict(start=start,end=end,cpu_s=elapsed_cpu,
                         cpu_cycles=thread_cpu()-cycles,thread=threading.get_ident())
                phases.setdefault(name,[]).append(row)
                if name=='Engine' and exports:
                    tick_number[0]+=1
                    if tick_number[0]%60==0 and not exporter.status['busy']:
                        journal=args[0].controller._pedal_journal.snapshot(expanded=False,include_history=True)
                        def export(snapshot=journal):
                            path=SteeringReplayBuffer(2).export(ROOT/'docs/steering-audit/oct14-completion/profile-exports',
                                reason='manual_disable',longitudinal=snapshot)
                            export_paths.append(str(path));return path
                        exporter.submit(export)
        return call
    original_get=IPCState.get
    def read(*args,**kwargs):
        start=time.perf_counter()
        try:return original_get(*args,**kwargs)
        finally:ipc.append((time.perf_counter()-start)*1000.)
    with frozen(before):
        gc.callbacks.append(callback)
        try:
            with patch.object(IPCState,'get',read), \
                 patch.object(Map,'on_tick',tracked('Map',Map.on_tick)), \
                 patch.object(Policy,'on_tick',tracked('Policy',Policy.on_tick)), \
                 patch.object(ACC,'on_tick',tracked('ACC',ACC.on_tick)), \
                 patch.object(AP,'on_tick',tracked('Autopilot',AP.on_tick)), \
                 patch.object(Engine,'_flush_controls',tracked('Engine',Engine._flush_controls)):
                result=native_pipeline_cost()
        finally:gc.callbacks.remove(callback)
    status=exporter.wait(30.)
    assert not status['busy'] and not status['error'],status
    for path in export_paths:assert inspect_replay(path)['integrity_valid']
    summary={}
    for name,rows in phases.items():
        slow=max(rows,key=lambda r:r['end']-r['start'])
        overlapping=[c for c in collections if c['thread']==slow['thread'] and
                     c['start']<slow['end'] and c['end']>slow['start']]
        summary[name]=dict(wall_ms=distribution([(r['end']-r['start'])*1000 for r in rows]),
            quantized_cpu_ms=distribution([r['cpu_s']*1000 for r in rows]),
            cpu_cycles=distribution([r['cpu_cycles'] for r in rows]),
            slowest=slow,gc_overlapping_slowest=overlapping)
    return dict(before=before,run=run,concurrent_exports=exports,pipeline=result,phases=summary,
        copied_ipc_read_ms=distribution(ipc),exported_integrity_valid=len(export_paths),
        gc_ms=distribution([(c['end']-c['start'])*1000 for c in collections]),
        limitations='CPU cycles are work, not converted milliseconds. thread_time is quantized. '
            'Copied IPC timings include deepcopy CPU and cannot be labeled live IPC wait. '
            'GC overlap is measured only in this run, not proof for the earlier 93 ms maximum. '
            'Bounded actual export worker runs separately; snapshots taken outside measured Engine wall phase.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT/'docs/steering-audit'):
        parser.error('Output must remain in workspace audit directory')
    models={str(mode):dict(before=moving_model(mode,True),after=moving_model(mode,False)) for mode in (0,3)}
    for row in models.values():
        assert row['before']['terminal_hold_samples']>0
        assert row['after']['stopped_samples']==row['after']['terminal_hold_samples']==0
    profiles=[dict(before=profile(True,run==3,run),after=profile(False,run==3,run)) for run in (1,2,3)]
    plain=[]
    for run in (1,2,3):
        with frozen(True):before=native_pipeline_cost()
        after=native_pipeline_cost()
        plain.append(dict(run=run,before=before,after=after))
    result=dict(baseline='add9a19',model=__doc__,models=models,profiles=profiles,
                uninstrumented_pipeline=plain,game_verified=False)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(dict(models={key:{side:{k:v for k,v in row[side].items() if k!='trace'}
        for side in ('before','after')} for key,row in models.items()},
        profiles=[{side:row[side]['pipeline'] for side in ('before','after')} for row in profiles]),indent=2))


if __name__=='__main__':main()
