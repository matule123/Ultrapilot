"""Actual dense ABI/control/display work, paired DEV off/on; no game access."""
import argparse
import ast
from contextlib import ExitStack
import json
import math
import os
from pathlib import Path
import subprocess
import time
from unittest.mock import patch

from tools import benchmark_oct15_crossing_dev_hud as bench
from tests import test_oct15_crossing_dev_hud as cases
from tests.test_oct16_joint_traffic_regressions import dense_capture
import core.traffic_dev_hud as hud


def native_dense_snapshot(*,with_memory=False):
    from tests.test_activation_observation_binding import flow
    from tests.test_oct11_joint_regressions import joint
    from types import SimpleNamespace
    gen=flow.__wrapped__();fixture=next(gen)
    source=joint.__wrapped__(fixture,SimpleNamespace(param=0));values=next(source)
    state,engine=values[:2];state.set('dev_hud_enabled',True)
    actors=[dict(id=100+i,x=70.+i,y=10.,z=180.+i,yaw=math.pi,speed=5.) for i in range(79)]
    actors.append(dict(id=29,x=2.25,y=10.,z=45.,yaw=math.pi,speed=3.))
    try:
        with patch.object(cases,'capture',dense_capture):
            for generation in range(1,9):cases.step(values,actors,generation)
        feed=engine._dev_hud
        snapshot=feed.snapshot()
        if with_memory:
            return snapshot,dict(owned_frames=len(feed.frames),
                frames_and_receipt_deep_bytes=bench.deep_size(dict(frames=tuple(feed.frames),latest=feed.latest)),
                snapshot_deep_bytes=bench.deep_size(snapshot),
                exclusion='Test histories, control caches, Python thread/executor overhead and OS stack/RSS are not counted')
        return snapshot
    finally:
        if getattr(engine,'_dev_hud',None):engine._dev_hud.close()
        source.close();gen.close()


def render(frame,output):
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QImage,QPainter,QFontDatabase,QFont
    from PyQt6.QtCore import QRectF
    from core.hud import UltraPilotHUD
    app=QApplication.instance() or QApplication([])
    for font in ('consola.ttf','segoeui.ttf'):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/font))
    app.setFont(QFont('Segoe UI',10))
    view=UltraPilotHUD.__new__(UltraPilotHUD)
    view._view_yaw=0.;view._display_truck_pos=None;view._display_truck_heading=None;view._t=0.;view._blink=True
    image=QImage(1100,650,QImage.Format.Format_ARGB32)
    sample=dict(pos=(2.25,15.),heading=math.pi,altitude=10.,speed_kmh=27.36,
        nav_path=[[2.25,10.,float(i)] for i in range(-20,151)],lane_width_m=4.5,lanes=2,
        road_segments=[((2.25,float(i),10.),(2.25,float(i+5),10.),'road',2,False) for i in range(-20,150,5)],
        traffic=[],light=None,trailer_attached=True,trailer_heading=math.pi,trailer_articulation=0.)
    snapshot=dict(detection=frame,applied=None,consumed_geometry=None,attribution='CONSUMED_GEOMETRY_UNAVAILABLE')
    timings={}
    for enabled in (False,True):
        data=dict(sample,**(dict(dev_snapshot=snapshot,dev_test_data=True,
            dev_now=frame['source']['observed_at']+.01) if enabled else {}))
        values=[]
        for i in range(125):
            at=time.perf_counter();p=QPainter(image);p.setRenderHint(QPainter.RenderHint.Antialiasing)
            view._draw_driving_view(p,QRectF(0,0,1100,650),data);p.end()
            if i>=25:values.append((time.perf_counter()-at)*1000)
        timings['on' if enabled else 'off']=bench.percentiles(values)
    assert image.save(str(output))
    return dict(wall_ms=timings,shown_actor_records=len(frame['actors']),image=str(output),
        basis='Actual dense admitted native boxes on classic 3-D QPainter; TEST DATA, no game measurement')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--ticks',type=int,default=160)
    p.add_argument('--render-ipc-only',action='store_true',help='Dense native fixture, actual 3-D renderer and separate Manager transport probe')
    a=p.parse_args()
    if a.render_ipc_only:
        snapshot=native_dense_snapshot()
        result=dict(render=render(snapshot['detection'],a.output.with_suffix('.png')))
        with patch('tools.preview_traffic_dev_hud.demo_snapshot',return_value=snapshot):
            result['ipc']=bench.ipc_benchmark()
        a.output.with_suffix('.frame.json').write_text(json.dumps(snapshot),encoding='utf-8')
        a.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
        return
    original=cases.step
    rows={};last_frame=None
    source=subprocess.check_output(['git','show','0ed435f:core/traffic_dev_hud.py']).decode()
    node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='geometry')
    namespace={};exec(compile(ast.Module(body=[node],type_ignores=[]),'baseline/geometry','exec'),vars(hud),namespace)
    old=namespace['geometry']
    for count in (65,80):
        actors=[dict(id=100+i,x=70.+i,y=10.,z=180.+i,yaw=math.pi,speed=5.) for i in range(count-1)]
        actors.append(dict(id=29,x=2.25,y=10.,z=45.,yaw=math.pi,speed=3.))
        def dense(values,unused,index):return original(values,actors,index)
        with patch.object(cases,'capture',dense_capture),patch.object(cases,'step',dense):
            for mode in (0,3):
                saved={}
                def old_capture(*args,**kwargs):
                    frame=old(*args);saved['before']=frame;return frame
                current=hud.geometry
                def new_capture(*args,**kwargs):
                    frame=current(*args,**kwargs);saved['after']=frame;return frame
                with patch.object(hud,'geometry',old_capture):
                    before=bench.run(True,mode,a.ticks)
                off=bench.run(False,mode,a.ticks)
                with patch.object(hud,'geometry',new_capture):on=bench.run(True,mode,a.ticks)
                assert off['control_output_sha256']==on['control_output_sha256']==before['control_output_sha256']
                assert off['source_reads']==on['source_reads']==before['source_reads']
                assert off['faults'] is on['faults'] is before['faults'] is None
                admission={label:dict(actors=len(frame.get('actors') or ()),
                    accounted_bytes=hud.bounded_copy(frame,limit=hud.FRAME_BUDGET)[1],
                    **{k:frame.get(k) for k in ('snapshot_status','omitted_actors','omitted_bodies',
                        'omitted_priority_actors','omitted_prediction_paths','omitted_prediction_points')})
                    for label,frame in saved.items()}
                last_frame=saved['after']
                rows[f'{count}/{mode}']=dict(before=before,off=off,on=on,admission=admission)
                print(count,mode,json.dumps({k:{f:v for f,v in d.items() if f not in ('source_reads','presentation_reads')}
                    for k,d in rows[f'{count}/{mode}'].items()}),flush=True)
    a.output.with_suffix('.frame.json').write_text(json.dumps(last_frame),encoding='utf-8')
    a.output.write_text(json.dumps(dict(basis='Synthetic ABI 40 moving + up to 40 parked; real Controller writes, no ETS2',
        rows=rows,render=render(last_frame,a.output.with_suffix('.png'))),indent=2),encoding='utf-8')


if __name__=='__main__':main()
