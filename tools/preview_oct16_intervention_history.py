"""Offscreen TEST DATA preview/memory audit of actual historical HUD adapter."""
import argparse
import json
import math
import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    from tests.test_activation_observation_binding import flow
    from tests.lifecycle.test_joint_regressions import joint
    from tests.traffic.test_crossing_dev_hud import step
    from tools.benchmark_oct15_crossing_dev_hud import deep_size
    from core.traffic_dev_hud import for_display,FRAME_BUDGET,RECEIPT_BUDGET
    from core.navigation.longitudinal_diagnostics import bounded_copy
    gen=flow.__wrapped__();fixture=next(gen)
    source=joint.__wrapped__(fixture,SimpleNamespace(param=0));values=next(source)
    state,engine,*_=values
    try:
        state.set('dev_hud_enabled',True)
        hazard=dict(id=26,x=-9.2,y=10.,z=38.,yaw=-math.pi/2,speed=4.)
        for generation in range(1,9):step(values,[hazard],generation)
        feed=engine._dev_hud
        engine._longitudinal_rejection_detail=dict(source='acc',following_target_id='28',
            decisive_brake_actor_id=26,invalid_reason='ACC original native owner continuity unavailable; driver takeover required')
        engine._automatic_safety_stop('acc: invalid longitudinal observation')
        snapshot=feed.snapshot();shown=for_display(snapshot,snapshot['applied']['context'],False)
        assert shown['history_only'] and shown['last_fault']['kind']=='technical'
        owned=dict(frames=tuple(feed.frames),latest=feed.latest,history=feed.last_intervention,fault=feed.last_fault)
        geometries={id(f):f for f in (*feed.frames,(feed.last_intervention or {}).get('geometry')) if f is not None}
        receipt_size=sum(bounded_copy(v,limit=RECEIPT_BUDGET)[1] for v in
            (feed.latest,(feed.last_intervention or {}).get('applied'),feed.last_fault) if v is not None)
        assert len(geometries)<=2 and receipt_size<=RECEIPT_BUDGET
        sizes=[bounded_copy(f,limit=FRAME_BUDGET)[1] for f in geometries.values()]
        assert all(size<=FRAME_BUDGET for size in sizes)
        result=dict(basis=__doc__,owned_adapter_deep_bytes=deep_size(owned),
            accounted_geometry_bytes=sizes,accounted_receipt_bytes=receipt_size,
            distinct_geometry_frames=len(geometries),
            limitation='Excludes fixtures/mock write history, selector/PID/journal, pending serialized IPC copy, worker/OS/RSS',
            snapshot=shown)
        (a.output/'history-TEST-DATA.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        render(shown,a.output/'history-TEST-DATA.png',values[-1][0]+2.)
        print(json.dumps({k:v for k,v in result.items() if k!='snapshot'},indent=2))
    finally:
        if getattr(engine,'_dev_hud',None):engine._dev_hud.close()
        source.close();gen.close()


def render(snapshot,output,now):
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QImage,QPainter,QFontDatabase,QFont
    from PyQt6.QtCore import QRectF
    from core.hud import UltraPilotHUD
    app=QApplication.instance() or QApplication([])
    for font in ('consola.ttf','segoeui.ttf'):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/font))
    app.setFont(QFont('Segoe UI',10))
    view=UltraPilotHUD.__new__(UltraPilotHUD)
    view._view_yaw=0.;view._display_truck_pos=None;view._display_truck_heading=None
    view._t=0.;view._blink=True
    sample=dict(pos=(2.25,15.),heading=math.pi,altitude=10.,speed_kmh=0.,
        nav_path=[[2.25,10.,float(i)] for i in range(151)],lane_width_m=4.5,lanes=2,
        road_segments=[((2.25,float(i),10.),(2.25,float(i+5),10.),'road',2,False) for i in range(0,150,5)],
        traffic=[],light=None,trailer_attached=False,trailer_heading=math.pi,trailer_articulation=0.,
        dev_snapshot=snapshot,dev_test_data=True,dev_now=now)
    image=QImage(1100,650,QImage.Format.Format_ARGB32);image.fill(0xff141517)
    painter=QPainter(image);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    view._draw_driving_view(painter,QRectF(0,0,1100,650),sample);painter.end()
    assert image.save(str(output))


if __name__=='__main__':main()
