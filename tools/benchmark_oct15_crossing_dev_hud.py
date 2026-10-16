"""Same actual producer/consumer/backend operations with DEV presentation off/on.

Synthetic SDK/vehicle poses; no measured game physics. Mock history is cleared
outside measured ticks. Runtime retained memory excludes fixture/log histories.
"""
import argparse
import collections
import gc
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import statistics
import sys
import time
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def percentiles(values):
    ordered=sorted(values)
    return dict(n=len(values),p50=statistics.median(ordered),
        p95=ordered[min(len(ordered)-1,int(.95*len(ordered)))],
        p99=ordered[min(len(ordered)-1,int(.99*len(ordered)))],max=max(ordered),min=min(ordered))


def deep_size(value, seen=None):
    seen=set() if seen is None else seen
    if id(value) in seen:return 0
    seen.add(id(value));total=sys.getsizeof(value)
    if isinstance(value,dict):return total+sum(deep_size(k,seen)+deep_size(v,seen) for k,v in value.items())
    if isinstance(value,(tuple,list,collections.deque)):return total+sum(deep_size(v,seen) for v in value)
    return total


def run(enabled,mode,ticks):
    from tests.test_activation_observation_binding import flow
    from tests.test_oct11_joint_regressions import joint
    from tests.test_oct15_crossing_dev_hud import step,crossing
    gen=flow.__wrapped__(); f=next(gen)
    source=joint.__wrapped__(f,SimpleNamespace(param=mode)); values=next(source)
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=values
    state.set('dev_hud_enabled',enabled)
    engine._maneuver_diagnostic_collector=None
    counts=collections.Counter();original=state.get
    def read(key,default=None):
        counts[key]+=1
        return original(key,default)
    state.get=read
    wall=[];cpu=[];output=[];gc_spans=[];started=[]
    def collect(phase,info):
        if phase=='start':started.append(time.perf_counter())
        elif started:gc_spans.append(time.perf_counter()-started.pop())
    gc.callbacks.append(collect)
    try:
        # Both feeds see identical moving native records and passive crossings;
        # unchanged Map route construction, ACC and real physical dispatch.
        for index in range(ticks+25):
            before=len(writes)
            at=time.perf_counter();cp=time.thread_time()
            actors=[crossing(at=60.,arrival=7.97)] + [
                dict(id=100+i,x=12.+(i%3)*3,y=10.,z=24.+i*4,
                     yaw=math.pi,speed=6.) for i in range(8)]
            step(values,actors,index+1)
            used=time.thread_time()-cp;elapsed=time.perf_counter()-at
            if index>=25:
                wall.append(elapsed*1000);cpu.append(used*1000)
                output.extend((ch,round(v,7)) for _,ch,v in writes[before:])
            # Exclude test Mock call histories and accumulated physical-log
            # assertions from retained runtime memory and allocation growth.
            writes.clear()
            if hasattr(time.monotonic,'reset_mock'):time.monotonic.reset_mock()
        feed=getattr(engine,'_dev_hud',None)
        if feed and feed.future:feed.future.result(timeout=3)
        snapshot=feed.snapshot() if feed else None
        memory=deep_size(snapshot)
        return dict(wall_ms=percentiles(wall),control_thread_cpu_ms=percentiles(cpu),
            gc_ms=percentiles([v*1000 for v in gc_spans]) if gc_spans else None,
            runtime_snapshot_deep_bytes=memory,control_output_sha256=hashlib.sha256(repr(output).encode()).hexdigest(),
            faults=state.get('autopilot_intervention'),
            source_reads={k:v for k,v in counts.items() if not k.startswith('dev_hud')},
            presentation_reads={k:v for k,v in counts.items() if k.startswith('dev_hud')},
            frame_status=(snapshot or {}).get('attribution'))
    finally:
        gc.callbacks.remove(collect)
        if getattr(engine,'_dev_hud',None):engine._dev_hud.close()
        source.close();gen.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--ticks',type=int,default=500)
    parser.add_argument('--ipc-only',action='store_true',
        help='Separate real Manager transport probe; not an end-to-end control benchmark')
    args=parser.parse_args();logging.disable(logging.WARNING)
    if args.ipc_only:
        result=ipc_benchmark()
        args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result,indent=2))
        return
    rows={str(mode):{label:run(flag,mode,args.ticks) for label,flag in (('off',False),('on',True))}
          for mode in (0,3)}
    for mode,pair in rows.items():
        assert pair['off']['control_output_sha256']==pair['on']['control_output_sha256'],mode
        assert pair['off']['source_reads']==pair['on']['source_reads'],mode
        assert pair['off']['faults'] is pair['on']['faults'] is None
    result=dict(basis='actual pipeline, synthetic native inputs; no ETS2 proof',ticks=args.ticks,
                rows=rows,render=render_benchmark())
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({mode:{label:{k:v for k,v in row.items() if k not in ('source_reads','presentation_reads')}
        for label,row in pair.items()} for mode,pair in rows.items()},indent=2))


