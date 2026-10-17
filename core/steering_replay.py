"""Bounded, observational high-rate steering telemetry.

The normal console diagnostic is intentionally human-readable and throttled to
roughly one row per second.  That cadence cannot prove or reject sub-second
steering oscillation.  ``SteeringReplayBuffer`` retains the latest control
ticks in memory and writes them only on an explicit safety/shutdown event.  It
does not publish shared state, alter timing inputs, or participate in control.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import json
import math
import os
import re
import threading
import time
import uuid
import hashlib


SCHEMA_VERSION = 3
CALCULATION_PACKET_SCHEMA_VERSION = 1
DEFAULT_CAPACITY = 3600
EXECUTION_CAPACITY_MULTIPLIER = 3
MAX_EXECUTION_CAPACITY = 20000

SIGNIFICANT_EVENT_MAX_FILES = 8
SIGNIFICANT_EVENT_MAX_BYTES = 16 * 1024 * 1024


def significant_event_export_budget(directory):
    """Read-only metadata check; call from export worker or offline tooling only."""
    from pathlib import Path
    root = Path(directory)
    files = sorted(root.glob('steering-replay-*-significant_event.json'))
    sizes = [p.stat().st_size for p in files]
    remaining = max(0, SIGNIFICANT_EVENT_MAX_BYTES - sum(sizes))
    blockers = []
    if len(files) >= SIGNIFICANT_EVENT_MAX_FILES:
        blockers.append('FILE_COUNT_LIMIT')
    if remaining == 0:
        blockers.append('BYTE_LIMIT')
    return dict(ready=not blockers, blockers=blockers, file_count=len(files),
                used_bytes=sum(sizes), remaining_bytes=remaining,
                maximum_files=SIGNIFICANT_EVENT_MAX_FILES,
                maximum_bytes=SIGNIFICANT_EVENT_MAX_BYTES,
                files=[dict(name=p.name, bytes=size) for p, size in zip(files, sizes)],
                fit_of_next_payload_verified=False)

PUBLISH_IDENTITY_FIELDS = (
    "navigation_intent_id", "route_build_id", "authority_revision",
    "source_game_session_id", "source_map_key",
    "source_dataset_fingerprint",
)


def publish_receipt_matches(receipt, packet):
    """Pair a diagnostic publish completion with its exact Map packet."""
    return bool(
        isinstance(receipt, dict) and isinstance(packet, dict)
        and receipt.get("sequence") == packet.get("calculation_sequence")
        and receipt.get("sdk_frame_us") == packet.get("sdk_frame_us")
        and isinstance(receipt.get("identity"), dict)
        and all(receipt["identity"].get(key) == packet.get(key)
                for key in PUBLISH_IDENTITY_FIELDS))

_TRAJECTORY_IDENTITY_FIELDS = (
    "navigation_intent_id",
    "route_build_id",
    "revision",
    "source_game_session_id",
    "source_map_key",
    "source_dataset_fingerprint",
)


def _json_value(value):
    """Return a deterministic JSON-safe copy; non-finite numbers are absent."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return str(value)
    return number if math.isfinite(number) else None


def diagnostic_copy(value):
    """Return a detached JSON-safe diagnostic value.

    Shared state and the lightweight test doubles used by the plugins may
    return mutable nested dictionaries.  A shallow ``dict(...)`` copy can
    therefore pair a command with lane/geometry values changed by a later map
    tick.  This copy is deliberately observational and is never passed back to
    the control path.
    """
    return _json_value(value)


def bind_steering_calculation(debug, lane_match, trajectory, *, sequence):
    """Freeze every input/output identity belonging to one Route calculation.

    The full LanePath is intentionally not duplicated at control frequency.
    Its revision-bound identity is sufficient to locate the immutable
    trajectory export, while the local projection/tangent/curvature already
    present in ``debug`` records the geometry actually used by the controller.
    """
    packet = diagnostic_copy(debug or {})
    identity = {
        key: (trajectory or {}).get(key) for key in _TRAJECTORY_IDENTITY_FIELDS
    }
    packet.update({
        "calculation_packet_schema_version": CALCULATION_PACKET_SCHEMA_VERSION,
        "calculation_sequence": int(sequence),
        "lane_match_snapshot": diagnostic_copy(lane_match or {}),
        "trajectory_identity": diagnostic_copy(identity),
    })
    return packet


