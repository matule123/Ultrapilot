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
import zlib
from contextlib import contextmanager


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
        self._diagnostic_inputs = None
        try:
            from core.navigation.diagnostic_build_config import ENABLED
        except ImportError:
            ENABLED = False
        if ENABLED:
            from core.navigation.longitudinal_diagnostics import _IncidentWindow
            self._diagnostic_inputs = _IncidentWindow(32*1024*1024,deferred=True)

    def append_consumer_input(self, kind, value, now):
        if self._diagnostic_inputs is not None:
            self._diagnostic_inputs.observe(kind,value,now)

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
               maximum_output_bytes=None, _diagnostic_child=False):
        """Write the current immutable snapshot using an atomic replacement."""
        if (self._diagnostic_inputs is not None and not _diagnostic_child
                and self._diagnostic_inputs.rolling_snapshot()['records']):
            return export_replay_isolated(self,directory,dict(reason=reason,identity=identity,
                filename_prefix=filename_prefix,sample_kind=sample_kind,longitudinal=longitudinal,
                maximum_output_bytes=maximum_output_bytes))
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
        if self._diagnostic_inputs is not None and self._diagnostic_inputs.rolling_snapshot()['records']:
            _archive_incidents(directory,reserve_bytes=32*1024*1024)
            safe_reason+='-devinputs'
            maximum_output_bytes=min(maximum_output_bytes or 32*1024*1024,
                32*1024*1024)
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
        if self._diagnostic_inputs is not None:
            payload['diagnostic_inputs_storage']=_intern_values(
                _json_value(self._diagnostic_inputs.rolling_snapshot()))
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
            separators=(',',':'),allow_nan=False).iterencode(value,_one_shot=True):
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


class _ReplayVerificationCache:
    """Two exact-content readbacks, owned only by one export operation.

    The caller re-reads and hashes current file bytes on EVERY access. Nothing
    is keyed by mtime, a mutable slot or a newer producer packet. This only
    avoids repeating JSON/type-tree decoding of the same verified content.
    No process-global retention: the existing child's RSS gate still applies.
    """
    MAX_FILES = 2
    MAX_SOURCE_BYTES = 64*1024*1024

    def __init__(self):
        from collections import OrderedDict
        self.rows=OrderedDict();self.source_bytes=0

    def get(self,key):
        row=self.rows.get(key)
        if row is not None:self.rows.move_to_end(key)
        return row[1] if row is not None else None

    def put(self,key,size,result):
        if not result.get('integrity_valid') or size>self.MAX_SOURCE_BYTES:return
        while self.rows and (len(self.rows)>=self.MAX_FILES or self.source_bytes+size>self.MAX_SOURCE_BYTES):
            _,old=self.rows.popitem(last=False);self.source_bytes-=old[0]
        self.rows[key]=(size,result);self.source_bytes+=size


def inspect_replay(path, *, _cache=None):
    """Integrity of stored evidence, never runtime authority/game consumption."""
    result = dict(integrity_valid=False, confirmed=False, runtime_authorized=False)
    try:
        if _cache is None:
            with open(path,encoding='utf-8') as stream:
                value = json.load(stream)
        else:
            from pathlib import Path
            raw=Path(path).read_bytes()
            cache_key=(str(Path(path).resolve()),hashlib.sha256(raw).hexdigest())
            cached=_cache.get(cache_key)
            if cached is not None:return cached
            value=json.loads(raw)
        if (value.get('schema_version') != SCHEMA_VERSION or
                value.get('integrity') != dict(algorithm='sha256',payload_sha256=_payload_hash(value))):
            raise ValueError('REPLAY_HASH_OR_SCHEMA_MISMATCH')
        if (value['sample_count'] != len(value['samples'])
                or value['execution_sample_count'] != len(value['execution_samples'])):
            raise ValueError('REPLAY_COUNT_MISMATCH')
        if 'longitudinal_storage' in value:
            value['longitudinal'] = _expand_values(value.pop('longitudinal_storage'))
            compressed=value['longitudinal'].get('diagnostic_incident')
            if isinstance(compressed,dict) and compressed.get('encoding')=='zlib-immutable-json-v1':
                import base64
                length=compressed['raw_bytes']
                if type(length) is not int or not 0<=length<=64*1024*1024:raise ValueError('INCIDENT_JSON_SIZE')
                raw=zlib.decompressobj().decompress(base64.b64decode(compressed['data'],validate=True),length+1)
                if len(raw)!=length or hashlib.sha256(raw).hexdigest()!=compressed['raw_sha256']:
                    raise ValueError('INCIDENT_JSON_HASH')
                value['longitudinal']['diagnostic_incident']=_expand_values(json.loads(raw))
            incident=value['longitudinal'].get('diagnostic_incident')
            if isinstance(incident,dict) and incident.get('_exact_record_window')==1:
                from core.navigation.longitudinal_diagnostics import unpack_exact_window
                value['longitudinal']['diagnostic_incident']=unpack_exact_window(incident)
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
        if 'diagnostic_inputs_storage' in value:
            value['diagnostic_consumed_inputs']=_expand_values(value.pop('diagnostic_inputs_storage'))
            if value['diagnostic_consumed_inputs'].get('_exact_record_window')==1:
                from core.navigation.longitudinal_diagnostics import unpack_exact_window
                value['diagnostic_consumed_inputs']=unpack_exact_window(value['diagnostic_consumed_inputs'])
        result.update(integrity_valid=True, replay=value)
        if _cache is not None:_cache.put(cache_key,len(raw),result)
    except (OSError, ValueError, KeyError, TypeError, RecursionError,zlib.error) as error:
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


def incident_diagnostic_budget(directory):
    """Worker/preflight only. Explicit active/archive budgets, never a drive gate."""
    import shutil
    from pathlib import Path
    root=Path(directory)
    active=list(root.glob('incident-*.json'))
    archived=list((root/'archive').rglob('*')) if (root/'archive').exists() else []
    active_parts=set(active)|set(root.glob('incident-*.md'))|set(root.glob('incident-*.pending-*'))|set(root.glob('steering-replay-*-diagnostic_incident.json'))|set(root.glob('steering-replay-*-devinputs.json'))|set(root.glob('ap-inputs-*.json'))
    used=sum(p.stat().st_size for p in active_parts)
    archive_bytes=sum(p.stat().st_size for p in archived if p.is_file())
    free=shutil.disk_usage(root if root.exists() else root.parent).free
    return dict(ready=free>=128*1024*1024 and archive_bytes<512*1024*1024,
        free_bytes=free,active_bytes=used,active_limit_bytes=128*1024*1024,
        archive_bytes=archive_bytes,archive_limit_bytes=512*1024*1024,
        maximum_active_incidents=8,runtime_authorized=False)


