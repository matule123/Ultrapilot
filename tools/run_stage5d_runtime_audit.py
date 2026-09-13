"""Offline 5D traffic/timing gate matrix. Does not start application or game."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from core.navigation.maneuver_runtime import ManeuverRuntime, decision_rejection_reason
from core.navigation.maneuver_reference import (
    _prepare, build_local_reference_packet, build_prepared_reference_packet,
)
from tests.maneuver_runtime_cases import runtime_request, live_state, clear_traffic, actor
from tools.run_stage5c_integration_audit import mod_ger_63_case


def run_case(right,trailers,lane_type):
    start=time.perf_counter()
    request=runtime_request(right,trailers,lane_type)
    runtime=ManeuverRuntime(request)
    prepare_elapsed=time.perf_counter()-start
    now=10.
    live=live_state(runtime,now)
    identity=request.result.context.identity
    traffic=clear_traffic(identity,now)
    start=time.perf_counter()
    blocked=runtime.update(live,clear_traffic(identity,now,(actor(now=now),)))
    blocked_elapsed=time.perf_counter()-start
    now=41.
    live=live_state(runtime,now)
    traffic=clear_traffic(identity,now)
    start=time.perf_counter()
    decision=runtime.update(live,traffic,enter=True)
    entry_elapsed=time.perf_counter()-start
    reason=decision_rejection_reason(decision,runtime,live,traffic)
    snapshot=dict(request.snapshot)
    snapshot['lane_path_fingerprint']=(
        request.result.context.full_lane_path_fingerprint)
    start=time.perf_counter()
    prepared=build_prepared_reference_packet(runtime,1,now-1.)
    prepared_packet_elapsed=time.perf_counter()-start
    start=time.perf_counter()
    prepared_route=_prepare(prepared,snapshot)
    route_prepare_elapsed=time.perf_counter()-start
    start=time.perf_counter()
    executing_packet=build_local_reference_packet(
        runtime,decision,live,traffic,2,prepared)
    execution_packet_elapsed=time.perf_counter()-start
    row={
        'lane_type':lane_type,'direction':'right' if right else 'left',
        'article_count':trailers+1,'geometric_plan_accepted':request.result.accepted,
        'blocked_state':blocked.state.value,'blocked_reason':blocked.failure_reason,
        'after_wait_state':decision.state.value,'after_wait_reason':decision.failure_reason,
        'synthetic_gate_authorized':decision.runtime_authorized,
        'runtime_reference_consumer_wired':True,
        'production_control_published':False,'consumer_rejection':reason,
        'geometric_clearance_m':request.result.plan.envelope.minimum_clearance_m,
        'clearance_after_tracking_reserve_m':getattr(runtime,'minimum_clearance_m',None),
        'tracking_corner_error_m':request.tracking.corner_error_m,
        'traffic_spatial_margin_m':decision.traffic.spatial_margin_m if decision.traffic else None,
        'traffic_temporal_margin_s':decision.traffic.temporal_margin_s if decision.traffic else None,
        'ramp_duration_s':runtime.timing.ramp_duration_s if runtime.timing else None,
        'duration_s':runtime.timing.times_s[-1]-now if runtime.timing else None,
        'prepare_elapsed_s':prepare_elapsed,
        'blocked_revalidation_elapsed_s':blocked_elapsed,
        'entry_revalidation_elapsed_s':entry_elapsed,
        'decision_compute_deadline_s':.1,
        'prepared_packet_elapsed_s':prepared_packet_elapsed,
        'route_worker_prepare_elapsed_s':route_prepare_elapsed,
        'execution_packet_elapsed_s':execution_packet_elapsed,
        'prepared_route_point_count':len(prepared_route.route),
        'prepared_geometry_sha256':prepared['geometry_sha256'],
        'execution_packet_point_count':len(executing_packet.get('points',())),
        'transitions':runtime.transitions,
    }
    assert blocked.state.value=='WAITING_FOR_TRAFFIC',row
    assert decision.runtime_authorized and not reason,row
    print(lane_type,trailers,right,'passed',flush=True)
    return row


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    output=args.output.resolve()
    if not output.is_relative_to(ROOT):parser.error('output must stay in repository')
    cases=[run_case(right,trailers,kind) for kind in ('prefab','roundabout','merge','split')
           for trailers in (0,1) for right in (False,True)]
    result={'scope':('synthetic evidence; production Map/Autopilot consumer is wired '
                     'but activation remains fail-closed without real producers'),
            'cases':cases,'mod_ger_63':mod_ger_63_case()}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(output)


if __name__=='__main__':main()
