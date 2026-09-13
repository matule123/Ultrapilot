"""Reproducible Phase 5C authority-chain audit (no runtime controls)."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.navigation.maneuver_integration import (
    audit_prefab_transition, build_maneuver_route_context,
    prepare_maneuver, validate_integration_result,
)
from core.navigation.maneuver_planner import PlannerLimits
from tests.maneuver_cases import junction
from tests.test_service_prefab_diagnostics import ModGer63DiagnosticReplayTests
from tests.test_stage5c_maneuver_integration import (
    ground, profile, snapshot, surface_catalog, synthetic_network,
)


def integration_case(right, trailers, lane_type):
    vehicle, start, path, source_surface, _ = junction(
        right=right, trailers=trailers, half_width=3.5)
    middle = replace(
        path.segments[1], lane_type=lane_type,
        connector_curve_indices=path.segments[1].lane_id.connector_path)
    path = replace(path, segments=(path.segments[0], middle, path.segments[2]))
    route_snapshot = snapshot(path)
    network = synthetic_network(path)
    context = build_maneuver_route_context(network, path, route_snapshot, 1)
    catalog = surface_catalog(context, source_surface)
    current_profile = profile(vehicle)
    reference = ground(start, context.identity, current_profile.token)
    limits = PlannerLimits(max_candidates=9)
    started = time.perf_counter()
    result = prepare_maneuver(
        network, path, route_snapshot, 1, catalog,
        current_profile, current_profile, reference, 10.,
        current_profile.token, "synthetic accessory confirmation", limits)
    elapsed = time.perf_counter()-started
    stale_guard = (validate_integration_result(
        result, network, path, route_snapshot, 1, catalog,
        current_profile, reference, 10., limits) if result.accepted
        else "not_run")
    return {
        "direction": "right" if right else "left",
        "lane_type": lane_type,
        "article_count": len(vehicle.bodies),
        "accepted": result.accepted,
        "failure_reason": result.failure_reason,
        "runtime_authorized": result.runtime_authorized,
        "runtime_blockers": result.runtime_blockers,
        "connector_path": context.connector_proofs[0].connector_path,
        "source_segment_indices": context.source_segment_indices,
        "source_gps_pair_indices": context.source_gps_pair_indices,
        "speed_kmh": result.plan.speed_mps*3.6 if result.plan else None,
        "minimum_clearance_m": (
            result.plan.envelope.minimum_clearance_m
            if result.plan and result.plan.envelope else None),
        "samples": len(result.plan.samples) if result.plan else 0,
        "callback_validation": stale_guard,
        "elapsed_s": elapsed,
    }


def mod_ger_63_case():
    fixture = ModGer63DiagnosticReplayTests(methodName="runTest")
    fixture.setUp()
    result = audit_prefab_transition(
        fixture.net, fixture.source, fixture.required)
    return {
        "accepted": result.accepted,
        "failure_reason": result.failure_reason,
        "prefab_token": result.prefab_token,
        "available_connector": result.source_connector_path,
        "required_connector": result.required_connector_path,
        "available_output_descriptor_nodes":
            result.source_output_descriptor_nodes,
        "required_input_descriptor_nodes":
            result.required_input_descriptor_nodes,
        "direct_curve_edge": result.direct_curve_edge,
        "raw_endpoint_gap_m": result.gap_m,
        "vertical_residual_m": result.vertical_residual_m,
        "heading_residual_deg": result.heading_residual_deg,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT):
        parser.error("output must stay in the repository")
    cases = [integration_case(right, trailers, lane_type)
             for lane_type in ("prefab", "roundabout")
             for trailers in (0, 1)
             for right in (False, True)]
    result = {
        "scope": "offline Phase 5C integration; no traffic/control authority",
        "cases": cases,
        "mod_ger_63": mod_ger_63_case(),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
