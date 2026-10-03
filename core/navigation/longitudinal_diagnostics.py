"""Bounded passive pedal provenance for the existing evidence collector.

This journal cannot send controls. Contexts belong to a single Engine flush;
calls outside that flush remain explicitly unbound. No game consumption proof.
"""
from collections import deque
import math
import threading
import time

INPUT_KEYS = (
    'schema_version', 'source', 'context', 'sdk_frame_us', 'observation_timestamp',
    'computed_at', 'expires_at', 'valid', 'throttle', 'brake', 'decision_source',
    'reason', 'emergency', 'requested_speed_kmh', 'constrained_speed_kmh',
    'control_target_kmh', 'speed_control_reason', 'following_status',
    'following_target_id', 'following_required', 'following_confirmed',
    'traffic_brake', 'light_brake', 'speed_cap_kmh', 'planned_speed_ms',
    'controller_mode', 'mode', 'following', 'brake_basis',
)


def bounded_copy(value, limit=16384):
    """Conservative byte/node budget, without serialization on the control tick."""
    remaining = limit

    def visit(item, depth=0):
        nonlocal remaining
        remaining -= 64
        if remaining < 0 or depth > 8:
            raise ValueError('SNAPSHOT_BUDGET')
        if isinstance(item, dict):
            return {visit(str(k), depth+1): visit(v, depth+1) for k, v in item.items()}
        if isinstance(item, (tuple, list)):
            return [visit(v, depth+1) for v in item]
        if isinstance(item, str):
            remaining -= 6*len(item)  # JSON escaping has at most six bytes/char.
            if remaining < 0:
                raise ValueError('SNAPSHOT_BUDGET')
            return item
        if type(item) in (float, int):
            return item if math.isfinite(item) else None
        return item if item is None or isinstance(item, bool) else None

    try:
        result = visit(value)
        return result, limit-remaining
    except (ValueError, OverflowError):
        return {'snapshot_status': 'UNVERIFIED_SNAPSHOT_BUDGET_EXCEEDED'}, 256


def bounded_input(value):
    # Producers already publish small immutable dictionaries. Exclude geometry,
    # actor arrays and transport buffers before any diagnostic copy.
    if not isinstance(value, dict):
        return None
    # Explicit unavailable-field list retains unknown semantics without
    # repeating dozens of null key/value nodes in every producer snapshot.
    # The fixed source/journal byte limits are unchanged.
    keys = tuple(k for k in INPUT_KEYS if k != 'following')
    result = {k: value[k] for k in keys if value.get(k) is not None}
    result['unavailable_fields'] = ','.join(k for k in keys if value.get(k) is None)
    following_keys = (
        'status', 'target_id', 'gap_m', 'speed_mps', 'speed_cap_mps', 'emergency',
        'reason', 'receiver_time', 'source_timestamp', 'source_sequence',
        'complete', 'atomic', 'confirmed', 'expires_at')
    result['following'] = {k: value['following'].get(k) for k in following_keys} if isinstance(value.get('following'), dict) else None
    return bounded_copy(result)[0]


class PedalJournal:
    CAPACITY = 128
    MAX_BYTES = 65536

    def __init__(self):
        self.enabled = False
        self._local = threading.local()
        self._lock = threading.Lock()
        self._events = deque(maxlen=self.CAPACITY)
        self._sizes = deque(maxlen=self.CAPACITY)
        self._bytes = 0
        self._sequence = 0
        self._decision_sequence = 0
        self._dropped = 0
        self._held = {'throttle': None, 'brake': None}

    def bind(self, value):
        # Keep the rare first intervention beside the decision, not repeated
        # inside its already bounded producer snapshots. Both allocations count
        # against the unchanged total journal byte budget.
        intervention = value.get('intervention') if isinstance(value, dict) else None
        if intervention is not None:
            value = {k: v for k, v in value.items() if k != 'intervention'}
        self._local.intervention, extra = bounded_copy(intervention, limit=16384)
        self._local.source, self._local.size = bounded_copy(value, limit=32768) if value is not None else (None, 64)
        self._local.size += extra

    def source(self):
        return getattr(self._local, 'source', None)

    def next_decision(self):
        self._decision_sequence += 1  # The Engine I/O lock owns this sequence.
        return self._decision_sequence

    def suspend(self):
        self.enabled = False
        self.bind(None)
        self.drain()
        self._held = {'throttle': None, 'brake': None}

    def record(self, channel, value, started, returned, backend, evidence, error=None):
        if not self.enabled:
            return
        with self._lock:
            self._sequence += 1
            size = getattr(self._local, 'size', 64) + 2048
            while self._events and (len(self._events) == self.CAPACITY or self._bytes+size > self.MAX_BYTES):
                self._events.popleft()
                self._bytes -= self._sizes.popleft()
                self._dropped += 1
            verified = evidence.get('status') == 'MAPPING_WRITE_RETURNED'
            self._held[channel] = evidence.get('value') if verified else None
            self._events.append(dict(
                sequence=self._sequence, channel=channel, requested_value=value,
                backend_mode=backend, call_started_at_s=started,
                call_returned_at_s=returned, call_returned=error is None,
                error=error, backend=evidence, pair_after=dict(self._held),
                source=self.source(), game_consumption_verified=False))
            self._events[-1]['intervention'] = getattr(self._local, 'intervention', None)
            self._sizes.append(size)
            self._bytes += size

    def drain(self):
        with self._lock:
            result = dict(schema_version=1, events=list(self._events),
                          dropped_events=self._dropped, capacity=self.CAPACITY,
                          byte_budget=self.MAX_BYTES,
                          game_consumption_verified=False)
            self._events.clear()
            self._sizes.clear()
            self._bytes = 0
            self._dropped = 0
            return result


def source_snapshot(state, truck, pending):
    from core.longitudinal import context
    from core.transmission_mode import vehicle_control_observation
    observed, reason = vehicle_control_observation(state, truck)
    return dict(
        context=list(context(state)), sdk_frame_us=truck.get('sdkFrameTimeUs'),
        observation_timestamp=observed.get('observed_at'),
        observation_valid=not reason and observed.get('valid') is True,
        actual_speed_mps=truck.get('speed'), observed_gear=truck.get('gear'),
        decision_started_at_s=time.monotonic(),
        autopilot_active=bool(state.get('autopilot_active', False)),
        activation=state.get('autopilot_failure_epoch'),
        control_state=state.get('autopilot_control_state'),
        regulator_mode=None, regulator_mode_status='NOT_EXPORTED_BY_PRODUCER',
        phase='launch' if pending else ('active' if state.get('autopilot_active') else 'inactive'),
        launch=None if not pending else {
            k: pending.get(k) for k in ('mode', 'request_id', 'started_at', 'deadline_at',
                'start_frame', 'phase', 'handoff_deadline_at')},
        requested=None, selected=None, inputs=None,
        disable_reason=state.get('autopilot_disable_reason'),
        safety_reason=state.get('automatic_safety_stop_reason'),
    )
