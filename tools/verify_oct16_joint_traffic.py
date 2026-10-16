"""Paired Oct 16 red-stop plant, exact Git baseline methods; never opens ETS2.

Uses the existing native signal -> Policy -> ACC -> Autopilot -> real Controller
and chronological BytesIO backend. Plant is explicitly uncalibrated: 2.2 m/s²
drive gain, 4 m/s² brake gain / mass ratio, .12 s input delay, first-order
actuators, drag .12+.004*v². Jerk is a MODEL derivative, not measured ETS2 jerk.
"""
import argparse
import ast
from contextlib import ExitStack
import hashlib
import itertools
import json
import math
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

from core.longitudinal import publish
from plugins.acc import main as acc
from plugins.drivepolicy.main import Plugin as Policy
from tools import run_prefab_signal_bench as bench
from tools.audit_oct10_native_signal import placed_route
from tools.run_oct10_signal_timing_bench import snapshot

BASE='0ed435f9d05b499fc9ee2aad1d6d8638a4f2450f'
CRITERIA=dict(no_red_overrun=True,no_positive_overlap=True,no_hold_brake_zero=True,
    green_restart=True,reference_offset_m=5.,
    model_reference_stop_gap_m=[0.,1.5],
    purpose='Existing terminal zone; no target movement, no false completion, no new positive pulse from reset')


def crossing_cycles(count,mode):
    """Repeated actual acquisition/decision/backend cycles, not a physics model."""
    from tests.test_activation_observation_binding import flow
    from tests.test_oct11_joint_regressions import joint
    from tests.test_oct15_crossing_dev_hud import step,crossing
    gen=flow.__wrapped__();fixture=next(gen)
    source=joint.__wrapped__(fixture,SimpleNamespace(param=mode));values=next(source)
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=values
    try:
        for i in range(count):
            actor=crossing(at=32.,arrival=4.1)
            step(values,[actor],i*2+1)
            assert acc._followed_target and acc._following_kind=='crossing'
            step(values,[dict(actor,x=actor['x']+1.1,yaw=math.pi)],i*2+2)
            assert state.get('autopilot_active') and not acc._followed_target
            assert not acc._following_fault and not engine._service_brake_hold
        pair={'aforward':0.,'abackward':0.};overlap=0
        for at,channel,value in writes:
            if channel in pair:
                pair[channel]=value;overlap+=all(v>0 for v in pair.values())
        assert overlap==0
        return dict(mode=mode,completed_cycles=count,acquisitions=2*count,
            automatic_disables=0,positive_physical_overlap=overlap,backend_write_count=len(writes),
            limitation='Synthetic poses/native clocks through actual producers and test backend; not closed vehicle physics or ETS2')
    finally:source.close();gen.close()


def original_methods(stack):
    source=subprocess.check_output(['git','show',BASE+':plugins/acc/main.py']).decode()
    tree=ast.parse(source)
    for name in ('on_tick','_reset_control'):
        node=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name==name)
        namespace={}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'baseline/'+name,'exec'),vars(acc),namespace)
        stack.enter_context(patch.object(acc.Plugin,name,namespace[name]))
    return hashlib.sha256(source.encode()).hexdigest()


def run(directory,*,before,mode,speed,response,mass,external,late=False,approach=100.):
    count=[0]
    started=[False]
    with ExitStack() as stack:
        baseline_hash=original_methods(stack) if before else None
        stack.enter_context(patch.object(bench,'plan_for',side_effect=lambda net,path:placed_route(directory)[2]))
        original=Policy.on_tick
        def limited(self,dt):
            original(self,dt)
            state=self.sdk.shared_state
            current=state.get('longitudinal_acc') or {}
            phase=current.get('speed_control_reason')
            eligible=(phase=='signal distance coast' if late else phase=='signal distance service brake')
            if eligible:started[0]=True
            if external and count[0]<2 and started[0]:
                truck=state.get('telemetry')['truck']
                policy=state.get('longitudinal_policy')
                publish(state,truck,'policy',brake=.12,planned_speed_ms=policy['planned_speed_ms'])
                count[0]+=1
        stack.enter_context(patch.object(Policy,'on_tick',limited))
        result=bench.run(directory,mode=mode,speed_kmh=speed,approach=approach,jitter=True,
            path_factory=placed_route,snapshot_factory=snapshot,observer_y=6.90234375,
            brake_response_s=response,mass_ratio=mass)
    red=[r for r in result['rows'] if r['red']]
    first=next((i for i,r in enumerate(red) if r['brake']>0),len(red))
    modes=[1 if r['throttle']>0 else -1 if r['brake']>0 else 0 for r in red[first:]]
    nonzero=[v for v in modes if v]
    result.update(injected_policy_ticks=count[0],baseline_source_sha256=baseline_hash,
        red_drive_samples_after_first_brake=sum(v==1 for v in modes),
        red_pedal_reversals=sum(a!=b for a,b in zip(nonzero,nonzero[1:])))
    gap=result['stop']['reference_gap_to_target_m'] if result['stop'] else None
    result['criteria_pass']=bool(result['resumed_without_n'] and gap is not None and 0<=gap<=1.5
        and result['stop']['reference_offset_m']==5.
        and not any(result[k] for k in ('simultaneous_positive_physical_writes','red_entry_overrun_samples',
            'hold_brake_zero_count','parking_writes')))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--workdir',type=Path,required=True)
    p.add_argument('--late-intervention',action='store_true',help='Independent brake after the first distance-coast transition')
    p.add_argument('--distances',type=float,nargs='+',default=[100.])
    p.add_argument('--crossing-cycles',type=int,default=0)
    a=p.parse_args();a.workdir.mkdir(parents=True,exist_ok=True)
    if a.crossing_cycles:
        a.output.write_text(json.dumps(dict(rows=[crossing_cycles(a.crossing_cycles,m) for m in (0,3)]),indent=2),encoding='utf-8')
        return
    results={}
    for approach,speed,mode,plant in itertools.product(a.distances,(20.,35.,50.),(0,3),((.15,.7),(.7,1.4))):
        response,mass=plant
        name=f'{approach:g}m-{speed:g}-{mode}-{response}-{mass}'
        pair={}
        for before in (True,False):
            label='before' if before else 'after';path=a.workdir/(name+'-'+label+'.json')
            result=run(a.workdir,before=before,mode=mode,speed=speed,response=response,mass=mass,
                external=True,late=a.late_intervention,approach=approach)
            path.write_text(json.dumps(result),encoding='utf-8')
            pair[label]={k:v for k,v in result.items() if k not in ('rows','writes','captures')}
        results[name]=pair
        print(name,json.dumps(pair),flush=True)
    a.output.write_text(json.dumps(dict(baseline=BASE,criteria=CRITERIA,cases=results),indent=2),encoding='utf-8')


if __name__=='__main__':main()
