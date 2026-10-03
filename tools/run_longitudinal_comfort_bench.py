"""Closed-loop Phase 7.2 regression, not a calibrated ETS2 plant.

Uses real ACC, Autopilot pedal stages, paired publication and Engine arbitration.
No gear model or game/device I/O. Full launch/physical Engine writes are covered
separately by production-flow tests. Targets/grades/noise are seeded and identical.
"""
import argparse
from bisect import bisect_left
from collections import deque
import json
import math
from pathlib import Path
import random
import subprocess
import sys
import types
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.longitudinal import context, publish, finalize, engine_decision
from sdk.plugin_sdk import PluginSDK


def classes(ref=None):
    if ref is None:
        from plugins.acc.main import Plugin as ACC
        from plugins.autopilot.main import Plugin as Autopilot
        return ACC, Autopilot
    def source(path):
        return subprocess.check_output(["git", "show", f"{ref}:{path}"], cwd=ROOT).decode("utf-8")
    pid = types.ModuleType("offline_baseline_pid")
    exec(compile(source("core/pid.py"), "baseline/core/pid.py", "exec"), pid.__dict__)
    acc = types.ModuleType("offline_baseline_acc")
    acc.PID = pid.PID
    exec(compile(source("plugins/acc/main.py").replace("from core.pid import PID", ""),
                 "baseline/plugins/acc/main.py", "exec"), acc.__dict__)
    ap = types.ModuleType("offline_baseline_autopilot")
    exec(compile(source("plugins/autopilot/main.py"), "baseline/plugins/autopilot/main.py", "exec"), ap.__dict__)
    return acc.Plugin, ap.Plugin


CASES = [
    dict(name="launch_flat", initial=0., target=50., load=1., grade=0.),
    dict(name="steady_noise", initial=50., target=50., load=1., grade=0., noise=.12),
    dict(name="target_down_up", initial=60., target=60., load=1., grade=0., changes=[(20., 35.), (60., 55.)]),
    dict(name="curve_cap", initial=60., target=60., load=1., grade=0., cap=35., changes=[(20., 35.), (60., 60.)]),
    dict(name="acc_slowdown", initial=50., target=50., load=1., grade=0., traffic=.2, changes=[(20., 35.), (60., 50.)]),
    dict(name="uphill_heavy", initial=0., target=45., load=1.4, grade=.02),
    dict(name="downhill_light", initial=45., target=45., load=.7, grade=-.015),
    dict(name="downhill_braking", initial=30., target=30., load=1.4, grade=-.06),
    dict(name="load_change", initial=50., target=50., load=1., grade=0., load_change=True),
    dict(name="jitter_delay", initial=0., target=50., load=1.2, grade=.005, noise=.12, jitter=True, delay=.25),
    dict(name="eco", initial=0., target=50., load=1., grade=0., eco=True),
    dict(name="emergency", initial=25., target=60., load=1., grade=0., emergency=True),
]


def percentile(values, p):
    values = sorted(values)
    return values[max(0, math.ceil(len(values)*p)-1)] if values else None