def render_benchmark():
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QImage,QPainter,QFontDatabase
    from PyQt6.QtCore import QRectF
    from core.hud import UltraPilotHUD
    from tools.preview_traffic_dev_hud import demo_snapshot
    app=QApplication.instance() or QApplication([])
    for font in ('consola.ttf','segoeui.ttf'):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/font))
    hud=UltraPilotHUD.__new__(UltraPilotHUD)
    hud._view_yaw=0.;hud._display_truck_pos=None;hud._display_truck_heading=None;hud._t=0.;hud._blink=True
    image=QImage(1100,650,QImage.Format.Format_ARGB32)
    data=dict(pos=(0.,0.),heading=0.,altitude=10.,speed_kmh=36.,
        nav_path=[[0.,10.,-float(i)] for i in range(-20,151)],lane_width_m=4.5,lanes=2,
        road_segments=[((0.,-float(i),10.),(0.,-float(i+5),10.),'road',2,False) for i in range(-20,150,5)],
        traffic=[],light=None,trailer_attached=True,trailer_heading=0.,trailer_articulation=0.)
    snapshot=demo_snapshot();results={}
    for enabled in (False,True):
        sample=dict(data,**(dict(dev_snapshot=snapshot,dev_test_data=True,dev_now=100.1) if enabled else {}))
        values=[]
        for i in range(225):
            at=time.perf_counter()
            painter=QPainter(image);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            hud._draw_driving_view(painter,QRectF(0,0,1100,650),sample);painter.end()
            if i>=25:values.append((time.perf_counter()-at)*1000)
        results['on' if enabled else 'off']=percentiles(values)
    return dict(wall_ms=results,image_bytes=image.sizeInBytes(),
        native_snapshot_deep_bytes=deep_size(snapshot),basis='actual classic 3D QPainter; synthetic scene; 25 warmup + 200 draws')


def ipc_benchmark():
    """Separate real IPC/display load from the fixture pipeline's CPU timing."""
    import multiprocessing
    import threading
    import pickle
    from core.ipc.shared_state import SharedState
    from core.traffic_dev_hud import DevHUDFeed
    from tools.preview_traffic_dev_hud import demo_snapshot
    snapshot=demo_snapshot()
    result=dict(basis='actual Manager transport; fixed TEST DATA, 50 Hz probe, 60 Hz display reads, '
        '10 Hz bounded publication; not control/SDK freshness or game physics',rows={},
        payload_pickle_bytes=len(pickle.dumps(snapshot)))
    with multiprocessing.get_context('spawn').Manager() as manager:
        raw=manager.dict(telemetry={'truck':{'speed':10.,'gear':4}})
        state=SharedState(raw)
        for enabled in (False,True):
            feed=DevHUDFeed()
            feed.capture(snapshot['detection']);feed.latest=snapshot['applied']
            state.set('dev_hud_enabled',enabled)
            stop=threading.Event();reads=[];failures=[]
            def display():
                while not stop.wait(1/60):
                    if enabled:
                        started=time.perf_counter()
                        try:
                            value=state.get('dev_hud_snapshot')
                            if value is not None:reads.append((time.perf_counter()-started)*1000)
                        except Exception as error:
                            failures.append(type(error).__name__)
            reader=threading.Thread(target=display,daemon=True)
            reader.start();probes=[];deadline=time.perf_counter()
            try:
                for i in range(160):
                    at=time.perf_counter()
                    assert state.get('telemetry')['truck']['gear']==4
                    assert state.get('dev_hud_enabled') is enabled
                    if enabled:feed.offer(state,time.monotonic())
                    if i>=10:probes.append((time.perf_counter()-at)*1000)
                    deadline+=.02
                    time.sleep(max(0.,deadline-time.perf_counter()))
                if feed.future:feed.future.result(timeout=3)
            finally:
                stop.set();reader.join(timeout=3);feed.close()
            assert not reader.is_alive() and not failures
            if enabled:
                assert reads and state.get('dev_hud_snapshot')['detection']==snapshot['detection']
            result['rows']['on' if enabled else 'off']=dict(
                probe_ms=percentiles(probes),display_read_ms=percentiles(reads) if reads else None,
                skipped_publications=feed.skipped,unbounded_queue=False)
    return result


if __name__=='__main__':main()