def _window_pedal_detail(window):
    """Exact call lineage in this incident; short safety-tail loss stays separate."""
    records=window.get('records') or []
    sources={(r.get('stream_id'),r.get('sequence')):r for r in records if r.get('kind')=='pedal_binding'}
    calls=[r['value'] for r in records if r.get('kind')=='backend_call']
    sequences=[r['sequence'] for r in calls]
    missing=sum(1 for call in calls if not call.get('decision_reference')
        or tuple(call['decision_reference']) not in sources)
    all_rows={(r.get('stream_id'),r.get('sequence')):r for r in records}
    missing_inputs=sum(1 for source in sources.values()
        for ref in (source['value'].get('consumed_input_references') or {}).values()
        if not ref or tuple(ref) not in all_rows)
    ordered=all(a<b for a,b in zip(sequences,sequences[1:]))
    gaps=sum(max(0,b-a-1) for a,b in zip(sequences,sequences[1:]))
    invalid=sum(1 for call in calls if call.get('channel') not in ('throttle','brake')
        or not isinstance(call.get('call_started_at_s'),(int,float))
        or not isinstance(call.get('call_returned_at_s'),(int,float))
        or call['call_returned_at_s']<call['call_started_at_s'])
    start=calls[0]['call_started_at_s'] if calls else None
    end=calls[-1]['call_returned_at_s'] if calls else None
    return dict(incomplete=bool(not calls or missing or missing_inputs or gaps or invalid or not ordered
            or window.get('capacity_drops') or window.get('capture_failures')),
        event_count=len(calls),first_sequence=sequences[0] if sequences else None,
        last_sequence=sequences[-1] if sequences else None,missing_decision_references=missing,
        missing_consumed_input_references=missing_inputs,
        missing_call_sequences=gaps,invalid_calls=invalid,ordered=ordered,
        detail_evidence=dict(start_s=start,end_s=end,duration_s=None if start is None else end-start,
            sampling='every physical pedal call; immutable binding reference',game_consumption_verified=False))


def inspect_incident(path, *, _verified_replays=None):
    """One dossier's integrity does not qualify a drive or runtime authority."""
    from pathlib import Path
    try:
        main=Path(path);value=json.loads(main.read_text(encoding='utf-8'))
        if value.get('integrity')!={'algorithm':'sha256','payload_sha256':_payload_hash(value)}:
            raise ValueError('INCIDENT_HASH_MISMATCH')
        assembly_of=value.get('assembly_of')
        if assembly_of:
            if (Path(assembly_of['name']).name!=assembly_of['name']
                    or assembly_of['name']==main.name):raise ValueError('INCIDENT_ASSEMBLY_PATH')
            original_raw=(main.parent/assembly_of['name']).read_bytes()
            if hashlib.sha256(original_raw).hexdigest()!=assembly_of['sha256']:
                raise ValueError('INCIDENT_ASSEMBLY_ORIGINAL_HASH')
            original=json.loads(original_raw)
            if (original.get('assembly_of') or original.get('integrity',{}).get('payload_sha256')!=_payload_hash(original)
                    or any(original.get(k)!=value.get(k) for k in
                        ('incident_id','replay','range_s','first_reason','subevents','episode'))):
                raise ValueError('INCIDENT_ASSEMBLY_ORIGINAL_MISMATCH')
        for row in value['files']:
            if Path(row['name']).name!=row['name']:raise ValueError('INCIDENT_PATH')
            raw=(main.parent/row['name']).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('INCIDENT_PART_HASH')
        replay=(inspect_replay(main.parent/value['replay']) if _verified_replays is None else
            inspect_replay(main.parent/value['replay'],_cache=_verified_replays))
        if not replay['integrity_valid']:raise ValueError('INCIDENT_REPLAY_INVALID')
        def raw_integrity(item):
            if isinstance(item,dict):
                if item.get('encoding')=='zlib-base64':
                    import base64,zlib
                    length=item['raw_bytes']
                    if type(length) is not int or not 0<=length<=512*1024:raise ValueError('INCIDENT_RAW_SIZE')
                    decoded=zlib.decompressobj().decompress(base64.b64decode(item['data'],validate=True),length+1)
                    if len(decoded)!=length or hashlib.sha256(decoded).hexdigest()!=item['raw_sha256']:
                        raise ValueError('INCIDENT_RAW_HASH')
                else:
                    for child in item.values():raw_integrity(child)
            elif isinstance(item,list):
                for child in item:raw_integrity(child)
        raw_integrity((replay['replay'].get('longitudinal') or {}).get('diagnostic_incident'))
        raw_integrity(value)  # Native bytes can also occur in event receipts.
        window=(replay['replay'].get('longitudinal') or {}).get('diagnostic_incident') or {}
        if value.get('complete') or value.get('part_complete'):
            # Independently check actual periodic observations, not just the
            # producer's flags/endpoints. Consumers/calls are event-driven.
            streams={}
            for row in window.get('records',()):
                if row.get('kind') in ('ego','traffic','signal_native','output_summary'):
                    streams.setdefault(row['kind'],[]).append(row['at_s'])
            if any(b-a>.25 for times in streams.values() for a,b in zip(times,times[1:])):
                raise ValueError('INCIDENT_INTERNAL_OBSERVATION_GAP')
        detail=value.get('component_completeness',{}).get('backend_detail') or {}
        if detail.get('storage')=='full_incident_window':
            actual=_window_pedal_detail(window)
            if any(actual.get(k)!=detail.get(k) for k in actual):raise ValueError('INCIDENT_PEDAL_LINEAGE')
        parts=value.get('parts')
        episode=value.get('episode') or {}
        previous=value.get('previous_part')
        if episode:
            if value.get('complete') and (episode.get('continues') or not value.get('episode_complete')):
                raise ValueError('INCIDENT_EPISODE_NOT_CLOSED')
            previous_parent=main.parent;chain_parts=0
            while previous:
                chain_parts+=1
                if chain_parts>256:raise ValueError('INCIDENT_EPISODE_CHAIN_LIMIT')
                candidate=(previous_parent/previous['name']).resolve()
                if not candidate.is_relative_to(previous_parent.resolve()):raise ValueError('INCIDENT_PREVIOUS_PART_PATH')
                if not candidate.exists():
                    # Exact original hash/id, recoverably rotated by this same
                    # bounded store. Do not rewrite a signed prior reference.
                    root=previous_parent.parent.parent if previous_parent.parent.name=='archive' else previous_parent
                    candidates=[root/Path(previous['name']).name]
                    candidates+=list((root/'archive').glob('*/'+Path(previous['name']).name))
                    candidate=next((p for p in candidates if p.exists() and
                        hashlib.sha256(p.read_bytes()).hexdigest()==previous['sha256']),candidate)
                if hashlib.sha256(candidate.read_bytes()).hexdigest()!=previous['sha256']:
                    raise ValueError('INCIDENT_PREVIOUS_PART_HASH')
                prior=json.loads(candidate.read_text(encoding='utf-8'))
                if (_payload_hash(prior)!=prior.get('integrity',{}).get('payload_sha256') or
                        prior.get('episode',{}).get('id')!=episode['id'] or
                        prior.get('episode',{}).get('part')!=episode['part']-1):
                    raise ValueError('INCIDENT_PREVIOUS_PART_IDENTITY')
                if value.get('complete') and (prior.get('part_complete') is not True or
                        (prior['episode'].get('part',0)>0 and prior.get('episode_chain_complete') is not True)):
                    raise ValueError('INCIDENT_PREVIOUS_PART_INCOMPLETE')
                # A valid previous manifest is not proof that its attached
                # evidence still exists. Verify the immutable file hashes too.
                # Disk quotas bound the store; do not accept an absent part as
                # a newer packet or an intact manifest standing in for data.
                for attachment in prior.get('files',[]):
                    attached=(candidate.parent/attachment['name']).resolve()
                    if not attached.is_relative_to(candidate.parent.resolve()):raise ValueError('INCIDENT_PREVIOUS_ATTACHMENT_PATH')
                    if hashlib.sha256(attached.read_bytes()).hexdigest()!=attachment['sha256']:
                        raise ValueError('INCIDENT_PREVIOUS_ATTACHMENT_HASH')
                episode=prior['episode'];previous=prior.get('previous_part');previous_parent=candidate.parent
                if episode.get('part',0)>0 and not previous:raise ValueError('INCIDENT_PREVIOUS_PART_MISSING')
            if episode.get('previous_incident_id') and value.get('complete'):
                raise ValueError('INCIDENT_PREVIOUS_PART_MISSING')
        if value.get('complete') and (value.get('incomplete') or not value.get('assembly_complete')):
            raise ValueError('INCIDENT_FALSE_COMPLETE')
        if value.get('assembly_complete') and not (parts or {}).get('autopilot',{}).get('verified'):
            raise ValueError('INCIDENT_REQUIRED_PART_MISSING')
        if parts is not None and parts.get('autopilot',{}).get('verified'):
            window=(replay['replay'].get('longitudinal') or {}).get('diagnostic_incident') or {}
            request=window.get('required_autopilot_part')
            checked=(inspect_autopilot_part(main.parent/parts['autopilot']['name'],request,window)
                if _verified_replays is None else inspect_autopilot_part(
                    main.parent/parts['autopilot']['name'],request,window,_verified_replays=_verified_replays))
            if not checked['verified']:raise ValueError('INCIDENT_AP_PART_INVALID')
            if not any(r['name']==checked['name'] and r['sha256']==checked['sha256'] for r in value['files']):
                raise ValueError('INCIDENT_AP_NOT_ATTACHED')
            if value.get('assembly_complete') and not checked['coverage_verified']:
                raise ValueError('INCIDENT_AP_COVERAGE_MISMATCH')
            if value.get('complete') and (not checked['complete'] or any(
                    (value.get('component_completeness',{}).get(k) or {}).get('incomplete',True)
                    for k in ('engine_window','backend_detail','decision_summary'))):
                raise ValueError('INCIDENT_INCOMPLETE_COMPONENT')
        return dict(integrity_valid=True,confirmed=False,runtime_authorized=False,
            incomplete=value['incomplete'],complete=value.get('complete',False),
            assembly_complete=value.get('assembly_complete',False),dossier=value,replay=replay['replay'])
    except (OSError,ValueError,KeyError,TypeError,RecursionError,zlib.error) as error:
        return dict(integrity_valid=False,complete=False,assembly_complete=False,
            confirmed=False,runtime_authorized=False,reason=str(error))