def simulate(case, types_=None, *, keep_trace=False):
    ACC, AP = classes() if types_ is None else types_
    clock = [1000.]
    rng = random.Random(7201)
    values = dict(longitudinal_control_schema=1, telemetry_control_schema=1,
        autopilot_active=True, autopilot_failure_epoch=1, system_state="CRUISE",
        game_session_id="offline", active_map_key="offline", active_dataset_fingerprint="offline",
        navigation_intent_id="intent", lane_trajectory_revision=1,
        lane_trajectory_identity={"route_build_id": "build"}, acc_obey_limit=False)
    acc = ACC(PluginSDK(values, "acc"))
    ap = AP(PluginSDK(values, "autopilot"))
    speed = case["initial"] / 3.6
    engine_throttle = engine_brake = 0.
    actuator_throttle = actuator_brake = 0.
    delay = case.get("delay", .12)
    queue = deque()
    records = []
    t, frame = 0., 10000
    with patch("time.monotonic", side_effect=lambda: clock[0]):
        acc.on_start()
        ap.on_start()
        state = acc.sdk.shared_state
        while t < 130.:
            dt = rng.choice([.02, .04, .05, .08, .15]) if case.get("jitter") else .05
            # Advance the plant to the next SDK observation using PREVIOUS
            # writes. A command computed below cannot act on its own past dt.
            old_speed = speed
            load = (1.4 if t >= 40 else .7) if case.get("load_change") else case["load"]
            steps = math.ceil(dt/.01)
            for j in range(steps):
                h = dt / steps
                at = t + j*h
                while queue and queue[0][0] <= at:
                    _, engine_throttle, engine_brake = queue.popleft()
                alpha = 1. - math.exp(-h / .35)
                actuator_throttle += alpha*(engine_throttle-actuator_throttle)
                actuator_brake += alpha*(engine_brake-actuator_brake)
                acceleration = (2.2*actuator_throttle - 4.*actuator_brake) / load - .12 - .004*speed*speed - 9.81*case["grade"]
                speed = max(0., speed+acceleration*h)
            t += dt
            clock[0] += dt
            frame += round(dt * 1e6)
            target = case["target"]
            for at, changed in case.get("changes", []):
                if t >= at:
                    target = changed
            values["acc_target_speed"] = target
            observed_speed = max(0., speed + rng.gauss(0., case.get("noise", 0.) / 3.6))
            truck = dict(speed=observed_speed, speedLimit=0., gear=8, parkBrake=False,
                sdkFrameTimeUs=frame, _control_observation=dict(schema_version=1, valid=True,
                    sdk_frame_us=frame, observed_at=clock[0]))
            values["telemetry"] = {"truck": truck}
            traffic_brake = .95 if case.get("emergency") and 10. <= t < 12. else 0.
            if case.get("traffic") and 20. <= t < 24.:
                traffic_brake = case["traffic"]
            publish(state, truck, "traffic", traffic_brake=traffic_brake, light_brake=0., light=None)
            if case.get("cap"):
                publish(state, truck, "road", speed_cap_kmh=target)
            if case.get("eco"):
                publish(state, truck, "eco", smoothing=.15)
            acc.on_tick(dt)
            request = values["longitudinal_acc"]
            emergency = request["emergency"] or traffic_brake > .7
            brake = max(request["brake"], 1. if emergency else traffic_brake)
            ap._longitudinal_decision = dict(source="acc", reason="closed-loop speed demand", emergency=emergency)
            ap._set_brake(brake, min(dt, .1))
            ap._apply_throttle(request["throttle"] if brake == 0 else 0., min(dt, .1))
            finalize(state, truck, ap._last_throttle, ap._last_brake,
                     ap._longitudinal_decision, context(state))
            output, reason = engine_decision(state, truck)
            assert not reason, (case["name"], t, reason, request)
            assert output["throttle"] == 0 or output["brake"] == 0
            queue.append((t+delay, output["throttle"], output["brake"]))
            records.append(dict(t=t, dt=dt, speed_kmh=speed*3.6, target_kmh=target,
                error_kmh=speed*3.6-target, throttle=output["throttle"], brake=output["brake"],
                acceleration_mps2=(speed-old_speed)/dt,
                observation_age_s=clock[0]-output["observation_timestamp"],
                emergency=emergency))
    last_change = case.get("changes", [(0., 0.)])[-1][0]
    steady = [r for r in records if r["t"] >= max(80., last_change+20.)]
    # Overshoot after a downward step is measured separately from the pre-existing
    # speed error; overshoot below means launch/upward-target steady completion.
    start_final = next(i for i, r in enumerate(records) if r["t"] >= last_change)
    final = records[start_final:]
    settle = None
    times = [r["t"] for r in final]
    for i, row in enumerate(final):
        end = bisect_left(times, row["t"] + 5.)
        window = final[i:end+1]
        if end < len(final) and all(abs(r["error_kmh"]) <= 1. for r in window):
            settle = row["t"]-last_change
            break
    def reversals(rows):
        modes = [1 if r["throttle"] > .02 else -1 if r["brake"] > .02 else 0 for r in rows]
        nonzero = [m for m in modes if m]
        return sum(a != b for a, b in zip(nonzero, nonzero[1:]))
    rate = [(b["throttle"]-a["throttle"])/b["dt"] for a, b in zip(records, records[1:])]
    brake_rate = [(b["brake"]-a["brake"])/b["dt"] for a, b in zip(records, records[1:])]
    jerk = [(b["acceleration_mps2"]-a["acceleration_mps2"])/b["dt"] for a, b in zip(records, records[1:])]
    metric = dict(samples=len(records), duration_s=records[-1]["t"],
        rms_error_kmh=math.sqrt(sum(r["error_kmh"]**2 for r in records)/len(records)),
        time_weighted_rms_kmh=math.sqrt(sum(r["error_kmh"]**2*r["dt"] for r in records)/sum(r["dt"] for r in records)),
        max_abs_error_kmh=max(abs(r["error_kmh"]) for r in records),
        steady_rms_kmh=math.sqrt(sum(r["error_kmh"]**2 for r in steady)/len(steady)),
        final_target_overshoot_kmh=max(0., max(r["error_kmh"] for r in final)),
        settling_s=settle, steady_pedal_reversals=reversals(steady), pedal_reversals=reversals(records),
        max_throttle_rise_per_s=max(rate), max_abs_throttle_rate_per_s=max(map(abs, rate)),
        max_abs_brake_rate_per_s=max(map(abs, brake_rate)),
        max_throttle_step=max(abs(b["throttle"]-a["throttle"]) for a, b in zip(records, records[1:])),
        max_brake_step=max(abs(b["brake"]-a["brake"]) for a, b in zip(records, records[1:])),
        max_abs_model_acceleration_mps2=max(abs(r["acceleration_mps2"]) for r in records),
        p95_abs_model_jerk_mps3=percentile(list(map(abs, jerk)), .95),
        max_abs_model_jerk_mps3=max(map(abs, jerk)),
        max_observation_age_s=max(r["observation_age_s"] for r in records),
        emergency_reaction_s=next((0. for r in records if r["emergency"] and r["brake"] == 1), None))
    return (metric, records) if keep_trace else metric


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = dict(source_ref=args.ref or "working-tree", model="unvalidated explicit plant; see report",
                  cases={case["name"]: simulate(case, classes(args.ref)) for case in CASES})
    encoded = json.dumps(result, indent=2, allow_nan=False)
    if args.output:
        args.output.write_text(encoded+"\n", encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()