def steering_packet_binding(packet, application_trajectory):
    """Validate replay causality without accepting or rejecting control.

    Returns ``(valid, reasons)``.  It is diagnostic only: runtime authority is
    still decided by ``navigation_command`` and the existing fail-closed
    checks.  Keeping this separate prevents telemetry instrumentation from
    becoming a second steering authority.
    """
    packet = packet or {}
    reasons = []
    if packet.get("calculation_packet_schema_version") != (
            CALCULATION_PACKET_SCHEMA_VERSION):
        reasons.append("missing_or_unknown_calculation_packet_schema")
    try:
        if int(packet.get("calculation_sequence", 0)) <= 0:
            reasons.append("missing_calculation_sequence")
    except (TypeError, ValueError, OverflowError):
        reasons.append("invalid_calculation_sequence")

    required = (
        "computed_at", "observation_timestamp", "sdk_frame_us",
        "controller", "raw", "output", "local_curvature",
        "preview_curvature", "tracking_progress_m",
        "tracking_segment_index", "tracking_segment_fraction",
        "tracking_projection_xz", "local_tangent_heading_rad",
        "observation_xz", "observation_heading_rad",
    )
    for key in required:
        if packet.get(key) is None:
            reasons.append(f"missing_{key}")

    match = packet.get("lane_match_snapshot")
    if not isinstance(match, dict) or not match:
        reasons.append("missing_lane_match_snapshot")
    identity = packet.get("trajectory_identity")
    if not isinstance(identity, dict):
        reasons.append("missing_trajectory_identity")
        identity = {}
    for key in _TRAJECTORY_IDENTITY_FIELDS:
        packet_value = identity.get(key)
        application_value = (application_trajectory or {}).get(key)
        if packet_value is None:
            reasons.append(f"missing_identity_{key}")
        elif application_value is not None and packet_value != application_value:
            reasons.append(f"application_mismatch_{key}")
    if isinstance(match, dict) and identity.get("revision") is not None:
        try:
            if int(match.get("revision")) != int(identity["revision"]):
                reasons.append("lane_match_revision_mismatch")
        except (TypeError, ValueError, OverflowError):
            reasons.append("invalid_lane_match_revision")
    return not reasons, tuple(reasons)


