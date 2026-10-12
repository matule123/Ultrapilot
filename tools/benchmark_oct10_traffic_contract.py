"""Same modeled traffic/real pedal pipeline: installed baseline vs candidate.

No game/native I/O. Operation wall cost is not packet-cadence or ETS2 latency.
The baseline publisher reproduces the installed inline publication contract;
its actor decoder and directed selector are the actual installed source.
"""
import argparse
import gc
import json
from pathlib import Path
import sys
import time
from types import ModuleType
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core import acc_following
from core import longitudinal
from core.longitudinal import context, publish
from tests.test_activation_observation_binding import flow
from tests.test_oct10_traffic_availability import produce
from tests.test_oct9_traffic_control_contract import setup_route, forward_actor


def stats(values):
    v=sorted(values)
    return dict(samples=len(v),**{key: v[int(q*(len(v)-1))]*1000
        for key,q in [('p50_ms',.5),('p95_ms',.95),('p99_ms',.99),('max_ms',1)]})


def baseline_publish(self,truck,stamp,binding,traffic,capture,following,brake,signal,detected):
    light=signal.get('candidate') if signal.get('valid') else signal.get('stop_candidate')
    available=following['status'] in ('candidate','no_candidate_unproven_coverage')
    self.shared_state.update_batch(dict(traffic=traffic,maneuver_traffic_capture=capture,
        traffic_light=light,traffic_light_detected=detected,traffic_light_relevance=signal.get('relevance'),
        traffic_light_coverage=signal.get('coverage'),traffic_light_selection_reason=signal.get('reason'),
        traffic_brake=brake,light_brake=self._light_brake(light),traffic_snapshot_valid=available,
        traffic_snapshot_timestamp=stamp,traffic_snapshot_failure='' if available else 'ETS2LA traffic shared-memory buffer unavailable'))
    observed=dict(schema_version=1,sdk_frame_us=truck['sdkFrameTimeUs'],observed_at=stamp,valid=bool(truck.get('pose_valid')))
    return publish(self.shared_state,{**truck,'_control_observation':observed},'traffic',binding=binding,
        evidence_valid=bool(available or light is not None),traffic_available=available,
        traffic_brake=brake,light_brake=self._light_brake(light),light=light,signal=signal,
        lead_distance=self.shared_state.get('lead_distance'),following=following,
        display_detection=dict(status='DETECTED_ONLY_UNTIMED',candidate=None),
        brake_basis=self._traffic_brake_basis,dependencies=following.get('deadline_dependencies',()),
        expires_at=following.get('expires_at',float('inf')))


def run(samples,baseline=None,baseline_longitudinal=None):
    generator=flow.__wrapped__()
    source=next(generator)
    patches=[]
    if baseline:
        patches=[patch.object(acc_following,'observation',baseline.observation),
                 patch.object(acc_following,'RouteLeadSelector',baseline.RouteLeadSelector)]
        patches.extend(patch.object(longitudinal,name,getattr(baseline_longitudinal,name))
            for name in ('read','traffic_required','engine_decision'))
    for p in patches:p.start()
    try:
        values=setup_route(source,0)
        state,truck,engine,ap,tick,n,clock,writes,collected=values
        if baseline: engine._publish_traffic_control=baseline_publish.__get__(engine)
        actors=[forward_actor(values,lateral=10.+i,actor_id=i+1) for i in range(40)]
        reads={}
        def count(key):reads[key]=reads.get(key,0)+1
        costs=[]; mapped=[]
        for i in range(samples):
            source[4](4,40/3.6,dt=.05)
            state.hook=count
            started=time.perf_counter()
            produce(values,actors)
            costs.append(time.perf_counter()-started)
            state.hook=None
            assert state.get('autopilot_active'),state.get('automatic_safety_stop_reason')
            mapped.append(engine.controller.scs._buf.getvalue())
            # Never count the test backend's unbounded assertion history as
            # retained runtime collector storage.
            writes.clear();collected.samples.clear()
        journal=engine.controller._pedal_journal
        retained=dict(detail_bytes=journal._bytes,detail_budget=journal.MAX_BYTES,
            history_bytes=sum(journal._history.bytes.values())+journal._history.identity_bytes,
            history_budget=journal._history.MAX_BYTES if hasattr(journal._history,'MAX_BYTES') else 1048576)
        return dict(cost=stats(costs),reads=reads,mapped=mapped,retained=retained)
    finally:
        for p in reversed(patches):p.stop()
        try:next(generator)
        except StopIteration:pass
        gc.collect()


def main():
    p=argparse.ArgumentParser();p.add_argument('--samples',type=int,default=1200)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if not 10<=a.samples<=3600:p.error('Use 10..3600 samples')
    if not a.output.resolve().is_relative_to(ROOT):p.error('Output must remain in workspace')
    baseline=ModuleType('oct10_installed_actor_decoder')
    file=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot\core\acc_following.py')
    exec(compile(file.read_text(),str(file),'exec'),baseline.__dict__)
    old_longitudinal=ModuleType('oct10_installed_longitudinal')
    sys.modules[old_longitudinal.__name__]=old_longitudinal
    file=file.parent/'longitudinal.py'
    exec(compile(file.read_text(),str(file),'exec'),old_longitudinal.__dict__)
    old,new=run(a.samples,baseline,old_longitudinal),run(a.samples)
    result=dict(samples=a.samples,modeled_duration_s=a.samples*.05,
        limitation=__doc__, baseline=old['cost'],candidate=new['cost'],
        increment_ms={k:new['cost'][k]-old['cost'][k] for k in ('p50_ms','p95_ms','p99_ms','max_ms')},
        mapped_outputs_identical=old['mapped']==new['mapped'],ipc_reads_identical=old['reads']==new['reads'],
        baseline_retained=old['retained'],candidate_retained=new['retained'])
    a.output.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
    return 0 if result['mapped_outputs_identical'] and result['ipc_reads_identical'] else 1

if __name__=='__main__':raise SystemExit(main())
