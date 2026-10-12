"""Oct 12 deployed-body counterfactual versus candidate on identical plants."""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.audit_oct11_stop_geometry import model_case
from tools.run_oct11_terminal_stop_bench import metrics


def saved(relative, name, globals_):
    record=json.loads((ROOT/'tests/fixtures/oct12-original-functions.json').read_text())
    namespace={}
    exec(compile(record[relative]['functions'][name], 'oct12-deployed/'+relative, 'exec'), globals_, namespace)
    return namespace[name]


def baseline(stack):
    from core import longitudinal
    from core import service_brake_hold
    from core.engine import UltraPilotEngine as Engine
    from plugins.acc.main import Plugin as ACC
    stack.enter_context(patch.object(longitudinal, 'signal_speed_control',
        saved('core/longitudinal.py','signal_speed_control',vars(longitudinal))))
    stack.enter_context(patch.object(Engine, '_light_brake',
        saved('core/engine.py','_light_brake',Engine._light_brake.__globals__)))
    stack.enter_context(patch.object(ACC, 'on_tick',
        saved('plugins/acc/main.py','on_tick',ACC.on_tick.__globals__)))
    stack.enter_context(patch.object(service_brake_hold, 'after_write',
        saved('core/service_brake_hold.py','after_write',vars(service_brake_hold))))


def compare(directory, *, speed=35., mode=0, curvature=0., plant=None):
    with ExitStack() as stack:
        baseline(stack)
        old=model_case(directory,speed=speed,mode=mode,approach_curvature=curvature,plant_options=plant)
    new=model_case(directory,speed=speed,mode=mode,approach_curvature=curvature,plant_options=plant)
    return metrics(old),metrics(new)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT/'docs/steering-audit'):
        raise ValueError('workspace analytical output only')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    rows={}
    cases=[(name,k,plant) for name,k,plant in (
        ('straight',0.,{}),('left',1./60.,{}),('right',-1./60.,{}),
        ('slow-loaded',0.,dict(brake_response_s=.6,input_delay_s=.22,mass_ratio=1.8)),
        ('idle-stress',0.,dict(idle_speed_mps=.92)))]
    for name,k,plant in cases:
        for speed in (20.,35.,50.):
            for mode in (0,3):
                label=f'{name}/{speed:g}/{mode}'
                before,after=compare(args.output.parent,speed=speed,mode=mode,curvature=k,plant=plant)
                rows[label]=dict(before=before,after=after,plant=plant,game_verified=False)
                args.output.write_text(json.dumps(rows,indent=2)+'\n',encoding='utf-8')
                print(label,'gap',before['gap_m'],'->',after['gap_m'],flush=True)


if __name__=='__main__': main()
