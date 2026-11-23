"""Finite actual Manager-RPC/production traffic profile, no installation writes.

Acquisition is a synthetic native ABI buffer. Wall/CPU/GC are measured locally;
this cannot identify an unrecorded historical inner operation.
"""
import argparse
import gc
import json
import logging
import math
import multiprocessing as mp
from pathlib import Path
import time
from types import SimpleNamespace
from unittest.mock import patch

from tools.benchmark_oct17_systemic import baseline
from tools.benchmark_oct15_crossing_dev_hud import percentiles


class TimedMapping:
    def __init__(self, raw):
        self.raw=raw;self.cost=[];self.calls=0

    def invoke(self, operation, *args):
        at=time.perf_counter()
        try:return getattr(self.raw,operation)(*args)
        finally:self.cost.append((time.perf_counter()-at)*1000);self.calls+=1

    def get(self,*args):return self.invoke('get',*args)
    def __getitem__(self,key):return self.invoke('__getitem__',key)
    def __setitem__(self,key,value):return self.invoke('__setitem__',key,value)
    def __contains__(self,key):return self.invoke('__contains__',key)
    def update(self,*args):return self.invoke('update',*args)


def run(manager,before,repeat,samples):
    from tests.test_activation_observation_binding import flow
    from tests.lifecycle.test_joint_regressions import joint
    from tests.lifecycle.test_systemic_longitudinal import native_producer
    import core.navigation.traffic_producer as producer
    generator=flow.__wrapped__();f=next(generator)
    source=joint.__wrapped__(f,SimpleNamespace(param=0));values=next(source)
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=values
    acquire=native_producer(values,actors=[dict(id=100+i,x=40.+i%8*2,y=10.,z=80.+i*2,yaw=math.pi,speed=3.) for i in range(35)])
    proxy=TimedMapping(manager.dict(state.values));state.values=proxy
    for plugin in (ap,acc,policy,tick.publish_map.__self__):
        for view in (plugin.sdk,*plugin.sdk.__dict__.values()):
            if hasattr(view,'_state'):object.__setattr__(view,'_state',proxy)
    rows=[];gc_spans=[];gc_begin=[]
    def callback(phase,info):
        if phase=='start':gc_begin.append(time.perf_counter())
        elif gc_begin:gc_spans.append((time.perf_counter()-gc_begin.pop())*1000)
    gc.callbacks.append(callback)
    try:
        with baseline(before) as old:
            for index in range(samples):
                tick(speed=5.,pedals=False);acquire(index+1)
                truck=state.get('telemetry')['truck']
                counts=proxy.calls;proxy.cost.clear();phases={}
                def timed(name,operation):
                    def measure(*args,**kwargs):
                        at=time.perf_counter()
                        try:return operation(*args,**kwargs)
                        finally:phases[name]=phases.get(name,0.)+(time.perf_counter()-at)*1000
                    return measure
                anchor=clock[0];wall=time.perf_counter();cpu=time.thread_time()
                with patch('time.monotonic',side_effect=lambda:anchor+time.perf_counter()-wall), \
                        patch.object(engine,'_signal_observation',timed('signal_ms',engine._signal_observation)), \
                        patch.object(engine,'_traffic_control_observation',timed('projection_ms',engine._traffic_control_observation)), \
                        patch.object(engine,'_publish_traffic_control',timed('publication_ms',engine._publish_traffic_control)), \
                        patch.object(producer,'capture_traffic',timed('native_ms',producer.capture_traffic)):
                    if old:packet=old(engine,truck,truck['_control_observation']['observed_at'])
                    else:packet=engine._traffic_tick()
                elapsed=(time.perf_counter()-wall)*1000
                producer_cpu=(time.thread_time()-cpu)*1000
                rpc_ms=sum(proxy.cost);rpc_calls=proxy.calls-counts
                clock[0]=anchor+elapsed/1000
                assert packet and packet['valid']
                # Final consumer/backend remain the ordinary unpatched flow.
                policy.on_tick(.033);acc.on_tick(.033);ap.on_tick(.033);engine._flush_controls()
                assert not state.get('autopilot_intervention'),state.get('autopilot_intervention')
                assert physical('aforward')==0. or physical('abackward')==0.
                rows.append(dict(index=index,wall_ms=elapsed,cpu_ms=producer_cpu,
                    rpc_ms=rpc_ms,rpc_calls=rpc_calls,**phases))
                writes.clear();proxy.cost.clear()
                if hasattr(time.monotonic,'reset_mock'):time.monotonic.reset_mock()
        warm=rows[10:]
        keys=('wall_ms','rpc_ms','signal_ms','native_ms','projection_ms','publication_ms')
        return dict(baseline=before,repeat=repeat,actors=35,cold=rows[0],warm_samples=len(warm),
            warm={k:percentiles([r.get(k,0.) for r in warm]) for k in keys},
            cpu_total_ms=sum(r['cpu_ms'] for r in rows),gc_ms=percentiles(gc_spans) if gc_spans else None,
            rows=rows,limitation='Actual local Manager RPC, synthetic ABI acquisition/route; warm distributions are not live scheduling or historical CPU attribution. RPC overlaps phase times; do not add them.')
    finally:
        gc.callbacks.remove(callback);source.close();generator.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--samples',type=int,default=65)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('Never overwrite evidence')
    logging.disable(logging.WARNING);rows=[]
    with mp.Manager() as manager:
        for repeat in range(3):
            for before in ((True,False) if repeat%2==0 else (False,True)):
                row=run(manager,before,repeat,args.samples);rows.append(row)
                print(json.dumps({k:v for k,v in row.items() if k!='rows'}),flush=True)
    args.output.write_text(json.dumps(rows,indent=2),encoding='utf-8')


if __name__=='__main__':
    mp.freeze_support();main()
