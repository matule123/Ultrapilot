"""Measure Phase 7.1 publication/guard operations, without a game/backend.

This is not a vehicle-comfort or end-to-end control-loop benchmark.
"""
import argparse
import json
import math
import multiprocessing as mp
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.ipc.shared_state import SharedState
from core.longitudinal import context, engine_decision, finalize, publish


def stats(values):
    values = sorted(values)
    def percentile(p):
        return values[max(0, math.ceil(p * len(values)) - 1)] * 1000
    return {"samples": len(values), "median_ms": percentile(.5),
            "p95_ms": percentile(.95), "p99_ms": percentile(.99),
            "max_ms": max(values) * 1000}


def run(raw, samples):
    state = SharedState(raw)
    state.update_batch({"telemetry_control_schema": 1,
        "autopilot_failure_epoch": 1, "game_session_id": "offline",
        "active_map_key": "offline", "active_dataset_fingerprint": "offline",
        "navigation_intent_id": "intent", "lane_trajectory_revision": 1,
        "lane_trajectory": {"revision": 1, "route_build_id": "build",
            "points": [[i, 0] for i in range(10000)]}})
    phases = {key: [] for key in ("producer_publication", "autopilot_publication",
                                  "engine_arbitration", "combined_operations")}
    for i in range(samples):
        t0 = time.perf_counter()
        observed_at = time.monotonic()
        truck = {"speed": 10., "gear": 5, "sdkFrameTimeUs": i + 1,
            "_control_observation": {"schema_version": 1, "sdk_frame_us": i + 1,
                "valid": True, "observed_at": observed_at}}
        binding = context(state)
        publish(state, truck, "traffic", binding=binding, traffic_brake=0.,
                light_brake=0., light=None, lead_distance=None)
        publish(state, truck, "road", binding=binding, speed_cap_kmh=90.)
        publish(state, truck, "policy", binding=binding, planned_speed_ms=25., brake=0.)
        t1 = time.perf_counter()
        finalize(state, truck, .3, 0., {"source": "acc"}, binding)
        t2 = time.perf_counter()
        result, reason = engine_decision(state, truck)
        assert not reason and result["throttle"] == .3 and result["brake"] == 0, reason
        t3 = time.perf_counter()
        for key, elapsed in zip(phases, (t1-t0, t2-t1, t3-t2, t3-t0)):
            phases[key].append(elapsed)
    return {key: stats(values) for key, values in phases.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=500)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 10 <= args.samples <= 10000:
        parser.error("samples must be between 10 and 10000")
    result = {"limitation": "Operation costs only; no plant, game, physical writes or scheduling.",
              "lane_points": 10000, "direct": run({}, args.samples)}
    with mp.Manager() as manager:
        result["manager_ipc"] = run(manager.dict(), args.samples)
    encoded = json.dumps(result, indent=2, allow_nan=False)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    mp.freeze_support()
    main()
