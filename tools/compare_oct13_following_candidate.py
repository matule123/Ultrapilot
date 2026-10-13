"""Reproduce the rejected closing-reserve experiment; never deploy this law."""
import argparse
import inspect
import hashlib
import json
import math
from pathlib import Path
from unittest.mock import patch

import core.acc_following as following
from tools import run_acc_following_bench as bench

RETAINED=following.following_demand


def candidate(gap_m,lead_speed_mps,ego_speed_mps,*,include_brake=False):
    result=RETAINED(gap_m,lead_speed_mps,ego_speed_mps,include_brake=include_brake)
    closing=max(0.,ego_speed_mps-lead_speed_mps)
    result['speed_cap_mps']=max(0.,lead_speed_mps+
        (gap_m-result['desired_gap_m']-closing*closing/2.)/following.HEADWAY_S)
    return result


def run(case, use_candidate=False):
    original=bench.engine_decision;rows=[]
    def decision(state,truck,*args,**kwargs):
        result=original(state,truck,*args,**kwargs)
        if result[0] is not None:
            lead=(state.get('longitudinal_traffic') or {}).get('following') or {}
            rows.append(dict(at=truck['_control_observation']['observed_at'],
                speed=truck['speed'],throttle=result[0]['throttle'],brake=result[0]['brake'],
                gap=lead.get('gap_m'),lead_speed=lead.get('speed_mps')))
        return result
    with patch.object(following,'following_demand',candidate if use_candidate else RETAINED), \
            patch.object(bench,'engine_decision',decision):
        result=bench.simulate(case)
    modes=['brake' if r['brake']>0 else 'drive' for r in rows if r['brake']>0 or r['throttle']>0]
    acceleration=[]
    if not case.get('noise'):
        acceleration=[(b['at'],(b['speed']-a['speed'])/(b['at']-a['at']))
            for a,b in zip(rows,rows[1:]) if 0<b['at']-a['at']<=.5]
    jerk=[abs((b[1]-a[1])/(b[0]-a[0])) for a,b in zip(acceleration,acceleration[1:])]
    ttc=[r['gap']/(r['speed']-r['lead_speed']) for r in rows
        if r['gap'] is not None and r['lead_speed'] is not None and r['speed']-r['lead_speed']>.1]
    result.update(reference_point_min_ttc_s=min(ttc,default=None),
        pedal_mode_changes=sum(a!=b for a,b in zip(modes,modes[1:])),
        peak_sampled_model_deceleration_mps2=max((-a for _,a in acceleration),default=None),
        peak_sampled_model_jerk_mps3=max(jerk,default=None),
        acceleration_status='NOT MEASURED: noisy observation' if case.get('noise') else
            'Finite differences of exact synthetic plant speeds and original model times',
        physical_game_consumption_verified=False)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not args.output.resolve().is_relative_to(Path.cwd()/'docs/steering-audit'):
        raise ValueError('write only workspace analysis')
    result=dict(retained_law_sha256=hashlib.sha256(inspect.getsource(RETAINED).encode()).hexdigest(),
        candidate_retained=False,game_verified=False,cases={})
    args.output.parent.mkdir(parents=True,exist_ok=True)
    for case in bench.CASES:
        result['cases'][case['name']]=dict(before=run(case),after=run(case,True))
        args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(case['name'],json.dumps(result['cases'][case['name']]),flush=True)
