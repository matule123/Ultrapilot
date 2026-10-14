"""Frozen Oct14 production vs candidate with the same source-timed model inputs.

Source times/frame/geometry are explicit synthetic producer inputs, not recorded
ETS2 observations. Compiled ABI and physical backend are verified separately.
"""
import argparse
from contextlib import contextmanager
import json
import math
from pathlib import Path
import statistics
import sys
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import run_acc_following_bench as following
from tools.run_longitudinal_comfort_bench import classes, percentile
from core.navigation.traffic_producer import TrafficCapture


@contextmanager
def native_model():
    original=following.raw_capture
    def capture(actors, stamp):
        raw=original(actors,stamp)
        source=dict(schema=1,valid=True,reason='',lifecycle=1,
            generation=round((stamp-1000.)*1e6),frame_us=round((stamp-1000.)*1e6)+10000,
            observed_at=stamp,ego_body_count=0,ego_body_flags=0)
        return TrafficCapture(raw.session,raw.observed_at,raw.moving,raw.parked,raw.stable,source)
    with patch.object(following,'raw_capture',capture):
        yield


def run(case, baseline):
    import pytest
    from tests.test_oct14_completion import frozen_production_baseline
    original=following.engine_decision
    ttcs=[]
    def decide(state,truck,*a,**kw):
        result=original(state,truck,*a,**kw)
        lead=(state.get('longitudinal_traffic') or {}).get('following') or {}
        closing=truck['speed']-lead.get('speed_mps',truck['speed'])
        if lead.get('gap_m') is not None and closing>0:
            ttcs.append(lead['gap_m']/closing)
        return result
    with pytest.MonkeyPatch.context() as m, native_model(), patch.object(following,'engine_decision',decide):
        if baseline:
            m.setenv('ULTRAPILOT_OCT14_BASELINE','1')
            frozen_production_baseline.__wrapped__(m)
            with patch.object(following,'classes',lambda unused=None:classes('b11777d')):
                result=following.simulate(case)
        else:
            result=following.simulate(case)
    return dict(result,minimum_reference_ttc_s=min(ttcs) if ttcs else None)


def costs(samples=200):
    from core.acc_following import RouteLeadSelector, observation
    from core.acc_body_prediction import predict
    selector=RouteLeadSelector();points=[[0.,10.,float(i)] for i in range(301)]
    selector.prepare(points,('model',))
    actors=[(i+1,[3.+i*.2,10.,30.+i*2.],math.pi,5.) for i in range(40)]
    raw=following.raw_capture(actors,1000.)
    decoded=observation(raw,1000.)['actors']
    ego=[dict(x=0.,y=10.,z=15.,yaw=math.pi,dimensions_whl=(2.5,4.,6.)),
         dict(x=0.,y=10.,z=6.,yaw=math.pi,dimensions_whl=(2.5,4.,12.))]
    values=[]
    for _ in range(samples):
        start=time.perf_counter()
        predict(selector,ego,decoded,10.,15.,(0.,10.,15.))
        values.append((time.perf_counter()-start)*1000.)
    return dict(samples=samples,actors=40,ego_bodies=2,
        p50_ms=statistics.median(values),p95_ms=percentile(values,.95),
        p99_ms=percentile(values,.99),max_ms=max(values),
        wire_bytes=8928,reader_retained_wire_bytes=8928,
        selector_actor_history_frames=2,selector_max_actors_per_frame=80,
        prediction_horizon_s=3.,prediction_step_s=.25,
        limitation='isolated body operation; not end-to-end packet cadence or game latency')


def native_pipeline_cost(samples=180):
    """Actual components and bytes, fixed SDK/no-game source; discard mocks."""
    import gc
    from tests.test_activation_observation_binding import flow
    from tests.test_rolling_longitudinal_authority import rolling
    from tests.test_oct14_completion import timed_step
    f=flow.__wrapped__(); source=next(f)
    r=rolling.__wrapped__(source); values=next(r)
    state,engine,ap,acc,policy,tick,_,_,_,writes,clock=values
    actors=[dict(id=i+1,x=10.+i,y=10.,z=30.+i*2.,yaw=math.pi,speed=5.) for i in range(40)]
    ego=[(2.25,10.,15.,0.,0.,1.,0.,2.5,4.,6.),(2.25,10.,6.,0.,0.,1.,0.,2.5,4.,12.)]
    times=[]
    def deep_size(value,seen):
        if id(value) in seen:return 0
        seen.add(id(value)); size=sys.getsizeof(value)
        if isinstance(value,dict):size+=sum(deep_size(k,seen)+deep_size(v,seen) for k,v in value.items())
        elif isinstance(value,(tuple,list)):size+=sum(deep_size(v,seen) for v in value)
        return size
    try:
        for generation in range(1,samples+1):
            start=time.perf_counter()
            timed_step(values,actors,generation=generation,ego=ego)
            times.append((time.perf_counter()-start)*1000.)
            assert state.get('autopilot_active'),state.get('autopilot_intervention')
            writes.clear()
            for item in source:
                if hasattr(item,'samples') and isinstance(item.samples,list):item.samples.clear()
                elif isinstance(item,list) and item is not clock:item.clear()
        selector=engine._acc_selector
        journal=engine.controller._pedal_journal
        return dict(samples=samples,actors=40,ego_bodies=2,modeled_duration_s=samples*.033333,
            p50_ms=statistics.median(times),p95_ms=percentile(times,.95),
            p99_ms=percentile(times,.99),max_ms=max(times),
            actor_motion_history_deep_bytes=deep_size((selector._native_previous,selector._native_current),set()),
            journal_detail_bytes=journal._bytes,detail_budget=journal.MAX_BYTES,
            journal_history_bytes=sum(journal._history.bytes.values())+journal._history.identity_bytes,
            history_budget=journal._history.MAX_BYTES if hasattr(journal._history,'MAX_BYTES') else 1048576,
            limitation='Map/native atomic bytes/Policy/ACC/AP/Engine/Controller; copied synthetic IPC. '
                'Includes fixture geometry and producer work; not live frame cadence, RSS or game latency. '
                'Assertion-write/collector histories cleared and excluded from retained memory.')
    finally:
        r.close();f.close();gc.collect()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if not a.output.resolve().is_relative_to(ROOT/'docs/steering-audit'):
        p.error('Output must remain in audit workspace')
    result=dict(ref='b11777d',seed=7301,model=following.__doc__,
        cases={c['name']:dict(before=run(c,True),after=run(c,False)) for c in following.CASES},
        isolated_cost=costs(),native_pipeline_cost=native_pipeline_cost())
    a.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    for name,row in result['cases'].items():
        print(name,'gap',row['before']['min_reference_gap_m'],'->',row['after']['min_reference_gap_m'],
            'RMS',row['before']['steady_speed_error_rms_kmh'],'->',row['after']['steady_speed_error_rms_kmh'])
    print(result['isolated_cost'])
