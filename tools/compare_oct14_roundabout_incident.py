"""Same-input closed plant and whole production flow; never ETS2 measurement."""
import ast
import argparse
from collections import deque
from contextlib import contextmanager
import json
import math
from pathlib import Path
import subprocess
import sys
import statistics
from types import ModuleType, SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import pytest
from tests.test_activation_observation_binding import flow
from tests.lifecycle.test_joint_regressions import joint
from tests.lifecycle.test_longitudinal_completion import timed_step


@contextmanager
def frozen(before):
    with pytest.MonkeyPatch.context() as patch:
        if before:
            import core.engine as module
            source=lambda path:subprocess.check_output(['git','show','ef8ea9d:'+path],cwd=ROOT).decode('utf-8')
            for name in ('core.acc_following','core.acc_body_prediction'):
                old=ModuleType(name)
                exec(compile(source(name.replace('.','/')+'.py'),'frozen/'+name,'exec'),old.__dict__)
                patch.setitem(sys.modules,name,old)
            cls=next(n for n in ast.parse(source('core/engine.py')).body if isinstance(n,ast.ClassDef) and n.name=='UltraPilotEngine')
            for name in ('_traffic_control_observation','_route_crossing_brake'):
                fn=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name==name)
                ns=dict(module.__dict__)
                exec(compile(ast.Module(body=[fn],type_ignores=[]),'frozen/engine','exec'),ns)
                patch.setattr(module.UltraPilotEngine,name,ns[name])
        yield


def simulate(mode,before, duration=18.):
    with frozen(before):
        f=flow.__wrapped__(); source=next(f)
        g=joint.__wrapped__(source,SimpleNamespace(param=mode)); values=next(g)
        state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=values
        state.set('acc_target_speed',11.323*3.6)
        speed=11.323; z=15.; x=2.25-30.; car_v=30./5.3197876
        delay=deque([(0.,0.)]*3);act_drive=act_brake=0.
        rows=[]
        observed_overlaps=0
        try:
            for i in range(round(duration*30)):
                ego=[(2.25,10.,z,0.,0.,1.,0.,2.5,4.,6.)]
                actor=dict(id=42,x=x,y=10.,z=95.52834,yaw=-math.pi/2,speed=car_v)
                following=timed_step(values,[actor],generation=i+1,speed=speed,z=z,ego=ego)
                from core.acc_body_prediction import contact_interval
                a=dict(x=2.25,y=10.,z=z,yaw=0.,dimensions_whl=(2.5,4.,6.))
                b=dict(x=x,y=10.,z=95.52834,yaw=-math.pi/2,dimensions_whl=(2.,2.,4.))
                observed_overlaps+=contact_interval(a,b,(0.,0.),(0.,0.),0.) is not None
                drive=physical('aforward');brake=physical('abackward')
                rows.append(dict(t=i/30.,speed=speed,z=z,actor_x=x,
                    throttle=drive,brake=brake,hold=bool(engine._service_brake_hold),
                    active=state.get('autopilot_active'),intervention=state.get('autopilot_intervention'),
                    traffic_brake=state.get('longitudinal_traffic')['traffic_brake'],
                    crossing=following.get('crossing'),body=following.get('body_prediction'),
                    acc_reason=state.get('longitudinal_acc').get('reason'),
                    motion_constraint=following.get('motion_constraint'),departure=following.get('departure')))
                delay.append((drive,brake));desired_drive,desired_brake=delay.popleft()
                for _ in range(4):
                    dt=1./120.
                    act_drive+=(desired_drive-act_drive)*dt/.35
                    act_brake+=(desired_brake-act_brake)*dt/.35
                    a=2.2*act_drive-4.*act_brake-(.12+.004*speed*speed)
                    speed=max(0.,speed+a*dt);z+=speed*dt;x+=car_v*dt
                writes.clear()
            def mode_of(r):return 'brake' if r['brake']>0 else 'drive' if r['throttle']>0 else 'coast'
            modes=[mode_of(r) for r in rows]; changes=sum(a!=b for a,b in zip(modes,modes[1:]))
            signed=[1 if r['throttle']>.01 else -1 if r['brake']>.01 else 0 for r in rows]
            nonzero=[v for v in signed if v]
            acceleration=[(b['speed']-a['speed'])*30. for a,b in zip(rows,rows[1:])]
            jerk=[(b-a)*30. for a,b in zip(acceleration,acceleration[1:])]
            return dict(mode=mode,before=before,samples=len(rows),duration_s=duration,
                hold_samples=sum(r['hold'] for r in rows),standstill_samples=sum(r['speed']<.05 for r in rows),
                minimum_speed_mps=min(r['speed'] for r in rows),final_speed_mps=rows[-1]['speed'],
                emergency_samples=sum((r['intervention'] or {}).get('kind')=='emergency' for r in rows),
                inactive_samples=sum(not r['active'] for r in rows),pedal_mode_changes=changes,
                simultaneous_pedals=sum(r['throttle']>0 and r['brake']>0 for r in rows),
                observed_box_overlap_samples=observed_overlaps,
                drive_brake_reversals=sum(a!=b for a,b in zip(nonzero,nonzero[1:])),
                maximum_model_deceleration_mps2=max(0.,-min(acceleration)),
                maximum_model_jerk_mps3=max(map(abs,jerk)),
                # Measured model box/reference separation at source poses;
                # it is not a validated continuous-game collision certificate.
                minimum_center_separation_m=min(math.hypot(r['actor_x']-2.25,95.52834-r['z']) for r in rows),
                trace=rows)
        finally:
            for generator in (g,f):
                try:next(generator)
                except StopIteration:pass


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT/'docs/steering-audit') or args.output.exists():
        parser.error('Use a new workspace audit output; preserve existing results')
    result=dict(model='30 Hz actual pipeline, .10 s pedal delay, .35 s actuator, 2.2/4 m/s2, quadratic drag; constant observed car motion',
        game_verified=False,cases=[simulate(mode,before) for mode in (0,3) for before in (True,False)])
    path=args.output
    path.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps([{k:v for k,v in c.items() if k!='trace'} for c in result['cases']],indent=2))
