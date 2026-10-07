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
JOURNAL_INPUT_KEYS = INPUT_KEYS + (
    'unavailable_field_schema', 'unavailable_field_mask', 'signal',
    'context_reference', 'observation_reference', 'deadline_reference', 'deadline_basis',
)

_COMPARISON_FIELDS = (
    'checked_at', 'sdk_frame_us', 'observation_timestamp', 'computed_at', 'expires_at',
    'valid', 'source', 'decision_source', 'reason', 'handoff_required',
    'remaining_at_computation_s', 'observation_age_s', 'decision_age_s', 'lease_overrun_s',
    'schema_version', 'throttle', 'brake', 'emergency',
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


def _pack_pairing(pairing):
    """Fixed-key receipt within existing budgets, expanded at the public edge."""
    def row(vehicle):
        observed = vehicle['observation']
        return [vehicle.get(k) for k in ('sdk_frame_us', 'gear', 'speed_mps', 'park_brake')] + [
            observed.get(k) for k in ('schema_version', 'sdk_frame_us', 'observed_at', 'valid', 'reason')]
    return dict(schema=1, values=[row(pairing['initial_vehicle']),
        row(pairing['compared_vehicle']), pairing['reread_count'],
        *(pairing[k] for k in ('command_read_started_at', 'command_read_at', 'checked_after_read_at'))])


def _expand_pairing(pairing):
    if not isinstance(pairing, dict) or pairing.get('schema') != 1:
        return pairing
    def row(values):
        result = dict(zip(('sdk_frame_us', 'gear', 'speed_mps', 'park_brake'), values[:4]))
        result['observation'] = dict(zip(
            ('schema_version', 'sdk_frame_us', 'observed_at', 'valid', 'reason'), values[4:]))
        return result
    values = pairing['values']
    return dict(initial_vehicle=row(values[0]), compared_vehicle=row(values[1]),
        reread_count=values[2], **dict(zip(
            ('command_read_started_at', 'command_read_at', 'checked_after_read_at'), values[3:])))


def bounded_fault_details(value, *, packed=False):
    """Account identical compared identities once inside one fault receipt.

    Restore the public explicit fields after the bounded immutable copy. Both
    refer to that copied identity, never to a later IPC value. Keep the original
    8 KB budget; genuinely different identities are copied independently.
    """
    if not isinstance(value, dict):
        return bounded_copy(value, limit=8192)[0]
    same = (isinstance(value.get('actual_context'), (list, tuple))
            and isinstance(value.get('expected_context'), (list, tuple))
            and tuple(value['actual_context']) == tuple(value['expected_context']))
    selected = {k: v for k, v in value.items() if not (same and k == 'expected_context')}
    pairing = selected.get('command_observation_pairing')
    if isinstance(pairing, dict):
        actual, expected = value.get('actual_context'), value.get('expected_context')
        if (not same and isinstance(actual, (tuple, list))
                and isinstance(expected, (tuple, list)) and len(actual) == len(expected)):
            # Preserve genuine differences, including foreign session, without
            # duplicating every unchanged route string within the 8 KB receipt.
            selected.pop('expected_context')
            selected['compared_context_delta'] = [[i, v] for i, v in enumerate(expected)
                                                  if v != actual[i]]
        selected['command_observation_pairing'] = _pack_pairing(pairing)
        selected.pop('vehicle_sdk_frame_us', None)
        selected.pop('vehicle_observation', None)
        # Fixed names already have a public schema. Account their values once,
        # then restore names after the bounded copy; no evidence is discarded.
        selected['comparison_fields'] = sum(1 << i for i, k in enumerate(_COMPARISON_FIELDS) if k in selected)
        selected['comparison_values'] = [selected.pop(k) for k in _COMPARISON_FIELDS if k in selected]
    result = bounded_copy(selected, limit=8192)[0]
    if packed:
        if same and 'actual_context' in result:
            result['expected_context_reference'] = 'actual_context'
        return result
    return _expand_fault_details(result, same=same)


def _expand_fault_details(result, *, same=False):
    result = dict(result)
    if 'command_observation_pairing' in result:
        mask = result.pop('comparison_fields')
        result.update(zip((k for i, k in enumerate(_COMPARISON_FIELDS) if mask & (1 << i)),
                          result.pop('comparison_values')))
        pairing = _expand_pairing(result['command_observation_pairing'])
        result['command_observation_pairing'] = pairing
        compared = pairing['compared_vehicle']
        result['vehicle_sdk_frame_us'] = compared['sdk_frame_us']
        result['vehicle_observation'] = {k: compared['observation'].get(k) for k in
            ('sdk_frame_us', 'observed_at', 'valid', 'reason')}
    if (same or result.pop('expected_context_reference', None) == 'actual_context') and 'actual_context' in result:
        result['expected_context'] = result['actual_context']
    elif 'compared_context_delta' in result:
        result['expected_context'] = list(result['actual_context'])
        for index, item in result.pop('compared_context_delta'):
            result['expected_context'][index] = item
    return result


def _pack_intervention(value):
    if not isinstance(value, dict) or not isinstance(value.get('details'), dict):
        return value
    return {**value, 'details': bounded_fault_details(value['details'], packed=True)}


def _expand_intervention(value):
    if not isinstance(value, dict) or not isinstance(value.get('details'), dict):
        return value
    return {**value, 'details': _expand_fault_details(value['details'])}


def bounded_input(value):
    # Producers already publish small immutable dictionaries. Exclude geometry,
    # actor arrays and transport buffers before any diagnostic copy.
    if not isinstance(value, dict):
        return None
    # Explicit missing-field bitmap retains unknown semantics without a long
    # repeated field-name string. Bit order is INPUT_KEYS excluding following;
    # schema 1 fixes that order. Fixed source/journal byte limits are unchanged.
    keys = tuple(k for k in INPUT_KEYS if k != 'following')
    result = {k: value[k] for k in keys if value.get(k) is not None}
    result['unavailable_field_schema'] = 1
    result['unavailable_field_mask'] = sum(1 << i for i,k in enumerate(keys) if value.get(k) is None)
    # Additive fields do not change schema-1 bitmap positions or byte limits.
    for key in ('deadline_basis',):
        if key in value:
            result[key] = value[key]
    following_keys = (
        'status', 'target_id', 'gap_m', 'speed_mps', 'speed_cap_mps', 'emergency',
        'reason', 'receiver_time', 'source_timestamp', 'source_sequence',
        'complete', 'atomic', 'confirmed', 'expires_at')
    result['following'] = {k: value['following'].get(k) for k in following_keys} if isinstance(value.get('following'), dict) else None
    if isinstance(value.get('signal'), dict):
        from core.sdk.signal_snapshot import compact
        result['signal'] = compact(value['signal'])
    return bounded_copy(result)[0]


def compact_decision(value):
    """Reference identical consumed metadata within ONE immutable journal row.

    Do not collapse a rejected/older packet's identity into the current one.
    References point only to this row, never to a mutable IPC slot or another
    event. Pedals, source times, selection and stop provenance remain explicit.
    """
    if not isinstance(value, dict) or not isinstance(value.get('context'), (list, tuple)):
        return value
    result = dict(value)
    if isinstance(result.get('command_observation_pairing'), dict):
        result['command_observation_pairing'] = _pack_pairing(result['command_observation_pairing'])
    binding = tuple(value['context'])
    inputs = value.get('inputs') if isinstance(value.get('inputs'), dict) else {}
    def same_observation(item):
        keys = ('sdk_frame_us', 'observation_timestamp')
        if all(k in item and item[k] == value.get(k) for k in keys):
            item = {k: v for k, v in item.items() if k not in keys}
            item['observation_reference'] = 'decision'
        return item
    for group in ('inputs', 'limits'):
        if not isinstance(value.get(group), dict):
            continue
        compacted = {}
        for name, original in value[group].items():
            item = original
            if isinstance(item, dict):
                consumed = inputs.get(name)
                limit_keys = {'source', 'context', 'sdk_frame_us', 'observation_timestamp',
                              'computed_at', 'expires_at', 'valid',
                              'speed_cap_kmh' if name == 'road' else 'planned_speed_ms'}
                if (group == 'limits' and isinstance(consumed, dict)
                        and item.keys() <= limit_keys
                        and all(k in consumed and (
                            tuple(consumed[k]) == tuple(v) if k == 'context'
                            and isinstance(consumed[k], (list, tuple)) and isinstance(v, (list, tuple))
                            else consumed[k] == v) for k, v in item.items())):
                    # The ceiling read exactly the recorded producer packet.
                    compacted[name] = {'input_reference': name}
                    continue
                if isinstance(item.get('context'), (list, tuple)) and tuple(item['context']) == binding:
                    item = {k: v for k, v in item.items() if k != 'context'}
                    item['context_reference'] = 'decision'
                item = same_observation(item)
            compacted[name] = item
        result[group] = compacted
    selected = value.get('selected')
    if (isinstance(selected, dict) and isinstance(selected.get('context'), (list, tuple))
            and tuple(selected['context']) == binding):
        result['selected'] = {k: v for k, v in selected.items() if k != 'context'}
        result['selected']['context_reference'] = 'decision'
        result['selected'] = same_observation(result['selected'])
    requested = value.get('requested')
    if isinstance(requested, dict) and requested.get('source') == 'autopilot':
        # The Autopilot command contract has no actor/following fields. Preserve
        # its OWN complete identity/time/pedals, including rejected old commands;
        # don't spend space describing absent fields from other producer types.
        result['requested'] = {k: v for k, v in requested.items()
            if k not in ('unavailable_field_schema', 'unavailable_field_mask', 'following')}
        if (selected is not None and isinstance(requested.get('context'), (list, tuple))
                and tuple(requested['context']) == binding):
            result['requested'].pop('context')
            result['requested']['context_reference'] = 'decision'
        # A rejected/earlier command retains any differing frame/time verbatim.
        result['requested'] = same_observation(result['requested'])
    # Deadline receipts often refer to the SAME original observation through
    # several producers. Intern them within this immutable row, just like its
    # context above; do not increase the fixed journal allocation budget.
    fields = ('source', 'kind', 'sdk_frame_us', 'observation_timestamp', 'expires_at')
    bases = []
    def intern(item):
        if not isinstance(item, dict) or not isinstance(item.get('deadline_basis'), dict):
            return item
        basis = item['deadline_basis']
        if not basis.keys() <= set(fields):
            return item  # Unknown schema remains explicit, never discarded.
        encoded = [basis.get(k) for k in fields]
        if encoded not in bases:
            bases.append(encoded)
        item = {k: v for k, v in item.items() if k != 'deadline_basis'}
        item['deadline_reference'] = bases.index(encoded)
        return item
    for group in ('inputs', 'limits'):
        if isinstance(result.get(group), dict):
            result[group] = {k: intern(v) for k, v in result[group].items()}
    for key in ('selected', 'requested'):
        if key in result:
            result[key] = intern(result[key])
    if bases:
        result['deadline_basis_schema'] = 1
        result['deadline_bases'] = bases
    return result


def pack_journal_inputs(value):
    """Lossless fixed-key storage; exported producer fields are unchanged."""
    if not isinstance(value, dict) or not isinstance(value.get('inputs'), dict):
        return value
    result = dict(value, inputs=dict(value['inputs']))
    for name, item in result['inputs'].items():
        if isinstance(item, dict) and item.keys() <= set(JOURNAL_INPUT_KEYS):
            result['inputs'][name] = dict(journal_input_schema=1,
                presence=sum(1 << i for i, k in enumerate(JOURNAL_INPUT_KEYS) if k in item),
                values=[item[k] for k in JOURNAL_INPUT_KEYS if k in item])
    return result


def expand_decision(value):
    """Restore the existing external field contract from this row's metadata.

    Stored references share immutable scalar/list values; no IPC reread and no
    timestamp repair. Export/readers continue to receive explicit source fields.
    """
    if not isinstance(value, dict):
        return value
    result = dict(value)
    def expand(item):
        if not isinstance(item, dict):
            return item
        item = dict(item)
        if item.get('journal_input_schema') == 1:
            values = iter(item['values'])
            item = {k: next(values) for i, k in enumerate(JOURNAL_INPUT_KEYS)
                    if item['presence'] & (1 << i)}
        reference = item.pop('deadline_reference', None)
        if reference is not None and value.get('deadline_basis_schema') == 1:
            basis = value['deadline_bases'][reference]
            item['deadline_basis'] = {k: v for k, v in zip(
                ('source', 'kind', 'sdk_frame_us', 'observation_timestamp', 'expires_at'), basis)
                if v is not None}
        if item.pop('context_reference', None) == 'decision':
            item['context'] = value['context']
        if item.pop('observation_reference', None) == 'decision':
            item.update({k: value[k] for k in ('sdk_frame_us', 'observation_timestamp')})
        return item
    if isinstance(value.get('inputs'), dict):
        result['inputs'] = {k: expand(v) for k, v in value['inputs'].items()}
    if isinstance(value.get('limits'), dict):
        limits = {}
        for k, v in value['limits'].items():
            if isinstance(v, dict) and v.get('input_reference') == k:
                consumed = result['inputs'][k]
                v = {key: consumed[key] for key in ('source', 'context', 'sdk_frame_us',
                    'observation_timestamp', 'computed_at', 'expires_at', 'valid',
                    'speed_cap_kmh' if k == 'road' else 'planned_speed_ms') if key in consumed}
            limits[k] = expand(v)
        result['limits'] = limits
    for k in ('selected', 'requested'):
        if k in result:
            result[k] = expand(result[k])
    if 'command_observation_pairing' in result:
        result['command_observation_pairing'] = _expand_pairing(result['command_observation_pairing'])
    result.pop('deadline_basis_schema', None)
    result.pop('deadline_bases', None)
    return result


class PedalJournal:
    CAPACITY = 128
    MAX_BYTES = 65536

    def __init__(self):
        self.enabled = False
        self._local = threading.local()
        self._lock = threading.Lock()
        self._events = deque(maxlen=self.CAPACITY)
        self._sizes = deque(maxlen=self.CAPACITY)
        self._source_uses = {}
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
        self._local.intervention, extra = bounded_copy(_pack_intervention(intervention), limit=16384)
        self._local.source, self._local.size = bounded_copy(pack_journal_inputs(compact_decision(value)), limit=32768) if value is not None else (None, 64)
        self._local.size += extra

    def source(self):
        source = expand_decision(getattr(self._local, 'source', None))
        intervention = getattr(self._local, 'intervention', None)
        # Nested release_all binding must carry the separately budgeted first
        # intervention into the actual zero writes and restore it afterwards.
        # Returning only the decision silently dropped that event on handover.
        if isinstance(source, dict) and intervention is not None:
            return {**source, 'intervention': _expand_intervention(intervention)}
        return source

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
            source = getattr(self._local, 'source', None)
            intervention = getattr(self._local, 'intervention', None)
            key = (id(source), id(intervention))
            source_size = getattr(self._local, 'size', 64)
            # All writes under one bind share the SAME immutable source object.
            # Charge it once, plus each event, instead of dropping the throttle
            # write merely because the paired brake repeats its provenance.
            while self._events and (len(self._events) == self.CAPACITY or self._bytes+2048
                    +(source_size if key not in self._source_uses else 0) > self.MAX_BYTES):
                self._events.popleft()
                old_key = self._sizes.popleft()
                self._bytes -= 2048
                uses = self._source_uses[old_key]
                uses['count'] -= 1
                if uses['count'] == 0:
                    self._bytes -= uses['size']
                    del self._source_uses[old_key]
                self._dropped += 1
            if key not in self._source_uses:
                self._source_uses[key] = dict(count=0, size=source_size)
                self._bytes += source_size
            self._source_uses[key]['count'] += 1
            verified = evidence.get('status') == 'MAPPING_WRITE_RETURNED'
            self._held[channel] = evidence.get('value') if verified else None
            self._events.append(dict(
                sequence=self._sequence, channel=channel, requested_value=value,
                backend_mode=backend, call_started_at_s=started,
                call_returned_at_s=returned, call_returned=error is None,
                error=error, backend=evidence, pair_after=dict(self._held),
                source=source, game_consumption_verified=False))
            self._events[-1]['intervention'] = intervention
            self._sizes.append(key)
            self._bytes += 2048

    def drain(self):
        with self._lock:
            result = dict(schema_version=1, events=list(self._events),
                          dropped_events=self._dropped, capacity=self.CAPACITY,
                          byte_budget=self.MAX_BYTES,
                          game_consumption_verified=False)
            self._events.clear()
            self._sizes.clear()
            self._source_uses.clear()
            self._bytes = 0
            self._dropped = 0
        for event in result['events']:
            event['source'] = expand_decision(event['source'])
            event['intervention'] = _expand_intervention(event.get('intervention'))
            if isinstance(event['source'], dict) and event.get('intervention') is not None:
                event['source'] = {**event['source'], 'intervention': event['intervention']}
        return result


def source_snapshot(state, truck, pending):
    from core.longitudinal import context
    from core.transmission_mode import vehicle_control_observation
    observed, reason = vehicle_control_observation(state, truck)
    hold = state.get('simple_auto_service_hold')
    if isinstance(hold, dict):
        # Context/activation already belong to this immutable source envelope;
        # repeating them exhausts the fixed journal source budget.
        original = hold
        hold = {k: hold.get(k) for k in ('phase',
            'chain', 'write_sequence', 'started_frame', 'returned_at',
            'brake', 'stop_reason', 'automatic_restart_supported', 'restart_blocker',
            'game_consumption_verified')}
        lock = original.get('signal_lock')
        if lock:
            hold['signal_lock'] = {k: lock[k] for k in ('lifecycle','generation','frame_us','observed_at')}
            hold['signal_lock']['id'] = lock['candidate']['id']
    return dict(
        context=list(context(state)), sdk_frame_us=truck.get('sdkFrameTimeUs'),
        observation_timestamp=observed.get('observed_at'),
        observation_valid=not reason and observed.get('valid') is True,
        actual_speed_mps=truck.get('speed'), observed_gear=truck.get('gear'),
        decision_started_at_s=time.monotonic(),
        autopilot_active=bool(state.get('autopilot_active', False)),
        activation=state.get('autopilot_failure_epoch'),
        control_state=state.get('autopilot_control_state'),
        service_hold=hold,
        regulator_mode=None, regulator_mode_status='NOT_EXPORTED_BY_PRODUCER',
        phase='launch' if pending else ('active' if state.get('autopilot_active') else 'inactive'),
        launch=None if not pending else {
            k: pending.get(k) for k in ('mode', 'request_id', 'started_at', 'deadline_at',
                'start_frame', 'phase', 'handoff_deadline_at')},
        requested=None, selected=None, inputs=None,
        disable_reason=state.get('autopilot_disable_reason'),
        safety_reason=state.get('automatic_safety_stop_reason'),
    )
