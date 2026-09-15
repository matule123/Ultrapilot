"""Strict, portable Phase 5E body-profile and ground-calibration contracts.

The catalog contains authenticated measurement records.  It never guesses a
body from a model name and never grants runtime authority.  Candidate and
revoked records remain useful for review, but only one exact, confirmed and
non-revoked record can be selected for compilation by the bounded evidence
worker.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math

from core.swept_envelope import EnvelopeError, finite, require
from core.vehicle_profile import configuration_fingerprint, fixed_axle_geometry


BODY_PROFILE_FRAME = "SCS_ARTICLE_LOCAL_X_RIGHT_Y_UP_Z_BACK_FIXED_AXLE_V1"
BODY_PROFILE_UNITS = {"angle": "rad", "length": "m"}
PROFILE_STATES = frozenset(("candidate", "reviewed", "confirmed", "revoked"))
DIMENSIONS = ("width_m", "front_m", "rear_m", "hitch_front_m", "hitch_rear_m")
DIMENSION_METHODS = frozenset(("physical_measurement", "verified_game_collision_export"))
GROUND_CHANNEL_CONTRACT = "calibrated_fixed_axle_projection_v2"
GROUND_REFERENCE_FRAME = "ETS2_WORLD_FIXED_AXLE_GROUND"
MIN_GROUND_SAMPLES = 30


def _sha256(value):
    return (type(value) is str and len(value) == 64
            and all(char in "0123456789abcdef" for char in value))


def _strings(value, *, maximum=256):
    return (type(value) is list and len(value) <= maximum
            and all(type(item) is str and bool(item.strip()) for item in value))


def wheel_fingerprint(observation):
    value = [{"slot": article.slot, "id": article.vehicle_id,
              "wheels": [(wheel.index, wheel.position_m, wheel.radius_m,
                           wheel.steerable, wheel.simulated, wheel.powered,
                           wheel.liftable) for wheel in article.wheels]}
             for article in observation.articles if article.attached]
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode("utf-8")).hexdigest()


def validate_profile_payload(payload, observation=None, *, usable=False):
    """Validate the distributable profile schema and optional live binding."""
    require(type(payload) is dict and payload.get("kind") == "body_profile"
            and payload.get("schema_version") == 1
            and type(payload.get("schema_version")) is int,
            "INVALID_BODY_PROFILE_SCHEMA")
    state = payload.get("status")
    require(state in PROFILE_STATES, "INVALID_BODY_PROFILE_STATUS")
    require(payload.get("runtime_authorized") is False,
            "BODY_PROFILE_CANNOT_AUTHORIZE_RUNTIME")
    require(payload.get("reviewed") is (state != "candidate")
            and payload.get("confirmed") is (state == "confirmed"),
            "INCONSISTENT_BODY_PROFILE_LIFECYCLE")
    if state == "revoked":
        require(_sha256(payload.get("revokes_sha256"))
                and bool(payload.get("revocation_reason")),
                "INVALID_BODY_PROFILE_REVOCATION")
        require(not usable, "REVOKED_BODY_PROFILE")
        return
    if usable:
        require(state == "confirmed",
                "BODY_PROFILE_NOT_CONFIRMED")
    require(payload.get("units") == BODY_PROFILE_UNITS,
            "UNSUPPORTED_BODY_PROFILE_UNITS")
    require(payload.get("coordinate_frame") == BODY_PROFILE_FRAME,
            "UNSUPPORTED_BODY_PROFILE_FRAME")
    require(_sha256(payload.get("configuration_fingerprint"))
            and _sha256(payload.get("wheel_fingerprint"))
            and _sha256(payload.get("accessory_fingerprint"))
            and _sha256(payload.get("mod_fingerprint"))
            and payload.get("accessory_inventory_complete") is True,
            "UNPROVEN_FULL_ACCESSORY_CONFIGURATION")
    require(bool(payload.get("cabin_configuration"))
            and bool(payload.get("chassis_configuration")),
            "MISSING_CABIN_OR_CHASSIS_IDENTITY")
    articles = payload.get("article_ids")
    slots = payload.get("article_slots")
    require(_strings(articles, maximum=5) and type(slots) is list
            and 1 <= len(slots) == len(articles) <= 5
            and all(type(slot) is int for slot in slots),
            "INVALID_BODY_PROFILE_ARTICLES")
    compatibility = payload.get("compatibility")
    require(type(compatibility) is dict and compatibility.get("game_id") == "ets2"
            and type(compatibility.get("sdk_game_version")) is list
            and compatibility["sdk_game_version"]
            and all(type(value) is int and value >= 0
                    for value in compatibility["sdk_game_version"])
            and _strings(compatibility.get("compatible_game_builds"), maximum=64),
            "INVALID_BODY_PROFILE_COMPATIBILITY")
    provenance = payload.get("provenance")
    hashes = {row.get("sha256") for row in payload.get("measurements", ())
              if type(row) is dict}
    require(type(provenance) is dict
            and provenance.get("source_kind") in DIMENSION_METHODS
            and _sha256(provenance.get("source_sha256"))
            and provenance["source_sha256"] in hashes
            and bool(provenance.get("license"))
            and provenance.get("distribution") in (
                "redistributable", "measurement_metadata_only",
                "reference_only_no_redistribution"),
            "INVALID_BODY_PROFILE_PROVENANCE")
    entry = payload.get("catalog_entry")
    bodies = entry.get("bodies") if type(entry) is dict else None
    require(type(bodies) is list and len(bodies) == len(articles),
            "MISSING_ARTICLE_BODY_PROFILE")
    for body, slot in zip(bodies, slots):
        require(type(body) is dict and body.get("slot") == slot,
                "BODY_PROFILE_SLOT_MISMATCH")
        require(body.get("axle_model") == "fixed_axle",
                "UNSUPPORTED_AXLE_MODEL")
        values = [body.get(name) for name in DIMENSIONS]
        require(all(finite(value) for value in values)
                and 0 < values[0] <= 5 and 0 < values[1] <= 25
                and 0 <= values[2] <= 15,
                "INVALID_BODY_PROFILE_DIMENSIONS")
        require(type(body.get("fixed_axle_local_m")) is list
                and len(body["fixed_axle_local_m"]) == 3
                and all(finite(value) for value in body["fixed_axle_local_m"]),
                "INVALID_FIXED_AXLE_POSITION")
        errors = body.get("dimension_uncertainty_m")
        sources = body.get("dimension_provenance")
        require(type(errors) is dict and set(errors) == set(DIMENSIONS)
                and all(finite(value) and .0001 <= value <= .25
                        for value in errors.values()),
                "MISSING_DIMENSION_UNCERTAINTY")
        require(type(sources) is dict and set(sources) == set(DIMENSIONS),
                "MISSING_DIMENSION_PROVENANCE")
        for name in DIMENSIONS:
            source = sources[name]
            if name == "width_m":
                require(type(source) is dict
                        and source.get("method") != "sdk_wheel_track",
                        "WHEEL_TRACK_IS_NOT_BODY_WIDTH")
            require(type(source) is dict
                    and source.get("method") in DIMENSION_METHODS
                    and _sha256(source.get("source_sha256"))
                    and source["source_sha256"] in hashes,
                    "INVALID_DIMENSION_PROVENANCE")
        require(finite(body.get("body_width_without_mirrors_m"))
                and 0 < body["body_width_without_mirrors_m"] <= body.get("width_m", 0)
                and body.get("collision_width_components_complete") is True,
                "INCOMPLETE_COLLISION_BODY_WIDTH")
        height = body.get("body_height_m")
        require(height is None or finite(height) and 0 < height <= 10,
                "INVALID_OPTIONAL_BODY_HEIGHT")
        require(finite(body.get("axle_position_uncertainty_m"))
                and .0001 <= body["axle_position_uncertainty_m"] <= .25,
                "MISSING_AXLE_POSITION_UNCERTAINTY")
    sdk_geometry = payload.get("sdk_geometry")
    require(type(sdk_geometry) is dict
            and finite(sdk_geometry.get("wheelbase_m"))
            and finite(sdk_geometry.get("comparison_uncertainty_m"))
            and .0001 <= sdk_geometry["comparison_uncertainty_m"] <= .25
            and type(sdk_geometry.get("hitch_forward_m")) is list
            and len(sdk_geometry["hitch_forward_m"]) == len(articles)
            and all(finite(value) for value in sdk_geometry["hitch_forward_m"]),
            "INVALID_PROFILE_SDK_GEOMETRY")
    if observation is None:
        return
    attached = tuple(article for article in observation.articles if article.attached)
    require(payload["configuration_fingerprint"] == configuration_fingerprint(observation)
            and payload["wheel_fingerprint"] == wheel_fingerprint(observation)
            and articles == [article.vehicle_id for article in attached]
            and slots == [article.slot for article in attached]
            and compatibility["sdk_game_version"] == list(observation.game_version),
            "MEASURED_PROFILE_CONFIGURATION_MISMATCH")
    axles = tuple(fixed_axle_geometry(article) for article in attached)
    tolerance = sdk_geometry["comparison_uncertainty_m"]
    require(abs(sdk_geometry["wheelbase_m"] - axles[0].wheelbase_m) <= tolerance
            and all(abs(measured - axle.hook_forward_m) <= tolerance
                    for measured, axle in zip(sdk_geometry["hitch_forward_m"], axles)),
            "PROFILE_SDK_GEOMETRY_CONFLICT")


def validate_ground_calibration_payload(payload, profile_payload=None, *, usable=False):
    require(type(payload) is dict and payload.get("kind") == "ground_calibration"
            and payload.get("schema_version") == 1
            and payload.get("units") == BODY_PROFILE_UNITS,
            "INVALID_GROUND_CALIBRATION_SCHEMA")
    state = payload.get("status")
    require(state in PROFILE_STATES, "INVALID_GROUND_CALIBRATION_STATUS")
    require(payload.get("runtime_authorized") is False,
            "GROUND_CALIBRATION_CANNOT_AUTHORIZE_RUNTIME")
    require(payload.get("reviewed") is (state != "candidate")
            and payload.get("confirmed") is (state == "confirmed"),
            "INCONSISTENT_GROUND_CALIBRATION_LIFECYCLE")
    if usable:
        require(state == "confirmed",
                "GROUND_CALIBRATION_NOT_CONFIRMED")
    require(payload.get("channel_contract") == GROUND_CHANNEL_CONTRACT,
            "UNSUPPORTED_GROUND_CHANNEL_CONTRACT")
    require(payload.get("coordinate_frame") == GROUND_REFERENCE_FRAME,
            "UNSUPPORTED_GROUND_REFERENCE_FRAME")
    require(_sha256(payload.get("configuration_fingerprint"))
            and _sha256(payload.get("profile_artifact_sha256"))
            and _sha256(payload.get("support_surface_sha256")),
            "UNBOUND_GROUND_CALIBRATION")
    rows = payload.get("articles")
    require(type(rows) is list and 1 <= len(rows) <= 5,
            "MISSING_ARTICLE_GROUND_CALIBRATION")
    for row in rows:
        require(type(row) is dict and type(row.get("slot")) is int
                and type(row.get("axle_local_m")) is list
                and len(row["axle_local_m"]) == 3
                and all(finite(value) for value in row["axle_local_m"]),
                "INVALID_GROUND_AXLE_CALIBRATION")
        require(type(row.get("sample_count")) is int
                and type(row.get("independent_sample_count")) is int
                and row["sample_count"] >= row["independent_sample_count"] >= MIN_GROUND_SAMPLES,
                "INSUFFICIENT_INDEPENDENT_GROUND_SAMPLES")
        require(type(row.get("sdk_frame_us_range")) is list
                and len(row["sdk_frame_us_range"]) == 2
                and all(type(value) is int and value > 0 for value in row["sdk_frame_us_range"])
                and row["sdk_frame_us_range"][0] < row["sdk_frame_us_range"][1],
                "INVALID_GROUND_SAMPLE_RANGE")
        require(all(finite(row.get(name)) for name in (
                    "ground_y_offset_m", "reference_pitch_rad", "reference_roll_rad",
                    "pitch_residual_bound_rad", "roll_residual_bound_rad",
                    "calibration_residual_m", "position_uncertainty_m",
                    "support_height_tolerance_m")),
                "NONFINITE_GROUND_CALIBRATION")
        require(abs(row["reference_pitch_rad"]) + row["pitch_residual_bound_rad"] <= .01
                and abs(row["reference_roll_rad"]) + row["roll_residual_bound_rad"] <= .01
                and 0 <= row["pitch_residual_bound_rad"] <= .01
                and 0 <= row["roll_residual_bound_rad"] <= .01
                and 0 <= row["calibration_residual_m"] <= row["support_height_tolerance_m"]
                and .0001 <= row["support_height_tolerance_m"]
                <= row["position_uncertainty_m"] <= .25,
                "INVALID_GROUND_REFERENCE_UNCERTAINTY")
        x, y, z = row["axle_local_m"]
        # Runtime projects the calibrated axle onto a confirmed horizontal
        # support layer.  Cover the full 3-D displacement that this projection
        # omits, including static attitude and the entire axle lever arm.
        lever = math.sqrt(x*x + y*y + z*z)
        pitch = abs(row["reference_pitch_rad"]) + row["pitch_residual_bound_rad"]
        roll = abs(row["reference_roll_rad"]) + row["roll_residual_bound_rad"]
        tilt_bound = lever * (math.sin(pitch) + math.sin(roll))
        require(row["position_uncertainty_m"] + 1e-12
                >= row["support_height_tolerance_m"] + tilt_bound,
                "GROUND_UNCERTAINTY_OMITS_TILT")
    if profile_payload is not None:
        require(payload["configuration_fingerprint"]
                == profile_payload.get("configuration_fingerprint"),
                "GROUND_CALIBRATION_CONFIGURATION_MISMATCH")


@dataclass(frozen=True)
class BodyProfileCatalog:
    artifacts: tuple

    def __init__(self, artifacts):
        values = tuple(artifacts)
        require(1 <= len(values) <= 128, "INVALID_BODY_PROFILE_CATALOG_SIZE")
        object.__setattr__(self, "artifacts", values)

    def select(self, observation, configuration_evidence=None):
        revoked = {artifact.payload().get("revokes_sha256")
                   for artifact in self.artifacts
                   if artifact.payload().get("status") == "revoked"}
        matches = []
        for artifact in self.artifacts:
            payload = artifact.payload()
            if payload.get("status") != "confirmed" or artifact.sha256 in revoked:
                continue
            try:
                validate_profile_payload(payload, observation, usable=True)
            except EnvelopeError:
                continue
            if configuration_evidence is not None:
                expected = (("cabin_configuration", "cabin_configuration"),
                            ("chassis_configuration", "chassis_configuration"),
                            ("accessory_fingerprint", "accessory_fingerprint"),
                            ("mod_fingerprint", "mod_fingerprint"))
                if any(payload.get(left) != configuration_evidence.get(right)
                       for left, right in expected):
                    continue
            matches.append(artifact)
        require(matches, "MISSING_CONFIRMED_BODY_PROFILE")
        require(len(matches) == 1, "AMBIGUOUS_CONFIRMED_BODY_PROFILE")
        return matches[0]
