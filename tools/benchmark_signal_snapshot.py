"""Isolated signal decode/projection cost; not live tick or game proof."""
import json
import math
from pathlib import Path
import statistics
import struct
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.sdk.signal_snapshot import LAYOUT, decode, RouteSignalSelector


def summary(values):
    values=sorted(values)
    return dict(samples=len(values),median_ms=statistics.median(values)*1000,
        p95_ms=values[math.ceil(len(values)*.95)-1]*1000,max_ms=max(values)*1000)


def run():
    points=[[0.,10.,-float(i)] for i in range(10000)]
    payload=b''.join(struct.pack('<fffhhffffifii',0.,10.,-5.-i*3.5,
        0,0,0.,0.,1.,0.,1,10.,2,19+i) for i in range(40))
    prep=[];warm=[]
    for i in range(10):
        selector=RouteSignalSelector()
        start=time.perf_counter();selector.route.prepare(points,('route',i))
        prep.append(time.perf_counter()-start)
    selector=RouteSignalSelector()
    for i in range(501):
        now=time.monotonic()
        raw=LAYOUT.pack((i+1)*2,0x32535055,2,LAYOUT.size,11,i+1,i+1,
            now,3,40,payload,(i+1)*2)
        start=time.perf_counter()
        decoded=decode(raw,time.monotonic())
        result=selector.select(decoded,points,'same-route',('session',),
            dict(x=0.,y=10.,z=0.,rotation=0.),0.)
        elapsed=time.perf_counter()-start
        assert result['valid'] and result['candidate']['id']==19,result
        if i: warm.append(elapsed)
    return dict(limitation='Synthetic ABI payload; operation cost only, no IPC/game/control scheduling.',
        points=10000,source_heads=40,geometry_preparation=summary(prep),
        cached_decode_and_selection=summary(warm))


if __name__=='__main__':
    result=run()
    text=json.dumps(result,indent=2)
    if len(sys.argv)>1: Path(sys.argv[1]).write_text(text,encoding='utf-8')
    print(text)
