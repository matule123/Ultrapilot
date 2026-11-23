"""Render the real developer panel OFFSCREEN using explicitly synthetic data."""
import argparse
import json
import os
from pathlib import Path
import sys

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def demo_snapshot():
    from core.traffic_dev_hud import DevHUDFeed
    from core.acc_following import RouteLeadSelector, observation
    from core.acc_body_prediction import predict
    from core.navigation.traffic_producer import capture_traffic
    from core.sdk.traffic_snapshot import TrafficReader
    from tests.test_acc_following import capture
    from tests.lifecycle.test_longitudinal_completion import native_bytes
    from types import SimpleNamespace
    import math
    at=100.
    actors=[dict(id=83,x=-9.,y=10.,z=-25.,yaw=-math.pi/2,speed=4.),
        dict(id=54,x=0.,y=10.,z=-50.,yaw=0.,speed=6.),
        dict(id=17,x=12.,y=10.,z=-20.,yaw=0.,speed=7.)]
    raw=capture(actors,at)
    native=TrafficReader();native.buffer=native_bytes(raw,at,ego=[(0.,10.,0.,1.,0.,0.,0.,2.5,4.,6.)])
    observed=observation(capture_traffic(SimpleNamespace(_timed_traffic_reader=native),'test-session',at),at)
    route=RouteLeadSelector();route.prepare([[0.,10.,-i] for i in range(151)],('TEST DATA',))
    truck=dict(x=0.,y=10.,z=0.,rotation=0.,speed=10.,gear=4,sdkFrameTimeUs=100000,
        _control_observation=dict(observed_at=at,valid=True))
    following=route.select(observed['actors'],truck,0.,receiver_time=at,source=observed['source'])
    following['crossing']=route.crossing(observed['actors'],truck,0.)
    debug={}
    following['body_prediction']=predict(route,observed['ego_bodies'],observed['actors'],10.,0.,
        (0.,10.,0.),debug_geometry=debug)
    from core.traffic_dev_hud import geometry
    feed=DevHUDFeed();feed.capture(geometry(observed,route,truck,0.,('TEST DATA',),following,debug))
    feed.latest=dict(context=['TEST DATA'],sequence=41,sdk_frame_us=100000,
        observation_timestamp=at,traffic_source={k:observed['source'][k] for k in
            ('lifecycle','generation','frame_us','observed_at')},
        source=dict(source='traffic',reason='observed crossing service brake',emergency=False),
        target_id='54',targets=[dict(id='83',cap_mps=5.),dict(id='54',cap_mps=6.)],
        braking_actor_ids=['83'],
        brake_basis=dict(decisive=dict(id=83)),output_intent=dict(throttle=0.,brake=.35),
        backend_pair=dict(throttle=0.,brake=.35),
        write_stats=dict(write_success_count=2,write_error_count=0,write_last_sequence=82,
                         backend_brake_max=.35,
                         last_backend_status='MAPPING_WRITE_RETURNED'),first_fault=None)
    return feed.snapshot()


def render(output):
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QImage,QPainter,QFontDatabase
    from PyQt6.QtCore import QRectF
    from core.hud import UltraPilotHUD
    app=QApplication.instance() or QApplication([])
    # Qt's offscreen Windows backend does not enumerate system fonts here.
    for font in ('consola.ttf','segoeui.ttf'):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/font))
    snap=demo_snapshot()
    paths=[]
    # The actual classic perspective renderer, with explicit synthetic asphalt
    # segments. These are preview fixtures, never installed map evidence.
    hud=UltraPilotHUD.__new__(UltraPilotHUD)
    hud._view_yaw=0.;hud._display_truck_pos=None;hud._display_truck_heading=None
    hud._t=0.;hud._blink=True
    points=[[0.,10.,-float(i)] for i in range(-20,151)]
    roads=[((0.,-float(i),10.),(0.,-float(i+5),10.),'road',2,False)
        for i in range(-20,150,5)]
    data=dict(pos=(0.,0.),heading=0.,altitude=10.,speed_kmh=36.,nav_path=points,
        lane_width_m=4.5,lanes=2,road_segments=roads,traffic=[],light=None,
        trailer_attached=True,trailer_heading=0.,trailer_articulation=0.,
        dev_snapshot=snap,dev_test_data=True)
    for label,now in (('live',100.1),('stale',100.7)):
        canvas=QImage(1100,650,QImage.Format.Format_ARGB32)
        painter=QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        canvas.fill(0xff141517)
        hud._draw_driving_view(painter,QRectF(0,0,1100,650),dict(data,dev_now=now))
        painter.end()
        path=output/f'dev-hud-{label}-TEST-DATA.png'
        assert canvas.save(str(path));paths.append(str(path))
    (output/'dev-hud-TEST-DATA.json').write_text(json.dumps(snap),encoding='utf-8')
    print('\n'.join(paths))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    render(args.output)
