"""Production source audit for Phase 5D; it never promotes legacy estimates."""
from __future__ import annotations

import time

from core.navigation.drivable_surface import DrivableSurfaceSnapshot
from core.navigation.maneuver_integration import GroundReferenceEvidence
from core.navigation.maneuver_traffic import TrafficSnapshot
from core.vehicle_profile import VehicleProfile


def production_data_availability(state, traffic_reader=None, settings=None,
                                 now=None):
    """Describe what the running process actually has for maneuver authority.

    The ordinary ETS2LA traffic list remains useful to ACC and the HUD.  Its
    connection status is reported separately because that ABI has no complete
    coverage/history/dimension proof and therefore cannot satisfy ``TrafficSnapshot``.
    """
    now = time.monotonic() if now is None else float(now)
    profile = state.get("vehicle_profile_snapshot")
    ground = state.get("maneuver_ground_reference")
    surface = state.get("maneuver_drivable_surface")
    traffic = state.get("maneuver_traffic_snapshot")
    reader_connected = bool(
        traffic_reader is not None
        and getattr(traffic_reader, "_traffic_buf", None) is not None)
    vehicle_observation = bool(
        isinstance(profile, VehicleProfile)
        and profile.observation is not None
        and not profile.observation_failure)
    profile_confirmed = bool(
        isinstance(profile, VehicleProfile)
        and profile.model is not None
        and not profile.model_failure)
    ground_confirmed = isinstance(ground, GroundReferenceEvidence)
    surface_confirmed = bool(
        isinstance(surface, DrivableSurfaceSnapshot)
        and surface.surface is not None and not surface.failure_reason)
    traffic_confirmed = isinstance(traffic, TrafficSnapshot)
    configured_profiles = configured_surfaces = 0
    try:
        configured_profiles = len(((settings or {}).get(
            "vehicle_profiles", {}) or {}).get("profiles", ()) or ())
        configured_surfaces = len(((settings or {}).get(
            "drivable_surfaces", {}) or {}).get("surfaces", ()) or ())
    except (TypeError, AttributeError):
        configured_profiles = configured_surfaces = 0
    rows = {
        "traffic": {
            "legacy_reader_connected": reader_connected,
            "legacy_live_objects_available": bool(state.get("traffic", ()) or ()),
            "phase5d_evidence_available": traffic_confirmed,
            "failure_reason": ("" if traffic_confirmed else
                "MISSING_COMPLETE_TRAFFIC_HISTORY_COVERAGE_AND_BODY_PRODUCER"),
        },
        "vehicle_profile": {
            "sdk_observation_available": vehicle_observation,
            "configured_catalog_records": configured_profiles,
            "phase5d_evidence_available": profile_confirmed,
            "failure_reason": ("" if profile_confirmed else
                str(getattr(profile, "model_failure", "")
                    or "MISSING_CONFIRMED_BODY_PROFILE")),
        },
        "ground_reference": {
            "sdk_chassis_pose_available": bool(state.get(
                "vehicle_envelope_snapshot", {}) or {}),
            "phase5d_evidence_available": ground_confirmed,
            "failure_reason": ("" if ground_confirmed else
                "MISSING_FIXED_AXLE_GROUND_REFERENCE_PRODUCER"),
        },
        "drivable_surface": {
            "configured_catalog_records": configured_surfaces,
            "phase5d_evidence_available": surface_confirmed,
            "failure_reason": ("" if surface_confirmed else
                "MISSING_CONFIRMED_DRIVABLE_SURFACE_PRODUCER"),
        },
    }
    blockers = [row["failure_reason"] for row in rows.values()
                if row["failure_reason"]]
    return {
        "schema_version": 1,
        "computed_at": now,
        "runtime_activation_ready": not blockers,
        "blockers": blockers,
        "sources": rows,
    }
