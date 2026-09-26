"""Bounded, measurement-only preparation for real maneuver evidence.

The collector is deliberately outside every steering and planning decision.  A
local operator command can arm raw observation, but neither a completed sample
nor a successfully written file is confirmed evidence.  All JSON work runs on
the collector worker; the Engine boundary only offers one small immutable
capture without waiting.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import re
import tempfile
import threading
import time

from core.navigation.traffic_producer import LegacyTrafficProducer, TrafficCapture


SCHEMA_VERSION = 1
MAX_DIAGNOSTIC_SAMPLES = 3600
MAX_DIAGNOSTIC_FILE_BYTES = 32 * 1024 * 1024
MAX_DIAGNOSTIC_CHUNK_BYTES = 8 * 1024 * 1024
MAX_DIAGNOSTIC_CHUNK_RECORDS = 128
CHUNKABLE_DOCUMENT_FIELDS = {
    "automatic-observations.json": "samples",
    "ground-reference-candidate.json": "frames",
    "traffic-coverage-observations.json": "history",
    "tracking-samples-candidate.json": "samples",
}
DIAGNOSTIC_STATES = (
    "DISABLED", "ARMED", "COLLECTING", "SAMPLE_COMPLETE",
    "INSUFFICIENT_EVIDENCE", "READY_FOR_OFFLINE_REVIEW",
    "REJECTED_STALE", "CANCELLED",
)
COLLECTION_PURPOSES = (
    "cab_profile", "trailer_profile", "ground_reference", "traffic_coverage",
    "tracking_global", "survey_area", "combined",
)
IDENTITY_KEYS = (
    "navigation_intent_id", "route_build_id", "revision",
    "source_game_session_id", "source_map_key", "source_dataset_fingerprint",
)
_COLLECTION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")


def _utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _sealed(payload):
    value = dict(payload)
    value["integrity_sha256"] = hashlib.sha256(_canonical(value)).hexdigest()
    return value


def _verify_seal(value):
    if not isinstance(value, dict):
        return False
    expected = value.get("integrity_sha256")
    payload = dict(value)
    payload.pop("integrity_sha256", None)
    return (isinstance(expected, str)
            and hashlib.sha256(_canonical(payload)).hexdigest() == expected)


def read_json(path, *, max_bytes=MAX_DIAGNOSTIC_FILE_BYTES):
    path = Path(path)
    with path.open("rb") as stream:
        raw = stream.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError("DIAGNOSTIC_FILE_TOO_LARGE")
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("DUPLICATE_DIAGNOSTIC_JSON_KEY")
            value[key] = item
        return value
    return json.loads(raw, object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(
            ValueError("NONFINITE_DIAGNOSTIC_JSON")))


def atomic_json_write(path, value, *, replace=os.replace):
    """Replace one JSON file atomically; an interrupted write keeps its predecessor."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, ensure_ascii=False, indent=2,
                     allow_nan=False).encode("utf-8")
    if len(raw) > MAX_DIAGNOSTIC_FILE_BYTES:
        raise ValueError("DIAGNOSTIC_FILE_TOO_LARGE")
    temporary = None
    try:
        fd, temporary = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        replace(temporary, path)
        temporary = None
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def _json_size(value):
    return len(json.dumps(value, ensure_ascii=False, indent=2,
                          allow_nan=False).encode("utf-8"))


def _file_entry(path, **metadata):
    return {"name": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            **metadata}


