"""Installed selector vs candidate, unchanged existing closed-loop stop model.

Operation cost is distinct from game cadence. Native response, front geometry,
brake consumption and grade are uncalibrated model assumptions.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools import run_prefab_signal_bench as bench
from tests.test_oct10_signal_approach import scene
from core.sdk.signal_snapshot import RouteSignalSelector


def stats(values):
    ordered=sorted(values)
    return {k:ordered[int(q*(len(ordered)-1))]*1000 for k,q in
            (('p50_ms',.5),('p95_ms',.95),('p99_ms',.99),('max_ms',1.))}


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--workdir',type=Path,required=True);a=p.parse_args();a.workdir.mkdir(exist_ok=False)
    path=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot\core\sdk\signal_snapshot.py')
    spec=importlib.util.spec_from_file_location('installed_selector_bench',path)
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    result={'limitation':__doc__,'qualified_cycles':{},'unknown_operation':{}}
    for mode in (0,3):
        for speed in (35.,50.):
            runs=[]
            for cls in (old.RouteSignalSelector,RouteSignalSelector):
                with patch.object(bench,'RouteSignalSelector',cls):
                    r=bench.run(a.workdir,mode=mode,speed_kmh=speed,jitter=True)
                runs.append({k:v for k,v in r.items() if k not in ('rows','writes','captures')})
            result['qualified_cycles'][f'{mode}/{speed}']=dict(before=runs[0],after=runs[1],
                                                              identical=runs[0]==runs[1])
    snap,points,plan,truck=scene(a.workdir)
    for name,cls in (('before',old.RouteSignalSelector),('after',RouteSignalSelector)):
        s=cls();cost=[]
        for i in range(1000):
            current=dict(snap,generation=i+1,frame_us=i+1,observed_at=1000.+i*.05)
            begin=time.perf_counter();selected=s.select(current,points,'route',('authority',),truck,0.,plan)
            cost.append(time.perf_counter()-begin)
        result['unknown_operation'][name]=dict(samples=1000,timings=stats(cost),
            coverage=selected['coverage'],retained_pending_entries=int(s._uncertain_approach is not None) if name=='after' else 0)
    a.output.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
    return 0 if all(c['identical'] for c in result['qualified_cycles'].values()) else 1

if __name__=='__main__':raise SystemExit(main())