class SteeringReplayBuffer:
    """Keep a fixed number of telemetry ticks and atomically export a replay."""

    def __init__(self, capacity=DEFAULT_CAPACITY, *, monotonic=time.monotonic,
                 wall_time=time.time):
        capacity = int(capacity)
        if capacity < 2 or capacity > 20000:
            raise ValueError("steering replay capacity must be within 2..20000")
        self._samples = deque(maxlen=capacity)
        # Normal samples follow the plugin/application cadence, while the
        # execution stream runs at 60 Hz.  Equal item counts retained only
        # about one third of the same drive in schema 3 and discarded the
        # beginning of ordinary three-minute reproductions.
        execution_capacity = min(
            MAX_EXECUTION_CAPACITY,
            capacity * EXECUTION_CAPACITY_MULTIPLIER)
        self._execution_samples = deque(maxlen=execution_capacity)
        self._monotonic = monotonic
        self._wall_time = wall_time
        self._sequence = 0
        self._execution_sequence = 0
        self._lock = threading.Lock()

    @property
    def capacity(self):
        return int(self._samples.maxlen)

    @property
    def execution_capacity(self):
        return int(self._execution_samples.maxlen)

    def __len__(self):
        with self._lock:
            return len(self._samples)

    def append(self, sample):
        """Copy one tick without feeding anything back to the control path."""
        with self._lock:
            self._sequence += 1
            row = dict(sample or {})
            row.update({
                "sequence": self._sequence,
                "monotonic_s": float(self._monotonic()),
                "wall_time_s": float(self._wall_time()),
            })
            self._samples.append(_json_value(row))

    def append_execution(self, sample):
        """Record one physical dynamics step independently of plugin cadence."""
        with self._lock:
            self._execution_sequence += 1
            row = dict(sample or {})
            row.update({
                "sequence": self._execution_sequence,
                "monotonic_s": float(self._monotonic()),
                "wall_time_s": float(self._wall_time()),
            })
            self._execution_samples.append(_json_value(row))

    def snapshot(self):
        # Do not let an analyser mutate nested evidence retained by the ring.
        with self._lock:
            return tuple(diagnostic_copy(row) for row in self._samples)

    def execution_snapshot(self):
        with self._lock:
            return tuple(diagnostic_copy(row)
                         for row in self._execution_samples)

    def export(self, directory, *, reason, identity=None,
               filename_prefix="steering-replay", sample_kind="dense_steering", longitudinal=None,
               maximum_output_bytes=None):
        """Write the current immutable snapshot using an atomic replacement."""
        # Copy both streams and their counters under one lock.  An execution
        # tick must not land between the copied rows and the dropped-row
        # counters recorded in the same evidence document.
        with self._lock:
            samples = tuple(self._samples)
            execution_samples = tuple(self._execution_samples)
            sample_sequence = self._sequence
            execution_sequence = self._execution_sequence
        # Retained rows are owned, immutable copies from append(). Copy outside
        # the short lock so a diagnostic writer cannot stall the executor.
        samples = tuple(diagnostic_copy(row) for row in samples)
        execution_samples = tuple(diagnostic_copy(row) for row in execution_samples)
        if not samples and not longitudinal:
            return None
        directory = os.path.abspath(os.fspath(directory))
        os.makedirs(directory, exist_ok=True)
        now = datetime.now(timezone.utc)
        stamp = now.strftime("%Y%m%dT%H%M%S.%fZ")
        safe_reason = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(reason or "event"))
        safe_reason = safe_reason.strip("-.")[:48] or "event"
        if filename_prefix not in ("steering-replay", "steering-timing"):
            raise ValueError("unsupported steering diagnostic filename prefix")
        path = os.path.join(
            directory, f"{filename_prefix}-{stamp}-{safe_reason}.json")
        temporary = path + ".tmp-" + uuid.uuid4().hex
        payload = {
            "schema_version": SCHEMA_VERSION,
            "sample_kind": sample_kind,
            "created_at": now.isoformat(),
            "reason": str(reason or "event"),
            "capacity": self.capacity,
            "execution_capacity": self.execution_capacity,
            "sample_count": len(samples),
            "dropped_sample_count": max(0, sample_sequence-len(samples)),
            "execution_sample_count": len(execution_samples),
            "dropped_execution_sample_count": max(
                0, execution_sequence-len(execution_samples)),
            "identity": _json_value(identity or {}),
            "samples": samples,
            "execution_samples": execution_samples,
        }
        if longitudinal is not None:
            from core.navigation.longitudinal_diagnostics import expand_journal
            longitudinal = expand_journal(longitudinal)
            longitudinal['field_capture_failures'] = sum(
                'snapshot_status' in (e.get('source') or {}) for e in longitudinal['events'])
            longitudinal['snapshot_incomplete'] = bool(longitudinal.get('snapshot_incomplete')
                or longitudinal['field_capture_failures'])
            # Exact references belong only to this sealed file, never IPC.
            payload['longitudinal_storage'] = _intern_values(_json_value(longitudinal))
            payload['confirmed'] = payload['runtime_authorized'] = False
        payload['integrity'] = dict(algorithm='sha256', payload_sha256=_payload_hash(payload))
        try:
            with open(temporary, "x", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False,
                          separators=(",", ":"), sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            if maximum_output_bytes is not None and os.path.getsize(temporary) > maximum_output_bytes:
                raise ValueError('SIGNIFICANT_EVENT_EXPORT_DISK_QUOTA')
            os.replace(temporary, path)
        except Exception:
            try:
                os.remove(temporary)
            except OSError:
                pass
            raise
        return path


def _payload_hash(payload):
    value = {k:v for k,v in payload.items() if k != 'integrity'}
    digest=hashlib.sha256()
    for piece in json.JSONEncoder(ensure_ascii=False,sort_keys=True,
            separators=(',',':'),allow_nan=False).iterencode(value):
        digest.update(piece.encode('utf-8'))
    return digest.hexdigest()


def _intern_values(value):
    values, indices = [], {}
    def encode(item):
        if not isinstance(item, (dict,list)):
            return item
        node = {k:encode(v) for k,v in item.items()} if isinstance(item,dict) else [encode(v) for v in item]
        key = json.dumps(node,sort_keys=True,separators=(',',':'),ensure_ascii=False)
        if key not in indices:
            indices[key] = len(values)
            values.append(node)
        return {'$immutable':indices[key]}
    root = encode(value)
    result=dict(schema_version=1,root=root,values=values)
    encode=None
    return result


def _expand_values(storage):
    if storage.get('schema_version') != 1 or not isinstance(storage.get('values'),list):
        raise ValueError('INVALID_IMMUTABLE_REPLAY_SCHEMA')
    values = storage['values']
    def expand(item, bound):
        if isinstance(item,dict) and '$immutable' in item:
            index = item['$immutable']
            if set(item) != {'$immutable'} or type(index) is not int or not 0 <= index < bound:
                raise ValueError('INVALID_OR_CYCLIC_IMMUTABLE_REFERENCE')
            return expand(values[index],index)
        if isinstance(item,dict):
            return {k:expand(v,bound) for k,v in item.items()}
        if isinstance(item,list):
            return [expand(v,bound) for v in item]
        return item
    try:
        return expand(storage['root'],len(values))
    finally:
        expand=None


def _validate_journal_order(block):
    events = block['events']
    seq = [e['sequence'] for e in events]
    if seq != sorted(set(seq)):
        raise ValueError('PEDAL_SEQUENCE_ORDER_INVALID')
    history = block.get('decision_history')
    if history is not None:
        if history.get('schema_version') != 1:
            raise ValueError('DECISION_HISTORY_SCHEMA_INVALID')
        seen = set()
        for stream in ('regular_samples', 'changes'):
            rows = history[stream]
            sequences = [r['sequence'] for r in rows]
            times = [r['monotonic_s'] for r in rows]
            if (sequences != sorted(set(sequences)) or times != sorted(times)
                    or any(not isinstance(t, (int, float)) or not math.isfinite(t) for t in times)):
                raise ValueError('DECISION_HISTORY_ORDER_INVALID')
            for row in rows:
                if row['sequence'] in seen or row['identity_reference'] not in history['identities']:
                    raise ValueError('DECISION_HISTORY_REFERENCE_INVALID')
                seen.add(row['sequence'])
    return bool(block.get('dropped_events') or block.get('snapshot_incomplete')
                or history and history['incomplete'])


def inspect_replay(path):
    """Integrity of stored evidence, never runtime authority/game consumption."""
    result = dict(integrity_valid=False, confirmed=False, runtime_authorized=False)
    try:
        with open(path,encoding='utf-8') as stream:
            value = json.load(stream)
        if (value.get('schema_version') != SCHEMA_VERSION or
                value.get('integrity') != dict(algorithm='sha256',payload_sha256=_payload_hash(value))):
            raise ValueError('REPLAY_HASH_OR_SCHEMA_MISMATCH')
        if (value['sample_count'] != len(value['samples'])
                or value['execution_sample_count'] != len(value['execution_samples'])):
            raise ValueError('REPLAY_COUNT_MISMATCH')
        if 'longitudinal_storage' in value:
            value['longitudinal'] = _expand_values(value.pop('longitudinal_storage'))
            events = value['longitudinal']['events']
            incomplete = _validate_journal_order(value['longitudinal'])
            history=value['longitudinal'].get('decision_history')
            if history is not None:
                result['history_incomplete']=history['incomplete']
                result['history_duration_s']=history['observed_range_s']['duration']
            preceding=value['longitudinal'].get('preceding_significant_event')
            if preceding is not None:
                incomplete = _validate_journal_order(preceding) or incomplete
                result['preceding_event_included']=True
            result.update(longitudinal_event_count=len(events), incomplete=incomplete,
                          evidence_status='INCOMPLETE_BOUNDED_INCIDENT' if incomplete else 'OFFLINE_REVIEW_ONLY')
        result.update(integrity_valid=True, replay=value)
    except (OSError, ValueError, KeyError, TypeError, RecursionError) as error:
        result['reason'] = str(error)
    return result


class AsyncReplayExporter:
    """One in-flight immutable replay job, no queued work or disk I/O in ticks."""
    def __init__(self):
        self._lock = threading.Lock()
        self._thread = None
        self.status = dict(path=None,error=None,error_detail=None,busy=False,dropped_requests=0)

    def submit(self, operation):
        with self._lock:
            if self.status['busy']:
                self.status['dropped_requests'] += 1
                import logging
                logging.warning('Replay export request dropped: one bounded job is already in flight')
                return False
            self.status.update(busy=True,error=None,error_detail=None,path=None)
            def write():
                try:
                    path = operation()
                    self.status['path'] = path
                except Exception as error:
                    self.status['error'] = type(error).__name__
                    self.status['error_detail'] = str(error)[:256]
                    import logging
                    logging.warning('Replay export failed: %s: %s',type(error).__name__,self.status['error_detail'])
                finally:
                    self.status['busy'] = False
            self._thread = threading.Thread(target=write,name='UltraPilot-ReplayExport',daemon=True)
            self._thread.start()
            return True

    def wait(self, timeout=5.):
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
        return dict(self.status)