def _command_evidence_key(packet):
    if not isinstance(packet,dict):return None
    fields=('context','sdk_frame_us','observation_timestamp','computed_at')
    if any(packet.get(k) is None for k in fields):return None
    # The key includes the entire consumed command, not merely nearby times.
    return json.dumps(packet,sort_keys=True,separators=(',',':'),allow_nan=False)


def inspect_autopilot_part(path, request, window=None, *, _verified_replays=None):
    from pathlib import Path
    result=dict(verified=False,coverage_verified=False,complete=False,incident_id=(request or {}).get('incident_id'))
    try:
        if not isinstance(request,dict) or request.get('phase')!='seal':raise ValueError('AP_SEAL_REQUEST_MISSING')
        checked=(inspect_replay(path) if _verified_replays is None else
            inspect_replay(path,_cache=_verified_replays))
        if not checked['integrity_valid']:raise ValueError('AP_PART_INTEGRITY')
        replay=checked['replay'];identity=replay.get('identity') or {}
        source=replay.get('diagnostic_consumed_inputs') or {}
        if identity.get('part_request')!=request:raise ValueError('AP_PART_REQUEST_OR_RANGE_MISMATCH')
        if identity.get('frozen_snapshot_sha256')!=_payload_hash(_json_value(source)):
            raise ValueError('AP_PART_SNAPSHOT_MISMATCH')
        records=source.get('records') or []
        keys=[];commands=set();failures=source.get('capture_failures',0)
        for row in records:
            keys.append((row.get('stream_id'),row['sequence']))
            value=row.get('value') or {}
            failures+=value.get('capture_failures',0)
            key=_command_evidence_key(value.get('command'))
            if key:commands.add(key)
        if len(keys)!=len(set(keys)) or any(a['at_s']>b['at_s'] for a,b in zip(records,records[1:])):
            raise ValueError('AP_PART_RECORD_ORDER')
        required=set();unpaired=0
        for row in (window or {}).get('records',[]):
            if row['kind']!='consumer_command_pair':continue
            packet=(row.get('value') or {}).get('command')
            if not packet:continue
            key=_command_evidence_key(packet)
            if key:required.add(key)
            else:unpaired+=1
        missing=required-commands
        coverage=bool(records) and not missing and not unpaired
        complete=coverage and not (failures or source.get('capacity_drops') or source.get('shutdown_before_seal'))
        return dict(result,verified=True,coverage_verified=coverage,complete=complete,
            name=Path(path).name,sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            token=request['token'],required_command_count=len(required),missing_command_count=len(missing),
            unpairable_command_count=unpaired,capture_failures=failures,
            capacity_drops=source.get('capacity_drops',0),record_count=len(records),
            actual_start_s=min((r['at_s'] for r in records),default=None),
            actual_end_s=max((r['at_s'] for r in records),default=None),
            reason=None if complete else 'AP_PART_COVERAGE_OR_CAPTURE_INCOMPLETE')
    except (OSError,ValueError,KeyError,TypeError,RecursionError) as error:
        return dict(result,reason=str(error))