def _write_candidate_document(stage, name, document, entries):
    """Write bounded files; retain the original record order and contents."""
    field = CHUNKABLE_DOCUMENT_FIELDS.get(name)
    records = document.get(field) if field else None
    if not isinstance(records, list):
        records = None
    if (records is None or (len(records) <= MAX_DIAGNOSTIC_CHUNK_RECORDS
                            and _json_size(document) <= MAX_DIAGNOSTIC_CHUNK_BYTES)):
        path = stage / name
        atomic_json_write(path, document)
        entries.append(_file_entry(path, role="document"))
        return False

    part_entries = []
    start = 0
    while start < len(records):
        stop = min(start + MAX_DIAGNOSTIC_CHUNK_RECORDS, len(records))
        while True:
            selected = records[start:stop]
            first, last = selected[0], selected[-1]
            chunk = _sealed({
                "schema_version": 2, "kind": "diagnostic_record_chunk",
                "parent_name": name, "record_field": field,
                "order": len(part_entries), "start_index": start,
                "sample_count": len(selected),
                "first_sdk_frame_us": (first.get("sdk_frame_us")
                                       if isinstance(first, dict) else None),
                "last_sdk_frame_us": (last.get("sdk_frame_us")
                                      if isinstance(last, dict) else None),
                "first_sequence": (first.get("sequence")
                                   if isinstance(first, dict) else None),
                "last_sequence": (last.get("sequence")
                                  if isinstance(last, dict) else None),
                "confirmed": False, "runtime_authorized": False,
                "records": selected,
            })
            if _json_size(chunk) <= MAX_DIAGNOSTIC_CHUNK_BYTES:
                break
            if stop - start == 1:
                raise ValueError("DIAGNOSTIC_EXPORT_SINGLE_RECORD_TOO_LARGE")
            stop = start + max(1, (stop - start) // 2)
        path = stage / f"{name[:-5]}.part-{len(part_entries):04d}.json"
        atomic_json_write(path, chunk)
        part_entries.append(_file_entry(path, role="chunk", parent_name=name,
            record_field=field, order=chunk["order"], start_index=start,
            sample_count=chunk["sample_count"],
            first_sdk_frame_us=chunk["first_sdk_frame_us"],
            last_sdk_frame_us=chunk["last_sdk_frame_us"],
            first_sequence=chunk["first_sequence"],
            last_sequence=chunk["last_sequence"]))
        start = stop

    header = dict(document)
    header.pop("integrity_sha256", None)
    header.pop(field)
    header.update({"chunked": True, "record_field": field,
                   "chunk_count": len(part_entries),
                   "chunk_sample_count": len(records)})
    path = stage / name
    atomic_json_write(path, _sealed(header))
    entries.append(_file_entry(path, role="index"))
    entries.extend(part_entries)
    return True


def _export_failure_reason(error):
    """Return a stable, non-sensitive diagnostic code, never an OS path."""
    if isinstance(error, ValueError):
        code = str(error)
        if code in ("DIAGNOSTIC_FILE_TOO_LARGE",
                    "DIAGNOSTIC_EXPORT_SINGLE_RECORD_TOO_LARGE",
                    "DIAGNOSTIC_COLLECTION_ALREADY_EXISTS"):
            return code
        return "DIAGNOSTIC_EXPORT_INVALID_CANDIDATE"
    if isinstance(error, (OSError, TypeError)):
        return "DIAGNOSTIC_EXPORT_WRITE_FAILED"
    return "DIAGNOSTIC_EXPORT_FAILED"


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _jsonable(value):
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(v) for v in value]
    if isinstance(value, bytes):
        return {"bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return str(value)


def _pick(value, keys):
    value = value if isinstance(value, dict) else {}
    return {key: _jsonable(value.get(key)) for key in keys}


@dataclass(frozen=True)
class DiagnosticCapture:
    sequence: int
    captured_at_s: float
    engine_steer: float | None
    backend_sent: bool
    autopilot_active: bool
    telemetry_valid: bool
    truck: dict
    profile: object
    traffic_capture: TrafficCapture | None
    lane: dict
    reference: dict
    applied_target: dict
    actuator_calibration: dict
    trailer_articulation_rad: float | None
    surface_token: object
    ground_reference: object
    steering_boundary: dict | None = None
    application_sdk_frame_us: int | None = None
    steering_write_returned_at_s: float | None = None


def capture_diagnostic_application(state, steering, now, sequence, *,
                                   steering_boundary=None,
                                   application_sdk_frame_us=None,
                                   steering_write_returned_at_s=None):
    """Take a bounded snapshot after the physical backend call returned."""
    telemetry = state.get("telemetry", {}) or {}
    truck = telemetry.get("truck", {}) or {}
    lane = state.get("lane_trajectory", {}) or {}
    applied = state.get("maneuver_diagnostic_applied_target", {}) or {}
    return DiagnosticCapture(
        int(sequence), float(now), (float(steering) if _finite(steering) else None),
        _finite(steering),
        bool(state.get("autopilot_active", False)),
        bool(state.get("telemetry_valid", False)),
        _pick(truck, ("sdkFrameTimeUs", "speed", "userSteer", "gameSteer", "rotation",
                      "x", "y", "z", "pose_valid", "roadWheelAnglesRad",
                      "yawRateRadS", "yawRateValid")),
        state.get("vehicle_profile_snapshot"),
        state.get("maneuver_traffic_capture"),
        _pick(lane, IDENTITY_KEYS + ("valid", "confidence", "active_lane_id",
              "source_gps_uids", "covered_gps_uids", "elevation_layer",
              "geometry_sha256", "failure_reason", "lane_match")),
        _pick(state.get("active_navigation_reference", {}) or {},
              ("mode", "authority_valid", "sequence", "plan_token", "binding",
               "geometry_hash", "computed_at", "valid_until") + IDENTITY_KEYS),
        _pick(applied, ("output", "raw", "rate", "acceleration",
              "executor_active", "target_fresh", "target_age_s",
              "submission_sequence", "execution_monotonic_s", "source_packet")),
        _pick(state.get("steering_actuator_calibration", {}) or {},
              ("schema_version", "tyre_angle_per_input_rad", "command_delay_s",
               "observation_delay_s", "source")),
        state.get("trailer_articulation"), state.get("maneuver_surface_token"),
        state.get("maneuver_ground_reference"),
        _pick(steering_boundary, ("backend_mode", "status", "value", "read_started_s",
                                  "read_completed_s")),
        application_sdk_frame_us, steering_write_returned_at_s,
    )


def _manual_value(name, allowed):
    return {"name": name, "value": None, "unit": "m",
            "allowed_range_m": list(allowed), "uncertainty_m": None,
            "uncertainty_allowed_range_m": [0.0001, 0.25], "source": None,
            "measured_at_utc": None, "schema_version": 1}


def _article_profile_templates(profile):
    observation = (profile or {}).get("observation", {}) if isinstance(profile, dict) else {}
    templates = []
    for article in observation.get("articles", ()) or ():
        if not article.get("attached"):
            continue
        slot = article.get("slot")
        names = (("width_m", (0.5, 4.0)), ("front_m", (0.0, 20.0)),
                 ("rear_m", (0.0, 20.0)),
                 ("reference_axle_position_m", (-20.0, 20.0)),
                 ("hitch_offset_m", (-20.0, 20.0)))
        if slot != -1:
            names += (("hitch_to_axle_group_m", (0.0, 30.0)),)
        templates.append({
            "slot": slot, "vehicle_id": article.get("vehicle_id"),
            "brand_id": article.get("brand_id"),
            "body_type": article.get("body_type"),
            "chain_type": article.get("chain_type"),
            "cargo_accessory_id": article.get("cargo_accessory_id"),
            "measurements": [_manual_value(name, allowed) for name, allowed in names],
        })
    return templates


def _identity(row):
    return tuple(row["lane"].get(key) for key in IDENTITY_KEYS)


def _finite_xyz(value):
    return (isinstance(value, (tuple, list)) and len(value) == 3
            and all(_finite(component) for component in value))


def _geometry_binding(row):
    profile = row.get("vehicle_profile") or {}
    token = profile.get("token") or {}
    return (token.get("producer_session"), token.get("generation"),
            token.get("configuration"))


def _navigation_binding(row):
    lane = row.get("lane") or {}
    return (tuple(lane.get(key) for key in IDENTITY_KEYS),
            json.dumps(row.get("lane_id"), sort_keys=True),
            lane.get("elevation_layer"))


def _trailer_geometry_reasons(row, previous_sdk_frame, previous_binding):
    """Check a passive SDK geometry frame without requiring any control write.

    The SDK read is stable but not atomic. Equal frame IDs only make the truck
    and trailer observations eligible for later independent offline review.
    """
    reasons = []
    frame = row["sdk_frame_us"]
    observation = (row.get("vehicle_profile") or {}).get("observation") or {}
    articles = observation.get("articles") or []
    trailer = next((article for article in articles if isinstance(article, dict)
                    and article.get("slot") == 0 and article.get("attached") is True), None)
    wheels = trailer.get("wheels") if trailer else None
    if (observation.get("source") != "scs_shared_memory_revision_12"
            or observation.get("failure_reason")
            or observation.get("stable_read") is not True
            or observation.get("active") is not True
            or observation.get("paused") is True
            or observation.get("sdk_frame_us") != frame
            or row.get("telemetry_valid") is not True
            or not _finite(observation.get("captured_at"))
            or not 0 <= row["captured_at_s"] - observation["captured_at"] <= 0.25):
        reasons.append("TRAILER_SDK_FRAME_STALE_OR_INCOHERENT")
    if previous_sdk_frame is not None and frame == previous_sdk_frame:
        reasons.append("DUPLICATE_SDK_FRAME")
    if (not _finite_xyz([row["truck"].get(axis) for axis in ("x", "y", "z")])
            or not _finite(row["truck"].get("rotation"))
            or row["truck"].get("pose_valid") is not True):
        reasons.append("TRACTOR_WORLD_POSE_MISSING")
    if (trailer is None or not isinstance(trailer.get("vehicle_id"), str)
            or not trailer.get("vehicle_id")
            or not _finite_xyz(trailer.get("position_m"))
            or not _finite_xyz(trailer.get("rotation_rad"))):
        reasons.append("TRAILER_SLOT_0_WORLD_POSE_MISSING")
    if (not isinstance(wheels, list) or len(wheels) < 2
            or not any(isinstance(wheel, dict) and wheel.get("on_ground") is True
                       for wheel in wheels)
            or any(not isinstance(wheel, dict)
                   or type(wheel.get("index")) is not int
                   or not _finite_xyz(wheel.get("position_m"))
                   or not _finite(wheel.get("radius_m"))
                   or not all(type(wheel.get(key)) is bool for key in
                              ("on_ground", "liftable", "steerable"))
                   or not _finite(wheel.get("lift"))
                   or not _finite(wheel.get("lift_offset_m"))
                   or not _finite(wheel.get("steering_right_rad"))
                   for wheel in (wheels or []))):
        reasons.append("TRAILER_SLOT_0_WHEELS_OR_CONTACT_MISSING")
    binding = _geometry_binding(row)
    if (not isinstance(binding[0], str) or not binding[0]
            or type(binding[1]) is not int or binding[1] <= 0
            or not isinstance(binding[2], str) or not binding[2]):
        reasons.append("CONFIGURATION_FINGERPRINT_MISSING")
    if previous_binding is not None and binding != previous_binding:
        reasons.append("TRAILER_CONFIGURATION_BINDING_CHANGED")
    return reasons


def _moving_command_reasons(row, geometry_reasons):
    """Check a moving backend write separately from parked trailer geometry."""
    reasons = []
    frame = row["sdk_frame_us"]
    if not _finite(row.get("speed_mps")) or abs(row["speed_mps"]) <= 0.5:
        reasons.append("MOVING_COMMAND_NOT_OBSERVED")
    if geometry_reasons:
        reasons.append("TRAILER_GEOMETRY_FRAME_NOT_ELIGIBLE")
    lane = row.get("lane") or {}
    source = (row.get("executor") or {}).get("source_packet") or {}
    if (lane.get("valid") is not True or not isinstance(row.get("lane_id"), dict)
            or not row["lane_id"] or not _finite(row.get("global_cte_m"))
            or not _finite(row.get("heading_error_rad"))
            or lane.get("elevation_layer") is None
            or any(lane.get(key) in (None, "") for key in IDENTITY_KEYS)
            or any(source.get(key) != lane.get(key) for key in IDENTITY_KEYS
                   if key != "revision")
            or source.get("authority_revision") != lane.get("revision")):
        reasons.append("NAVIGATION_LANE_IDENTITY_OR_CTE_MISSING")
    calculation_frame = row.get("calculation_sdk_frame_us")
    calculated_at = source.get("computed_at")
    executed_at = (row.get("executor") or {}).get("execution_monotonic_s")
    if (row.get("autopilot_active") is not True
            or not row.get("command_binding_proven")
            or type(calculation_frame) is not int or not 0 < calculation_frame <= frame
            or frame - calculation_frame > 250_000
            or not _finite(calculated_at) or not _finite(executed_at)
            or not 0 <= executed_at - calculated_at <= 0.25
            or type(row.get("calculation_sequence")) is not int
            or row["calculation_sequence"] <= 0
            or not _finite(row.get("steer_raw"))
            or not _finite(row.get("steer_out"))
            or not _finite(row.get("game_steer"))
            or not isinstance(row.get("tyre_angles_rad"), (list, tuple))
            or not row["tyre_angles_rad"]
            or not all(_finite(value) for value in row["tyre_angles_rad"])):
        reasons.append("CALCULATION_TO_APPLIED_COMMAND_BINDING_MISSING")
    return reasons


def _empty_trailer_preflight():
    return {"atomic": False, "latest_sdk_frame_us": None,
            "vehicle_stationary": None,
            "stationary_geometry_frames": 0,
            "consecutive_stationary_geometry_frames": 0,
            "stationary_geometry_ready": False,
            "latest_geometry_reasons": ["WAITING_FOR_SAMPLE"],
            "moving_command_frames": 0,
            "moving_command_binding_observed": False,
            "latest_command_reasons": ["WAITING_FOR_MOVING_COMMAND"],
            "replay_channels_observed": False,
            "replay_candidate_complete": False}


class EvidenceDiagnosticCollector:
    """One bounded queue and one writer for unqualified live observations."""

    def __init__(self, output_root, *, capacity=1800, max_sessions=8,
                 status_callback=None, clock=time.monotonic):
        if type(capacity) is not int or not 30 <= capacity <= MAX_DIAGNOSTIC_SAMPLES:
            raise ValueError("INVALID_DIAGNOSTIC_CAPACITY")
        if type(max_sessions) is not int or not 1 <= max_sessions <= 32:
            raise ValueError("INVALID_DIAGNOSTIC_SESSION_LIMIT")
        self.output_root = Path(output_root).resolve()
        if self.output_root.name != "evidence-diagnostics":
            raise ValueError("INVALID_DIAGNOSTIC_OUTPUT_DIRECTORY")
        self.capacity = capacity
        self.max_sessions = max_sessions
        self.status_callback = status_callback
        self.clock = clock
        self._rows = deque(maxlen=capacity)
        self._queue = queue.Queue(maxsize=1)
        self._traffic = LegacyTrafficProducer()
        self._state = "DISABLED"
        self._reason = "DIAGNOSTIC_MODE_DISABLED"
        self._collection_id = None
        self._purpose = None
        self._started_at = None
        self._max_duration_s = 180.0
        self._sample_period_s = 0.1
        self._next_sample_s = 0.0
        self._dropped = 0
        self._last_capture_s = None
        self._last_sdk_frame = None
        self._last_geometry_binding = None
        self._last_moving_navigation_binding = None
        self._trailer_preflight = _empty_trailer_preflight()
        self._last_command_sequence = 0
        self._stop = threading.Event()
        self._thread = None
        self._lock = threading.Lock()
        self._publish()

    @property
    def control_path(self):
        return self.output_root / "control.json"

    @property
    def status_path(self):
        return self.output_root / "status.json"

    @property
    def state(self):
        with self._lock:
            return self._state

    def status(self):
        with self._lock:
            state, reason = self._state, self._reason
            return {
                "schema_version": SCHEMA_VERSION, "state": state,
                "reason": reason, "collection_id": self._collection_id,
                "purpose": self._purpose, "sample_count": len(self._rows),
                "sample_period_s": self._sample_period_s,
                "dropped_samples": self._dropped,
                "capacity": self.capacity,
                "runtime_authorized": False, "confirmed": False,
                "accepting_samples": state in ("ARMED", "COLLECTING"),
                "trailer_preflight": dict(self._trailer_preflight),
            }

    def _publish(self):
        status = self.status()
        if self.status_callback is not None:
            self.status_callback(dict(status))
        try:
            atomic_json_write(self.status_path, _sealed(status))
        except OSError:
            pass

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run,
            name="UltraPilot-EvidenceDiagnostics", daemon=True)
        self._thread.start()

    def close(self, timeout=1.0):
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=max(0.0, float(timeout)))
        with self._lock:
            if self._state in ("ARMED", "COLLECTING"):
                self._rows.clear()
                self._state, self._reason = "CANCELLED", "APPLICATION_STOPPED_BEFORE_FINISH"
        self._publish()

    def should_sample(self, now):
        with self._lock:
            if self._state not in ("ARMED", "COLLECTING") or now < self._next_sample_s:
                return False
            self._next_sample_s = now + self._sample_period_s
            return True

    def offer(self, capture):
        if not isinstance(capture, DiagnosticCapture):
            return False
        try:
            self._queue.put_nowait(capture)
            return True
        except queue.Full:
            with self._lock:
                self._dropped += 1
            return False

    def apply_command(self, command):
        if not isinstance(command, dict) or command.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("INVALID_DIAGNOSTIC_COMMAND_SCHEMA")
        sequence = command.get("sequence")
        action = command.get("action")
        if type(sequence) is not int or sequence <= self._last_command_sequence:
            raise ValueError("STALE_DIAGNOSTIC_COMMAND")
        if action not in ("arm", "finish", "cancel", "disable"):
            raise ValueError("UNKNOWN_DIAGNOSTIC_COMMAND")
        collection_id = command.get("collection_id")
        if action == "arm":
            purpose = command.get("purpose")
            duration = command.get("max_duration_s")
            period = command.get("sample_period_s")
            if (not isinstance(collection_id, str) or not _COLLECTION_ID.fullmatch(collection_id)
                    or purpose not in COLLECTION_PURPOSES
                    or not _finite(duration) or not 30 <= duration <= 600
                    or not _finite(period) or not 0.05 <= period <= 0.5):
                raise ValueError("INVALID_DIAGNOSTIC_ARM_REQUEST")
            existing = ([p for p in self.output_root.iterdir() if p.is_dir()]
                        if self.output_root.exists() else [])
            if len(existing) >= self.max_sessions:
                raise ValueError("DIAGNOSTIC_SESSION_LIMIT_REACHED")
            if (self.output_root / collection_id).exists():
                raise ValueError("DIAGNOSTIC_COLLECTION_ALREADY_EXISTS")
            with self._lock:
                self._rows.clear()
                while not self._queue.empty():
                    try:
                        self._queue.get_nowait()
                    except queue.Empty:
                        break
                self._state, self._reason = "ARMED", "WAITING_FOR_FIRST_FRESH_SAMPLE"
                self._collection_id, self._purpose = collection_id, purpose
                self._started_at = self.clock()
                self._max_duration_s, self._sample_period_s = float(duration), float(period)
                self._next_sample_s = 0.0
                self._dropped = 0
                self._last_capture_s = self._last_sdk_frame = None
                self._last_geometry_binding = None
                self._last_moving_navigation_binding = None
                self._trailer_preflight = _empty_trailer_preflight()
        else:
            with self._lock:
                if (action != "disable" and collection_id != self._collection_id):
                    raise ValueError("DIAGNOSTIC_COLLECTION_MISMATCH")
            if action == "finish":
                self.finalize()
            elif action in ("cancel", "disable"):
                with self._lock:
                    self._rows.clear()
                    self._state = "CANCELLED" if action == "cancel" else "DISABLED"
                    self._reason = ("USER_CANCELLED_COLLECTION" if action == "cancel"
                                    else "DIAGNOSTIC_MODE_DISABLED")
        self._last_command_sequence = sequence
        self._publish()

    def _ingest(self, capture):
        profile = _jsonable(capture.profile) or {}
        sdk_frame = capture.truck.get("sdkFrameTimeUs")
        if (not _finite(capture.captured_at_s)
                or (self._last_capture_s is not None
                    and capture.captured_at_s <= self._last_capture_s)
                or type(sdk_frame) is not int or sdk_frame <= 0
                or (self._last_sdk_frame is not None and sdk_frame < self._last_sdk_frame)):
            with self._lock:
                self._state, self._reason = "REJECTED_STALE", "STALE_OR_REGRESSING_DIAGNOSTIC_FRAME"
            self._publish()
            return
        traffic = None
        if isinstance(capture.traffic_capture, TrafficCapture):
            try:
                traffic = _jsonable(self._traffic.produce(
                    capture.traffic_capture, capture.captured_at_s))
            except (ValueError, TypeError, OSError):
                traffic = {"status": "traffic_decode_failed", "complete": False,
                           "failure_reason": "MISSING_COMPLETE_TRAFFIC_HISTORY_COVERAGE_AND_BODY_PRODUCER"}
        source = capture.applied_target.get("source_packet") or {}
        lane_match = source.get("lane_match_snapshot") or capture.lane.get("lane_match") or {}
        executor_output = capture.applied_target.get("output")
        execution_time = capture.applied_target.get("execution_monotonic_s")
        command_bound = bool(
            capture.applied_target.get("executor_active")
            and capture.applied_target.get("target_fresh")
            and _finite(executor_output)
            and _finite(execution_time)
            and 0 <= capture.captured_at_s - execution_time <= 0.1
            and capture.backend_sent and _finite(capture.engine_steer)
            and abs(float(executor_output) - capture.engine_steer) <= 1e-12)
        row = {
            "schema_version": SCHEMA_VERSION,
            "measurement_domain": "ets2_unqualified_diagnostic_observation",
            "qualification": "UNQUALIFIED_RAW_MEASUREMENT",
            "runtime_authorized": False, "confirmed": False,
            "sequence": capture.sequence, "captured_at_s": capture.captured_at_s,
            "sdk_frame_us": sdk_frame, "autopilot_active": capture.autopilot_active,
            "backend_sent": capture.backend_sent,
            "telemetry_valid": capture.telemetry_valid, "truck": capture.truck,
            "vehicle_profile": profile, "traffic": traffic,
            "lane": capture.lane, "reference": capture.reference,
            "actuator_calibration": capture.actuator_calibration,
            "engine_steer": capture.engine_steer,
            "steering_boundary": {
                **(capture.steering_boundary or {}),
                "application_sdk_frame_us": capture.application_sdk_frame_us,
                "steering_write_returned_at_s": capture.steering_write_returned_at_s,
                "dll_consumed_value": None,
                "physical_axis_value": None,
                "dll_consumption_observed": False,
            },
            "user_steer": capture.truck.get("userSteer"),
            "executor": capture.applied_target,
            "command_binding_proven": command_bound,
            "calculation_sdk_frame_us": source.get("sdk_frame_us"),
            "calculation_sequence": source.get("calculation_sequence"),
            "navigation_intent_id": source.get("navigation_intent_id", capture.lane.get("navigation_intent_id")),
            "revision": source.get("authority_revision", capture.lane.get("revision")),
            "route_build_id": source.get("route_build_id", capture.lane.get("route_build_id")),
            "session": source.get("source_game_session_id", capture.lane.get("source_game_session_id")),
            "map_key": source.get("source_map_key", capture.lane.get("source_map_key")),
            "dataset_fingerprint": source.get("source_dataset_fingerprint", capture.lane.get("source_dataset_fingerprint")),
            "lane_id": lane_match.get("active_lane_id", capture.lane.get("active_lane_id")),
            "reference_mode": source.get("reference_mode", capture.reference.get("mode")),
            "plan_token": source.get("maneuver_plan_token", capture.reference.get("plan_token")),
            "geometry_hash": source.get("geometry_sha256", capture.reference.get("geometry_hash")),
            "reference_binding": source.get("maneuver_reference_binding", capture.reference.get("binding")),
            "prepared_sequence": capture.reference.get("sequence"),
            "execution_sequence": capture.applied_target.get("submission_sequence"),
            "global_cte_m": lane_match.get("lateral_error_m"),
            "local_cte_m": source.get("control_cte"),
            "heading_error_rad": source.get("guidance_heading_error_rad", lane_match.get("heading_error_rad")),
            "curvature_reference": source.get("local_curvature", source.get("curvature_per_m")),
            "steer_raw": capture.applied_target.get("raw"),
            "steer_out": executor_output,
            "game_steer": capture.truck.get("gameSteer"),
            "tyre_angles_rad": capture.truck.get("roadWheelAnglesRad"),
            "yaw_rate_rad_s": (capture.truck.get("yawRateRadS")
                               if capture.truck.get("yawRateValid") else None),
            "speed_mps": capture.truck.get("speed"),
            "acceleration_mps2": source.get("acceleration_mps2"),
            "articulation_rad": capture.trailer_articulation_rad,
            "planned_point": source.get("tracking_projection_xz"),
            "planned_tangent": source.get("local_tangent_heading_rad"),
            "predicted_clearance_m": (source.get("trailer_envelope") or {}).get("estimated_clearance_m"),
            "surface_token": _jsonable(capture.surface_token),
            "ground_reference": _jsonable(capture.ground_reference),
            "article_positions": [
                {"slot": article.get("slot"), "vehicle_id": article.get("vehicle_id"),
                 "position_m": article.get("position_m"),
                 "rotation_rad": article.get("rotation_rad")}
                for article in ((profile.get("observation") or {}).get("articles", ()) or ())
                if article.get("attached")],
        }
        geometry_reasons = _trailer_geometry_reasons(
            row, self._last_sdk_frame, self._last_geometry_binding)
        command_reasons = _moving_command_reasons(row, geometry_reasons)
        geometry_binding = _geometry_binding(row)
        navigation_binding = _navigation_binding(row)
        stationary = _finite(row.get("speed_mps")) and abs(row["speed_mps"]) <= 0.2
        row["trailer_geometry_eligible"] = not geometry_reasons
        row["trailer_geometry_rejection_reasons"] = geometry_reasons
        row["trailer_moving_command_binding_eligible"] = not command_reasons
        row["trailer_command_rejection_reasons"] = command_reasons
        row["trailer_axle_replay_eligible"] = not geometry_reasons and not command_reasons
        with self._lock:
            if self._state not in ("ARMED", "COLLECTING"):
                return
            if len(self._rows) == self._rows.maxlen:
                self._dropped += 1
            self._rows.append(row)
            preflight = dict(self._trailer_preflight)
            binding_changed = (self._last_geometry_binding is not None
                               and geometry_binding != self._last_geometry_binding)
            duplicate = self._last_sdk_frame == sdk_frame
            if binding_changed or (geometry_reasons and not (
                    duplicate and geometry_reasons == [
                        "DUPLICATE_SDK_FRAME"])):
                preflight["consecutive_stationary_geometry_frames"] = 0
                preflight["stationary_geometry_ready"] = False
                preflight["moving_command_frames"] = 0
                preflight["moving_command_binding_observed"] = False
            elif not geometry_reasons and stationary:
                preflight["stationary_geometry_frames"] += 1
                preflight["consecutive_stationary_geometry_frames"] += 1
                if preflight["consecutive_stationary_geometry_frames"] >= 3:
                    preflight["stationary_geometry_ready"] = True
            if (self._last_moving_navigation_binding is not None
                    and navigation_binding != self._last_moving_navigation_binding):
                preflight["moving_command_frames"] = 0
                preflight["moving_command_binding_observed"] = False
            if not command_reasons:
                preflight["moving_command_frames"] += 1
                if preflight["moving_command_frames"] >= 3:
                    preflight["moving_command_binding_observed"] = True
                self._last_moving_navigation_binding = navigation_binding
            elif _finite(row.get("speed_mps")) and abs(row["speed_mps"]) > 0.5:
                preflight["moving_command_frames"] = 0
            preflight.update({
                "latest_sdk_frame_us": sdk_frame,
                "vehicle_stationary": stationary,
                "latest_geometry_reasons": list(geometry_reasons),
                "latest_command_reasons": list(command_reasons),
                "replay_channels_observed": bool(
                    preflight["stationary_geometry_ready"]
                    and preflight["moving_command_binding_observed"]
                    and self._dropped == 0),
                "replay_candidate_complete": False,
            })
            self._trailer_preflight = preflight
            self._state, self._reason = "COLLECTING", "RAW_MEASUREMENTS_NOT_CONFIRMED"
            self._last_capture_s, self._last_sdk_frame = capture.captured_at_s, sdk_frame
            self._last_geometry_binding = geometry_binding
        self._publish()

    def _candidate_documents(self, rows):
        latest = rows[-1]
        identities = [list(_identity(row)) for row in rows]
        identity_counts = Counter(tuple(json.dumps(v, sort_keys=True) for v in identity)
                                  for identity in identities)
        profile = latest.get("vehicle_profile") or {}
        observation = profile.get("observation") or {}
        attached_articles = [article for article in (observation.get("articles") or [])
                             if article.get("attached")]
        traffic_rows = [row["traffic"] for row in rows if isinstance(row.get("traffic"), dict)]
        actors = [actor for value in traffic_rows for actor in (value.get("actors") or [])]
        truck_xz = [(row["truck"].get("x"), row["truck"].get("z")) for row in rows]
        distances = []
        for row, position in zip(rows, truck_xz):
            if not all(_finite(v) for v in position) or not isinstance(row.get("traffic"), dict):
                continue
            for actor in row["traffic"].get("actors", ()) or ():
                bodies = actor.get("bodies", ()) or ()
                if bodies:
                    xyz = bodies[0].get("position_xyz", ())
                    if len(xyz) >= 3 and _finite(xyz[0]) and _finite(xyz[2]):
                        distances.append(math.hypot(xyz[0]-position[0], xyz[2]-position[1]))
        profile_candidate = _sealed({
            "schema_version": 1, "kind": "body_profile_candidate",
            "measurement_domain": "ets2_observed_plus_manual_measurement_required",
            "reviewed": False, "confirmed": False, "runtime_authorized": False,
            "qualification": "MISSING_CONFIRMED_BODY_PROFILE",
            "configuration_fingerprint": ((profile.get("token") or {}).get("configuration")),
            "sdk_observation": (profile.get("observation") or {}),
            "accessory_fingerprint": None, "accessory_inventory_complete": False,
            "manual_article_measurements": _article_profile_templates(profile),
            "collected_at_utc": _utc_now(),
        })
        configuration_candidate = _sealed({
            "schema_version": 1, "kind": "active_configuration_candidate",
            "measurement_domain": "scs_shared_memory_revision_12",
            "reviewed": False, "confirmed": False, "runtime_authorized": False,
            "qualification": "MISSING_COMPLETE_ACTIVE_CONFIGURATION",
            "atomic": bool(observation.get("atomic", False)),
            "stable_read": bool(observation.get("stable_read", False)),
            "observation_sdk_frame_us": observation.get("sdk_frame_us"),
            "observed_at_monotonic_s": observation.get("captured_at"),
            "game_version": observation.get("game_version"),
            "configuration_revision": None,
            "truck_model_identifier": (attached_articles[0].get("vehicle_id")
                                         if attached_articles else None),
            "cabin_identifier": None, "chassis_identifier": None,
            "relevant_accessory_identifiers": None,
            "accessory_inventory_complete": False,
            "active_mod_identifiers": None, "mod_inventory_complete": False,
            "resulting_asset_fingerprint": None,
            "trailer_chain": [{key: article.get(key) for key in (
                "slot", "vehicle_id", "brand_id", "name", "body_type",
                "chain_type", "cargo_accessory_id")}
                for article in attached_articles if article.get("slot") != -1],
            "available_producer_fields": [
                "truck_model_identifier", "trailer_chain", "game_version",
                "observation_sdk_frame_us"],
            "missing_producer_fields": [
                "cabin_identifier", "chassis_identifier",
                "relevant_accessory_identifiers", "configuration_revision",
                "active_mod_identifiers", "resulting_asset_fingerprint"],
            "producer_limit": (
                "SCS telemetry/shared-memory revision 12 exposes truck/trailer IDs, "
                "wheel and hook geometry but not installed cabin, chassis or complete "
                "accessory unit paths"),
        })
        ground_candidate = _sealed({
            "schema_version": 1, "kind": "ground_reference_candidate",
            "reviewed": False, "confirmed": False, "runtime_authorized": False,
            "qualification": "MISSING_FIXED_AXLE_GROUND_REFERENCE_PRODUCER",
            "reason": ("SDK_FRAME_NOT_ATOMIC_OR_CHANNEL_VALIDATED"
                       if not (profile.get("observation") or {}).get("atomic")
                       else "GROUND_CALIBRATION_REQUIRES_OFFLINE_REVIEW"),
            "coordinate_frame": "scs_world_x_right_y_up_z_south_heading_right_rad",
            "configuration_fingerprint": ((profile.get("token") or {}).get("configuration")),
            "frames": [{"sdk_frame_us": row["sdk_frame_us"],
                        "captured_at_s": row["captured_at_s"],
                        "elevation_layer": row["lane"].get("elevation_layer"),
                        "transform_uncertainty_m": None,
                        "articles": ((row.get("vehicle_profile") or {}).get("observation") or {}).get("articles", [])}
                       for row in rows],
        })
        traffic_candidate = _sealed({
            "schema_version": 1, "kind": "traffic_coverage_observation",
            "reviewed": False, "confirmed": False, "complete": False,
            "runtime_authorized": False,
            "qualification": "MISSING_COMPLETE_TRAFFIC_HISTORY_COVERAGE_AND_BODY_PRODUCER",
            "buffer_status_counts": dict(Counter(v.get("status") for v in traffic_rows)),
            "sample_count": len(traffic_rows), "actor_observation_count": len(actors),
            "stable_actor_identity_counts": dict(Counter(a.get("actor_id") for a in actors)),
            "actors_with_unknown_dimensions": sum(not a.get("dimensions_present") for a in actors),
            "maximum_observed_distance_m": max(distances) if distances else None,
            "sensor_range_m": None, "spatial_coverage_known": False,
            "unseen_entry_boundary_known": False, "source_sequence_known": False,
            "source_time_known": False, "elevation_discrimination_proven": False,
            "history": traffic_rows,
        })
        tracking_candidate = _sealed({
            "schema_version": 1, "kind": "tracking_samples_candidate",
            "measurement_domain": "ets2_backend_observation",
            "qualification": "PASSIVE_GLOBAL_OR_UNQUALIFIED_RAW_MEASUREMENT",
            "reviewed": False, "confirmed": False, "runtime_authorized": False,
            "local_maneuver_qualification": False,
            "trailer_axle_replay_channels_observed": bool(
                self._trailer_preflight["replay_channels_observed"]),
            "trailer_axle_replay_candidate_complete": False,
            "command_bound_sample_count": sum(row["command_binding_proven"] for row in rows),
            "samples": [{k: row.get(k) for k in (
                "sequence", "captured_at_s", "sdk_frame_us", "calculation_sdk_frame_us",
                "calculation_sequence", "navigation_intent_id", "revision", "route_build_id",
                "session", "map_key", "dataset_fingerprint", "lane_id", "reference_mode",
                "plan_token", "geometry_hash", "reference_binding", "prepared_sequence", "execution_sequence",
                "global_cte_m", "local_cte_m", "heading_error_rad", "curvature_reference",
                "steer_raw", "steer_out", "engine_steer", "game_steer", "tyre_angles_rad",
                "yaw_rate_rad_s", "speed_mps", "acceleration_mps2", "articulation_rad",
                "planned_point", "planned_tangent", "predicted_clearance_m",
                "actuator_calibration", "command_binding_proven", "article_positions",
                "ground_reference", "surface_token", "trailer_geometry_eligible",
                "trailer_moving_command_binding_eligible", "trailer_axle_replay_eligible")}
                for row in rows],
        })
        lane_ids = []
        gps_uids = []
        layers = []
        trace = []
        for row in rows:
            lane_id = row.get("lane_id")
            if lane_id is not None and (not lane_ids or lane_id != lane_ids[-1]):
                lane_ids.append(lane_id)
            for uid in row["lane"].get("source_gps_uids", ()) or ():
                if uid not in gps_uids:
                    gps_uids.append(uid)
            layer = row["lane"].get("elevation_layer")
            if layer is not None and layer not in layers:
                layers.append(layer)
            truck = row["truck"]
            if all(_finite(truck.get(k)) for k in ("x", "y", "z")):
                trace.append([truck["x"], truck["y"], truck["z"]])
        survey_candidate = _sealed({
            "schema_version": 1, "kind": "surface_survey_candidate",
            "measurement_domain": "UNMEASURED_SURVEY_CANDIDATE",
            "method": None, "reviewed": False, "confirmed": False,
            "runtime_authorized": False,
            "qualification": "MISSING_CONFIRMED_DRIVABLE_SURFACE_PRODUCER",
            "map_key": latest.get("map_key"),
            "dataset_fingerprint": latest.get("dataset_fingerprint"),
            "game_session": latest.get("session"), "gps_uid_range": gps_uids,
            "lane_id_sequence": lane_ids, "elevation_layers_observed": layers,
            "observed_vehicle_trace_xyz": trace,
            "trace_is_drivable_boundary": False, "exterior_xyz": [], "holes_xyz": [],
            "boundary_uncertainty_m": None,
            "survey_coverage": {key: False for key in (
                "outer_boundary", "islands", "curbs", "barriers", "fixed_obstacles",
                "support_layer", "interior_inspected")},
        })
        identity_candidate = _sealed({
            "schema_version": 1, "kind": "diagnostic_identity_binding",
            "confirmed": False, "runtime_authorized": False,
            "identity_keys": list(IDENTITY_KEYS), "identity_counts": [
                {"identity": identities[index], "count": count}
                for index, count in ((identities.index([json.loads(v) for v in key]), count)
                                     for key, count in identity_counts.items())],
            "single_identity": len(identity_counts) == 1,
            "configuration_fingerprint": ((profile.get("token") or {}).get("configuration")),
        })
        raw = _sealed({
            "schema_version": 1, "kind": "automatic_observations",
            "measurement_domain": "ets2_unqualified_diagnostic_observation",
            "qualification": "UNQUALIFIED_RAW_MEASUREMENT", "confirmed": False,
            "runtime_authorized": False, "sample_count": len(rows),
            "dropped_samples": self._dropped, "samples": rows,
        })
        return {
            "automatic-observations.json": raw,
            "body-profile-candidate.json": profile_candidate,
            "configuration-identity-candidate.json": configuration_candidate,
            "ground-reference-candidate.json": ground_candidate,
            "traffic-coverage-observations.json": traffic_candidate,
            "tracking-samples-candidate.json": tracking_candidate,
            "surface-survey-candidate.json": survey_candidate,
            "identity-binding.json": identity_candidate,
        }

    def finalize(self):
        with self._lock:
            rows = list(self._rows)
            collection_id = self._collection_id
            if self._state not in ("ARMED", "COLLECTING"):
                raise ValueError("DIAGNOSTIC_COLLECTION_NOT_ACTIVE")
            self._state, self._reason = "SAMPLE_COMPLETE", "RAW_SAMPLE_COMPLETE_NOT_CONFIRMED"
        self._publish()
        if len(rows) < 30:
            with self._lock:
                self._state, self._reason = "INSUFFICIENT_EVIDENCE", "FEWER_THAN_30_FRESH_SAMPLES"
            self._publish()
            return
        try:
            target = self.output_root / collection_id
            if target.exists():
                raise ValueError("DIAGNOSTIC_COLLECTION_ALREADY_EXISTS")
            self.output_root.mkdir(parents=True, exist_ok=True)
            stage = Path(tempfile.mkdtemp(prefix=f".{collection_id}.",
                                          suffix=".partial", dir=self.output_root))
            documents = self._candidate_documents(rows)
            entries = []
            chunked = False
            for name, document in documents.items():
                chunked |= _write_candidate_document(stage, name, document, entries)
            manifest = _sealed({
                "schema_version": 2 if chunked else 1,
                "kind": "diagnostic_collection_manifest",
                "collection_id": collection_id, "purpose": self._purpose,
                "created_at_utc": _utc_now(), "sample_count": len(rows),
                "dropped_samples": self._dropped, "files": entries,
                "qualification": "READY_FOR_OFFLINE_REVIEW",
                "trailer_axle_replay_channels_observed": bool(
                    self._trailer_preflight["replay_channels_observed"]),
                "trailer_axle_replay_candidate_complete": False,
                "confirmed": False, "runtime_authorized": False,
            })
            atomic_json_write(stage / "manifest.json", manifest)
            if target.exists():
                raise ValueError("DIAGNOSTIC_COLLECTION_ALREADY_EXISTS")
            os.rename(stage, target)
        except (OSError, ValueError, TypeError) as error:
            with self._lock:
                self._state, self._reason = "INSUFFICIENT_EVIDENCE", _export_failure_reason(error)
            self._publish()
            return
        with self._lock:
            self._state, self._reason = "READY_FOR_OFFLINE_REVIEW", "RAW_FILES_REQUIRE_INDEPENDENT_REVIEW"
        self._publish()

    def _poll_command(self):
        try:
            command = read_json(self.control_path, max_bytes=64 * 1024)
            if command.get("sequence", 0) > self._last_command_sequence:
                self.apply_command(command)
        except FileNotFoundError:
            return
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            with self._lock:
                if self._state in ("ARMED", "COLLECTING"):
                    self._state, self._reason = "INSUFFICIENT_EVIDENCE", "INVALID_DIAGNOSTIC_CONTROL:" + type(error).__name__
            self._publish()

    def _run(self):
        while not self._stop.wait(0.02):
            self._poll_command()
            try:
                capture = self._queue.get(timeout=0.05)
            except queue.Empty:
                capture = None
            if capture is not None:
                self._ingest(capture)
            with self._lock:
                expired = (self._state in ("ARMED", "COLLECTING")
                           and self._started_at is not None
                           and self.clock() - self._started_at >= self._max_duration_s)
            if expired:
                self.finalize()


