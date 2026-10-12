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


def run(selector_type=RouteSignalSelector):
    points=[[0.,10.,-float(i)] for i in range(10000)]
    payload=b''.join(struct.pack('<fffhhffffifii',0.,10.,-5.-i*3.5,
        0,0,0.,0.,1.,0.,1,10.,2,19+i) for i in range(40))
    prep=[];warm=[]
    for i in range(10):
        selector=selector_type()
        start=time.perf_counter();selector.route.prepare(points,('route',i))
        prep.append(time.perf_counter()-start)
    selector=selector_type()
    plan = dict(schema_version=1,status='prepared',passages=[dict(
        passage_key='operation-benchmark',semaphore_id=19,entry_progress_m=10.,
        entry_xyz=[0.,10.,-10.],entry_heading_rad=0.,bounds_xyz=[-5.,9.,-200.,5.,11.,0.],
        front_allowance_m=6.,junction_standoff_m=2.,front_geometry_status='unmeasured_operation_fixture')])
    for i in range(501):
        now=time.monotonic()
        raw=LAYOUT.pack((i+1)*2,0x32535055,2,LAYOUT.size,11,i+1,i+1,
            now,3,40,payload,(i+1)*2)
        start=time.perf_counter()
        decoded=decode(raw,time.monotonic())
        result=selector.select(decoded,points,'same-route',('session',),
            dict(x=0.,y=10.,z=0.,rotation=0.),0.,plan)
        elapsed=time.perf_counter()-start
        assert result['valid'] and result['candidate']['id']==19,result
        if i: warm.append(elapsed)
    return dict(limitation='Synthetic ABI payload; operation cost only, no IPC/game/control scheduling.',
        points=10000,source_heads=40,geometry_preparation=summary(prep),
        cached_decode_and_selection=summary(warm))


if __name__=='__main__':
    import argparse,hashlib,importlib.util
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('output',nargs='?',type=Path)
    p.add_argument('--baseline-runtime',type=Path)
    args=p.parse_args()
    if args.baseline_runtime:
        source=args.baseline_runtime/'core/sdk/signal_snapshot.py'
        spec=importlib.util.spec_from_file_location('installed_signal_operation_baseline',source)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        result=dict(before=run(module.RouteSignalSelector),after=run(),
                    baseline_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                    candidate_sha256=hashlib.sha256((Path(__file__).resolve().parents[1]/'core/sdk/signal_snapshot.py').read_bytes()).hexdigest())
    else:result=run()
    text=json.dumps(result,indent=2)
    if args.output: args.output.write_text(text,encoding='utf-8')
    print(text)