def _await_autopilot_part(directory,window,wait_s=20.):
    """Only export child polls disk; this is not a control/evidence timeout."""
    from pathlib import Path
    request=window.get('required_autopilot_part')
    if not request:return dict(required=False,verified=False,coverage_verified=False,reason='AP_PART_NOT_REQUESTED')
    path=Path(directory)/('ap-inputs-'+request['incident_id']+'.json')
    failed=path.with_suffix('.failed.json')
    deadline=time.perf_counter()+wait_s
    while True:
        if path.exists():return dict(inspect_autopilot_part(path,request,window),required=True)
        if failed.exists():return dict(required=True,verified=False,coverage_verified=False,
            complete=False,incident_id=request['incident_id'],reason='AP_PART_EXPORT_FAILED')
        if time.perf_counter()>=deadline:
            return dict(required=True,verified=False,coverage_verified=False,complete=False,
                incident_id=request['incident_id'],reason='AP_PART_NOT_DELIVERED_WITHIN_ASSEMBLY_WINDOW')
        time.sleep(.02)


def _archive_incidents(directory, *, reserve_bytes):
    from pathlib import Path
    import shutil
    root=Path(directory);root.mkdir(parents=True,exist_ok=True)
    budget=incident_diagnostic_budget(root)
    if not budget['ready']:raise ValueError('INCIDENT_DISK_OR_ARCHIVE_BUDGET')
    for main in sorted(root.glob('incident-*.json'),key=lambda p:p.stat().st_mtime):
        if not main.exists():continue  # Its exact late-assembly group moved together.
        budget=incident_diagnostic_budget(root)
        if len(list(root.glob('incident-*.json')))<8 and budget['active_bytes']+reserve_bytes<=budget['active_limit_bytes']:break
        verified=inspect_incident(main)
        if not verified['integrity_valid']:raise ValueError('INCIDENT_ARCHIVE_SOURCE_INVALID')
        names={r['name'] for r in verified['dossier']['files']}|{main.name}
        # Original and immutable late resolution share attachments. Archive
        # them as one verified group, never strand a signed original reference.
        related=main.with_name(main.stem+'-assembled.json')
        if related.exists():
            resolution=inspect_incident(related)
            if not resolution['integrity_valid']:raise ValueError('INCIDENT_ARCHIVE_SOURCE_INVALID')
            names.update(r['name'] for r in resolution['dossier']['files']);names.add(related.name)
        names=sorted(names)
        size=sum((root/n).stat().st_size for n in names)
        if budget['archive_bytes']+size>budget['archive_limit_bytes']:
            raise ValueError('INCIDENT_ARCHIVE_BUDGET')
        target=root/'archive'/main.stem;target.mkdir(parents=True,exist_ok=False)
        moved=[]
        try:
            for name in names:
                shutil.move(str(root/name),str(target/name));moved.append(name)
            if not inspect_incident(target/main.name)['integrity_valid']:raise ValueError('INCIDENT_ARCHIVE_INTEGRITY')
            if related.exists() or related.name in names:
                if not inspect_incident(target/related.name)['integrity_valid']:raise ValueError('INCIDENT_ARCHIVE_ASSEMBLY_INTEGRITY')
        except Exception:
            for name in reversed(moved):shutil.move(str(target/name),str(root/name))
            raise
    budget=incident_diagnostic_budget(root)
    # Standalone dense input replays count against active bytes too. They may
    # never receive a main incident (manual disable, failed Engine export).
    # Preserve them recoverably, with their original bytes and signed hash;
    # do not move AP prerequisites or any attachment named by a live dossier.
    # This runs only inside the existing serialized export boundary.
    if budget['active_bytes']+reserve_bytes>budget['active_limit_bytes']:
        referenced=set()
        for main in root.glob('incident-*.json'):
            value=json.loads(main.read_text(encoding='utf-8'))
            referenced.update(r['name'] for r in value.get('files',()))
        for path in sorted(root.glob('steering-replay-*-devinputs.json'),key=lambda p:p.stat().st_mtime):
            if path.name in referenced:continue
            budget=incident_diagnostic_budget(root)
            if budget['active_bytes']+reserve_bytes<=budget['active_limit_bytes']:break
            raw=path.read_bytes();value=json.loads(raw)
            if (value.get('schema_version')!=SCHEMA_VERSION or value.get('integrity')!=dict(
                    algorithm='sha256',payload_sha256=_payload_hash(value))):
                raise ValueError('INCIDENT_STANDALONE_ARCHIVE_SOURCE_INVALID')
            if budget['archive_bytes']+len(raw)>budget['archive_limit_bytes']:
                raise ValueError('INCIDENT_ARCHIVE_BUDGET')
            digest=hashlib.sha256(raw).hexdigest()
            target=root/'archive'/('standalone-'+digest)
            target.mkdir(parents=True,exist_ok=False)
            destination=target/path.name
            try:
                shutil.move(str(path),str(destination))
                if hashlib.sha256(destination.read_bytes()).hexdigest()!=digest:
                    raise ValueError('INCIDENT_STANDALONE_ARCHIVE_READBACK')
            except Exception:
                if destination.exists():shutil.move(str(destination),str(path))
                raise
        budget=incident_diagnostic_budget(root)
    if budget['active_bytes']+reserve_bytes>budget['active_limit_bytes']:
        raise ValueError('INCIDENT_ACTIVE_BUDGET_REQUIRES_PARTIAL_REVIEW')