def inspect_collection(path):
    """Offline integrity check. It can never return driving authorization."""
    root = Path(path)
    manifest = read_json(root / "manifest.json")
    if (not _verify_seal(manifest) or manifest.get("runtime_authorized") is not False
            or manifest.get("confirmed") is not False
            or manifest.get("schema_version") not in (1, 2)):
        raise ValueError("INVALID_DIAGNOSTIC_MANIFEST")
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise ValueError("INVALID_DIAGNOSTIC_MANIFEST")
    values = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            raise ValueError("INVALID_DIAGNOSTIC_MANIFEST")
        name = entry["name"]
        target = (root / name).resolve()
        if (name in values or not target.is_relative_to(root.resolve())
                or target == root.resolve() or target.parent != root.resolve()):
            raise ValueError("DIAGNOSTIC_MANIFEST_PATH_ESCAPE")
        if (not target.is_file() or target.stat().st_size > MAX_DIAGNOSTIC_FILE_BYTES
                or hashlib.sha256(target.read_bytes()).hexdigest() != entry["sha256"]):
            raise ValueError("DIAGNOSTIC_FILE_INTEGRITY_MISMATCH")
        value = read_json(target)
        if (not _verify_seal(value) or value.get("confirmed") is not False
                or value.get("runtime_authorized") is not False):
            raise ValueError("DIAGNOSTIC_CANDIDATE_WAS_PROMOTED")
        values[name] = value
    if manifest["schema_version"] == 2:
        _inspect_chunked_collection(root, manifest, entries, values)
    return {"integrity_valid": True, "file_count": len(manifest["files"]),
            "sample_count": manifest["sample_count"], "confirmed": False,
            "runtime_authorized": False,
            "trailer_axle_replay_channels_observed": bool(
                manifest.get("trailer_axle_replay_channels_observed", False)),
            "trailer_axle_replay_candidate_complete": bool(
                manifest.get("trailer_axle_replay_candidate_complete", False)),
            "qualification": "READY_FOR_OFFLINE_REVIEW"}


