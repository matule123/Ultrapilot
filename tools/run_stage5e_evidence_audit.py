"""Joint offline 5A–5E matrix and isolated evidence costs, never game approval."""
import argparse
import copy
from dataclasses import replace
import json
from pathlib import Path
import statistics
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.navigation.production_evidence import compile_measured_profile, bind_survey
from core.navigation.evidence_worker import ProductionEvidenceWorker, production_reference_rejection
from core.navigation.traffic_producer import LegacyTrafficProducer, TrafficCapture, CompleteTrafficProducer
from core.navigation.maneuver_reference import ManeuverReferenceMux, build_prepared_reference_packet, build_local_reference_packet
from core.navigation.maneuver_runtime import ManeuverRuntime
from core.navigation.route import Route
from core.sdk.ets2la_data import _TRAFFIC_SIZE, _PARKED_SIZE
from plugins.autopilot.main import maneuver_reference_rejection_reason
from tests.test_stage5e_production_evidence import measured_profile, survey_artifact, traffic_artifact, bundle
from tests.test_stage5b1_vehicle_profile import observation
from tests.maneuver_runtime_cases import runtime_request, live_state, clear_traffic
from tools.run_stage5a_envelope_bench import scenario
from tools.run_stage5d_runtime_audit import run_case
from tools.run_stage5c_integration_audit import mod_ger_63_case


def measure(operation, count=20):
    samples=[]
    for _ in range(count):
        start=time.perf_counter(); operation(); samples.append(time.perf_counter()-start)
    ordered=sorted(samples)
    return {'n':count,'median_s':statistics.median(samples),
            'p95_s':ordered[min(count-1,int(.95*count))], 'max_s':max(samples)}


def run():
    o=observation(); profile_artifact=measured_profile(o); request=runtime_request()
    c=request.result.context; survey=survey_artifact(request)
    capture=TrafficCapture('test-only',10.,bytes(_TRAFFIC_SIZE),bytes(_PARKED_SIZE),True)
    legacy=LegacyTrafficProducer(); complete=CompleteTrafficProducer(); traffic=traffic_artifact(request)
    worker=ProductionEvidenceWorker(clock=lambda:10.)
    metrics={
        'profile_load_compile':measure(lambda:compile_measured_profile(profile_artifact,o)),
        'surface_lookup':measure(lambda:bind_survey(survey,c.local_lane_path,c.identity)),
        'legacy_traffic_snapshot':measure(lambda:legacy.produce(capture,10.)),
        'confirmed_traffic_import':measure(lambda:complete.produce(traffic,c.identity,10.)),
        'unconfigured_evidence_worker':measure(lambda:worker._produce(None,None,{},None,None,None,1,None)),
    }
    worker.close()
    # Real transforms cannot be timed as successful production work: the SDK
    # lacks atomic contact frames. Time the exact fail-closed check separately.
    from core.navigation.production_evidence import GroundReferenceProducer
    from core.swept_envelope import EnvelopeError
    prof=compile_measured_profile(profile_artifact,o).update(o,10.)
    measured_surface=bundle(request).surface
    def ground_rejection():
        try: GroundReferenceProducer().produce(prof,c.identity,measured_surface,None,10.)
        except EnvelopeError: pass
    metrics['ground_missing_calibration_rejection']=measure(ground_rejection)
    b=bundle(request)
    state={'maneuver_production_evidence':b.lease(),'vehicle_profile_snapshot':request.profile}
    packet={'plan_token':b.plan_token,'production_evidence_receipt':b.receipt}
    metrics['production_receipt_consumer']=measure(lambda:production_reference_rejection(
        state,request.snapshot,packet,1_000_000,10.),1000)
    # Consumer timings are Python in-process costs, not Windows process IPC.
    runtime=ManeuverRuntime(request); live=live_state(runtime); t=clear_traffic(c.identity)
    decision=runtime.update(live,t,enter=True)
    prepared=build_prepared_reference_packet(runtime,1,9.)
    execution=build_local_reference_packet(runtime,decision,live,t,2,prepared)
    snapshot=dict(request.snapshot,lane_path_fingerprint=c.full_lane_path_fingerprint)
    mux=ManeuverReferenceMux(); mux.offer(prepared,snapshot); mux._future.result(); mux.offer(prepared,snapshot)
    route=Route(snapshot['points']); pose=live.ground.frame.poses[0]
    def consume():
        execution['sequence']+=1
        result=mux.select(route,snapshot,execution,(pose.x,pose.z),pose.heading,10.,1_000_000,True)
        assert result.authority_valid
    metrics['map_reference_consumption_inprocess']=measure(consume,100)
    mux.close()
    metrics['autopilot_production_rejection_inprocess']=measure(lambda:maneuver_reference_rejection_reason(
        {'maneuver_production_guard_required':True},snapshot,{'reference_mode':'local_maneuver'},10.),1000)
    envelope=[scenario(radius,right,length,2.6 if length==10. else 2.5)
              for radius in (18.,22.,25.,35.) for right in (False,True) for length in (0.,6.,8.,10.)]
    runtime_cases=[run_case(right,trailers,kind) for kind in ('prefab','roundabout','merge','split')
                   for trailers in (0,1) for right in (False,True)]
    return {'scope':'synthetic fixtures only; no production certificate or activation',
        'verdict':'BLOCKED BY MISSING REAL EVIDENCE','latencies':metrics,
        'envelope_cases':envelope,'runtime_cases':runtime_cases,'mod_ger_63':mod_ger_63_case(),
        'successful_production_ground_transform':None,'measured_game_tracking':None,
        'game_ipc_latency':None}


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--output',required=True)
    args=parser.parse_args(); path=Path(args.output).resolve()
    if not path.is_relative_to(ROOT): parser.error('Output must remain in repository')
    value=run(); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(path)


if __name__=='__main__': main()