def export_incident(directory, window, journal):
    """Called ONLY by the existing background exporter. Manifest is committed last.

    Closed dossiers are hash-verified then moved recoverably into archive; no
    deletion, compression on the control tick or unrelated replay rotation.
    """
    from pathlib import Path
    import base64
    import zlib
    from core.navigation.longitudinal_diagnostics import expand_incident_window,diagnostic_build_limits
    window=expand_incident_window(window)
    root=Path(directory);root.mkdir(parents=True,exist_ok=True)
    verified_replays=_ReplayVerificationCache()
    file_limit=diagnostic_build_limits()['engine_file_bytes']
    _archive_incidents(root,reserve_bytes=file_limit)
    def encode(item):
        if isinstance(item,bytes):
            return dict(encoding='zlib-base64',raw_bytes=len(item),
                raw_sha256=hashlib.sha256(item).hexdigest(),data=base64.b64encode(zlib.compress(item)).decode('ascii'))
        if isinstance(item,dict):return {k:encode(v) for k,v in item.items()}
        if isinstance(item,(list,tuple)):return [encode(v) for v in item]
        return item
    name='incident-'+window['incident_id']
    main=root/(name+'.json')
    if main.exists():raise ValueError('INCIDENT_OVERWRITE_FORBIDDEN')
    # Full native metadata and changing decision trees can exceed the existing
    # 16 MiB file ceiling even though retained input fits its fixed budget.
    # Compress the existing exact immutable JSON stream on this EXPORT worker;
    # neither truncate evidence nor enlarge the file/memory budgets.
    if window.get('record_format')=='simple-exact-record':
        from core.navigation.longitudinal_diagnostics import pack_exact_window
        incident_storage=pack_exact_window(window)
    else:incident_storage=encode(window)
    if len(window['records'])>=256:
        raw=json.dumps(_intern_values(_json_value(incident_storage)),ensure_ascii=False,
            sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
        if len(raw)>64*1024*1024:raise ValueError('INCIDENT_JSON_SIZE')
        incident_storage=dict(encoding='zlib-immutable-json-v1',raw_bytes=len(raw),
            raw_sha256=hashlib.sha256(raw).hexdigest(),data=base64.b64encode(zlib.compress(raw,
                6 if window.get('record_format')=='simple-exact-record' else 1)).decode('ascii'))
    replay=SteeringReplayBuffer(2).export(root,reason='diagnostic_incident',
        sample_kind='temporary_diagnostic_build',identity={'incident_id':window['incident_id']},
        longitudinal=dict(journal,diagnostic_incident=incident_storage),maximum_output_bytes=file_limit,
        _diagnostic_child=True)
    if not replay:raise ValueError('INCIDENT_REPLAY_MISSING')
    if not inspect_replay(replay)['integrity_valid']:raise ValueError('INCIDENT_REPLAY_READBACK_FAILED')
    overview=root/(name+'.md')
    text=('# Temporary diagnostic incident\n\n'+
        f"ID: {window['incident_id']}\n\nFirst reason: {window['first_reason']}\n\n"+
        f"Actual range: {window['range_s']}\n\nEngine window incomplete: {window['incomplete']}\n\n"+
        'Dossier completeness is determined only by the final verified JSON manifest and all component counters.\n\n'+
        'Backend return is not game consumption. No runtime authority or successful-drive verdict.\n')
    if overview.exists():
        if overview.read_text(encoding='utf-8')!=text:raise ValueError('INCIDENT_OVERWRITE_FORBIDDEN')
    else:
        with overview.open('x',encoding='utf-8') as stream:stream.write(text)
    files=[dict(name=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in (Path(replay),overview)]
    ap=window.get('autopilot_part_result') or _await_autopilot_part(root,window,wait_s=0.)
    if ap.get('verified'):files.append(dict(name=ap['name'],sha256=ap['sha256']))
    assembly_complete=bool(ap.get('verified') and ap.get('coverage_verified'))
    history=journal.get('decision_history') or {}
    components=dict(engine_window=dict(incomplete=bool(window['incomplete']),
            capacity_drops=window.get('capacity_drops'),capture_failures=window.get('capture_failures')),
        backend_detail=dict(incomplete=bool(journal.get('snapshot_incomplete') or journal.get('dropped_events')),
            dropped_events=journal.get('dropped_events'),detail_evidence=journal.get('detail_evidence')),
        decision_summary=dict(incomplete=bool(history.get('incomplete')),capture_failures=history.get('capture_failures')),
        autopilot=ap)
    if any(r.get('kind')=='backend_call' for r in window['records']):
        components['legacy_safety_tail']=components['backend_detail']
        components['backend_detail']=dict(_window_pedal_detail(window),storage='full_incident_window')
    complete=assembly_complete and bool(ap.get('complete')) and not any(
        components[k]['incomplete'] for k in ('engine_window','backend_detail','decision_summary'))
    episode=window.get('episode')
    episode_link=None;part_complete=complete;part_assembled=assembly_complete
    if episode:
        previous=episode.get('previous_incident_id')
        linked=True
        if previous:
            # The same serial exporter finished the preceding part first.
            # Rotation may have moved it recoverably to the bounded archive.
            # AP can finish before THIS Engine export, after the preceding
            # original manifest timed out. Its verified immutable resolution
            # is the chain predecessor; never bless/rewrite that original.
            candidates=[root/('incident-'+previous+'-assembled.json'),root/('incident-'+previous+'.json')]
            candidates+=list((root/'archive').glob('*/incident-'+previous+'-assembled.json'))
            candidates+=list((root/'archive').glob('*/incident-'+previous+'.json'))
            prior=next((p for p in candidates if p.exists()),None)
            linked=False
            if prior:
                if not inspect_incident(prior,_verified_replays=verified_replays)['integrity_valid']:
                    raise ValueError('INCIDENT_PREDECESSOR_INVALID')
                prior_data=json.loads(prior.read_text(encoding='utf-8'))
                prior_ep=prior_data.get('episode') or {}
                linked=(_payload_hash(prior_data)==prior_data.get('integrity',{}).get('payload_sha256')
                    and prior_ep.get('id')==episode['id'] and prior_ep.get('part')==episode['part']-1
                    and prior_data.get('part_complete') is True
                    and (prior_ep.get('part')==0 or prior_data.get('episode_chain_complete') is True))
                episode_link=dict(name=prior.relative_to(root).as_posix(),
                    sha256=hashlib.sha256(prior.read_bytes()).hexdigest(),verified=linked,
                    preceding_end_s=(prior_data.get('range_s') or {}).get('end_s'))
                linked=linked and (window['range_s']['start_s'] is not None and
                    episode_link['preceding_end_s'] is not None and
                    window['range_s']['start_s']<=episode_link['preceding_end_s'])
        assembly_complete=assembly_complete and linked and not episode.get('continues')
        complete=complete and assembly_complete
    value=dict(schema_version=1,build='UP-DIAGNOSTIC-20261025-07',incident_id=window['incident_id'],
        first_reason=window['first_reason'],subevents=window['subevents'],range_s=window['range_s'],
        incomplete=not complete,complete=complete,assembly_complete=assembly_complete,
        parts=dict(engine=dict(verified=True,name=Path(replay).name),autopilot=ap),
        component_completeness=components,files=files,replay=Path(replay).name,
        confirmed=False,runtime_authorized=False,game_verified=False)
    if episode:value.update(episode=episode,previous_part=episode_link,
        part_complete=part_complete,part_assembly_complete=part_assembled,
        episode_chain_complete=bool(part_complete and linked),episode_complete=complete)
    # Pair Engine/AP files by the preserved intervention, never filename order.
    # These are references to original evidence, not files moved by rotation.
    first=(window.get('first_intervention') or {}).get('receipt') or {}
    related=[]
    if first.get('epoch') is not None and first.get('observed_at') is not None:
        candidates=sorted(root.glob('steering-replay-*-automatic_disable*.json'),
            key=lambda p:p.stat().st_mtime,reverse=True)[:8]
        for path in candidates:
            checked=inspect_replay(path)
            if not checked['integrity_valid']:continue
            data=checked['replay']
            cause=(data.get('identity') or {}).get('control_intervention') or (
                data.get('longitudinal') or {}).get('first_intervention') or {}
            if cause.get('epoch')==first['epoch'] and cause.get('observed_at')==first['observed_at']:
                related.append(dict(name=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    incident_id=window['incident_id'],match='exact intervention epoch and observed_at'))
                if path.name.endswith('-devinputs.json'):
                    value['files'].append(dict(name=path.name,sha256=related[-1]['sha256']))
    value['related_original_exports']=related
    value=encode(value)  # The same exact raw-byte codec as the incident replay.
    value['integrity']=dict(algorithm='sha256',payload_sha256=_payload_hash(value))
    temporary=main.with_suffix('.pending-'+uuid.uuid4().hex)
    with temporary.open('x',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,allow_nan=False);stream.flush();os.fsync(stream.fileno())
    if main.exists():raise ValueError('INCIDENT_OVERWRITE_FORBIDDEN')
    os.replace(temporary,main)
    if not inspect_incident(main,_verified_replays=verified_replays)['integrity_valid']:raise ValueError('INCIDENT_READBACK_FAILED')
    return str(main)


@contextmanager
def _diagnostic_disk_lock(directory, *, name='.diagnostic-export.lock'):
    """Only export children wait here; never share this lock with controls."""
    from pathlib import Path
    root=Path(directory);root.mkdir(parents=True,exist_ok=True)
    if name not in ('.diagnostic-export.lock','.diagnostic-export-admission.lock'):
        raise ValueError('DIAGNOSTIC_LOCK_NAME')
    with (root/name).open('a+b') as lock:
        if lock.seek(0,os.SEEK_END)==0:lock.write(b'\0');lock.flush()
        deadline=time.perf_counter()+45.
        while True:
            try:
                lock.seek(0)
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except OSError:
                if time.perf_counter()>=deadline:raise TimeoutError('DIAGNOSTIC_DISK_LOCK_TIMEOUT')
                time.sleep(.02)
        try:yield
        finally:
            lock.seek(0)
            if os.name=='nt':msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(lock,fcntl.LOCK_UN)


def _incident_export_child(directory, window, journal, connection):
    try:
        from core.navigation.longitudinal_diagnostics import expand_incident_window
        window=expand_incident_window(window)
        from pathlib import Path
        request=window.get('required_autopilot_part') or {}
        part=Path(directory)/('ap-inputs-'+str(request.get('incident_id'))+'.json')
        if window.get('ap_parent_wait_expired') and not part.exists() and not part.with_suffix('.failed.json').exists():
            ap=dict(required=True,verified=False,coverage_verified=False,complete=False,
                incident_id=request.get('incident_id'),reason='AP_PART_NOT_DELIVERED_WITHIN_ASSEMBLY_WINDOW')
        else:ap=_await_autopilot_part(directory,window,wait_s=0.)
        window=dict(window,autopilot_part_result=ap)
        with _diagnostic_disk_lock(directory):path=export_incident(directory,window,journal)
        with open(path,'rb') as stream:manifest_sha=hashlib.sha256(stream.read()).hexdigest()
        connection.send(dict(path=path,manifest_sha256=manifest_sha,integrity_valid=True))
    except Exception as error:connection.send(dict(error=type(error).__name__,detail=str(error)[:256]))
    finally:connection.close()


class _SealedDiagnosticInputs:
    def __init__(self,value):self.value=value
    def rolling_snapshot(self):return self.value


def export_autopilot_part(directory, snapshot):
    """Existing replay codec, exact sealed range, atomic deterministic part.

    Worker-only. A repeated token never replaces a different frozen payload.
    """
    from pathlib import Path
    # Retention uses exact compressed transactions in the same bounded ring.
    # Expand only on the export worker; the existing codec then interns values.
    simple_records=any((r.get('value') or {}).get('record_codec') in ('marshal2-exact-v1','pickle5-primitives-v1')
        for r in snapshot['records'])
    rows=[]
    for row in snapshot['records']:
        from core.navigation.longitudinal_diagnostics import _IncidentWindow
        row=_IncidentWindow.expanded_row(row)
        value=row.get('value') or {}
        if value.get('encoding')=='ap-transaction-zlib-v1':
            length=value['raw_bytes']
            if type(length) is not int or not 0<=length<=512*1024:raise ValueError('AP_TRANSACTION_SIZE')
            raw=zlib.decompressobj().decompress(value['blob'],length+1)
            if len(raw)!=length or hashlib.sha256(raw).hexdigest()!=value['raw_sha256']:
                raise ValueError('AP_TRANSACTION_HASH')
            row=dict(row,value=json.loads(raw))
        rows.append(row)
    snapshot=dict(snapshot,records=rows)
    semantic_digest=_payload_hash(_json_value(snapshot))
    if simple_records:
        from core.navigation.longitudinal_diagnostics import pack_exact_window
        snapshot=pack_exact_window(snapshot)
    request=snapshot['request'];incident_id=request['incident_id']
    if not re.fullmatch(r'[a-f0-9]{32}-[0-9]+',incident_id):raise ValueError('AP_PART_ID')
    root=Path(directory);root.mkdir(parents=True,exist_ok=True)
    target=root/('ap-inputs-'+incident_id+'.json')
    digest=semantic_digest
    if target.exists():
        checked=inspect_replay(target)
        if (not checked['integrity_valid'] or
                checked['replay'].get('identity',{}).get('frozen_snapshot_sha256')!=digest):
            raise ValueError('AP_PART_OVERWRITE_FORBIDDEN')
        return str(target)
    replay=SteeringReplayBuffer(2)
    replay._diagnostic_inputs=_SealedDiagnosticInputs(snapshot)
    # An explicitly non-control row makes the existing codec export even an
    # empty/incomplete shutdown part; no invented control input is introduced.
    replay.append(dict(diagnostic_part_only=True))
    path=replay.export(root,reason='autopilot_part',identity=dict(incident_id=incident_id,
        part_request=request,frozen_snapshot_sha256=digest),
        maximum_output_bytes=32*1024*1024,_diagnostic_child=True)
    if not path or not inspect_replay(path)['integrity_valid']:raise ValueError('AP_PART_READBACK')
    if target.exists():raise ValueError('AP_PART_OVERWRITE_FORBIDDEN')
    os.replace(path,target)
    return str(target)


def complete_incident_assembly(directory, incident_id):
    """Existing export child only: one immutable late-attachment resolution.

    Never reopens a timeout or rewrites original evidence. Identity, original
    hash, exact AP seal/range/commands, component losses and predecessor chain
    remain mandatory. One file per existing case, inside the same disk quota.
    No polling, new process, queue, control RPC or control-thread operation.
    """
    from pathlib import Path
    import copy
    if not re.fullmatch(r'[a-f0-9]{32}-[0-9]+',str(incident_id)):
        raise ValueError('INCIDENT_ASSEMBLY_ID')
    root=Path(directory);main=root/('incident-'+incident_id+'.json')
    verified_replays=_ReplayVerificationCache()
    target=root/('incident-'+incident_id+'-assembled.json')
    if target.exists():
        if not inspect_incident(target,_verified_replays=verified_replays)['integrity_valid']:
            raise ValueError('INCIDENT_LATE_ASSEMBLY_INVALID')
        return str(target)
    if not main.exists():return None  # Engine can still attach the file normally.
    original=inspect_incident(main,_verified_replays=verified_replays)
    if not original['integrity_valid']:raise ValueError('INCIDENT_ORIGINAL_INVALID')
    if original['assembly_complete']:return None
    value=copy.deepcopy(original['dossier'])
    window=(original['replay'].get('longitudinal') or {}).get('diagnostic_incident') or {}
    request=window.get('required_autopilot_part')
    part=root/('ap-inputs-'+incident_id+'.json')
    if not part.exists():return None
    ap=dict(inspect_autopilot_part(part,request,window,_verified_replays=verified_replays),required=True)
    if not ap['verified'] or not ap['coverage_verified']:return None
    # Integrity/coverage is assembly, NOT completeness. Original component
    # failures and original AP capture failures cannot be erased by arrival.
    value['parts']['autopilot']=ap
    components=value['component_completeness'];components['autopilot']=ap
    value['files'].append(dict(name=ap['name'],sha256=ap['sha256']))
    value['assembly_of']=dict(name=main.name,sha256=hashlib.sha256(main.read_bytes()).hexdigest())
    value['files'].append(dict(value['assembly_of']))
    part_complete=bool(ap['complete'] and not any(components[k]['incomplete']
        for k in ('engine_window','backend_detail','decision_summary')))
    episode=value.get('episode') or {};linked=True
    previous=value.get('previous_part')
    if episode.get('previous_incident_id'):
        linked=False
        if previous:
            prior=root/previous['name']
            # Prefer an exactly linked late resolution of this original part.
            resolved=prior.with_name(prior.stem+'-assembled.json')
            if resolved.exists():prior=resolved
            checked=inspect_incident(prior,_verified_replays=verified_replays)
            prior_value=checked.get('dossier') or {}
            prior_ep=prior_value.get('episode') or {}
            linked=bool(checked['integrity_valid'] and prior_value.get('part_complete')
                and prior_ep.get('id')==episode['id'] and prior_ep.get('part')==episode['part']-1
                and (prior_ep.get('part')==0 or prior_value.get('episode_chain_complete'))
                and window['range_s']['start_s']<=prior_value['range_s']['end_s'])
            if linked:value['previous_part']=dict(name=prior.relative_to(root).as_posix(),
                sha256=hashlib.sha256(prior.read_bytes()).hexdigest(),verified=True,
                preceding_end_s=prior_value['range_s']['end_s'])
    assembled=bool(linked and not episode.get('continues'))
    complete=part_complete and assembled
    value.update(assembly_complete=assembled,complete=complete,incomplete=not complete,
        confirmed=False,runtime_authorized=False,game_verified=False)
    if episode:value.update(part_complete=part_complete,part_assembly_complete=True,
        episode_chain_complete=bool(part_complete and linked),episode_complete=complete)
    value.pop('integrity',None)
    value['integrity']=dict(algorithm='sha256',payload_sha256=_payload_hash(value))
    raw=json.dumps(value,ensure_ascii=False,allow_nan=False).encode('utf-8')
    budget=incident_diagnostic_budget(root)
    if (not budget['ready'] or budget['active_bytes']+len(raw)>budget['active_limit_bytes']):
        raise ValueError('INCIDENT_LATE_ASSEMBLY_DISK_BUDGET')
    temporary=target.with_suffix('.pending-'+uuid.uuid4().hex)
    with temporary.open('xb') as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())
    if target.exists():raise ValueError('INCIDENT_OVERWRITE_FORBIDDEN')
    os.replace(temporary,target)
    if not inspect_incident(target,_verified_replays=verified_replays)['integrity_valid']:raise ValueError('INCIDENT_LATE_ASSEMBLY_READBACK')
    return str(target)


def _autopilot_part_child(directory,snapshot,connection):
    try:
        with _diagnostic_disk_lock(directory):
            path=export_autopilot_part(directory,snapshot)
            assembled=complete_incident_assembly(directory,snapshot['request']['incident_id'])
        with open(path,'rb') as stream:digest=hashlib.sha256(stream.read()).hexdigest()
        connection.send(dict(path=path,manifest_sha256=digest,integrity_valid=True,
            assembled_incident=assembled))
    except Exception as error:
        # No I/O on the controlling tick. Do not overwrite earlier failure proof.
        try:
            from pathlib import Path
            request=snapshot['request'];root=Path(directory)
            failures=list(root.glob('ap-inputs-*.failed.json'))
            if len(failures)<8 and sum(p.stat().st_size for p in failures)<64*1024:
                path=root/('ap-inputs-'+request['incident_id']+'.failed.json')
                with path.open('x',encoding='utf-8') as stream:
                    json.dump(dict(request=request,complete=False,error=type(error).__name__,
                        detail=str(error)[:256]),stream)
        except (OSError,KeyError):pass
        connection.send(dict(error=type(error).__name__,detail=str(error)[:256]))
    finally:connection.close()


def export_autopilot_part_isolated(directory,snapshot):
    return _run_diagnostic_export(_autopilot_part_child,(os.fspath(directory),snapshot))


def _replay_export_child(state,directory,options,connection):
    try:
        replay=SteeringReplayBuffer(state['capacity'])
        replay._samples.extend(state['samples'])
        replay._execution_samples.extend(state['executions'])
        replay._sequence=state['sequence'];replay._execution_sequence=state['execution_sequence']
        replay._diagnostic_inputs=_SealedDiagnosticInputs(state['inputs']) if state['inputs'] else None
        with _diagnostic_disk_lock(directory):path=replay.export(directory,**options,_diagnostic_child=True)
        if path is None:
            connection.send(dict(path=None,integrity_valid=True));return
        if not inspect_replay(path)['integrity_valid']:raise ValueError('DIAGNOSTIC_REPLAY_READBACK')
        with open(path,'rb') as stream:digest=hashlib.sha256(stream.read()).hexdigest()
        connection.send(dict(path=path,manifest_sha256=digest,integrity_valid=True))
    except Exception as error:connection.send(dict(error=type(error).__name__,detail=str(error)[:256]))
    finally:connection.close()


def export_replay_isolated(replay,directory,options):
    with replay._lock:
        state=dict(capacity=replay.capacity,samples=tuple(replay._samples),
            executions=tuple(replay._execution_samples),sequence=replay._sequence,
            execution_sequence=replay._execution_sequence)
    state['inputs']=replay._diagnostic_inputs.rolling_snapshot() if replay._diagnostic_inputs is not None else None
    return _run_diagnostic_export(_replay_export_child,(state,os.fspath(directory),options))


def export_incident_isolated(directory, window, journal):
    """One child for the existing one-job exporter, not a second collector.

    Large JSON/hash/compression work must not monopolize the control process's
    GIL. Invocation and argument transport happen on its existing background
    thread; no process/queue or serialization is started by the control tick.
    """
    # Wait in the EXISTING background submitter before admitting an Engine
    # child. Never occupy the sole child slot while waiting for the AP job
    # which must produce its prerequisite. This does not validate/complete the
    # part: the unchanged child performs all exact-input/hash checks.
    from pathlib import Path
    request=window.get('required_autopilot_part')
    if request:
        root=Path(directory);part=root/('ap-inputs-'+request['incident_id']+'.json')
        failed=part.with_suffix('.failed.json');deadline=time.perf_counter()+20.
        while not part.exists() and not failed.exists():
            if time.perf_counter()>=deadline:
                # Export an explicitly incomplete dossier without occupying
                # the sole child slot while waiting for another queued child.
                window=dict(window,ap_parent_wait_expired=True)
                break
            time.sleep(.02)
    return _run_diagnostic_export(_incident_export_child,(os.fspath(directory),window,journal))


_diagnostic_export_service=None


def configure_diagnostic_export(state):
    global _diagnostic_export_service
    proxy=getattr(state,'_state',None)
    if callable(getattr(proxy,'reserve_diagnostic_export',None)):
        _diagnostic_export_service=proxy
        return True
    return False


def _run_diagnostic_export(target,args):
    import multiprocessing
    service=_diagnostic_export_service
    if service is not None or multiprocessing.current_process().daemon:
        if service is None:raise RuntimeError('DIAGNOSTIC_EXPORT_SERVICE_UNAVAILABLE')
        # Existing background job owns its bounded immutable arguments while
        # waiting. Reserve before transferring any payload; only one Manager
        # export request can own a payload. Control never waits here.
        deadline=time.perf_counter()+45.;ticket=None
        while ticket is None:
            ticket=service.reserve_diagnostic_export()
            if ticket is None:
                if time.perf_counter()>=deadline:raise TimeoutError('DIAGNOSTIC_EXPORT_SERVICE_BUSY')
                time.sleep(.02)
        try:return service.diagnostic_export(ticket,target.__name__,args)
        finally:service.release_diagnostic_export(ticket)
    # One exporter process at a time across Engine/AP owners for this output
    # directory. Only their already bounded background jobs wait; no control
    # thread takes this lock and no new queue is introduced. On timeout the
    # existing owner retains/reports the failed sealed job, never silent loss.
    directory=args[0] if isinstance(args[0],(str,os.PathLike)) else args[1]
    with _diagnostic_disk_lock(directory,name='.diagnostic-export-admission.lock'):
        return _run_admitted_diagnostic_export(target,args)


def _shared_export_child(target,name,length,connection):
    """One bounded internal argument transfer; external evidence codec unchanged."""
    from multiprocessing.shared_memory import SharedMemory
    import pickle
    memory=SharedMemory(name=name,create=False)
    try:arguments=pickle.loads(bytes(memory.buf[:length]))
    finally:memory.close()
    target(*arguments,connection)


def _run_admitted_diagnostic_export(target,args):
    import multiprocessing
    from multiprocessing.shared_memory import SharedMemory
    import pickle
    context=multiprocessing.get_context('spawn')
    # Windows Process.start serializes its arguments synchronously. A child
    # dying during a large spawn-argument dump can leave the sender blocked
    # before the old completion deadline even starts. Own ONE capped internal
    # transfer in shared memory, then spawn with only a name/length/pipe. The
    # existing admission owns this mapping and always closes it on failure.
    raw=pickle.dumps(args,protocol=pickle.HIGHEST_PROTOCOL)
    if len(raw)>128*1024*1024:raise ValueError('INCIDENT_EXPORT_TRANSFER_BUDGET')
    transfer=SharedMemory(create=True,size=max(1,len(raw)))
    transfer.buf[:len(raw)]=raw;length=len(raw);del raw
    try:
        receive,send=context.Pipe(duplex=False)
        process=context.Process(target=_shared_export_child,
            args=(target,transfer.name,length,send),name='UltraPilot-IncidentExport',daemon=True)
    except BaseException:
        transfer.close();transfer.unlink();raise
    try:
        process.start();send.close()
        from core.navigation.longitudinal_diagnostics import diagnostic_build_limits
        limits=diagnostic_build_limits()
        if limits['approved']:
            # Existing export wait only; never on the control thread. Keep a
            # bounded worker failure/retry if expanded verification exceeds
            # the approved ceiling. RSS is sampled, not an OS reservation.
            import psutil
            try:child=psutil.Process(process.pid)
            except psutil.NoSuchProcess:child=None
            deadline=time.perf_counter()+60.
            while not receive.poll(.02):
                if not process.is_alive():raise RuntimeError('INCIDENT_EXPORT_WORKER_EXITED_WITHOUT_RESULT')
                try:
                    if child is not None and child.memory_info().rss>limits['export_child_rss_bytes']:
                        raise MemoryError('INCIDENT_EXPORT_WORKER_RSS_BUDGET')
                except psutil.NoSuchProcess:pass
                if time.perf_counter()>=deadline:raise TimeoutError('INCIDENT_EXPORT_WORKER_TIMEOUT')
        elif not receive.poll(60.):raise TimeoutError('INCIDENT_EXPORT_WORKER_TIMEOUT')
        result=receive.recv()
        process.join(2.)
        if process.is_alive():raise TimeoutError('INCIDENT_EXPORT_WORKER_EXIT_TIMEOUT')
        if result.get('error'):raise RuntimeError(result['error']+': '+result.get('detail',''))
        if result.get('path') is None:return None
        # The child already checked every replay/raw hash. Re-expanding the
        # large tree here would reintroduce its GIL pause into the parent.
        with open(result['path'],'rb') as stream:actual=hashlib.sha256(stream.read()).hexdigest()
        if not result.get('integrity_valid') or actual!=result['manifest_sha256']:
            raise ValueError('INCIDENT_WORKER_READBACK_FAILED')
        return result['path']
    finally:
        send.close();receive.close()
        if process.pid is not None:
            if process.is_alive():process.terminate();process.join(2.)
            if not process.is_alive():process.close()
        transfer.close();transfer.unlink()