def _inspect_chunked_collection(root, manifest, entries, values):
    expected_names = {"manifest.json", *(entry["name"] for entry in entries)}
    if {p.name for p in root.iterdir()} != expected_names:
        raise ValueError("DIAGNOSTIC_FILE_SET_MISMATCH")
    index = 0
    raw_count = None
    while index < len(entries):
        entry = entries[index]
        name = entry["name"]
        document = values[name]
        role = entry.get("role")
        if role == "document":
            if document.get("chunked") is True or name not in (
                    set(CHUNKABLE_DOCUMENT_FIELDS) | {
                        "body-profile-candidate.json",
                        "configuration-identity-candidate.json",
                        "surface-survey-candidate.json", "identity-binding.json"}):
                raise ValueError("DIAGNOSTIC_CHUNK_ORDER_MISMATCH")
            index += 1
            continue
        if role != "index" or name not in CHUNKABLE_DOCUMENT_FIELDS:
            raise ValueError("DIAGNOSTIC_CHUNK_ORDER_MISMATCH")
        field = CHUNKABLE_DOCUMENT_FIELDS[name]
        count = document.get("chunk_count")
        if (document.get("chunked") is not True or document.get("record_field") != field
                or type(count) is not int or count <= 0
                or type(document.get("chunk_sample_count")) is not int):
            raise ValueError("DIAGNOSTIC_CHUNK_INDEX_INVALID")
        total = 0
        last_sequence = last_time = last_frame = None
        for order in range(count):
            index += 1
            if index >= len(entries):
                raise ValueError("DIAGNOSTIC_CHUNK_MISSING")
            part = entries[index]
            expected_name = f"{name[:-5]}.part-{order:04d}.json"
            if (part.get("role") != "chunk" or part.get("name") != expected_name
                    or part.get("parent_name") != name
                    or part.get("record_field") != field
                    or part.get("order") != order
                    or part.get("start_index") != total):
                raise ValueError("DIAGNOSTIC_CHUNK_ORDER_MISMATCH")
            chunk = values[expected_name]
            records = chunk.get("records")
            if (not isinstance(records, list) or not records
                    or chunk.get("kind") != "diagnostic_record_chunk"
                    or chunk.get("schema_version") != 2
                    or chunk.get("confirmed") is not False
                    or chunk.get("runtime_authorized") is not False):
                raise ValueError("DIAGNOSTIC_CHUNK_INVALID")
            for key in ("parent_name", "record_field", "order", "start_index",
                        "sample_count", "first_sdk_frame_us", "last_sdk_frame_us",
                        "first_sequence", "last_sequence"):
                if part.get(key) != chunk.get(key):
                    raise ValueError("DIAGNOSTIC_CHUNK_METADATA_MISMATCH")
            if chunk["sample_count"] != len(records):
                raise ValueError("DIAGNOSTIC_CHUNK_COUNT_MISMATCH")
            first, last = records[0], records[-1]
            if not all(isinstance(row, dict) for row in records):
                raise ValueError("DIAGNOSTIC_CHUNK_INVALID")
            for key, record_key in (("first_sdk_frame_us", "sdk_frame_us"),
                                    ("last_sdk_frame_us", "sdk_frame_us"),
                                    ("first_sequence", "sequence"),
                                    ("last_sequence", "sequence")):
                row = first if key.startswith("first") else last
                if chunk[key] != row.get(record_key):
                    raise ValueError("DIAGNOSTIC_CHUNK_METADATA_MISMATCH")
            if name == "automatic-observations.json":
                for row in records:
                    sequence = row.get("sequence")
                    frame = row.get("sdk_frame_us")
                    captured = row.get("captured_at_s")
                    if (type(sequence) is not int or type(frame) is not int
                            or not _finite(captured)
                            or (last_sequence is not None and sequence <= last_sequence)
                            or (last_frame is not None and frame <= last_frame)
                            or (last_time is not None and captured <= last_time)):
                        raise ValueError("DIAGNOSTIC_CHUNK_TIME_ORDER_MISMATCH")
                    last_sequence, last_frame, last_time = sequence, frame, captured
            total += len(records)
        if total != document["chunk_sample_count"]:
            raise ValueError("DIAGNOSTIC_CHUNK_COUNT_MISMATCH")
        if name == "automatic-observations.json":
            raw_count = total
        index += 1
    if raw_count != manifest.get("sample_count"):
        raise ValueError("DIAGNOSTIC_CHUNK_COUNT_MISMATCH")
