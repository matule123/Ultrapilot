"""Small paired closed-loop reference experiment, no production evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.navigation.trailer_guidance import (
    derived_lane_corridor, plan_hybrid_reference, reference_route,
)
from tests.trailer_guidance_cases import case, simulate


def run():
    output = {'synthetic': True, 'runtime_authorized': False,
              'clearance_scope': 'derived lane placement; not physical body clearance',
              'cases': {}, 'rejections': {}}
    for length, radius, speed, lag, delay, noise in (
            (5., 60., 5., .25, .05, False),
            (8., 83., 5., .32, .10, False),
            (11., 150., 8., .60, .15, True)):
        for sign in (-1., 1.):
            p, ident, model, _ = case(radius, sign, length)
            corridor = derived_lane_corridor(p, ident)
            started = time.monotonic()
            plan = plan_hybrid_reference(p, ident, model, corridor,
                initial_trailer_heading=p.points[0].heading, speed_mps=speed,
                actuator_response_s=lag, actuator_delay_s=delay)
            planning_s = time.monotonic()-started
            if not plan.accepted:
                raise RuntimeError(plan.failure_reason)
            started = time.monotonic()
            route = reference_route(plan, p, ident, model.configuration)
            preparation_s = time.monotonic()-started
            options = dict(speed=plan.design_speed_mps, lag=lag, delay=delay,
                           noise=noise, jitter=noise)
            before, _ = simulate(p, model, **options)
            after, _ = simulate(p, model, route, **options)
            comparative_pass = bool(
                before['completed'] and after['completed']
                and after['trailer_max_cte_m'] <= .85*before['trailer_max_cte_m']
                and after['steering_step'] <= before['steering_step']
                and after['exit_cab_cte_m'] <= before['exit_cab_cte_m']
                and after['exit_trailer_cte_m'] <= before['exit_trailer_cte_m']
                and after['heading_max_error_rad'] < .02
                and after['settling_time_s'] is not None
                and after['settling_time_s'] <= before['settling_time_s'])
            output['cases'][f'R{radius:g}_L{length:g}_{"left" if sign < 0 else "right"}'] = {
                'before': before, 'after': after,
                'closed_loop_comparative_pass': comparative_pass,
                'eligible_for_runtime': False,
                'input_speed_mps': speed,
                'design_speed_mps': plan.design_speed_mps,
                'lag_s': lag, 'delay_s': delay,
                'noise_and_jitter': noise,
                'planning_s': planning_s, 'route_preparation_s': preparation_s,
                'derived_placement_reserve_m': plan.minimum_axle_reserve_m,
                'maximum_reference_offset_m': plan.tractor_max_offset_m,
            }
    for name, request in (
            ('straight', case(sections=((0., 150.),))),
            ('s_bend', case(sections=((0., 40.), (1/83., 55.),
                                     (-1/83., 55.), (0., 75.)))),
            ('R35', case(35.)), ('R25', case(25.)),
            ('R18', case(18.))):
        p, ident, model, _ = request
        plan = plan_hybrid_reference(p, ident, model,
            derived_lane_corridor(p, ident),
            initial_trailer_heading=p.points[0].heading, speed_mps=3.)
        output['rejections'][name] = {
            'accepted': plan.accepted,
            'reason': plan.failure_reason,
            'handoff_before_m': plan.handoff_before_m,
        }
    output['source_hashes'] = {str(p): hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
        for p in map(Path, ('core/navigation/route.py', 'core/lateral_controller.py',
                          'core/steering_dynamics.py', 'core/navigation/trailer_guidance.py'))}
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT/'docs'/'steering-audit'):
        parser.error('Output must be in ignored docs/steering-audit')
    result = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
