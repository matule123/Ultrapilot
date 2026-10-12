"""Paired actual traffic/pedal pipeline operation cost, not live cadence proof."""
import argparse
import ast
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core import acc_following,engine
from tools.benchmark_oct10_traffic_contract import run
from tools.verify_oct11_joint_baseline import module


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--samples',type=int,default=1200)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if not 10<=args.samples<=3600 or not args.output.resolve().is_relative_to(ROOT):
        p.error('10..3600 samples; output must be in workspace')
    baseline=json.loads((ROOT/'tests/fixtures/oct11-joint-original-functions.json').read_text(encoding='utf-8'))
    old=module('oct11_original_actors',baseline['files']['core/acc_following.py']['source'])
    namespace=dict(engine.__dict__)
    for source in baseline['files']['core/engine.py']['source'].values():
        exec(compile(ast.parse(source),'<frozen Engine>','exec'),namespace)
    with patch.object(acc_following,'observation',old.observation), \
            patch.object(acc_following,'RouteLeadSelector',old.RouteLeadSelector), \
            patch.object(engine.UltraPilotEngine,'_route_lead_observation',namespace['_route_lead_observation']), \
            patch.object(engine.UltraPilotEngine,'_flush_controls_unlocked',namespace['_flush_controls_unlocked']):
        before=run(args.samples)
    after=run(args.samples)
    result=dict(baseline=baseline['build'],samples=args.samples,modeled_duration_s=args.samples*.05,
        description='40 raw actors; actual decoder/selector/traffic publication/AP/Engine/SCS BytesIO; fixed inactive signal/lead constraints.',
        before_ms=before['cost'],after_ms=after['cost'],
        increment_ms={k:after['cost'][k]-before['cost'][k] for k in ('p50_ms','p95_ms','p99_ms','max_ms')},
        physical_mapping_identical=before['mapped']==after['mapped'],
        ipc_reads_identical=before['reads']==after['reads'],
        ipc_reads_before=before['reads'],ipc_reads_after=after['reads'],
        retained_before=before['retained'],retained_after=after['retained'],
        limitation='In-process copied IPC fixture, wall operation time; no CPU/scheduling/game input or end-to-end packet-cadence claim.')
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if not k.startswith('ipc_reads_') or k=='ipc_reads_identical'},indent=2))
    return 0 if result['physical_mapping_identical'] and result['ipc_reads_identical'] else 1


if __name__=='__main__':raise SystemExit(main())
