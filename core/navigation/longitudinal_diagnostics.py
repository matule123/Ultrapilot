"""Bounded passive pedal provenance for the existing evidence collector.

This journal cannot send controls. Contexts belong to a single Engine flush;
calls outside that flush remain explicitly unbound. No game consumption proof.
"""
from collections import deque, Counter
import copy
import json
import math
import threading
import time
import zlib
import marshal
import hashlib
import weakref
import pickle


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
    'light','light_reference','radius_m','distance_m','roundabout_entry_distance_m','display_detection',
    'producer_trace','refresh_pending','smoothing',
    'capture_incomplete','traffic_availability',
)

SOURCE_KEYS = (
    'context','sdk_frame_us','observation_timestamp','observation_valid','actual_speed_mps',
    'observed_gear','sdk_response','decision_started_at_s','activation','route_identity',
    'control_state','phase','requested','selected','inputs','service_hold','launch',
    'decision_sequence','autopilot_active','forward_history','input_rejections','regulator_mode',
    'regulator_mode_status','rejected_inputs','limits','speed_ceiling_mps','output_intent',
    'deadline_basis_schema','deadline_bases','command_observation_pairing','forward_coast_confirmation',
    'safety_reason','disable_reason',
    'sdk_observation',
)
_NESTED_FIELDS = {
    'forward_history': ('phase','confirmed_frame','confirmed_at','last_frame','last_observed_at',
        'zero_deadline_at','launch_deadline_at','brake_only','coast_only'),
    'service_hold': ('phase','chain','write_sequence','started_frame','returned_at','brake',
        'stop_reason','automatic_restart_supported','restart_blocker','game_consumption_verified','signal_lock'),
}
_BRAKE_SOURCES = ('acc','traffic','traffic_light','collision','speed_policy','maneuver','curve','autopilot_safety','autopilot')
_BRAKE_KINDS = ('acc','traffic','curve','maneuver','safety','obstacle','emergency')
_MODE_STATUS = ('PRODUCER_SPEED_CONTROL_REASON','NOT_VERIFIED','NOT_EXPORTED_BY_PRODUCER')
_TREE_KEYS = tuple(sorted(set(SOURCE_KEYS+JOURNAL_INPUT_KEYS+tuple(k for keys in _NESTED_FIELDS.values() for k in keys)+(
    'producer_trace','truck','gear','speed_mps','context_reference','inputs','brake_requests',
    'input_failure','vehicle_reference','engine_input_reference','field_changes','removed_fields',
    'brake_request_schema','brake_request_values','schema_version','sdk_frame_us','observed_at',
    'valid','reason','signal_lock','candidate','id','x','y','z','yaw','color','distance','lifecycle',
    'generation','frame_us','relevance','prefab_required','prefab_binding_reason','stop_candidate',
    'passage_key','distance_basis','stop_line_verified','stop_target_kind','entry_progress_m',
    'entry_xyz','front_allowance_m','junction_standoff_m','front_geometry_status','head_observed',
    'journal_input_schema','presence','values','unavailable_field_schema','unavailable_field_mask',
    'gameThrottle','gameBrake','kind','expires_at','source','status','target_id','gap_m',
    'receiver_time','source_timestamp','source_sequence','complete','atomic','confirmed',
))))
_TREE_KEY_INDEX = {key:i for i,key in enumerate(_TREE_KEYS)}


def pack_brake_requests(trace):
    requests = trace.get('brake_requests')
    if isinstance(requests,list) and all(len(r)==3 and r[0] in _BRAKE_SOURCES and r[1] in _BRAKE_KINDS for r in requests):
        trace = {k:v for k,v in trace.items() if k != 'brake_requests'}
        trace['brake_request_schema'] = 1
        trace['brake_request_values'] = [v for s,k,b in requests for v in (_BRAKE_SOURCES.index(s),_BRAKE_KINDS.index(k),b)]
    return trace


def input_delta(original, base, name):
    """Exact differences from this row's immutable Engine input, not its slot."""
    changes, removed = {}, []
    def visit(a,b,path=''):
        for key in b.keys()-a.keys():
            removed.append(path+'/'+key.replace('~','~0').replace('/','~1'))
        for key,value in a.items():
            target=path+'/'+key.replace('~','~0').replace('/','~1')
            if key not in b:
                changes[target]=value
            elif isinstance(value,dict) and isinstance(b[key],dict):
                visit(value,b[key],target)
            elif value != b[key]:
                changes[target]=value
    try:
        visit(original,base)
    finally:
        visit = None
    result=dict(engine_input_reference=name)
    if changes:result['field_changes']=changes
    if removed:result['removed_fields']=removed
    return result


def restore_input_delta(item, base):
    result=copy.deepcopy(base)
    for path in item.get('removed_fields',()):
        keys=[k.replace('~1','/').replace('~0','~') for k in path.split('/')[1:]]
        parent=result
        for key in keys[:-1]:parent=parent[key]
        parent.pop(keys[-1])
    for path,value in item.get('field_changes',{}).items():
        keys=[k.replace('~1','/').replace('~0','~') for k in path.split('/')[1:]]
        parent=result
        for key in keys[:-1]:parent=parent[key]
        parent[keys[-1]]=value
    return result


def pack_source(value):
    if not isinstance(value,dict):
        return value
    # Flat immutable nodes avoid repeatedly allocating fixed field names and
    # identical subtrees. Bounded in-memory encoding; no SDK/RPC or disk calls.
    nodes, indices, visits = [], {}, 0
    def encode(item):
        nonlocal visits
        visits+=1
        if visits>2048:raise ValueError('SNAPSHOT_NODE_BUDGET')
        if not isinstance(item,(dict,list,tuple)):
            return item if not isinstance(item,float) or math.isfinite(item) else None
        if isinstance(item,dict):
            row=[1]
            for key,v in sorted(item.items()):
                row.extend((_TREE_KEY_INDEX.get(key,key),encode(v)))
        else:row=[2,*(encode(v) for v in item)]
        key=tuple(row)
        if key not in indices:
            references=sum(1<<i for i,v in enumerate(row[1:]) if isinstance(v,tuple) and v[0]=='@node')
            flat=[row[0],references,*(v[1] if isinstance(v,tuple) and v[0]=='@node' else v for v in row[1:])]
            indices[key]=len(nodes);nodes.append(flat)
        return ('@node',indices[key])
    try:
        root=encode(value)
        tree=dict(source_tree=1,root=root[1],nodes=nodes)
        blob=json.dumps(tree,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf-8')
        if len(blob)>32768:raise ValueError('SNAPSHOT_BYTE_BUDGET')
        # Exact lossless storage inside the unchanged 32/64 KB budgets. Fixed
        # field/index references above remain the source of deduplication.
        compressor=zlib.compressobj(level=1,wbits=9,memLevel=1)
        return dict(source_blob_schema=2,source_blob=compressor.compress(blob)+compressor.flush())
    except (ValueError,TypeError,RecursionError):
        return {'snapshot_status':'UNVERIFIED_SNAPSHOT_BUDGET_EXCEEDED'}
    finally:
        encode = None  # Break the recursive closure's ownership of node tables.


def unpack_source(value):
    # Internal-only reuse of the already verified primitive ownership codec.
    # External replay/combined readers still receive the original source fields.
    if isinstance(value,dict) and value.get('record_codec')=='pickle5-primitives-v1':
        restored=restore_exact_record(value)
        return pack_journal_inputs(compact_decision(restored)) if value.get('journal_compaction_pending') else restored
    if isinstance(value,dict) and value.get('source_blob_schema') == 2:
        decoder=zlib.decompressobj()
        blob=decoder.decompress(value['source_blob'],32769)
        if len(blob)>32768 or not decoder.eof or decoder.unused_data:
            raise ValueError('INVALID_SOURCE_BYTE_BUDGET')
        value=json.loads(blob)
    if isinstance(value,dict) and value.get('source_blob_schema') == 1:
        value=json.loads(value['source_blob'])  # Own bounded JSON bytes; never pickle.
    if isinstance(value,dict) and value.get('source_tree') == 1:
        nodes=value['nodes']
        def decode(index,bound):
            if type(index) is not int or not 0<=index<bound:raise ValueError('INVALID_SOURCE_NODE')
            row=nodes[index]
            def item(i):return decode(row[i],index) if row[1] & (1<<(i-2)) else row[i]
            if row[0]==1:
                return {(_TREE_KEYS[row[i]] if type(row[i]) is int else row[i]):item(i+1)
                        for i in range(2,len(row),2)}
            return [item(i) for i in range(2,len(row))]
        try:
            return decode(value['root'],len(nodes))
        finally:
            decode = None
    if not isinstance(value,dict) or value.get('source_storage') != 1:
        return value
    result=dict(value.get('extensions') or {})
    result.update(zip((k for i,k in enumerate(SOURCE_KEYS) if value['fields'] & (1<<i)),value['values']))
    status=result.get('regulator_mode_status')
    if type(status) is int and 0 <= status < len(_MODE_STATUS):
        result['regulator_mode_status'] = _MODE_STATUS[status]
    for field,keys in _NESTED_FIELDS.items():
        item = result.get(field)
        if isinstance(item,dict) and 'fixed_fields' in item:
            result[field] = dict(zip((k for i,k in enumerate(keys) if item['fixed_fields'] & (1<<i)),item['values']))
    return result


def hold_snapshot(original):
    if not isinstance(original,dict):
        return None
    hold = {k:original.get(k) for k in _NESTED_FIELDS['service_hold'] if k != 'signal_lock'}
    if 'standstill_deadline_at' in original:
        # Additive string key: do NOT change the fixed schema-1 tree-key index.
        hold['standstill_deadline_at']=original['standstill_deadline_at']
    lock = original.get('signal_lock')
    if lock:
        hold['signal_lock'] = {k:lock[k] for k in ('lifecycle','generation','frame_us','observed_at')}
        hold['signal_lock']['id'] = lock['candidate']['id']
    # Additive extensions remain literal keys. Do NOT reorder schema-1 field
    # tables/tree dictionaries: existing incident files must still decode.
    for key in ('traffic_lock', 'other_stop_sources'):
        if key in original:
            hold[key] = original[key]
    return hold

_COMPARISON_FIELDS = (
    'checked_at', 'sdk_frame_us', 'observation_timestamp', 'computed_at', 'expires_at',
    'valid', 'source', 'decision_source', 'reason', 'handoff_required',
    'remaining_at_computation_s', 'observation_age_s', 'decision_age_s', 'lease_overrun_s',
    'schema_version', 'throttle', 'brake', 'emergency',
    'rejection_cause',
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
        if isinstance(item, bytes):
            remaining -= len(item)
            if remaining < 0:raise ValueError('SNAPSHOT_BUDGET')
            return item
        if type(item) in (float, int):
            return item if math.isfinite(item) else None
        return item if item is None or isinstance(item, bool) else None

    try:
        result = visit(value)
        return result, limit-remaining
    except (ValueError, OverflowError):
        return {'snapshot_status': 'UNVERIFIED_SNAPSHOT_BUDGET_EXCEEDED'}, 256
    finally:
        visit = None


def _pack_pairing(pairing):
    """Fixed-key receipt within existing budgets, expanded at the public edge."""
    def row(vehicle):
        observed = vehicle['observation']
        return [vehicle.get(k) for k in ('sdk_frame_us', 'gear', 'speed_mps', 'park_brake')] + [
            observed.get(k) for k in ('schema_version', 'sdk_frame_us', 'observed_at', 'valid', 'reason')]
    result = dict(schema=1, values=[row(pairing['initial_vehicle']),
        row(pairing['compared_vehicle']), pairing['reread_count'],
        *(pairing[k] for k in ('command_read_started_at', 'command_read_at', 'checked_after_read_at'))])
    if 'refresh_recovery' in pairing:
        result['refresh_recovery'] = pairing['refresh_recovery']
    return result


def _expand_pairing(pairing):
    if not isinstance(pairing, dict) or pairing.get('schema') != 1:
        return pairing
    def row(values):
        result = dict(zip(('sdk_frame_us', 'gear', 'speed_mps', 'park_brake'), values[:4]))
        result['observation'] = dict(zip(
            ('schema_version', 'sdk_frame_us', 'observed_at', 'valid', 'reason'), values[4:]))
        return result
    values = pairing['values']
    result = dict(initial_vehicle=row(values[0]), compared_vehicle=row(values[1]),
        reread_count=values[2], **dict(zip(
            ('command_read_started_at', 'command_read_at', 'checked_after_read_at'), values[3:])))
    if 'refresh_recovery' in pairing:
        result['refresh_recovery'] = pairing['refresh_recovery']
    return result


def emergency_evidence(traffic, source, source_observation_timestamp):
    """Priority fixed-shape cause, never an oversized optional following tree."""
    traffic = traffic or {}
    following = traffic.get('following') or {}
    basis = traffic.get('brake_basis') or {}
    decisive = basis.get('decisive') or {}
    row = {k:traffic.get(k) for k in ('sdk_frame_us','observation_timestamp','computed_at',
                                     'expires_at','traffic_brake','light_brake','valid')}
    row['source_acquisition'] = following.get('source_acquisition')
    row['following'] = {k:following[k] for k in ('status','target_id','protective_target_id',
        'gap_m','speed_mps','speed_cap_mps','emergency','protective_brake','unassigned_protective_brake') if k in following}
    row['brake_basis'] = {k:basis.get(k) for k in ('kind','source_acquisition','model',
        'stop_contract','conflict_count','confirmed_route_conflict','complete_envelope_verified')}
    # At most one decisive actor/four measured ego boxes. Do not copy an actor
    # list, route geometry or all forecast candidates into the 8 KiB fault.
    row['brake_basis']['decisive'] = {k:decisive.get(k) for k in (
        'id','body_index','distance_m','route_progress_m','actor_arrival_s',
        'ego_arrival_earliest_s','ego_arrival_latest_s','reserve_s','brake',
        'predicted_contact_s','contact_from_source_observation_s','source_age_s',
        'contact_basis','motion_model','actor_motion_basis','actor','ego_anchor_xyz',
        'ego_observed_speed_mps') if k in decisive}
    if isinstance(decisive.get('ego_bodies'),list):
        row['brake_basis']['decisive']['ego_bodies'] = decisive['ego_bodies'][:4]
    small_basis,_ = bounded_copy(basis,limit=4096)
    if 'snapshot_status' not in small_basis:
        row['brake_basis'] = small_basis  # Preserve the existing small public contract verbatim.
    row = {k:v for k,v in row.items() if v is not None and v != {}}
    result = dict(traffic=row,source=source,source_observation_timestamp=source_observation_timestamp,
        optional_candidate_details_omitted=True,game_consumption_verified=False)
    public,_ = bounded_copy(result,limit=4096)
    if 'snapshot_status' not in public:
        return public
    # Existing immutable tree codec removes repeated literal keys BEFORE the
    # fault's conservative 8 KiB accounting; no larger memory budget.
    return {'emergency_evidence_schema':1,'packed':pack_source(result)}


def expand_emergency_evidence(value):
    if isinstance(value,dict) and value.get('emergency_evidence_schema')==1:
        return unpack_source(value['packed'])
    return value


def compact_traffic_cause(traffic):
    """Exact fixed scalar cause taken before optional input-tree accounting."""
    traffic=traffic or {}
    basis=traffic.get('brake_basis') or {}
    decisive=basis.get('decisive') or {}
    actor=decisive.get('actor') or {}
    if not decisive:
        return None
    return dict(kind=basis.get('kind'),stop_contract=basis.get('stop_contract'),
        sdk_frame_us=traffic.get('sdk_frame_us'),observation_timestamp=traffic.get('observation_timestamp'),
        source_acquisition=basis.get('source_acquisition'),
        decisive={k:decisive.get(k) for k in ('id','distance_m','route_progress_m',
            'actor_arrival_s','ego_arrival_earliest_s','ego_arrival_latest_s',
            'assumed_ego_acceleration_mps2','ego_motion_basis','predicted_contact_s','contact_basis','brake')},
        actor={k:actor.get(k) for k in ('id','source','slot','record_fingerprint',
            'x','y','z','yaw','speed','dimensions_whl')})


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
    emergency = selected.get('evidence')
    if isinstance(emergency,dict) and 'traffic' in emergency:
        selected['evidence'] = {'emergency_evidence_schema':1,'packed':pack_source(emergency)}
    signal = selected.get('signal')
    if isinstance(signal,dict) and any((signal.get('coverage') or {}).get(k) is True
                                      for k in ('requires_takeover','requires_approach')):
        # Fixed public fields, accounted once like command/vehicle pairing.
        # Preserve the actually rejected head and original source clock inside
        # the existing 8 KiB receipt, rather than erasing all details on overflow.
        coverage = signal.get('coverage') or {}
        head = signal.get('unassigned_candidate') or {}
        from core.sdk.signal_snapshot import UNASSIGNED_CONTROL_REASON
        selected.pop('signal')
        selected['signal_comparison'] = dict(schema=2, values=[
            *[signal.get(k) for k in ('valid','reason','lifecycle','generation','frame_us','observed_at','relevance')],
            [*[coverage.get(k) for k in ('status','requires_takeover','candidate_count','distance_m')],
             0 if coverage.get('reason') == UNASSIGNED_CONTROL_REASON else coverage.get('reason')],
            [head.get(k) for k in ('id','x','y','z','yaw','color','distance','distance_basis')],
            [head.get(k) for k in ('scope_schema','ownership_valid','id_basis','owner_prefab_uid',
                                   'owner_node_uids','owner_origin_index','instance_slot')],
            [coverage.get(k) for k in ('requires_approach','approach_target','stopping_reserve_m',
                                       'clearance_confirmed')],
            [signal.get(k) for k in ('authority_lane_id','route_progress_m','route_publication_token')]])
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
    if isinstance(pairing,dict) or 'signal_comparison' in selected:
        # Fixed names already have a public schema. Account their values once,
        # then restore names after the bounded copy; no evidence is discarded.
        selected['comparison_fields'] = sum(1 << i for i, k in enumerate(_COMPARISON_FIELDS) if k in selected)
        selected['comparison_values'] = [selected.pop(k) for k in _COMPARISON_FIELDS if k in selected]
    result = bounded_copy(selected, limit=8192)[0]
    if result.get('snapshot_status') and 'recovery_deadlines' in selected:
        # New recovery receipts must not erase an otherwise retained first
        # comparison. Exact existing codec, unchanged 8 KiB evidence budget.
        compact = bounded_copy(pack_source(selected), limit=8192)[0]
        if not compact.get('snapshot_status'):
            result = unpack_source(compact)
    if result.get('snapshot_status') and value.get('invalid_reason'):
        # Preserve the complete comparison first, including its deadline and
        # vehicle binding. Reuse the exact codec within the SAME byte budget.
        compact = bounded_copy(pack_source(selected), limit=8192)[0]
        if not compact.get('snapshot_status'):
            result = unpack_source(compact)
    if result.get('snapshot_status') and value.get('invalid_reason'):
        # A compact producer cause survives optional-tree budget exhaustion.
        priority = {k:value[k] for k in (*_COMPARISON_FIELDS, 'invalid_reason',
            'speed_control_reason', 'actual_context', 'different_fields', 'following_target_id',
            'decisive_brake_actor_id', 'target_evidence') if k in value}
        result = bounded_copy(priority, limit=8192)[0]
        result['optional_details_omitted'] = True
        if same and 'actual_context' in result:
            result['expected_context'] = result['actual_context']
    if result.get('snapshot_status') and isinstance(value.get('refresh_protocol'), dict):
        # Refresh attribution is priority evidence, not a verbose optional
        # subtree. Existing exact codec and SAME 8 KiB allocation; dictionary
        # tables remain unchanged so historical incidents still decode.
        compact = bounded_copy(pack_source(selected), limit=8192)[0]
        if not compact.get('snapshot_status'):
            result = unpack_source(compact)
    if result.get('snapshot_status') and (isinstance(value.get('traffic_comparison'),dict)
                                         or 'signal_comparison' in selected):
        # Preserve the first required traffic cause even when unrelated detail
        # exceeds the existing 8 KiB receipt. Exact source/frame/time and small
        # producer ID examples have priority over optional verbose subtrees.
        priority = {k:value[k] for k in (
            *_COMPARISON_FIELDS, 'actual_context','expected_context','different_fields',
            'rejected_source','traffic_comparison') if k in value}
        if 'signal_comparison' in selected:
            # The rejected physical head is priority evidence too, not optional
            # verbose detail. Reuse its bounded fixed-field representation.
            priority['signal_comparison'] = selected['signal_comparison']
        if same:
            priority.pop('expected_context', None)
        compact = bounded_copy(pack_source(priority), limit=8192)[0]
        preserved = unpack_source(compact)
        if not preserved.get('snapshot_status'):
            result = dict(preserved, capture_incomplete=True,
                snapshot_status='OPTIONAL_FAULT_DETAIL_BUDGET_EXCEEDED')
    if packed:
        if same and 'actual_context' in result:
            result['expected_context_reference'] = 'actual_context'
        return result
    return _expand_fault_details(result, same=same)


def _expand_fault_details(result, *, same=False):
    result = dict(result)
    if 'evidence' in result:
        result['evidence'] = expand_emergency_evidence(result['evidence'])
    signal = result.pop('signal_comparison',None)
    if isinstance(signal,dict) and signal.get('schema') in (1,2):
        values = signal['values']
        if (not isinstance(values,(list,tuple)) or len(values)!=(9 if signal['schema']==1 else 12)
                or not isinstance(values[7],(list,tuple)) or len(values[7])!=5
                or not isinstance(values[8],(list,tuple)) or len(values[8])!=8
                or (signal['schema']==2 and (not isinstance(values[9],(list,tuple)) or len(values[9])!=7
                                            or not isinstance(values[10],(list,tuple)) or len(values[10])!=4
                                            or not isinstance(values[11],(list,tuple)) or len(values[11])!=3))):
            raise ValueError('INVALID_SIGNAL_COMPARISON_FIELDS')
        result['signal'] = dict(zip(
            ('valid','reason','lifecycle','generation','frame_us','observed_at','relevance'),values[:7]))
        result['signal']['coverage'] = dict(zip(
            ('status','requires_takeover','candidate_count','distance_m','reason'),values[7]))
        if type(result['signal']['coverage']['reason']) is int and result['signal']['coverage']['reason'] == 0:
            from core.sdk.signal_snapshot import UNASSIGNED_CONTROL_REASON
            result['signal']['coverage']['reason'] = UNASSIGNED_CONTROL_REASON
        result['signal']['unassigned_candidate'] = dict(zip(
            ('id','x','y','z','yaw','color','distance','distance_basis'),values[8]))
        if signal['schema']==2:
            result['signal']['unassigned_candidate'].update(zip(
                ('scope_schema','ownership_valid','id_basis','owner_prefab_uid','owner_node_uids',
                 'owner_origin_index','instance_slot'),values[9]))
            result['signal']['coverage'].update(zip(
                ('requires_approach','approach_target','stopping_reserve_m','clearance_confirmed'),values[10]))
            result['signal'].update(zip(
                ('authority_lane_id','route_progress_m','route_publication_token'),values[11]))
    if 'comparison_fields' in result:
        mask = result.pop('comparison_fields')
        result.update(zip((k for i, k in enumerate(_COMPARISON_FIELDS) if mask & (1 << i)),
                          result.pop('comparison_values')))
    if 'command_observation_pairing' in result:
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
    details = bounded_fault_details(value['details'], packed=True)
    if (isinstance(details.get('traffic_comparison'),dict)
            or isinstance(details.get('refresh_protocol'),dict)
            or details.get('invalid_reason')):
        # The outer 16 KiB first-fault allocation must not re-charge all the
        # expanded field names and duplicate identity/ID receipts. Reuse the
        # existing exact bounded codec; decode at the same public export edge.
        details = pack_source(details)
    return {**value, 'details': details}


def _expand_intervention(value):
    if not isinstance(value, dict) or not isinstance(value.get('details'), dict):
        return value
    return {**value, 'details': _expand_fault_details(unpack_source(value['details']))}


_DEPARTURE_FIELDS = (
    'schema_version','target_id','status','confirmed','observation_kind',
    'previous_receiver_time','receiver_time','previous_record','record',
    'previous_position_xyz','position_xyz','minimum_body_reference_clearance_m',
    'source','slot','coverage_confirmed',
)


def _expand_departure(following):
    if not isinstance(following, dict):
        return None
    if following.get('departure_schema') == 1:
        values = following.get('departure_values')
        if isinstance(values, (list, tuple)) and len(values) == len(_DEPARTURE_FIELDS):
            return dict(zip(_DEPARTURE_FIELDS, values))
        return None
    return following.get('departure')


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
    for key in ('deadline_basis', 'refresh_protocol', 'invalid_reason', 'traffic_availability', 'destination_brake_selected',
                'producer_timing',
                'signal_stop_control','signal_brake_selected',
                'leader_prediction', 'stop_clearance', 'requested_acceleration_ms2',
                'selected_acceleration_ms2', 'acceleration_basis', 'motion_constraint', 'braking_actor_ids',
                'braking_acquisition','following_kind','following_owner','target_evidence'):
        if key in value:
            result[key] = value[key]
    following_keys = (
        'status', 'target_id', 'gap_m', 'speed_mps', 'speed_cap_mps', 'emergency',
        'reason', 'receiver_time', 'source_timestamp', 'source_sequence',
        'complete', 'atomic', 'confirmed', 'expires_at','protective_target_id',
        'protective_brake','unassigned_protective_brake','actor_identity',
        'leader_prediction','source_acquisition','body_prediction','retained_target_continuity','constraint_completion')
    result['following'] = {k: value['following'].get(k) for k in following_keys} if isinstance(value.get('following'), dict) else None
    if result['following'] is not None and value['following'].get('constraint_completions'):
        result['following']['constraint_completions']=value['following']['constraint_completions']
    if result['following'] is not None:
        for key in ('retained_target_continuities','owner_witnesses_schema','owner_witnesses','candidate_ids'):
            if key in value['following']:result['following'][key]=value['following'][key]
    if result['following'] is not None and isinstance(value['following'].get('departure'), dict):
        proof = value['following']['departure']
        # Fixed fields, exact immutable values, unchanged attribution budget.
        # Repeated literal field names must not erase this short receipt.
        result['following'].update(departure_schema=1,
            departure_values=[proof.get(k) for k in _DEPARTURE_FIELDS])
    if isinstance(value.get('signal'), dict):
        from core.sdk.signal_snapshot import compact
        result['signal'] = compact(value['signal'])
    for key in ('radius_m','distance_m','roundabout_entry_distance_m','display_detection','smoothing'):
        if key in value:
            result[key] = value[key]
    if isinstance(value.get('light'),dict):
        light = value['light']
        candidate = (result.get('signal') or {}).get('candidate')
        if candidate and all(light.get(k) == v for k,v in candidate.items()):
            result['light_reference'] = 'signal.candidate'
        else:
            result['light'] = {k:light[k] for k in ('id','color','x','y','z','yaw','distance',
                'producer_timestamp','producer_generation','passage_key','stop_target_kind') if k in light}
    # Optional crossing/display attribution must not consume the whole input
    # allocation and erase the actually consumed signal/frame/time. Give each
    # auxiliary field a sub-budget inside the existing total allocation.
    for key in ('brake_basis', 'display_detection', 'following'):
        if isinstance(result.get(key), dict):
            original = result[key]
            result[key] = bounded_copy(original, limit=2048)[0]
            if (result[key].get('snapshot_status')
                    and not bounded_copy(original, limit=8192)[0].get('snapshot_status')):
                # Conservative escaped-key accounting can exceed this budget
                # for small, bounded crossing receipts. Use the existing exact
                # source codec, still charged against the same sub-budget.
                # Keep a decoded-size guard: a highly compressible oversized
                # display/reason string must not bypass attribution limits.
                packed, _ = bounded_copy(pack_source(original), limit=2048)
                if not packed.get('snapshot_status'):
                    result[key] = unpack_source(packed)
            if key == 'brake_basis' and result[key].get('snapshot_status'):
                # Added scalar actor evidence can exceed the conservative
                # escaped-key/node estimate while its entire wire value fits
                # the SAME 2 KiB attribution allocation. Bound traversal first
                # by the existing overall input budget; accept only <=2 KiB
                # decoded JSON as well as <=2 KiB compressed storage. Long
                # compressible strings cannot bypass either size guard.
                candidate,_ = bounded_copy(original,limit=16384)
                if not candidate.get('snapshot_status'):
                    wire=json.dumps(candidate,separators=(',',':'),allow_nan=False).encode('utf-8')
                    if len(wire)<=2048:
                        packed,_=bounded_copy(zlib.compress(wire),limit=2048)
                        if isinstance(packed,bytes):
                            result[key]=json.loads(zlib.decompress(packed))
            if key == 'following' and result[key].get('snapshot_status'):
                # Priority receipt only after the full exact codec attempt.
                # Preserve departure witnesses when present, never replace a
                # successfully exported historical contract with a summary.
                compact = {k:original.get(k) for k in ('status','target_id','gap_m',
                    'speed_mps','speed_cap_mps','emergency','source_acquisition',
                    'departure_schema','departure_values','constraint_completion') if original.get(k) is not None}
                compact['optional_prediction_details_omitted'] = True
                kept = bounded_copy(pack_source(compact), limit=2048)[0]
                if not kept.get('snapshot_status'):
                    result[key] = unpack_source(kept)
            if result[key].get('snapshot_status'):
                result['capture_incomplete'] = True
    saved = bounded_copy(result)[0]
    if saved.get('snapshot_status'):
        # Fixed-key/interned storage charges repeated names/values once. It
        # uses the same bounded source codec and fixed input byte budget;
        # external readers still receive explicit original values.
        saved = unpack_source(bounded_copy(pack_source(result))[0])
    result = saved
    # Producer trace is already bounded/packed at publication. Account it once
    # in the journal bind instead of recopying it into every intermediate read.
    if isinstance(value.get('producer_trace'),dict):
        result['producer_trace'] = value['producer_trace']
    return result


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
        trace = requested.get('producer_trace')
        if isinstance(trace,dict):
            trace = expand_decision(trace)
            trace_inputs = trace.get('inputs') or {}
            trace_inputs = {k:{**v,'context':list(v['context'])} if isinstance(v,dict)
                and isinstance(v.get('context'),(tuple,list)) else v for k,v in trace_inputs.items()}
            trace['inputs'] = {k: input_delta(v,inputs[k],k) if isinstance(v,dict)
                and isinstance(inputs.get(k),dict) else v for k,v in trace_inputs.items()}
            truck = trace.get('truck')
            vehicle = dict(sdk_frame_us=value.get('sdk_frame_us'),
                observation_timestamp=value.get('observation_timestamp'),
                observation_valid=value.get('observation_valid'), gear=value.get('observed_gear'),
                speed_mps=value.get('actual_speed_mps'))
            if truck == vehicle:
                trace['truck'] = {'vehicle_reference':'decision'}
            if tuple(trace.get('context', ())) == binding:
                trace.pop('context',None)
                trace['context_reference'] = 'decision'
            result['requested']['producer_trace'] = pack_journal_inputs(pack_brake_requests(trace))
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


def expand_decision(value, *, _defer_departure=False):
    """Restore the existing external field contract from this row's metadata.

    Stored references share immutable scalar/list values; no IPC reread and no
    timestamp repair. Export/readers continue to receive explicit source fields.
    """
    if not isinstance(value, dict):
        return value
    result = dict(value)
    if result.pop('brake_request_schema',None) == 1:
        items=result.pop('brake_request_values')
        result['brake_requests'] = [[_BRAKE_SOURCES[items[i]],_BRAKE_KINDS[items[i+1]],items[i+2]]
                                   for i in range(0,len(items),3)]
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
    requested = result.get('requested')
    if isinstance(requested,dict) and isinstance(requested.get('producer_trace'),dict):
        trace = requested['producer_trace']
        if trace.get('context_reference') == 'decision':
            trace = {**trace, 'context': value['context']}
            trace.pop('context_reference',None)
        trace = expand_decision(trace, _defer_departure=True)
        if trace.get('truck') == {'vehicle_reference':'decision'}:
            trace['truck'] = dict(sdk_frame_us=value.get('sdk_frame_us'),
                observation_timestamp=value.get('observation_timestamp'),
                observation_valid=value.get('observation_valid'), gear=value.get('observed_gear'),
                speed_mps=value.get('actual_speed_mps'))
        trace['inputs'] = {k: restore_input_delta(v,result['inputs'][k]) if isinstance(v,dict)
            and v.get('engine_input_reference') == k else v for k,v in (trace.get('inputs') or {}).items()}
        requested['producer_trace'] = trace
    if 'command_observation_pairing' in result:
        result['command_observation_pairing'] = _expand_pairing(result['command_observation_pairing'])
    result.pop('deadline_basis_schema', None)
    result.pop('deadline_bases', None)
    if not _defer_departure:
        # Delta paths address the stored representation. Restore them before
        # decoding this additive receipt, including the older producer input.
        trace = (result.get('requested') or {}).get('producer_trace') or {}
        for inputs in (result.get('inputs') or {}, trace.get('inputs') or {}):
            for name, item in tuple(inputs.items()):
                following = item.get('following') if isinstance(item, dict) else None
                proof = _expand_departure(following)
                if proof is not None and following.get('departure_schema') == 1:
                    decoded = {k:v for k,v in following.items()
                               if k not in ('departure_schema','departure_values')}
                    inputs[name] = dict(item, following=dict(decoded, departure=proof))
    return result


HISTORY_FIELDS = (
    'monotonic_s','sdk_frame_us','observation_timestamp','activation','decision_sequence',
    'command_sequence','command_sdk_frame_us','command_observation_timestamp',
    'command_computed_at','command_expires_at','command_valid',
    'speed_mps','gear','observation_valid','phase','control_state',
    'requested_speed_kmh','constrained_speed_kmh','control_target_kmh','speed_ceiling_mps',
    'selected_source','reason','throttle','brake','pedal_mode',
    'requested_throttle','requested_brake','selected_throttle','selected_brake','brake_requests',
    'acc_throttle','acc_brake','acc_target_id','acc_status','acc_gap_m','acc_confirmed',
    'traffic_target_id','traffic_target_status','traffic_gap_m','traffic_target_confirmed','speed_control_reason',
    'traffic_brake','light_brake','policy_brake','curve_brake','curve_radius_m','curve_distance_m',
    'signal_id','signal_color','signal_relevance','signal_valid','signal_reason',
    'signal_observed_at','signal_frame_us','signal_generation','signal_lifecycle',
    'signal_lock','stop_target','forward_phase','coast_only','hold_phase','hold_chain',
    'hold_brake','hold_reason','first_reason','first_reason_observed_at',
    'write_first_sequence','write_last_sequence','write_count','write_success_count',
    'write_error_count','write_unverified_count','write_first_started_at_s','write_last_returned_at_s',
    'last_backend_status','last_backend_error','written_throttle','written_brake',
    'backend_throttle_min','backend_throttle_max','backend_brake_min','backend_brake_max',
    'backend_pair_mode_changes','write_source_changes',
    'sdk_game_throttle','sdk_game_brake','aggregate',
    'capture_incomplete',
    # Append only; existing history field indices retain their meanings.
    'signal_native_state','signal_time_left_s','signal_phase_plan',
    'traffic_departure',
    'load_observation', 'sdk_user_throttle', 'sdk_user_brake',
    'motion_constraint',
    'traffic_cause',
    'powertrain_observation',
)


def _decision_summary(source):
    """Small owned values from the actual bind; no producer packets or reads."""
    source=source or {}
    inputs=source.get('inputs') or {}
    acc=inputs.get('acc') or {}
    following=acc.get('following') or {}
    traffic=inputs.get('traffic') or {}
    traffic_target=traffic.get('following') or {}
    traffic_cause=source.get('traffic_cause') or compact_traffic_cause(traffic)
    signal=traffic.get('signal') or {}
    head=signal.get('candidate') or signal.get('stop_candidate') or {}
    policy=inputs.get('policy') or {}
    curve=inputs.get('curve') or {}
    hold=source.get('service_hold') or {}
    forward=source.get('forward_history') or {}
    requested=source.get('requested') or {}
    selected=source.get('selected') or {}
    output=source.get('output_intent') or selected
    trace=requested.get('producer_trace') or {}
    # Producer trace uses the existing compact input schema. Resolve only the
    # small curve fields consumed upstream, not whole producer packets.
    prior_curve=(trace.get('inputs') or {}).get('curve') or {}
    if prior_curve.get('journal_input_schema')==1:
        items=iter(prior_curve['values'])
        prior_curve={k:next(items) for i,k in enumerate(JOURNAL_INPUT_KEYS)
                     if prior_curve['presence'] & (1<<i)}
    if not curve:curve=prior_curve
    intervention=source.get('intervention') or {}
    response=source.get('sdk_response') or {}
    observation=source.get('sdk_observation') or {}
    throttle,brake=output.get('throttle'),output.get('brake')
    mode=('unknown' if throttle is None or brake is None else
          'overlap' if throttle>0 and brake>0 else 'brake' if brake>0 else 'drive' if throttle>0 else 'coast')
    requests=trace.get('brake_requests') or []
    if trace.get('brake_request_schema') == 1:
        values=trace.get('brake_request_values') or []
        requests=[[_BRAKE_SOURCES[values[i]],_BRAKE_KINDS[values[i+1]],values[i+2]]
                  for i in range(0,len(values),3)]
    curve_brake=next((r[2] for r in requests if r[0]=='curve'),None)
    summary=dict(
        sdk_frame_us=source.get('sdk_frame_us'),observation_timestamp=source.get('observation_timestamp'),
        activation=source.get('activation'),decision_sequence=source.get('decision_sequence'),
        command_sequence=trace.get('decision_sequence'),command_sdk_frame_us=requested.get('sdk_frame_us'),
        command_observation_timestamp=requested.get('observation_timestamp'),
        command_computed_at=requested.get('computed_at'),command_expires_at=requested.get('expires_at'),
        command_valid=requested.get('valid'),
        speed_mps=source.get('actual_speed_mps'),gear=source.get('observed_gear'),
        observation_valid=source.get('observation_valid',observation.get('valid')),
        phase=source.get('phase'),control_state=source.get('control_state'),
        requested_speed_kmh=acc.get('requested_speed_kmh'),constrained_speed_kmh=acc.get('constrained_speed_kmh'),
        control_target_kmh=acc.get('control_target_kmh'),speed_ceiling_mps=source.get('speed_ceiling_mps'),
        selected_source=selected.get('source') or output.get('source'),
        reason=output.get('reason') or selected.get('reason'),throttle=throttle,brake=brake,pedal_mode=mode,
        requested_throttle=requested.get('throttle'),requested_brake=requested.get('brake'),
        selected_throttle=selected.get('throttle'),selected_brake=selected.get('brake'),
        brake_requests=requests if requests else None,
        acc_throttle=acc.get('throttle'),acc_brake=acc.get('brake'),
        acc_target_id=following.get('target_id',acc.get('following_target_id')),
        acc_status=following.get('status',acc.get('following_status')),acc_gap_m=following.get('gap_m'),
        acc_confirmed=following.get('confirmed',acc.get('following_confirmed')),
        traffic_target_id=traffic_target.get('target_id'),traffic_target_status=traffic_target.get('status'),
        traffic_gap_m=traffic_target.get('gap_m'),traffic_target_confirmed=traffic_target.get('confirmed'),
        traffic_departure=_expand_departure(traffic_target),
        traffic_cause=traffic_cause,
        speed_control_reason=acc.get('speed_control_reason'),
        traffic_brake=traffic.get('traffic_brake'),light_brake=traffic.get('light_brake'),
        policy_brake=policy.get('brake'),curve_brake=curve_brake,
        curve_radius_m=curve.get('radius_m'),curve_distance_m=curve.get('distance_m'),
        signal_id=head.get('id'),signal_color=head.get('color'),signal_relevance=signal.get('relevance'),
        signal_valid=signal.get('valid'),signal_reason=signal.get('reason'),
        signal_native_state=head.get('state'),signal_time_left_s=head.get('time_left'),
        signal_phase_plan=head.get('phase_plan'),
        signal_observed_at=signal.get('observed_at'),signal_frame_us=signal.get('frame_us'),
        signal_generation=signal.get('generation'),signal_lifecycle=signal.get('lifecycle'),
        signal_lock=hold.get('signal_lock'),
        stop_target={k:head.get(k) for k in ('passage_key','stop_target_kind','distance','distance_basis',
            'entry_progress_m','entry_xyz','stop_line_verified','front_allowance_m')} if head else None,
        forward_phase=forward.get('phase'),coast_only=forward.get('coast_only'),
        hold_phase=hold.get('phase'),hold_chain=hold.get('chain'),hold_brake=hold.get('brake'),
        motion_constraint=({k:v for k,v in traffic['motion_constraint'].items() if k!='authority'}
                           if isinstance(traffic.get('motion_constraint'),dict) else None),
        hold_reason=hold.get('stop_reason'),sdk_game_throttle=response.get('gameThrottle'),sdk_game_brake=response.get('gameBrake'),
        load_observation=source.get('load_observation'),
        powertrain_observation=source.get('powertrain_observation'),
        sdk_user_throttle=response.get('userThrottle'), sdk_user_brake=response.get('userBrake'),
        first_reason=intervention.get('reason'),first_reason_observed_at=intervention.get('observed_at'))
    if any(isinstance(p, dict) and (p.get('capture_incomplete') or p.get('snapshot_status'))
           for p in inputs.values()):
        summary['capture_incomplete'] = True
    # Freeze the small nested lock/target; bound strings without pretending zero.
    for key,value in list(summary.items()):
        if isinstance(value,str) and len(value)>1024:
            summary[key]=None
            summary['capture_incomplete']=True
        elif isinstance(value,(dict,list,tuple)):
            summary[key]=copy.deepcopy(value)
    identity=copy.deepcopy(dict(context=source.get('context'),route_identity=source.get('route_identity')))
    return summary,identity


class _DecisionHistory:
    """An owned PedalJournal component, not a second collector/authority.

    Separate regular/event reservations prevent change bursts from evicting
    the 10 Hz timeline. Fixed-value rows and exact shared identity references.
    """
    WINDOW_S=30.
    PERIOD_S=.1
    REGULAR_CAPACITY=320
    CHANGE_CAPACITY=2048
    REGULAR_BYTES=512*1024
    CHANGE_BYTES=448*1024
    IDENTITY_BYTES=64*1024
    MAX_BYTES=REGULAR_BYTES+CHANGE_BYTES+IDENTITY_BYTES
    ROW_LIMIT=4096

    def __init__(self):
        self.regular=deque();self.changes=deque()
        self.identities={};self.identity_keys={};self.identity_bytes=0;self.next_identity=0
        self.bytes={'regular':0,'changes':0}
        self.dropped={'regular':0,'changes':0};self.aged_out={'regular':0,'changes':0}
        self.failures=0;self.regressions=0;self.sequence=0
        self.failure_reasons=[];self.failure_reason_bytes=0
        self.last_time=None;self.last_sample=None;self.last_signature=None;self.first_time=None
        self.first_reason=None;self.first_reason_at=None;self.first_epoch=None
        self.aggregate={};self.aggregate_started=None

    def _release(self,kind,capacity=False):
        row=getattr(self,kind).popleft();self.bytes[kind]-=row[4]
        entry=self.identities.get(row[2])
        if entry:
            entry['uses']-=1
            if not entry['uses']:
                self.identity_bytes-=entry['size'];del self.identity_keys[entry['blob']];del self.identities[row[2]]
        (self.dropped if capacity else self.aged_out)[kind]+=1

    def _prune(self,now):
        cutoff=now-self.WINDOW_S
        # One leading regular anchor bounds the start of the requested window.
        while len(self.regular)>1 and self.regular[1][1]<=cutoff:
            self._release('regular')
        while self.changes and self.changes[0][1]<cutoff:
            self._release('changes')

    def _append(self,kind,now,row,identity):
        values=[row.get(k) for k in HISTORY_FIELDS]
        blob=json.dumps(values,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')
        identity_blob=json.dumps(identity,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')
        capacity=self.REGULAR_CAPACITY if kind=='regular' else self.CHANGE_CAPACITY
        budget=self.REGULAR_BYTES if kind=='regular' else self.CHANGE_BYTES
        # The exact summary can be slightly over 4 KiB before compression
        # (observed 4,193--4,256 B), yet its retained representation is much
        # smaller. Bound BOTH independently; do not discard valid fields or
        # enlarge any retained ring/pool allowance. The source journal already
        # supports a 32 KiB temporary ownership envelope.
        if len(blob)>32768 or len(identity_blob)>4096:
            self.capture_failure('summary_encode','expanded summary/identity bound',now);return
        # Fixed-value summaries repeat nulls/labels, not full producer packets.
        # Lossless bounded compression retains the thirty-second reservation
        # even with long real identities and physical-edge aggregate fields.
        blob=zlib.compress(blob,1)
        if len(blob)>self.ROW_LIMIT:
            self.capture_failure('summary_encode','compressed summary bound',now);return
        size=len(blob)+256  # Owned bytes/tuple/deque and reference accounting.
        while getattr(self,kind) and (len(getattr(self,kind))>=capacity or self.bytes[kind]+size>budget):
            self._release(kind,capacity=True)
        identity_id=self.identity_keys.get(identity_blob)
        if identity_id is None:
            identity_size=len(identity_blob)+512
            if self.identity_bytes+self.failure_reason_bytes+identity_size>self.IDENTITY_BYTES:
                self.capture_failure('summary_identity','identity pool bound',now);return
            self.next_identity+=1;identity_id=self.next_identity
            self.identities[identity_id]=dict(blob=identity_blob,uses=0,size=identity_size)
            self.identity_keys[identity_blob]=identity_id;self.identity_bytes+=identity_size
        self.identities[identity_id]['uses']+=1
        self.sequence+=1
        getattr(self,kind).append((self.sequence,now,identity_id,blob,size))
        self.bytes[kind]+=size

    def capture_failure(self,operation,reason,now=None):
        self.failures+=1
        # Error-only metadata shares the EXISTING identity-pool reservation.
        # Counters never disappear when the bounded reason ledger fills.
        entry=dict(operation=str(operation)[:48],reason=str(reason)[:96],at_s=now)
        size=128+len(json.dumps(entry,separators=(',',':')).encode('utf-8'))
        if (len(self.failure_reasons)<8 and self.failure_reason_bytes+size<=2048
                and self.identity_bytes+self.failure_reason_bytes+size<=self.IDENTITY_BYTES):
            self.failure_reasons.append(entry);self.failure_reason_bytes+=size

    def observe(self,now,row,identity):
        if not math.isfinite(now) or self.last_time is not None and now<self.last_time:
            self.regressions+=1;return
        if row.get('capture_incomplete'):self.capture_failure('summary_input','consumed input marked incomplete',now)
        self._prune(now)
        if self.first_time is None:self.first_time=now
        self.last_time=now
        row=dict(row,monotonic_s=now)
        if row.get('activation') is not None and row.get('activation')!=self.first_epoch:
            self.first_reason=self.first_reason_at=None;self.first_epoch=row.get('activation')
        if not row.get('first_reason') and row.get('activation')==self.first_epoch:
            row.update(first_reason=self.first_reason,first_reason_observed_at=self.first_reason_at)
        signature=(json.dumps(identity,sort_keys=True,separators=(',',':')),*(row.get(k) for k in
            ('activation','phase','control_state','selected_source','reason','pedal_mode','gear',
             'observation_valid','signal_id','signal_color','signal_relevance','signal_valid',
             'signal_reason','forward_phase','coast_only','hold_phase','hold_chain','hold_reason',
             'traffic_target_id','traffic_target_status',
             'last_backend_status','last_backend_error','first_reason')),
            (row.get('traffic_departure') or {}).get('target_id'),
            ((row.get('traffic_cause') or {}).get('kind'),
             ((row.get('traffic_cause') or {}).get('actor') or {}).get('id')),
            (row.get('signal_lock') or {}).get('id'),(row.get('stop_target') or {}).get('passage_key'))
        changed=self.last_signature is not None and signature!=self.last_signature
        mode_changed=self.last_signature is not None and row.get('pedal_mode')!=self.aggregate.get('last_mode')
        a=self.aggregate
        if self.aggregate_started is None:self.aggregate_started=now
        for key,value in (('decision_count',1),('state_changes',int(changed)),('pedal_mode_changes',int(mode_changed)),
                          ('write_count',row.get('write_count',0)),('write_error_count',row.get('write_error_count',0))):
            a[key]=a.get(key,0)+value
        for key in ('backend_pair_mode_changes','write_source_changes'):
            a[key]=a.get(key,0)+(row.get(key) or 0)
        for name in ('backend_throttle','backend_brake'):
            for suffix,op in (('_min',min),('_max',max)):
                value=row.get(name+suffix)
                if value is not None:a[name+suffix]=op(a.get(name+suffix,value),value)
        for name in ('throttle','brake','speed_mps'):
            value=row.get(name)
            if isinstance(value,(int,float)) and math.isfinite(value):
                a[name+'_min']=min(a.get(name+'_min',value),value)
                a[name+'_max']=max(a.get(name+'_max',value),value)
        a['last_mode']=row.get('pedal_mode')
        if self.last_signature is None or changed:
            self._append('changes',now,row,identity)
        self.last_signature=signature
        if self.last_sample is None or now-self.last_sample>=self.PERIOD_S-1e-9:
            row['aggregate']=dict(a,started_at_s=self.aggregate_started,ended_at_s=now,
                                  exact_write_timing=False)
            self._append('regular',now,row,identity)
            self.last_sample=now;self.aggregate={ 'last_mode':row.get('pedal_mode') };self.aggregate_started=None

    def intervention(self,fault,now):
        if self.first_epoch==fault.get('epoch') and self.first_reason is not None:return
        self.first_epoch=fault.get('epoch');self.first_reason=fault.get('reason');self.first_reason_at=fault.get('observed_at')
        self._prune(now)
        self._append('changes',now,dict(monotonic_s=now,activation=fault.get('epoch'),
            sdk_frame_us=fault.get('sdk_frame_us'),observation_timestamp=fault.get('observation_timestamp'),
            phase='intervention',first_reason=self.first_reason,first_reason_observed_at=self.first_reason_at),
            dict(context=fault.get('context'),route_identity=None))

    def snapshot(self):
        rows=list(self.regular)+list(self.changes)
        start=min((r[1] for r in rows),default=None);end=max((r[1] for r in rows),default=None)
        return dict(schema_version=1,storage='fixed_values_zlib',fields=HISTORY_FIELDS,
            regular_samples=list(self.regular),changes=list(self.changes),
            identities={str(k):v['blob'] for k,v in self.identities.items()},
            byte_budget=self.MAX_BYTES,retained_bytes=sum(self.bytes.values())+self.identity_bytes+self.failure_reason_bytes,
            regular_byte_budget=self.REGULAR_BYTES,change_byte_budget=self.CHANGE_BYTES,
            identity_byte_budget=self.IDENTITY_BYTES,regular_capacity=self.REGULAR_CAPACITY,change_capacity=self.CHANGE_CAPACITY,
            requested_window_s=self.WINDOW_S,regular_period_s=self.PERIOD_S,
            window_start_s=None if end is None else end-self.WINDOW_S,window_end_s=end,
            observed_range_s=dict(start=start,end=end,duration=None if start is None else end-start),
            regular_dropped_capacity=self.dropped['regular'],change_dropped_capacity=self.dropped['changes'],
            regular_aged_out=self.aged_out['regular'],change_aged_out=self.aged_out['changes'],
            capture_failures=self.failures,time_regressions=self.regressions,
            failure_reasons=list(self.failure_reasons),failure_reason_bytes=self.failure_reason_bytes,
            incomplete=bool(sum(self.dropped.values()) or self.failures or self.regressions),
            aggregate_tail=dict(self.aggregate),full_backend_resolution=False,
            last_decision_at_s=self.last_time,
            unsampled_tail_s=None if end is None or self.last_time is None else max(0.,self.last_time-end),
            warmup=bool(self.first_time is None or self.last_time-self.first_time<self.WINDOW_S),
            game_consumption_verified=False)


def expand_history(value):
    if not isinstance(value,dict) or value.get('storage')!='fixed_values_zlib':return value
    result={k:v for k,v in value.items() if k not in ('storage','fields','identities','regular_samples','changes')}
    identities={k:json.loads(v) for k,v in value['identities'].items()}
    for kind in ('regular_samples','changes'):
        rows=[]
        for sequence,t,reference,blob,size in value[kind]:
            values=json.loads(zlib.decompress(blob))
            if len(values)!=len(value['fields']):raise ValueError('INVALID_DECISION_HISTORY_FIELDS')
            row=dict(zip(value['fields'],values))
            if row['monotonic_s']!=t:raise ValueError('INVALID_DECISION_HISTORY_TIME')
            row.update(sequence=sequence,identity_reference=str(reference))
            rows.append(row)
        result[kind]=rows
    result['identities']=identities
    return result


class _WindowEntry(list):
    __slots__=('__weakref__',)


def freeze_exact_record(value, *, byte_limit=512*1024):
    """Standalone primitive-record codec; not connected to runtime by default.

    No field splitting, deduplication, live-row rewriting or timestamp changes.
    Validation rejects types marshal would silently coerce (e.g. bytearray).
    The private binary transport is decoded only by the paired bounded reader;
    the external incident files keep their existing JSON/integrity contract.
    """
    remaining=[(value,0)];nodes=0;estimated=0
    while remaining:
        item,depth=remaining.pop();nodes+=1
        if depth>32 or nodes>40000:raise ValueError('EXACT_RECORD_NODE_BUDGET')
        kind=type(item)
        if kind is dict:
            estimated+=5
            for key,child in item.items():remaining.extend(((key,depth+1),(child,depth+1)))
        elif kind in (list,tuple):
            estimated+=5;remaining.extend((child,depth+1) for child in item)
        elif kind is str:estimated+=5+len(item)*4
        elif kind is bytes:estimated+=5+len(item)
        elif kind is int:estimated+=5+2*((item.bit_length()+14)//15)
        elif kind is float:estimated+=9
        elif item is None or kind is bool:estimated+=1
        else:raise ValueError('EXACT_RECORD_UNSUPPORTED_TYPE:'+kind.__name__)
        if estimated>byte_limit:raise ValueError('EXACT_RECORD_BYTE_BUDGET')
    raw=marshal.dumps(value,2)
    if len(raw)>byte_limit:raise ValueError('EXACT_RECORD_BYTE_BUDGET')
    return dict(encoding='internal-owned-raw-v1',record_codec='marshal2-exact-v1',
        blob=raw,raw_bytes=len(raw),raw_sha256=hashlib.sha256(raw).hexdigest())


def restore_exact_record(record, *, byte_limit=512*1024):
    """Restore exactly once; source dictionaries are never interpreted as tags."""
    import io
    length=record.get('raw_bytes')
    if (record.get('record_codec') not in ('marshal2-exact-v1','pickle5-primitives-v1') or type(length) is not int
            or not 0<=length<=byte_limit or type(record.get('blob')) is not bytes):
        raise ValueError('EXACT_RECORD_HEADER')
    encoding=record.get('encoding')
    if encoding=='internal-owned-window-v1':
        decoder=zlib.decompressobj();raw=decoder.decompress(record['blob'],length+1)
        if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:raise ValueError('EXACT_RECORD_COMPRESSION')
    elif encoding in ('internal-owned-raw-v1','internal-owned-raw-stored-v1'):raw=record['blob']
    else:raise ValueError('EXACT_RECORD_ENCODING')
    if len(raw)!=length or hashlib.sha256(raw).hexdigest()!=record.get('raw_sha256'):
        raise ValueError('EXACT_RECORD_HASH')
    source=io.BytesIO(raw)
    value=(_PrimitiveRecordUnpickler(source).load() if record['record_codec']=='pickle5-primitives-v1'
        else marshal.load(source))
    if source.tell()!=len(raw):raise ValueError('EXACT_RECORD_TRAILING_BYTES')
    return value


class _PrimitiveRecordPickler(pickle.Pickler):
    """C fast path for built-in values; never invoke a producer object's reducer."""
    def reducer_override(self,value):
        raise ValueError('EXACT_RECORD_UNSUPPORTED_TYPE:'+type(value).__name__)


class _PrimitiveRecordUnpickler(pickle.Unpickler):
    # Only this process's owned internal frames use pickle. External incident
    # files use the independently tested whitelisted typed-JSON reader above.
    def find_class(self,module,name):raise ValueError('EXACT_RECORD_CLASS_FORBIDDEN')
    def persistent_load(self,pid):raise ValueError('EXACT_RECORD_PERSISTENT_FORBIDDEN')


def freeze_primitive_record(value, *, byte_limit=512*1024):
    """One bounded C ownership copy, no custom object hooks or field walk.

    The existing SDK's primitive dict/list/tuple/bytes/scalar contract is used;
    custom instances are rejected before __reduce__ can execute. This function
    is not connected to the candidate until its standalone tests pass.
    """
    import io
    stream=io.BytesIO();_PrimitiveRecordPickler(stream,protocol=5).dump(value);raw=stream.getvalue()
    if len(raw)>byte_limit:raise ValueError('EXACT_RECORD_BYTE_BUDGET')
    return dict(encoding='internal-owned-raw-v1',record_codec='pickle5-primitives-v1',
        blob=raw,raw_bytes=len(raw),raw_sha256=hashlib.sha256(raw).hexdigest())


def pack_exact_window(value):
    """Worker-only JSON transport of independent exact records, not a new ring.

    The simple frame's original primitive types survive the existing JSON
    export. No paths into producer fields, cross-record interning or deferred
    mutable shared-state references are introduced.
    """
    import base64,struct
    def typed(item):
        kind=type(item)
        if item is None:return ['n']
        if kind is bool:return ['b',item]
        if kind is int:return ['i',hex(item)]
        if kind is float:return ['f',struct.pack('!d',item).hex()]
        if kind is str:return ['s',item]
        if kind is bytes:return ['y',base64.b64encode(item).decode('ascii')]
        if kind is dict:return ['d',[[typed(k),typed(v)] for k,v in item.items()]]
        if kind in (list,tuple):return ['l' if kind is list else 't',[typed(v) for v in item]]
        raise ValueError('EXACT_RECORD_UNSUPPORTED_TYPE')
    def frame(original):
        record=freeze_exact_record(original)
        # External files never deserialize marshal. An explicit per-record
        # primitive-type JSON tree preserves float bits/tuples/bytes without
        # callable classes, field paths or cross-record reconstruction.
        raw=json.dumps(typed(original),ensure_ascii=False,separators=(',',':')).encode('utf-8')
        if len(raw)>4*1024*1024:raise ValueError('EXACT_WINDOW_WIRE_SIZE')
        return dict(record_codec='typed-json-v1',source_bytes=record['raw_bytes'],
            source_sha256=record['raw_sha256'],blob=dict(encoding='typed-json-zlib-base64',raw_bytes=len(raw),
            raw_sha256=hashlib.sha256(raw).hexdigest(),data=base64.b64encode(zlib.compress(raw,1)).decode('ascii')))
    result=dict(value,_exact_record_window=1,
        records=[dict(row,value=frame(row['value'])) for row in value['records']])
    if 'subevents' in value:
        result['subevents']=[dict(event,receipt=frame(event['receipt'])) for event in value['subevents']]
    if value.get('first_intervention'):
        result['first_intervention']=dict(value['first_intervention'],receipt=frame(value['first_intervention']['receipt']))
    return result


def unpack_exact_window(value):
    """Paired bounded reader, after the existing outer JSON/file hash check."""
    import base64,struct
    if value.get('_exact_record_window')!=1:raise ValueError('EXACT_WINDOW_SCHEMA')
    def original(frame):
        blob=frame.get('blob') or {};length=blob.get('raw_bytes')
        if (frame.get('record_codec')!='typed-json-v1' or type(length) is not int or not 0<=length<=4*1024*1024
                or blob.get('encoding')!='typed-json-zlib-base64'):raise ValueError('EXACT_WINDOW_RECORD_HEADER')
        compressed=base64.b64decode(blob['data'],validate=True)
        decoder=zlib.decompressobj();raw=decoder.decompress(compressed,length+1)
        if (not decoder.eof or decoder.unused_data or decoder.unconsumed_tail or len(raw)!=length
                or hashlib.sha256(raw).hexdigest()!=blob.get('raw_sha256')):raise ValueError('EXACT_WINDOW_WIRE_HASH')
        nodes=[0]
        def untyped(item,depth=0):
            nodes[0]+=1
            if depth>32 or nodes[0]>40000 or type(item) is not list or not item:raise ValueError('EXACT_WINDOW_TYPE_TREE')
            tag=item[0]
            if tag=='n' and len(item)==1:return None
            if len(item)!=2:raise ValueError('EXACT_WINDOW_TYPE_TREE')
            v=item[1]
            if tag=='b' and type(v) is bool:return v
            if tag=='i' and type(v) is str:return int(v,16)
            if tag=='f' and type(v) is str and len(v)==16:return struct.unpack('!d',bytes.fromhex(v))[0]
            if tag=='s' and type(v) is str:return v
            if tag=='y' and type(v) is str:return base64.b64decode(v,validate=True)
            if tag in ('l','t') and type(v) is list:
                values=[untyped(child,depth+1) for child in v]
                return values if tag=='l' else tuple(values)
            if tag=='d' and type(v) is list:
                result={}
                for pair in v:
                    if type(pair) is not list or len(pair)!=2:raise ValueError('EXACT_WINDOW_TYPE_TREE')
                    key=untyped(pair[0],depth+1)
                    if key in result:raise ValueError('EXACT_WINDOW_DUPLICATE_KEY')
                    result[key]=untyped(pair[1],depth+1)
                return result
            raise ValueError('EXACT_WINDOW_TYPE_TREE')
        result=untyped(json.loads(raw));checked=freeze_exact_record(result)
        if checked['raw_bytes']!=frame.get('source_bytes') or checked['raw_sha256']!=frame.get('source_sha256'):
            raise ValueError('EXACT_WINDOW_SOURCE_HASH')
        return result
    result=dict(value,records=[dict(row,value=original(row['value'])) for row in value['records']])
    result.pop('_exact_record_window')
    if 'subevents' in value:
        result['subevents']=[dict(event,receipt=original(event['receipt'])) for event in value['subevents']]
    if value.get('first_intervention'):
        result['first_intervention']=dict(value['first_intervention'],receipt=original(value['first_intervention']['receipt']))
    return result


class _SharedWindowInput:
    """Exact immutable-byte identity, shared only within one evidence window."""
    __slots__=('value','size','uses','__weakref__')
    def __init__(self,value):
        self.value=value;self.size=1024+len(value['blob']);self.uses=0


class _WindowCompression:
    """One bounded, passive compression worker per process; no payload queue.

    Windows own all bytes in their existing budgets. Notifications retain only
    weak window references (maximum 16), never additional producer snapshots.
    A batch pins at most 32 existing records, <=16 MiB of bounded scratch.
    """
    lock=threading.Lock()
    windows=weakref.WeakSet()
    wake=threading.Event()
    worker=None

    @classmethod
    def register(cls,window):
        with cls.lock:
            if len(cls.windows)>=16:
                window.failures+=1
                return  # Diagnostic overload must never fail plugin startup.
            cls.windows.add(window)
            if cls.worker is None:
                cls.worker=threading.Thread(target=cls.run,name='diagnostic-window-compression',daemon=True)
                cls.worker.start()

    @classmethod
    def run(cls):
        while True:
            cls.wake.wait();cls.wake.clear()
            # Optional retention compression is not control work. Coalesce
            # notifications for one existing 60 Hz control period instead of
            # repeatedly reacquiring the parent's GIL after every offered row.
            # Raw rows remain exact and charged to the SAME fixed ring budget;
            # the existing 32-record batch/weak queue limits are unchanged.
            time.sleep(1/60)
            with cls.lock:windows=list(cls.windows)
            for window in windows:
                batch=[]
                with window.lock:
                    for _ in range(min(32,len(window.compression_pending))):
                        entry=window.compression_pending.popleft()()
                        if entry is not None:batch.append(entry)
                for entry in batch:
                    shared=isinstance(entry,_SharedWindowInput)
                    value=entry.value if shared else entry[0]['value'];raw=value['blob']
                    try:blob=zlib.compress(raw,1)
                    except Exception:
                        # Exact raw bytes are still retained. Compression is
                        # optional; do not kill the sole worker or lose data.
                        blob=raw
                        with window.lock:window.compression_errors+=1
                    if len(blob)>=len(raw):
                        # Do not retry incompressible bytes each notification.
                        replacement=dict(value,encoding='internal-owned-raw-stored-v1')
                    else:
                        replacement=dict(value,encoding='internal-owned-window-v1',blob=blob)
                    with window.lock:
                        if shared:
                            size=1024+len(replacement['blob'])
                            if entry.uses:window.bytes+=size-entry.size
                            if entry in window._pin_shared:window._pin_bytes+=size-entry.size
                            entry.value=replacement;entry.size=size
                        else:entry[0]['value']=replacement
                        if not shared and id(entry) in window.live:
                            size=1024+len(replacement['blob'])
                            if id(entry) in window._pin_ids:window._pin_bytes+=size-entry[1]
                            window.bytes+=size-entry[1];entry[1]=size
                if window.compression_pending:cls.wake.set()
            # The registry is weak. A daemon's loop locals must not accidentally
            # retain all finished test/application windows forever.
            windows.clear()
            if 'batch' in locals():batch.clear()
            window=entry=value=raw=blob=replacement=None


def _freeze_input(value):
    """Bounded C ownership copy; no JSON, compression, I/O or worker wait.

    Marshal operates only on already-consumed primitive snapshots. It is not
    an external-file codec. Original values and times are never synthesized.
    """
    # Version 4 embeds Python reference-count-dependent intern/reference flags.
    # IPC copies of equal primitive values then hash differently and defeat
    # exact-value sharing. Version 2 preserves the same values/types/order and
    # float bytes without those process-local ownership flags. This changes no
    # observation, source field, live-record layout or control decision.
    raw=marshal.dumps(value,2)
    if len(raw)>512*1024:raise ValueError('INCIDENT_PACKED_RECORD_SIZE')
    return dict(encoding='internal-owned-raw-v1',blob=raw,raw_bytes=len(raw),
        raw_sha256=hashlib.sha256(raw).hexdigest())


def _thaw_input(value):
    if isinstance(value,dict):
        encoding=value.get('encoding')
        if encoding in ('internal-owned-raw-v1','internal-owned-raw-stored-v1','internal-owned-window-v1'):
            length=value['raw_bytes']
            if type(length) is not int or not 0<=length<=512*1024:raise ValueError('INCIDENT_PACKED_SIZE')
            raw=(zlib.decompressobj().decompress(value['blob'],length+1)
                if encoding=='internal-owned-window-v1' else value['blob'])
            if len(raw)!=length or hashlib.sha256(raw).hexdigest()!=value['raw_sha256']:
                raise ValueError('INCIDENT_PACKED_HASH')
            return _thaw_input(marshal.loads(raw))
        return {k:_thaw_input(v) for k,v in value.items()}
    if isinstance(value,list):return [_thaw_input(v) for v in value]
    if isinstance(value,tuple):return tuple(_thaw_input(v) for v in value)
    return value


def diagnostic_build_limits():
    """Only the separately approved temporary build uses the larger budget."""
    try:
        from core.navigation.diagnostic_build_config import ENABLED, MEMORY_BUDGET_APPROVED
        approved=ENABLED is True and MEMORY_BUDGET_APPROVED is True
    except ImportError:approved=False
    return dict(approved=approved,engine_ring_bytes=(64 if approved else 32)*1024*1024,
        autopilot_ring_bytes=32*1024*1024,engine_file_bytes=(32 if approved else 16)*1024*1024,
        export_child_rss_bytes=(1536 if approved else 512)*1024*1024,
        additional_family_rss_bytes=2048*1024*1024 if approved else None,
        parent_additional_rss_bytes=512*1024*1024 if approved else None)


class _IncidentWindow:
    """Optional full-input window owned by the existing journal, not authority.

    10 Hz per source, exact state edges, 40 s rolling retention, 32 MiB ceiling.
    One pending incident pins no second ring. Large owned input values use
    exact compressed retention in this same budget. Expansion and disk export
    belong to the existing worker, never the control tick.
    """
    PRE_S, POST_S, PERIOD_S = 30., 10., .1
    MAX_EVENTS = 256
    PART_SECONDS = 20.

    def __init__(self, byte_limit, *, deferred=False, simple_records=None):
        if not 4096 <= byte_limit <= diagnostic_build_limits()['engine_ring_bytes']:
            raise ValueError('INCIDENT_MEMORY_BUDGET')
        self.limit = byte_limit
        self.rows = deque()
        self.live=set()
        # Weak work references cannot keep evicted payloads alive. The minimum
        # charged row size is 1 KiB, so this also bounds queued references by
        # the maximum rows in the unchanged 32 MiB ring. No scanning of 40 s
        # of history under the producer lock is needed for each new record.
        self.compression_pending=deque(maxlen=32768)
        self.shared_inputs=weakref.WeakValueDictionary()
        self.deferred=deferred
        self.bytes = self.drops = self.failures = self.sequence = 0
        self.compression_errors=0
        self.pending = None
        self._pin_ids=set();self._pin_shared=set();self._pin_bytes=0
        self.last = {}
        self.signatures = {}
        self.lock = threading.Lock()
        self.session = __import__('uuid').uuid4().hex
        self.receiver_retention_margin_s = 0.
        self.exact_consumers=False
        if simple_records is None:
            try:
                from core.navigation.diagnostic_build_config import SIMPLE_RECORDS
            except ImportError:SIMPLE_RECORDS=False
            simple_records=SIMPLE_RECORDS
        self.simple_records=deferred and bool(simple_records)
        if deferred:_WindowCompression.register(self)

    @staticmethod
    def copy(value, limit):
        remaining = [limit]
        visits = [0]
        def own(item, depth=0):
            visits[0] += 1
            if depth > 32 or visits[0] > 40000:
                raise ValueError('INCIDENT_NODE_BUDGET')
            if isinstance(item, dict):
                remaining[0] -= 72+len(item)*32
                result = {str(k):own(v,depth+1) for k,v in item.items()}
            elif isinstance(item,(tuple,list)):
                remaining[0] -= 64+len(item)*8
                result = [own(v,depth+1) for v in item]
            elif isinstance(item,(str,bytes)):
                remaining[0] -= 64+len(item)* (4 if isinstance(item,str) else 1)
                result = item  # immutable bytes/string, no pointer to producer dict
            elif item is None or isinstance(item,(int,float,bool)):
                remaining[0] -= 32
                result = item
            else:
                remaining[0] -= 128
                result = {'status':'unavailable','type':type(item).__name__}
            if remaining[0] < 0:
                raise ValueError('INCIDENT_RECORD_MEMORY_BUDGET')
            return result
        copied = own(value)
        return copied, limit-remaining[0]

    @staticmethod
    def retain(value,size):
        if size<8192 or isinstance(value,dict) and value.get('encoding')=='ap-transaction-zlib-v1':return value,size
        # Only owned primitive trees enter this internal transport. Marshal is
        # never accepted from an external replay/file; final evidence remains
        # the existing JSON/immutable-reference codec. No values are discarded.
        import marshal,hashlib
        raw=marshal.dumps(value,4)
        if len(raw)>512*1024:raise ValueError('INCIDENT_PACKED_RECORD_SIZE')
        blob=zlib.compress(raw,1)
        retained=1024+len(blob)  # container, row, digest and primitive overhead
        if retained>=size:return value,size
        return dict(encoding='internal-owned-window-v1',blob=blob,
            raw_bytes=len(raw),raw_sha256=hashlib.sha256(raw).hexdigest()),retained

    @staticmethod
    def expanded_row(row, cache=None):
        value=row.get('value') or {}
        if isinstance(value,dict) and value.get('record_codec') in ('marshal2-exact-v1','pickle5-primitives-v1'):
            return dict(row,value=restore_exact_record(value))
        if isinstance(value,dict) and value.get('encoding')=='owned-input-envelope-v1':
            result=_thaw_input(value['skeleton'])
            for key,shared in value['inputs'].items():
                token=id(shared)
                if cache is not None and token in cache:decoded=cache[token]
                else:
                    decoded=_thaw_input(shared.value)
                    if cache is not None:cache[token]=decoded
                result[key]=decoded
            return dict(row,value=result)
        if isinstance(value,dict) and value.get('encoding') in ('internal-owned-raw-v1','internal-owned-raw-stored-v1'):
            return dict(row,value=_thaw_input(value))
        if not isinstance(value,dict) or value.get('encoding')!='internal-owned-window-v1':return row
        import marshal,hashlib
        length=value['raw_bytes']
        if type(length) is not int or not 0<=length<=512*1024:raise ValueError('INCIDENT_PACKED_SIZE')
        raw=zlib.decompressobj().decompress(value['blob'],length+1)
        if len(raw)!=length or hashlib.sha256(raw).hexdigest()!=value['raw_sha256']:
            raise ValueError('INCIDENT_PACKED_HASH')
        return dict(row,value=_thaw_input(marshal.loads(raw)))

    def own_envelope(self,value):
        """Freeze large field values once, share their exact SHA-256 identity.

        Read/check times stay in each individual envelope. The weak intern
        table cannot keep expired payloads alive; live/pinned row references
        own them. All unique live payload bytes count in the SAME ring limit.
        """
        skeleton=dict(value);inputs={};total=0
        for key,item in value.items():
            if not isinstance(item,(dict,list,tuple,bytes)):continue
            frozen=_freeze_input(item);total+=len(frozen['blob'])
            if total>512*1024:raise ValueError('INCIDENT_RECORD_MEMORY_BUDGET')
            if len(frozen['blob'])<1024:continue
            token=(frozen['raw_sha256'],frozen['raw_bytes'])
            with self.lock:
                shared=self.shared_inputs.get(token)
                if shared is None:
                    shared=_SharedWindowInput(frozen);self.shared_inputs[token]=shared
                    if frozen['raw_bytes']>=8192:self.compression_pending.append(weakref.ref(shared))
            inputs[key]=shared;del skeleton[key]
        frozen=_freeze_input(skeleton)
        if total+len(frozen['blob'])>512*1024:raise ValueError('INCIDENT_RECORD_MEMORY_BUDGET')
        return dict(encoding='owned-input-envelope-v1',skeleton=frozen,inputs=inputs),1024+len(frozen['blob'])+len(inputs)*64

    @staticmethod
    def row_inputs(row):
        value=row['value']
        return set(value['inputs'].values()) if isinstance(value,dict) and value.get('encoding')=='owned-input-envelope-v1' else set()

    def drop_entry(self,entry):
        self.live.discard(id(entry));self.bytes-=entry[1]
        value=entry[0]['value']
        if isinstance(value,dict) and value.get('encoding')=='owned-input-envelope-v1':
            for shared in self.row_inputs(entry[0]):
                shared.uses-=1
                if shared.uses==0:self.bytes-=shared.size

    def retained_cost(self,entries):
        entries=list(entries)
        shared={v for row,_ in entries for v in self.row_inputs(row)}
        return sum(size for _,size in entries)+sum(v.size for v in shared)

    def _start_pending_pin(self):
        # Called under the existing window lock. Retain original mutable size
        # accounting entries, not copies whose charge cannot follow compression.
        before=self.pending['before']
        self.pending['before']=list(before)
        self._pin_ids={id(e) for e in before}
        if self.simple_records:
            # This format never has shared-envelope rows. Do not allocate two
            # empty tracked sets PER retained row under the common ring lock.
            # Those needless allocations could run a major collection here.
            self._pin_shared.clear()
            self._pin_bytes=sum(e[1] for e in before)
        else:
            self._pin_shared={s for row,_ in before for s in self.row_inputs(row)}
            self._pin_bytes=self.retained_cost(before)

    def _pin_pending_entry(self,entry,inputs):
        if self.pending is None or id(entry) in self._pin_ids:return
        # observe already prepared this exact set OUTSIDE the shared lock.
        # Do not allocate another set/list here: collection under this lock
        # can otherwise stall the independent producer/executor.
        size=entry[1]
        for shared in inputs:
            if shared not in self._pin_shared:size+=shared.size
        if self._pin_bytes+size>self.limit:
            self.drops+=1
            return  # Honest finite overload, never an unbounded second queue.
        self.pending['before'].append(entry)
        self._pin_ids.add(id(entry));self._pin_shared.update(inputs);self._pin_bytes+=size

    def observe(self, kind, value, now, *, force=False, primitive_snapshot=None):
        packet=(value.get('packet') or value.get('command') or value) if isinstance(value,dict) else {}
        packet=packet if isinstance(packet,dict) else {}
        following=packet.get('following') or {}
        signal=packet.get('signal') or {}
        following=following if isinstance(following,dict) else {}
        signal=signal if isinstance(signal,dict) else {}
        light=signal.get('candidate') or signal.get('stop_candidate') or {}
        selected=packet.get('selected') or packet
        light=light if isinstance(light,dict) else {}
        selected=selected if isinstance(selected,dict) else {}
        def pedal_mode(field):
            v=selected.get(field)
            return v>0. if isinstance(v,(int,float)) else None
        signature=(packet.get('context'),packet.get('valid'),value.get('reason') if isinstance(value,dict) else None,
            packet.get('phase'),packet.get('control_state'),following.get('target_id'),following.get('status'),
            light.get('id'),light.get('color'),light.get('stop_required'),pedal_mode('throttle'),pedal_mode('brake'),
            bool(packet.get('traffic_brake')),bool(packet.get('light_brake')),packet.get('emergency'))
        with self.lock:
            previous = self.last.get(kind)
            changed=kind in self.signatures and self.signatures[kind]!=signature
            if previous is not None and not force and not changed and now >= previous and now-previous < self.PERIOD_S-1e-9:
                return
            self.last[kind] = now
            self.signatures[kind]=signature
        # Own the source outside the short ring lock. The traffic producer's
        # native array copy must not hold up the executor's independent tap.
        try:
            if self.deferred:
                if self.simple_records:
                    owned=freeze_primitive_record(value);size=1024+len(owned['blob'])
                    if primitive_snapshot is not None:
                        # Each store owns its metadata. Only the immutable bytes are shared.
                        primitive_snapshot.append(owned.copy())
                elif self.exact_consumers and isinstance(value,dict):owned,size=self.own_envelope(value)
                else:owned=_freeze_input(value);size=1024+len(owned['blob'])
                if size>self.limit:raise ValueError('INCIDENT_RECORD_MEMORY_BUDGET')
                if kind=='ap_decision':owned['command_computed_at']=value.get('command_computed_at')
                if kind=='backend_call':owned['decision_reference']=value.get('decision_reference')
                if kind=='pedal_binding':owned['consumed_input_references']=value.get('consumed_input_references')
            else:
                owned,size = self.copy(value,min(self.limit,512*1024))
                owned,size = self.retain(owned,size)
        except (ValueError,TypeError,RecursionError):
            with self.lock:
                self.failures += 1
            return
        # Allocate GC-tracked containers and weak references before taking the
        # shared ring lock. A generation collection here must not stall its
        # independent producer/executor while holding that lock.
        row=dict(sequence=None,stream_id=self.session,kind=kind,at_s=now,value=owned)
        entry=_WindowEntry([row,size])
        inputs=self.row_inputs(row)
        compression_reference=(weakref.ref(entry) if self.deferred and owned.get('raw_bytes',0)>=8192 else None)
        with self.lock:
            self.sequence += 1
            row['sequence']=self.sequence
            while self.rows and now-self.rows[0][0]['at_s']>self.PRE_S+self.POST_S+.2+self.receiver_retention_margin_s:
                self.drop_entry(self.rows.popleft())
            required=size
            for shared in inputs:
                if not shared.uses:required+=shared.size
            while self.rows and self.bytes+required>self.limit:
                self.drop_entry(self.rows.popleft());self.drops+=1
                required=size
                for shared in inputs:
                    if not shared.uses:required+=shared.size
            if self.bytes+required>self.limit:
                self.failures+=1;return
            for shared in inputs:
                if not shared.uses:self.bytes+=shared.size
                shared.uses+=1
            self.rows.append(entry);self.live.add(id(entry));self.bytes+=size
            self._pin_pending_entry(entry,inputs)
            if compression_reference is not None:self.compression_pending.append(compression_reference)
        if self.deferred and self.compression_pending:_WindowCompression.wake.set()
        return [self.session,row['sequence']]

    def event(self, kind, receipt, now):
        # The previous implementation copied/compressed a potentially large
        # owner witness while holding the control-side ring lock. A deferred
        # window freezes it once in C; the unchanged aggregate receipt budget
        # (256 * 16 KiB) also bounds uncompressed ownership until export.
        generic=kind in ('EGO_TRANSITION','TRAFFIC_TRANSITION','SIGNAL_NATIVE_TRANSITION','STATE_TRANSITION')
        if generic and self.pending is None and not (isinstance(receipt,dict) and receipt.get('reason')):return
        frozen=None
        if self.deferred:
            try:
                original=receipt
                details=receipt.get('details') if isinstance(receipt,dict) else None
                if isinstance(details,dict):
                    # Preserve the pre-existing compact first-fault contract
                    # even when exact shared-value ownership now fits the full
                    # witness which formerly exhausted the recursive budget.
                    priority={k:details.get(k) for k in ('checked_at','sdk_frame_us',
                        'observation_timestamp','computed_at','expires_at','actual_context',
                        'expected_context','different_fields','rejected_source','rejection_cause')}
                    original=dict(receipt,priority_details=bounded_copy(priority,limit=4096)[0])
                frozen=freeze_primitive_record(original) if self.simple_records else _freeze_input(original)
            except (ValueError,TypeError,RecursionError):pass
        with self.lock:
            try:
                if self.deferred:
                    if frozen is None:raise ValueError('EVENT_RECEIPT_BUDGET')
                    size=1024+len(frozen['blob'])
                    used=(self.pending or {}).get('receipt_bytes',0)
                    if used+size>self.MAX_EVENTS*16384:raise ValueError('EVENT_RECEIPT_BUDGET')
                    owned=dict(frozen,**{k:receipt.get(k) for k in ('reason','epoch','observed_at')})
                else:
                    owned,size=self.copy(receipt,512*1024)
                    original=owned
                    owned,size=self.retain(owned,size)
                    if size>16384:raise ValueError('EVENT_RECEIPT_BUDGET')
                    if isinstance(owned,dict) and owned.get('encoding')=='internal-owned-window-v1':
                        owned=dict(owned,**{k:original.get(k) for k in ('reason','epoch','observed_at')})
            except (ValueError,RecursionError):
                owned={'status':'unavailable','capture_error':'EVENT_RECEIPT_BUDGET',
                    'reason':str(receipt.get('reason'))[:512] if isinstance(receipt,dict) else None,
                    'epoch':receipt.get('epoch') if isinstance(receipt,dict) else None}
                if isinstance(receipt,dict):
                    for key in ('observed_at','producer','kind','sequence'):
                        owned[key]=receipt.get(key)
                    details=receipt.get('details') or {}
                    details=details if isinstance(details,dict) else {}
                    priority={k:details.get(k) for k in ('checked_at','sdk_frame_us',
                        'observation_timestamp','computed_at','expires_at','actual_context',
                        'expected_context','different_fields','rejected_source','rejection_cause')}
                    owned['priority_details']=bounded_copy(priority,limit=4096)[0]
                self.failures+=1
            if self.pending is None:
                self.pending=dict(incident_id=self.session+'-'+str(self.sequence+1),
                    trigger_at_s=now,tail_until_s=now+self.POST_S,subevents=[],event_drops=0,
                    first_reason=None,first_intervention=None,
                    before=tuple(e for e in self.rows if e[0]['at_s']>=now-self.PRE_S-.2))
                self._start_pending_pin()
            p=self.pending
            if self.deferred:p['receipt_bytes']=p.get('receipt_bytes',0)+(size if frozen is not None else 16384)
            if not generic:p['tail_until_s']=max(p['tail_until_s'],now+self.POST_S)
            if kind in ('TECHNICAL_STOP','AEB') and p['first_intervention'] is None:
                p['first_intervention']=dict(kind=kind,at_s=now,receipt=owned)
                p['first_reason']=owned.get('reason') if isinstance(owned,dict) else None
            if p['first_reason'] is None and isinstance(owned,dict) and owned.get('reason'):
                p['first_reason']=owned['reason']
            if len(p['subevents'])>=self.MAX_EVENTS:
                p['event_drops']+=1
            else:
                summary=owned.get('summary') or {} if isinstance(owned,dict) else {}
                summary=summary if isinstance(summary,dict) else {}
                classification=({'TECHNICAL_STOP':'technical_stop','TECHNICAL_AUTHORITY_LOSS':'technical_stop',
                    'AEB':'aeb','AVOID_OBSTACLE':'protective_slowdown'}.get(kind) or
                    ('planned_wait' if summary.get('control_state')=='planned_wait' else
                     'launch' if summary.get('phase') in ('launch','signal_resume') else 'unknown'))
                p['subevents'].append(dict(kind=kind,classification=classification,at_s=now,receipt=owned))

    def keep_activity(self, now):
        """One episode across braking/waiting, not a second incident per edge.

        The pre-event references pin at most ONE ring budget; the rolling tail
        retains its own original budget. Long gaps are explicitly reported.
        """
        with self.lock:
            if self.pending is not None:
                self.pending['tail_until_s']=max(self.pending['tail_until_s'],now+self.POST_S)

    def seal(self, now, *, shutdown=False, packed=False):
        with self.lock:
            p=self.pending
            continuation=bool(p and p.get('episode') and now-p['trigger_at_s']>=self.PART_SECONDS
                and now<p['tail_until_s'] and not shutdown)
            if p is None or (now<p['tail_until_s'] and not shutdown and not continuation):return None
            self.pending=None
            self._pin_ids=set();self._pin_shared=set();self._pin_bytes=0
            before=p.pop('before')
            if p.get('episode'):
                p['episode']=dict(p['episode'],continues=continuation,
                    closed_at_s=now,clock_basis='time.monotonic (SDK observation times preserved separately)')
                if continuation:
                    self.pending=dict(incident_id=self.session+'-'+str(self.sequence+1),
                        trigger_at_s=now,tail_until_s=p['tail_until_s'],subevents=[],event_drops=0,
                        first_reason=p['first_reason'],first_intervention=p['first_intervention'],
                        episode=dict(p['episode'],part=p['episode']['part']+1,
                            previous_incident_id=p['incident_id'],continues=None),
                        before=tuple(e for e in self.rows if e[0]['at_s']>=now-self.PRE_S-.2))
                    self._start_pending_pin()
            # Detach bounded references only. Sorting, dependency closure and
            # gap analysis belong to the existing export worker, not to the
            # controller while holding the ring lock. Payload bytes are owned
            # already; this neither repacks live rows nor copies their inputs.
            records=tuple(row for row,_ in before)+tuple(row for row,_ in self.rows)
            end=self.rows[-1][0]['at_s'] if self.rows else None
            result=dict(schema_version=1,**p,records=records,
                record_format='simple-exact-record' if self.simple_records else 'legacy-shared-envelope',
                range_s=dict(end_s=end),incomplete=True,
                capacity_drops=self.drops,capture_failures=self.failures,
                _metadata_pending=dict(now=now,session=self.session,pre_s=self.PRE_S,
                    period_s=self.PERIOD_S,exact_consumers=self.exact_consumers),
                unavailable=dict(physical_vehicle_color='unavailable',game_consumption='unavailable'),
                confirmed=False,runtime_authorized=False,game_verified=False)
        return result if packed else expand_incident_window(result)

    def status(self):
        with self.lock:
            return dict(enabled=True,retained_bytes=self.bytes,byte_limit=self.limit,
                record_format='simple-exact-record' if self.simple_records else 'legacy-shared-envelope',
                compression_errors=self.compression_errors,compression_pending=len(self.compression_pending),
                compression_queue_limit=32768,compression_worker_limit_per_process=1,
                capacity_drops=self.drops,capture_failures=self.failures,
                pinned_pre_bytes=self._pin_bytes if self.pending else 0,
                maximum_ring_and_pinned_bytes=2*self.limit,
                pending=bool(self.pending),samples=len(self.rows))

    def rolling_snapshot(self, *, packed=False):
        with self.lock:
            rows=[row for row,_ in self.rows]
            result=dict(records=rows,capacity_drops=self.drops,capture_failures=self.failures,
                byte_limit=self.limit,retained_bytes=self.bytes,
                requested_window_s=self.PRE_S+self.POST_S,
                first_s=rows[0]['at_s'] if rows else None,last_s=rows[-1]['at_s'] if rows else None,
                confirmed=False,runtime_authorized=False)
        return result if packed else expand_incident_window(result)


def _finalize_incident_metadata(value):
    """Same sealed evidence/order/coverage, assembled on the export boundary."""
    metadata=value.get('_metadata_pending')
    if metadata:
        p={k:v for k,v in value.items() if k!='_metadata_pending'}
        available={row['sequence']:row for row in value['records']}
        owned={sequence:row for sequence,row in available.items()
            if p['trigger_at_s']-metadata['pre_s']-1e-8<=row['at_s']<=metadata['now']}
        # A call at the left boundary can bind a few microseconds earlier.
        # Retain that exact dependency, never substitute the next decision.
        dependencies=list(owned.values())
        for row in dependencies:
            if row['kind']=='backend_call':
                call=row['value']
                ref=call.get('decision_reference')
                if ref and ref[0]==metadata['session'] and ref[1] in available:
                    if ref[1] not in owned:dependencies.append(available[ref[1]])
                    owned[ref[1]]=available[ref[1]]
            if row['kind']=='pedal_binding':
                for ref in (row['value'].get('consumed_input_references') or {}).values():
                    if ref and ref[0]==metadata['session'] and ref[1] in available:owned[ref[1]]=available[ref[1]]
        rows=sorted(owned.values(),key=lambda r:(r['at_s'],r['sequence']))
        start=min((r['at_s'] for r in rows),default=None)
        end=max((r['at_s'] for r in rows),default=None)
        pre=0. if start is None else max(0.,p['trigger_at_s']-start)
        post=0. if end is None else max(0.,end-p['trigger_at_s'])
        streams={}
        for r in rows:streams.setdefault(r['kind'],[]).append(r['at_s'])
        # Call/binding streams are event driven, not periodic sensors.
        gaps={k:[[a,b] for a,b in zip(v,v[1:]) if b-a>.25] for k,v in streams.items()
            if k not in ('backend_call','pedal_binding','drive_boundary','activation')
            and not (metadata['exact_consumers'] and k.startswith('consumer_'))}
        p.update(records=rows,
            range_s=dict(start_s=start,end_s=end,pre_s=pre,post_s=post,
                pre_incomplete=pre<29.9,post_incomplete=post<10.),
            sampling=dict(period_s=metadata['period_s'],state_events='exact ordered, maximum 256',gaps=gaps,
                consumer_inputs='every invocation' if metadata['exact_consumers'] else 'periodic and state edges'),
            incomplete=bool(p['capacity_drops'] or p['capture_failures'] or p['event_drops'] or pre<29.9 or post<10. or any(gaps.values())))
        return p
    return value


def expand_incident_window(value):
    """Worker/public inspection boundary; owned compressed rows stay in runtime."""
    value=_finalize_incident_metadata(value)
    def receipt(event):
        if not event:return event
        return dict(event,receipt=_IncidentWindow.expanded_row(dict(value=event.get('receipt')))['value'])
    cache={}
    return dict(value,records=[_IncidentWindow.expanded_row(r,cache) for r in value['records']],
        subevents=[receipt(e) for e in value.get('subevents',[])],
        **({'first_intervention':receipt(value['first_intervention'])} if 'first_intervention' in value else {}))


class PedalJournal:
    CAPACITY = 128
    MAX_BYTES = 65536

    def __init__(self):
        self._incident_window = None
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
        self._last_successful = dict(self._held)
        self._history = _DecisionHistory()
        self._event_lock=threading.Lock()
        self._pending_event=None
        self._event_sequence=0
        self._event_window_started=None
        self._event_exports=0
        self._event_suppressed=0
        self._event_last_source=None
        self._event_last_fault_signature=None
        self._event_export_failure=None
        try:
            from core.navigation.diagnostic_build_config import ENABLED
        except ImportError:
            ENABLED = False
        if ENABLED:
            self.enable_incident_window()

    def enable_incident_window(self, *, byte_limit=None):
        """Explicit diagnostic-build opt-in; never changes pedal decisions."""
        if byte_limit is None:byte_limit=diagnostic_build_limits()['engine_ring_bytes']
        self._incident_window = _IncidentWindow(byte_limit,deferred=True)
        self._incident_window.exact_consumers=True
        # A binding just before the left boundary can refer to inputs from the
        # preceding validated tick; retain that existing evidence, never invent
        # or relabel its rows during dependency closure.
        self._incident_window.receiver_retention_margin_s=.5

    def observe_stop_episode(self,value,now):
        ring=self._incident_window
        if ring is None:return
        active=value.get('active') is True
        speed=value.get('speed_mps');brake=value.get('brake')
        stopped=isinstance(speed,(int,float)) and math.isfinite(speed) and abs(speed)<.05
        braking=active and (isinstance(brake,(int,float)) and brake>0. or value.get('stop_required') is True)
        previous=getattr(self,'_stop_episode_state',dict(active=False,stopped=False,braking=False))
        events=[]
        if braking and not previous['braking']:events.append('BRAKING_STARTED')
        if active and stopped and not (previous['active'] and previous['stopped']):events.append('STOP_OBSERVED')
        if previous['active'] and not active:events.append('AUTOPILOT_DISABLED')
        if active and not stopped and previous['stopped'] and not braking:events.append('MOTION_RESUMED')
        for kind in events:
            self.incident_event(kind,dict(value,reason=value.get('reason') or 'unknown',observed_at=now),now)
            with ring.lock:
                if ring.pending and 'episode' not in ring.pending:
                    ring.pending['episode']=dict(id=ring.pending['incident_id'],part=0,
                        started_at_s=now,first_braking_reason=value.get('reason') or 'unknown',
                        first_braking_source=value.get('source'),previous_incident_id=None,continues=None)
        if active and (stopped or braking):ring.keep_activity(now)
        self._stop_episode_state=dict(active=active,stopped=stopped,braking=braking)

    def observe_incident(self, kind, value, now):
        window = self._incident_window
        if self.enabled and window is not None:
            consumer=kind.startswith('consumer_')
            reference=window.observe(kind,value,now,force=consumer)
            if consumer:
                refs=getattr(self._local,'input_references',None)
                if refs is None:refs=self._local.input_references={}
                refs[kind]=reference
            return reference

    def incident_event(self, kind, receipt, now):
        window = self._incident_window
        if self.enabled and window is not None:
            window.event(kind, receipt, now)

    def seal_incident(self, now, *, shutdown=False, packed=False):
        window = self._incident_window
        return window.seal(now, shutdown=shutdown,packed=packed) if window is not None else None

    def incident_status(self):
        window = self._incident_window
        return window.status() if window is not None else {'enabled': False}

    def begin_decision(self):
        self._local.input_references={}
        self._local.decision_open=True
        self._local.writes=dict(write_first_sequence=None,write_last_sequence=None,write_count=0,
            write_success_count=0,write_error_count=0,write_unverified_count=0,write_first_started_at_s=None,
            write_last_returned_at_s=None,last_backend_status=None,last_backend_error=None,
            backend_throttle_min=None,backend_throttle_max=None,backend_brake_min=None,backend_brake_max=None,
            backend_pair_mode_changes=0,write_source_changes=0)
        self._local.last_write_source=None
        self._local.last_pair_mode=self._pair_mode()
        self._local.summary=None
        self._local.written_summary=None

    def finish_decision(self,now):
        self._local.decision_open=False
        if not self.enabled:return
        # release_all temporarily binds release provenance, then restores the
        # caller's binding. Retain the source of the actual last pedal call,
        # rather than attributing those zero writes to the restored command.
        source=getattr(self._local,'written_summary',None) or getattr(self._local,'summary',None)
        if source is None:return
        row,identity=source
        row=dict(row,**getattr(self._local,'writes',{}))
        self.observe_stop_episode(dict(active=getattr(self,'_diagnostic_active',
            row.get('phase') in ('active','signal_resume','launch') or row.get('control_state')=='planned_wait'),
            speed_mps=row.get('speed_mps'),brake=row.get('selected_brake'),
            stop_required=row.get('control_state')=='planned_wait',reason=row.get('first_reason') or row.get('reason'),
            source=row.get('selected_source'),gear=row.get('gear'),activation=row.get('activation'),
            sdk_frame_us=row.get('sdk_frame_us'),observation_timestamp=row.get('observation_timestamp')),now)
        if self._incident_window is not None:
            try:
                edge=(row.get('activation'),row.get('control_state'),row.get('phase'),
                    row.get('selected_source'),row.get('pedal_mode'),row.get('signal_color'),
                    row.get('following_target_id'),row.get('hold_phase'))
                old=getattr(self,'_incident_last_edge',None)
                if edge!=old:
                    self.incident_event('STATE_TRANSITION',dict(previous=old,current=edge,
                        reason=row.get('first_reason') or row.get('reason'),summary=row),now)
                self._incident_last_edge=edge
                self.observe_incident('output_summary',row,now)
                if not row.get('first_reason') and (
                        row.get('control_state')=='planned_wait' or
                        row.get('phase')=='active' and (row.get('selected_brake') or 0.)>0.):
                    self._incident_window.keep_activity(now)
            except Exception:
                self._incident_window.failures+=1
        with self._lock:
            row.update(written_throttle=self._held['throttle'],written_brake=self._held['brake'])
            try:self._history.observe(now,row,identity)
            except Exception as error:self._history.capture_failure('summary_observe',type(error).__name__+': '+str(error),now)
        source=row.get('selected_source')
        if (row.get('selected_brake',0.) and source!=self._event_last_source
                and row.get('phase')=='active' and not row.get('first_reason')
                and row.get('control_state')!='controlled_stop'):
            self.significant('BRAKE_SOURCE_CHANGED',self.source(),now)
        self._event_last_source=source
        signature=(row.get('control_state'),row.get('first_reason'))
        if signature!=self._event_last_fault_signature:
            reason=str(row.get('first_reason') or row.get('reason') or '')
            if 'signal regulation coverage' in reason:
                self.significant('UNASSIGNED_SIGNAL',self.source(),now)
            elif row.get('control_state')=='controlled_stop' or row.get('first_reason'):
                self.significant('TECHNICAL_AUTHORITY_LOSS',self.source(),now)
        self._event_last_fault_signature=signature

    def significant(self,kind,receipt,now):
        """One sealed event slot, existing history/ring, no extra source reads.

        Maximum four exports/minute. Busy edges are counted/coalesced, not
        queued. All retained row references are immutable and bounded by the
        existing 1 MiB history / 64 KiB ring; background expansion does disk I/O.
        """
        if not self.enabled:return
        if self._incident_window is not None:
            self.incident_event(kind,receipt,now)
            return
        with self._event_lock:
            if kind not in ('AVOID_OBSTACLE','BRAKE_SOURCE_CHANGED','UNASSIGNED_SIGNAL','TECHNICAL_AUTHORITY_LOSS'):
                self._event_suppressed+=1;return
            if self._event_window_started is None or now-self._event_window_started>=60.:
                self._event_window_started=now;self._event_exports=0
            if self._pending_event is not None:
                pending=self._pending_event
                pending['coalesced'][kind]=pending['coalesced'].get(kind,0)+1
                return
            if self._event_exports>=4:
                self._event_suppressed+=1;return
            self._event_sequence+=1
            if isinstance(receipt,dict) and receipt.get('schema_version')==1:
                receipt={'input':bounded_input(receipt),'context':receipt.get('context'),
                         'sdk_frame_us':receipt.get('sdk_frame_us'),
                         'observation_timestamp':receipt.get('observation_timestamp')}
            original_context=receipt.get('context') if isinstance(receipt,dict) else None
            owned_context,context_size=bounded_copy(original_context,limit=4096)
            context_complete=isinstance(owned_context,list) or owned_context is None
            frozen,size=bounded_copy(pack_source(receipt),limit=32768-context_size)
            before=self.snapshot(expanded=False,include_history=True)
            self._pending_event=dict(sequence=self._event_sequence,kind=kind,observed_at=now,
                receipt=frozen,receipt_bytes=size+context_size,before=before,after=None,
                receipt_incomplete=bool(not context_complete or isinstance(frozen,dict) and frozen.get('snapshot_status')),
                tail_until=now+.1,coalesced={},suppressed_events=self._event_suppressed,
                context=owned_context if context_complete else None)

    def ready_significant(self,now,*,shutdown=False):
        with self._event_lock:
            p=self._pending_event
            if p is None or (not shutdown and now<p['tail_until']):return None
            if p['after'] is None:
                p['after']=self.snapshot(p['before']['last_sequence'],expanded=False)
            return dict(p,coalesced=dict(p['coalesced']))

    def significant_submitted(self,sequence):
        with self._event_lock:
            if self._pending_event and self._pending_event['sequence']==sequence:
                self._pending_event=None;self._event_exports+=1
                self._event_export_failure=None

    def significant_export_failed(self,reason,now):
        with self._event_lock:
            previous=self._event_export_failure or {}
            self._event_export_failure=dict(reason=str(reason)[:256],
                first_failed_at_s=previous.get('first_failed_at_s',now),
                last_failed_at_s=now,attempts=previous.get('attempts',0)+1,
                complete=False,requires_archive=reason=='SIGNIFICANT_EVENT_EXPORT_DISK_QUOTA')

    @staticmethod
    def expand_significant(p):
        before=expand_journal(p['before']);after=expand_journal(p['after'])
        events={e['sequence']:e for e in before['events']+after['events']}
        result=dict(before,events=[events[k] for k in sorted(events)],
            dropped_events=before['dropped_events']+after['dropped_events'],
            last_sequence=after['last_sequence'])
        result['significant_event']={k:v for k,v in p.items() if k not in ('before','after','receipt')}
        result['significant_event'].update(receipt=expand_decision(unpack_source(p['receipt'])),
            export_budget=dict(pending_slots=1,maximum_exports_per_minute=4,
                history_bytes=1048576,detail_bytes_per_snapshot=65536,receipt_bytes=32768,
                maximum_event_files=8,maximum_event_bytes=16777216),
            subsequent_write_loss=after['dropped_events'],game_consumption_verified=False)
        result['snapshot_incomplete']=bool(result['dropped_events'] or p.get('receipt_incomplete'))
        events=result['events']
        start=min((e['call_started_at_s'] for e in events),default=None)
        end=max((e['call_returned_at_s'] for e in events),default=None)
        result['detail_evidence']=dict(start_s=start,end_s=end,duration_s=None if start is None else end-start,
            event_count=len(events),dropped_events=result['dropped_events'],incomplete=result['snapshot_incomplete'],
            sampling='sealed pre-event ring plus bounded subsequent window',game_consumption_verified=False)
        return result

    def history_intervention(self,fault):
        if self.enabled:
            self.incident_event('AEB' if fault.get('kind')=='emergency' else 'TECHNICAL_STOP',fault,time.monotonic())
            with self._lock:
                try:self._history.intervention(fault,time.monotonic())
                except Exception as error:self._history.capture_failure('summary_intervention',type(error).__name__+': '+str(error))

    def _pair_mode(self):
        t,b=self._held['throttle'],self._held['brake']
        return ('unknown' if t is None or b is None else 'overlap' if t>0 and b>0
                else 'brake' if b>0 else 'drive' if t>0 else 'coast')

    def bind(self, value):
        self._local.decision_reference=None
        window = self._incident_window
        approved = value is not None and diagnostic_build_limits()['approved']
        intervention = value.get('intervention') if isinstance(value, dict) else None
        snapshot = None
        if self.enabled and window is not None and value is not None:
            try:
                now=time.monotonic()
                if approved and window.simple_records and intervention is None:
                    snapshot = []
                    window.observe('consumed_decision',value,now,primitive_snapshot=snapshot)
                else:
                    self.observe_incident('consumed_decision',value,now)
                binding=dict(value,consumed_input_references=dict(getattr(self._local,'input_references',{})))
                self._local.decision_reference=window.observe('pedal_binding',binding,now,force=True)
            except Exception:window.failures+=1
        self._local.summary=None
        if value is not None:
            try:self._local.summary=_decision_summary(value)
            except Exception as error:self._history.capture_failure('summary_bind',type(error).__name__+': '+str(error))
        # Keep the rare first intervention beside the decision, not repeated
        # inside its already bounded producer snapshots. Both allocations count
        # against the unchanged total journal byte budget.
        if intervention is not None:
            value = {k: v for k, v in value.items() if k != 'intervention'}
        self._local.intervention, extra = bounded_copy(_pack_intervention(intervention), limit=16384)
        try:
            if value is None:self._local.source,self._local.size=None,64
            else:
                if approved:
                    # The full incident already owns exact raw inputs. The
                    # legacy short safety journal must not JSON/compress on
                    # the controller as well. Reuse its approved C ownership
                    # codec under the SAME 32/64 KiB source/journal ceilings.
                    frozen=snapshot[0] if snapshot else freeze_primitive_record(value,byte_limit=32768-1024)
                    frozen['journal_compaction_pending']=True
                    size=1024+len(frozen['blob'])
                    if size>32768:raise ValueError('SHORT_JOURNAL_SOURCE_BUDGET')
                    self._local.source,self._local.size=frozen,size
                else:self._local.source,self._local.size=bounded_copy(pack_source(pack_journal_inputs(compact_decision(value))),limit=32768)
        except ValueError as error:
            status=('UNVERIFIED_SNAPSHOT_BUDGET_EXCEEDED' if str(error) in
                ('SHORT_JOURNAL_SOURCE_BUDGET','EXACT_RECORD_BYTE_BUDGET') else
                'UNVERIFIED_DIAGNOSTIC_CAPTURE_FAILURE')
            self._local.source,self._local.size={'snapshot_status':status},256
        except Exception:
            self._local.source, self._local.size = {'snapshot_status':'UNVERIFIED_DIAGNOSTIC_CAPTURE_FAILURE'},256
        self._local.size += extra

    def source(self):
        source = expand_decision(unpack_source(getattr(self._local, 'source', None)))
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
        self._last_successful = dict(self._held)
        self._history = _DecisionHistory()
        with self._event_lock:self._pending_event=None

    def record(self, channel, value, started, returned, backend, evidence, error=None):
        if not self.enabled:
            return
        # A hotkey/shutdown can release controls outside Engine's flush scope.
        # Capture these existing calls too; do not wait for the next decision
        # (which would replace their temporary release binding).
        standalone=not getattr(self._local,'decision_open',False)
        if standalone:
            summary=getattr(self._local,'summary',None)
            self.begin_decision()
            self._local.summary=summary
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
            if verified:
                self._last_successful[channel] = evidence.get('value')
            self._events.append(dict(
                sequence=self._sequence, channel=channel, requested_value=value,
                backend_mode=backend, call_started_at_s=started,
                call_returned_at_s=returned, call_returned=error is None,
                error=error, backend=evidence, pair_after=dict(self._held),
                source=source, game_consumption_verified=False))
            self._events[-1]['last_successful_pair_after'] = dict(self._last_successful)
            self._events[-1]['intervention'] = intervention
            if self._incident_window is not None:
                # One exact binding per bind, shared by every physical call.
                # The legacy 64 KiB safety tail remains unchanged.
                event={k:v for k,v in self._events[-1].items() if k not in ('source','intervention')}
                event['decision_reference']=getattr(self._local,'decision_reference',None)
                event['first_intervention_reference']=None  # Preserved by incident first_intervention.
                self._incident_window.observe('backend_call',event,returned,force=True)
            writes=getattr(self._local,'writes',None)
            if writes is not None:
                self._local.written_summary=getattr(self._local,'summary',None)
                if writes['write_first_sequence'] is None:
                    writes.update(write_first_sequence=self._sequence,write_first_started_at_s=started)
                writes.update(write_last_sequence=self._sequence,write_last_returned_at_s=returned,
                    last_backend_status=evidence.get('status'),last_backend_error=error or evidence.get('error'))
                writes['write_count']+=1;writes['write_success_count']+=int(verified)
                failed=bool(error or evidence.get('status') in ('MAPPING_WRITE_FAILED','MAPPING_NOT_CONNECTED'))
                writes['write_error_count']+=int(failed)
                writes['write_unverified_count']+=int(not verified and not failed)
                if verified:
                    for suffix,op in (('_min',min),('_max',max)):
                        k='backend_'+channel+suffix
                        v=evidence.get('value')
                        if v is not None:writes[k]=v if writes[k] is None else op(writes[k],v)
                mode=self._pair_mode()
                writes['backend_pair_mode_changes']+=int(mode!=self._local.last_pair_mode)
                self._local.last_pair_mode=mode
                summary=getattr(self._local,'summary',None)
                row=summary[0] if summary is not None else {}
                tag=tuple(row.get(k) for k in ('activation','sdk_frame_us','phase','selected_source','reason'))
                if self._local.last_write_source is not None:
                    writes['write_source_changes']+=int(tag!=self._local.last_write_source)
                self._local.last_write_source=tag
            self._sizes.append(key)
            self._bytes += 2048
        if standalone:self.finish_decision(returned)

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
        return expand_journal(result)

    def snapshot(self, after_sequence=0, *, expanded=True, include_history=False):
        """Non-destructive cursor read; combined cannot erase an incident ring.

        Internal packed snapshots contain immutable retained row references.
        Export workers expand them; public snapshots are detached copies.
        """
        with self._lock:
            rows = [e for e in self._events if e['sequence'] > after_sequence]
            first = rows[0]['sequence'] if rows else self._sequence+1
            result = dict(schema_version=1, journal_storage='packed', events=rows,
                dropped_events=max(0, first-after_sequence-1),
                last_sequence=self._sequence, capacity=self.CAPACITY,
                byte_budget=self.MAX_BYTES, retained_bytes=self._bytes,
                game_consumption_verified=False)
            result['event_capture_status']=dict(pending=bool(self._pending_event),
                maximum_exports_per_minute=4,suppressed_events=self._event_suppressed,
                pending_capacity=1,receipt_byte_budget=32768,
                export_failure=dict(self._event_export_failure) if self._event_export_failure else None)
            start=min((e['call_started_at_s'] for e in rows),default=None)
            end=max((e['call_returned_at_s'] for e in rows),default=None)
            result['detail_evidence']=dict(start_s=start,end_s=end,
                duration_s=None if start is None else end-start,event_count=len(rows),
                dropped_events=result['dropped_events'],sampling='every retained physical pedal call',
                incomplete=bool(result['dropped_events']),game_consumption_verified=False)
            if include_history:result['decision_history']=self._history.snapshot()
        return copy.deepcopy(expand_journal(result)) if expanded else result


def expand_journal(result):
    result = dict(result)
    result.pop('journal_storage', None)
    if 'decision_history' in result:result['decision_history']=expand_history(result['decision_history'])
    result['events'] = [dict(e) for e in result['events']]
    if 'first_intervention' in result:
        result['first_intervention'] = _expand_intervention(result['first_intervention'])
    if 'preceding_significant_event' in result:
        result['preceding_significant_event']=PedalJournal.expand_significant(result['preceding_significant_event'])
    if 'preceding_significant_event_receipt' in result:
        preceding=dict(result['preceding_significant_event_receipt'])
        preceding['receipt']=expand_decision(unpack_source(preceding['receipt']))
        result['preceding_significant_event_receipt']=preceding
    sources={};source_bytes=0
    for event in result['events']:
        original=event['source'];cached=sources.get(id(original))
        if cached is not None and cached[0] is original:
            event['source']=restore_exact_record(cached[1])
        else:
            event['source'] = expand_decision(unpack_source(original))
            # One call-local, 512 KiB scratch budget; equal physical writes
            # share the original immutable source, not a nearby/newer packet.
            # Each returned event still owns a detached mutable source tree.
            try:
                frozen=freeze_primitive_record(event['source'])
                cost=len(frozen['blob'])+256
                if source_bytes+cost<=512*1024:
                    sources[id(original)]=(original,frozen);source_bytes+=cost
            except (TypeError,ValueError,RecursionError):pass
        event['intervention'] = _expand_intervention(event.get('intervention'))
        if isinstance(event['source'], dict) and event.get('intervention') is not None:
            event['source'] = {**event['source'], 'intervention': event['intervention']}
    return result


def local_source_snapshot(truck, pending=None):
    """Reuse the already captured truck; no diagnostic SDK or IPC reads."""
    observed = truck.get('_control_observation') or {}
    pending = pending or {}
    identity = pending.get('identity')
    return dict(sdk_frame_us=truck.get('sdkFrameTimeUs'),
        sdk_observation={k:observed.get(k) for k in ('schema_version','sdk_frame_us','observed_at','valid','reason')},
        observation_timestamp=observed.get('observed_at'), observation_valid=observed.get('valid'),
        actual_speed_mps=truck.get('speed'), observed_gear=truck.get('gear'),
        # Additive extension keys: never change the indexed codec tables.
        gps_remainder_m=truck.get('routeDistance'), gps_route_time_s=truck.get('routeTime'),
        load_observation=truck.get('loadObservation'),
        powertrain_observation=truck.get('powertrainObservation'),
        sdk_response={k: truck.get(k) for k in ('gameThrottle', 'gameBrake', 'userThrottle', 'userBrake')},
        decision_started_at_s=time.monotonic(), activation=pending.get('request_id'),
        route_identity=identity, context=None, control_state=None,
        phase='launch' if pending else 'unbound', requested=None, selected=None,
        inputs=None, service_hold=None,
        launch={k: pending.get(k) for k in ('mode', 'request_id', 'started_at', 'deadline_at',
            'start_frame', 'phase', 'handoff_deadline_at')} if pending else None)


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
        load_observation=truck.get('loadObservation'),
        powertrain_observation=truck.get('powertrainObservation'),
        sdk_response={k: truck.get(k) for k in ('gameThrottle', 'gameBrake', 'userThrottle', 'userBrake')},
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


def observe_engine_incident(engine, kind, value):
    """Observe already-consumed locals only; fail observationally, never reread IPC."""
    journal=getattr(getattr(engine,'controller',None),'_pedal_journal',None)
    if journal is None or journal._incident_window is None:return
    if hasattr(engine,'shared_state'):
        engine.shared_state._diagnostic_consumer=journal.observe_incident
        preflight=getattr(engine,'_significant_export_preflight',None)
        if preflight is not None and not getattr(engine,'_diagnostic_preflight_published',False):
            engine.shared_state.set('diagnostic_capture_status',dict(preflight,build='UP-DIAGNOSTIC-20261025-07'))
            engine._diagnostic_preflight_published=True
    try:
        now=time.monotonic()
        journal.observe_incident(kind,value,now)
        if kind=='ego':
            journal._diagnostic_active=bool(getattr(engine,'_was_active',False))
            # Preserve all available SDK fields, but a value near zero is not
            # proof of a particular hold/gearbox transition or game consumption.
            edge=(value.get('gear'),abs(value.get('speed') or 0.)<.05,
                bool(value.get('userThrottle')),bool(value.get('userBrake')))
        elif kind in ('drive_boundary','activation'):
            if kind=='activation' and value.get('enabled') is False:
                journal.observe_stop_episode(dict(active=False,reason=value.get('reason') or 'manual disable',
                    speed_mps=(value.get('ego') or {}).get('speed')),now)
            event=('ACTIVATION_REJECTED' if value.get('reason') else
                'ACTIVATION_REQUESTED' if value.get('enabled') or value.get('pending_started') else
                'DRIVER_CANCEL_OR_DISABLE') if kind=='activation' else 'ACTIVATION_OR_DRIVE_BOUNDARY'
            journal.incident_event(event,value,now)
            return
        else:
            packet=value.get('packet') or {}
            following=packet.get('following') or {}
            signal=packet.get('signal') or {}
            light=signal.get('candidate') or signal.get('stop_candidate') or {}
            edge=(packet.get('context'),following.get('target_id'),following.get('status'),
                light.get('id'),light.get('color'),signal.get('reason'),
                bool(packet.get('traffic_brake')),bool(packet.get('light_brake')))
        attr='_incident_edge_'+kind
        old=getattr(journal,attr,None)
        if old!=edge:
            receipt=dict(previous=old,current=edge)
            if kind=='traffic':
                receipt.update(sdk_frame_us=packet.get('sdk_frame_us'),
                    observation_timestamp=packet.get('observation_timestamp'),
                    context=packet.get('context'),source=value.get('capture',{}).get('source'),
                    following={k:following.get(k) for k in ('target_id','status','reason','retained_target_continuity')},
                    signal={k:signal.get(k) for k in ('observed_at','generation','lifecycle','reason')},
                    controlling_light=light)
            journal.incident_event(kind.upper()+'_TRANSITION',receipt,now)
            setattr(journal,attr,edge)
    except Exception:
        journal._incident_window.failures+=1


def finish_engine_incident(engine, journal, *, shutdown=False):
    """Diagnostic-build export on the SAME existing single background writer.

    Returns False for a normal build. A temporary build bypasses only redundant
    longitudinal export paths, never any control or original steering replay.
    """
    if journal._incident_window is None:return False
    from core.steering_replay import AsyncReplayExporter,export_incident_isolated
    if not getattr(engine,'_diagnostic_service_configured',False):
        # Engine is a non-daemon process, unlike plugins. Both export owners
        # must reserve the SAME existing Manager service before disk admission.
        # This is local proxy configuration, not another control/SDK IPC read.
        from core.steering_replay import configure_diagnostic_export
        configure_diagnostic_export(getattr(engine,'shared_state',None))
        engine._diagnostic_service_configured=True
    directory=getattr(engine,'_automatic_replay_directory',None)
    if not directory:return True
    fault=getattr(engine,'_automatic_longitudinal_fault',None)
    if (fault and getattr(engine,'_automatic_longitudinal_export_epoch',None)!=fault.get('epoch')
            and not shutdown):
        # The pre-existing immediate safety replay owns the first submission
        # after its 100 ms tail. A ready continuation must not occupy the sole
        # writer in that gap and make the original safety replay wait for AP.
        return True
    writer=getattr(engine,'_automatic_replay_writer',None)
    if writer is not None and writer.status.get('busy'):return True
    retry=getattr(engine,'_diagnostic_export_retry',None)
    if retry is not None:
        if not shutdown and time.monotonic()<retry['retry_at']:return True
        window,snapshot=retry['window'],retry['snapshot']
    else:
        window=journal.seal_incident(time.monotonic(),shutdown=shutdown,packed=True)
        if window is None:return True
        snapshot=journal.snapshot(expanded=False,include_history=True)
        start=window['trigger_at_s']-30.
        end=window['range_s']['end_s']
        end=window['tail_until_s'] if end is None else end
        request=dict(schema=2,incident_id=window['incident_id'],phase='seal',
            start_s=start,end_s=end,trigger_at_s=window['trigger_at_s'],shutdown=shutdown)
        request['token']=request['incident_id']+'@'+repr(start)+'..'+repr(end)
        if any(r['kind']=='consumer_command_pair' for r in window['records']):
            window['required_autopilot_part']=request
    engine._diagnostic_join_request=window.get('required_autopilot_part')
    if writer is None:writer=engine._automatic_replay_writer=AsyncReplayExporter()
    def write():
        try:
            # Background-only compact rendezvous for a disabled AP. Its
            # control path no longer consumes traffic; copying that large
            # packet just to find a seal is unnecessary. One existing-state
            # slot, one export owner, no control-thread RPC or payload queue.
            if hasattr(engine,'shared_state'):
                engine.shared_state.set('diagnostic_incident_seal_request',window.get('required_autopilot_part'))
            path=export_incident_isolated(directory,window,snapshot)
            engine._diagnostic_export_retry=None
            engine._diagnostic_join_request=None
            if hasattr(engine,'shared_state'):
                engine.shared_state.set('diagnostic_capture_status',dict(
                    build='UP-DIAGNOSTIC-20261025-04',last_incident=window['incident_id'],
                    last_export=path,export_failed=False,complete=None,
                    completeness_source='inspect the verified dossier and its component counters',
                    confirmed=False,runtime_authorized=False))
            return path
        except Exception as error:
            # Existing worker exposes this error. Preserve the FIRST compact
            # cause on Engine as well; no success attestation on failed export.
            engine._diagnostic_incident_failure=dict(incident_id=window['incident_id'],
                first_reason=window['first_reason'],error=type(error).__name__,
                detail=str(error)[:256],complete=False,confirmed=False)
            engine._diagnostic_export_retry=dict(window=window,snapshot=snapshot,
                retry_at=time.monotonic()+30.)
            if hasattr(engine,'shared_state'):
                engine.shared_state.set('diagnostic_capture_status',dict(
                    engine._diagnostic_incident_failure,ready=False,
                    build='UP-DIAGNOSTIC-20261025-04'))
            try:
                # Failure evidence uses a separate explicit 64 KiB disk budget.
                # Only worker I/O; existing failure is never overwritten.
                from pathlib import Path
                import json
                root=Path(directory);root.mkdir(parents=True,exist_ok=True)
                files=list(root.glob('incident-failure-*.txt'))
                if len(files)<8 and sum(p.stat().st_size for p in files)<64*1024:
                    path=root/('incident-failure-'+window['incident_id']+'.txt')
                    if not path.exists():
                        with path.open('x',encoding='utf-8') as stream:
                            json.dump(engine._diagnostic_incident_failure,stream)
            except OSError:
                pass  # Existing worker status/log remains explicit if disk is full.
            raise
    if not writer.submit(write):
        engine._diagnostic_incident_failure=dict(incident_id=window['incident_id'],
            error='EXISTING_EXPORT_WORKER_BUSY',complete=False,confirmed=False)
    return True


def diagnostic_consume(state, kind, value, now):
    """Local callback only; never call get()/SDK/IPC for diagnostic source data."""
    callback=getattr(state,'_diagnostic_consumer',None)
    if callback is not None:
        try:callback('consumer_'+kind,value,now)
        except Exception:
            # An observation failure must not replace a control result.
            owner=getattr(callback,'__self__',None)
            window=getattr(owner,'_incident_window',None)
            if window is not None:window.failures+=1


def decorate_traffic_diagnostic(engine, packet):
    """Compact request piggybacks on an EXISTING publication; no extra RPC read."""
    journal=getattr(getattr(engine,'controller',None),'_pedal_journal',None)
    if journal is None or journal._incident_window is None:return
    request=getattr(engine,'_diagnostic_join_request',None)
    if request is None:
        window=journal._incident_window
        with window.lock:
            pending=window.pending
            if pending:
                request=dict(schema=2,incident_id=pending['incident_id'],phase='open',
                    start_s=pending['trigger_at_s']-30.,end_s=None,
                    trigger_at_s=pending['trigger_at_s'],token=None)
    if request is not None:packet['diagnostic_part_request']=dict(request)


class _RetiredAutopilotInputs:
    """One bounded retired row set across rotations, retaining exact objects.

    Replaces the prior retired slot; it is not another ring or export queue.
    Charge actual existing row/shared-input ownership without JSON/codec work.
    """
    def __init__(self, previous, current):
        self.limit=current.limit
        def entries(owner):
            if isinstance(owner,_RetiredAutopilotInputs):
                with owner.lock:return tuple(owner.entries)
            with owner.lock:return tuple(owner.rows)
        rows={}
        for row,size in (*entries(previous),*entries(current)):
            rows[(row.get('stream_id'),row['sequence'])]=(row,size)
        ordered=sorted(rows.values(),key=lambda e:(e[0]['at_s'],e[0]['sequence']))
        kept=[];used=0;shared=set();dropped=0
        for row,size in reversed(ordered):
            new=[s for s in _IncidentWindow.row_inputs(row) if s not in shared]
            charge=size+sum(s.size for s in new)
            if used+charge>self.limit:
                dropped+=1;continue
            shared.update(new);used+=charge;kept.append((row,size))
        self.lock=threading.Lock()
        self.entries=deque(reversed(kept));self.bytes=used
        self.entry_inputs={};self.entry_keys=set();self.shared_counts=Counter()
        for row,size in self.entries:
            key=(row.get('stream_id'),row['sequence'])
            inputs=tuple(_IncidentWindow.row_inputs(row))
            self.entry_keys.add(key);self.entry_inputs[key]=inputs
            self.shared_counts.update(inputs)
        self.failures=previous.failures+current.failures
        self.drops=previous.drops+current.drops+dropped

    def _discard_first(self):
        row,size=self.entries.popleft();key=(row.get('stream_id'),row['sequence'])
        self.entry_keys.remove(key);self.bytes-=size
        for shared in self.entry_inputs.pop(key):
            self.shared_counts[shared]-=1
            if not self.shared_counts[shared]:
                self.bytes-=shared.size;del self.shared_counts[shared]

    def append_original(self,entry):
        """Own the already-frozen AP row, without encoding or rereading it.

        This is the existing retired slot, now also protecting the middle
        AFTER an in-flight seal. It never grows beyond the same byte limit.
        """
        row,size=entry;key=(row.get('stream_id'),row['sequence'])
        inputs=tuple(_IncidentWindow.row_inputs(row))  # outside the short lock
        with self.lock:
            if key in self.entry_keys:return
            self.bytes+=size+sum(s.size for s in inputs if not self.shared_counts[s])
            self.entries.append(entry);self.entry_keys.add(key);self.entry_inputs[key]=inputs
            self.shared_counts.update(inputs)
            while self.bytes>self.limit:
                self._discard_first();self.drops+=1

    def retain_from(self,cutoff):
        """Retire only evidence preceding the next possible overlap."""
        with self.lock:
            while self.entries and self.entries[0][0]['at_s']<cutoff:self._discard_first()

    def rolling_snapshot(self,*,packed=False):
        with self.lock:
            rows=[r for r,_ in self.entries]
            value=dict(records=rows,capture_failures=self.failures,capacity_drops=self.drops,
                byte_limit=self.limit,retained_bytes=self.bytes,
                first_s=rows[0]['at_s'] if rows else None,last_s=rows[-1]['at_s'] if rows else None)
        return value if packed else expand_incident_window(value)


class AutopilotIncidentParts:
    """Assemble parts from the existing dense input ring, not a new collector.

    One pending case and one frozen existing-worker operation; no control/SDK
    calls, no filesystem polling on ticks. Requests ride consumed traffic.
    """
    def __init__(self, plugin):
        self.plugin=plugin
        from core.steering_replay import configure_diagnostic_export
        configure_diagnostic_export(getattr(getattr(plugin,'sdk',None),'shared_state',None))
        ring=getattr(plugin._steering_replay,'_diagnostic_inputs',None)
        if ring is not None:
            # Engine can consume a legal command from the preceding AP tick;
            # its seal arrives on a later traffic publication. Retain that
            # diagnostic boundary within the SAME byte budget, covering the
            # unchanged maximum 500 ms input-age interval. No control timeout
            # or command freshness is extended.
            ring.receiver_retention_margin_s=.5
        self.local=threading.local()
        self.case=None
        self.next_request=None
        self.next_case=None
        self.frozen=None
        self.submitted=False
        self.retry_at=0.
        self.completed_id=None
        self.known_ring=ring
        self.retired_ring=None
        self.rendezvous_submitted=False
        self.previous_tail=()

    def after_disabled_replay(self, sealed_replay, directory):
        """Existing worker only; fetch a seal, never a new control input.

        The rotated ring owns decisions through disable; the current ring
        owns passive post-disable observations. Neither is replaced by a
        newly read traffic packet. No extra worker or request queue is used.
        """
        state=getattr(getattr(self.plugin,'sdk',None),'shared_state',None)
        if state is None:return
        directory=getattr(self.plugin,'_diagnostic_part_directory',None) or directory
        incident_id=self.case['request']['incident_id'] if self.case else None
        old=getattr(sealed_replay,'_diagnostic_inputs',None)
        old_snapshot=old.rolling_snapshot(packed=True) if old is not None else None
        old_end=(old_snapshot or {}).get('last_s')
        deadline=time.perf_counter()+20.
        request=None
        while time.perf_counter()<deadline:
            candidate=state.get('diagnostic_incident_seal_request')
            if (isinstance(candidate,dict) and candidate.get('phase')=='seal'
                    and candidate.get('incident_id')!=self.completed_id
                    and (candidate.get('incident_id')==incident_id or incident_id is None
                        and isinstance(old_end,(int,float))
                        and isinstance(candidate.get('start_s'),(int,float))
                        and isinstance(candidate.get('end_s'),(int,float))
                        and candidate['start_s']<=old_end<=candidate['end_s'])):
                self.accept(candidate)
                if (self.case and self.case['request']['incident_id']==candidate['incident_id']
                        and self.case['request'].get('phase')=='seal'):
                    request=dict(self.case['request']);break
            time.sleep(.02)
        if request is None:return  # Engine reports the missing part explicitly.
        incident_id=request['incident_id']
        current=getattr(self.plugin._steering_replay,'_diagnostic_inputs',None)
        snapshots=([old_snapshot] if old_snapshot else [])+([current.rolling_snapshot(packed=True)] if current is not None else [])
        rows={}
        for row in (*self.case['before'],*(r for snapshot in snapshots for r in snapshot['records'])):
            value=row.get('value') or {}
            command=value.get('command') or {}
            command_at=value.get('command_computed_at',command.get('computed_at'))
            if request['start_s']-.5<=row['at_s']<=request['end_s']+.5 and (
                    row['at_s']<=request['end_s'] or isinstance(command_at,(int,float)) and command_at<=request['end_s']):
                rows[(row.get('stream_id'),row['sequence'])]=row
        frozen=dict(request=request,records=sorted(rows.values(),key=lambda r:(r['at_s'],r['sequence'])),
            capacity_drops=max([self.case['before_drops']]+[s['capacity_drops'] for s in snapshots]),
            capture_failures=sum(s['capture_failures'] for s in snapshots),shutdown_before_seal=False)
        from core.steering_replay import export_autopilot_part_isolated
        path=export_autopilot_part_isolated(directory,frozen)
        # Publish a completion marker; only the AP tick retires/promotes its
        # case, so the background worker cannot race a tick's state access.
        self.background_completed_id=incident_id
        self.background_completion=(incident_id,frozen)
        return path

    def begin(self):
        self.local.inputs=[];self.local.command=None;self.local.command_at=None;self.local.bytes=0;self.local.failures=0

    def consume(self, kind, value, now):
        ring=getattr(self.plugin._steering_replay,'_diagnostic_inputs',None)
        if ring is None:return
        if not hasattr(self.local,'inputs'):self.begin()
        try:
            frozen=freeze_primitive_record(value) if ring.simple_records else _freeze_input(value)
            size=1024+len(frozen['blob'])
            owned=restore_exact_record(frozen) if ring.simple_records else frozen
            if self.local.bytes+size>512*1024 or len(self.local.inputs)>=16:
                self.local.failures+=1
            elif kind=='consumer_ap_command':
                self.local.command=owned.get('packet') if ring.simple_records else _freeze_input(value.get('packet'))
                self.local.command_at=(value.get('packet') or {}).get('computed_at');self.local.bytes+=size
            else:self.local.inputs.append(dict(source=kind,at_s=now,value=owned));self.local.bytes+=size
        except (ValueError,RecursionError):self.local.failures+=1
        packet=value.get('packet') if isinstance(value,dict) else None
        request=packet.get('diagnostic_part_request') if isinstance(packet,dict) else None
        if isinstance(request,dict):self.accept(request)

    def accept(self, request):
        import math,re
        if (request.get('schema')!=2 or not re.fullmatch(r'[a-f0-9]{32}-[0-9]+',str(request.get('incident_id')))
                or request.get('phase') not in ('open','seal')
                or not isinstance(request.get('start_s'),(int,float)) or not math.isfinite(request['start_s'])):return
        if request['phase']=='seal' and (not isinstance(request.get('end_s'),(int,float))
                or not math.isfinite(request['end_s']) or request['end_s']<request['start_s']):return
        if request['incident_id']==self.completed_id:return
        ring=getattr(self.plugin._steering_replay,'_diagnostic_inputs',None)
        if ring is None:return
        if self.case and self.case['request']['incident_id']!=request['incident_id']:
            # Pin the next case's ORIGINAL prehistory when first observed,
            # not after the current export finishes. One bounded next case;
            # overflow is reported, never silently replaced by a newer ID.
            if self.next_case is None:
                self.next_case=self.pin_case(request,ring)
            elif self.next_case['request']['incident_id']==request['incident_id']:
                if not (self.next_case['request']['phase']=='seal' and request['phase']=='open'):
                    self.next_case['request']=dict(request)
            else:ring.failures+=1
            return
        if self.case is None:
            if isinstance(self.retired_ring,_RetiredAutopilotInputs):
                self.retired_ring.retain_from(request['start_s']-.5)
            self.case=self.pin_case(request,ring)
            self.retry_at=0.  # prior completed-case backoff does not own this request
        elif not self.frozen:
            # Never regress a seal to a repeated older open request.
            if self.case['request']['phase']=='seal' and request['phase']=='open':return
            self.case['request']=dict(request)

    def pin_case(self,request,ring):
        """Exact overlapping references from the preceding sealed part.

        A later seal can arrive after its left edge leaves the rolling ring.
        Reuse the already-owned ORIGINAL rows, not a newly sampled packet.
        Keep one bounded 30 s predecessor tail, never a list of prior parts.
        """
        snapshot=ring.rolling_snapshot(packed=True);rows={}
        sources=[self.previous_tail,snapshot['records']]
        if self.case:sources.append(self.case['before'])
        if self.frozen:sources.append(self.frozen['records'])
        for source in sources:
            for row in source:
                if row['at_s']>=request['start_s']-.5:
                    rows[(row.get('stream_id'),row['sequence'])]=row
        ordered=sorted(rows.values(),key=lambda r:(r['at_s'],r['sequence']))
        kept=[];used=0
        for row in reversed(ordered):
            size=1024+len((row.get('value') or {}).get('blob',b''))
            if used+size>ring.limit:
                ring.failures+=1;break  # Explicit incomplete, never growing ownership.
            used+=size;kept.append(row)
        return dict(request=dict(request),before=tuple(reversed(kept)),
            before_drops=snapshot['capacity_drops'],before_failures=ring.failures)

    def keep_previous_tail(self):
        if not self.frozen:return
        ring=self.known_ring
        end=self.frozen['request']['end_s']
        rows=[r for r in self.frozen['records'] if end-30.5<=r['at_s']<=end]
        # Same AP ring allowance for this one extra overlapping reference set;
        # payload bytes are shared with a current frozen/pinned part where equal.
        used=0;kept=[]
        for row in reversed(rows):
            value=row.get('value') or {}
            size=1024+len(value.get('blob',b''))
            if used+size>ring.limit:
                ring.failures+=1;break
            used+=size;kept.append(row)
        self.previous_tail=tuple(reversed(kept))
        if isinstance(self.retired_ring,_RetiredAutopilotInputs):
            cutoff=min(end-30.5,(self.next_case or {}).get('request',{}).get('start_s',end)-.5)
            self.retired_ring.retain_from(cutoff)

    def end(self, *, shutdown=False):
        plugin=self.plugin
        ring=getattr(getattr(plugin,'_steering_replay',None),'_diagnostic_inputs',None)
        if ring is None:return
        if ring is not self.known_ring:
            if self.retired_ring is None:self.retired_ring=self.known_ring
            else:self.retired_ring=_RetiredAutopilotInputs(self.retired_ring,self.known_ring)
            self.known_ring=ring
        now=time.monotonic()
        if hasattr(self.local,'inputs'):
            transaction=dict(inputs=self.local.inputs,command=self.local.command,
                truck=getattr(plugin,'_longitudinal_truck',{}),
                context=getattr(plugin,'_longitudinal_binding',None),
                capture_failures=self.local.failures,
                no_control_decision=self.local.command is None and not self.local.inputs)
            try:
                # Exact compressed immutable transaction, not repeated expanded
                # producer trees in the fixed ring. Expansion/hash checks are
                # worker-only. No observation/frame/command field is rewritten.
                transaction['command_computed_at']=self.local.command_at
                ring.observe('ap_decision',transaction,now,force=True)
            except (ValueError,TypeError,RecursionError):ring.failures+=1
            self.local.inputs=[];self.local.command=None;self.local.bytes=0;self.local.failures=0
        if self.case is not None:
            # A later continuation's request can arrive after 30 s while the
            # old writer is busy. Retain ORIGINAL forward rows in the existing
            # bounded retired slot; a predecessor snapshot cannot supply them.
            if not isinstance(self.retired_ring,_RetiredAutopilotInputs):
                self.retired_ring=_RetiredAutopilotInputs(self.retired_ring or ring,ring)
            else:
                with ring.lock:entry=ring.rows[-1] if ring.rows else None
                if entry is not None:self.retired_ring.append_original(entry)
        writer=getattr(plugin,'_replay_export_writer',None)
        if self.case is None:
            if not getattr(plugin,'_was_active',False) and self.retired_ring is not None and now>=self.retry_at and not (
                    writer is not None and writer.status.get('busy')):
                if writer is None:
                    from core.steering_replay import AsyncReplayExporter
                    writer=plugin._replay_export_writer=AsyncReplayExporter()
                from types import SimpleNamespace
                from core.paths import app_dir
                import os
                retired=SimpleNamespace(_diagnostic_inputs=self.retired_ring)
                directory=getattr(plugin,'_diagnostic_part_directory',None) or os.path.join(app_dir(),'route-diagnostics')
                self.retry_at=now+30.
                self.rendezvous_submitted=writer.submit(lambda:self.after_disabled_replay(retired,directory))
            return
        completion=getattr(self,'background_completion',None)
        if completion and completion[0]==self.case['request']['incident_id']:
            # Exactly the original worker snapshot, not a later traffic read.
            # Retain one bounded overlapping tail just like the tick-export
            # path; the next continuation can be sealed after this completes.
            self.frozen=completion[1]
            self.keep_previous_tail()
            self.completed_id=completion[0];self.background_completed_id=None
            self.background_completion=None
            self.case=self.next_case;self.next_case=None;self.frozen=None;self.submitted=False
            # Keep the existing bounded rotated ring for the disabled AP's
            # compact-seal rendezvous. No next request may exist yet.
            self.rendezvous_submitted=False
            if self.case is None:return
        if self.rendezvous_submitted:
            if writer is not None and writer.status.get('busy'):return
            self.rendezvous_submitted=False
            self.retry_at=0. if self.case['request']['phase']=='seal' else now+30.
        if self.submitted:
            if writer is not None and writer.status.get('busy'):return
            if writer is not None and writer.status.get('path'):
                self.completed_id=self.case['request']['incident_id']
                self.keep_previous_tail()
                self.case=self.next_case;self.next_case=None;self.frozen=None;self.submitted=False
                if self.next_request:
                    request=self.next_request;self.next_request=None;self.accept(request)
                return
            self.submitted=False;self.retry_at=now+30.
        request=self.case['request']
        if request['phase']!='seal' and not shutdown:
            # A disable can rotate the dense ring while its writer is busy,
            # so the ordinary replay submission may have been rejected. Once
            # that SAME writer is free, complete the diagnostic-only handshake
            # using the retained original ring. No control IPC/SDK read here.
            if not getattr(plugin,'_was_active',False) and self.retired_ring is not None and now>=self.retry_at and not (
                    writer is not None and writer.status.get('busy')):
                if writer is None:
                    from core.steering_replay import AsyncReplayExporter
                    writer=plugin._replay_export_writer=AsyncReplayExporter()
                from types import SimpleNamespace
                from core.paths import app_dir
                import os
                retired=SimpleNamespace(_diagnostic_inputs=self.retired_ring)
                directory=getattr(plugin,'_diagnostic_part_directory',None) or os.path.join(app_dir(),'route-diagnostics')
                self.rendezvous_submitted=writer.submit(lambda:self.after_disabled_replay(retired,directory))
            return
        if writer is not None and writer.status.get('busy'):return
        if not shutdown and now<self.retry_at:return
        if self.frozen is None:
            snapshot=ring.rolling_snapshot(packed=True)
            retired=self.retired_ring.rolling_snapshot(packed=True) if self.retired_ring is not None else None
            end=request.get('end_s')
            if end is None:end=now
            rows={}
            for row in (*self.case['before'],*(retired['records'] if retired else ()),*snapshot['records']):
                command=(row.get('value') or {}).get('command') or {}
                if request['start_s']-.5<=row['at_s']<=end+.5 and (
                        row['at_s']<=end or (row.get('value') or {}).get('command_computed_at',
                            command.get('computed_at',float('inf')))<=end):
                    rows[(row.get('stream_id'),row['sequence'])]=row
            self.frozen=dict(request=dict(request),records=sorted(rows.values(),key=lambda r:(r['at_s'],r['sequence'])),
                capacity_drops=snapshot['capacity_drops']+(retired['capacity_drops'] if retired else 0),
                capture_failures=snapshot['capture_failures']+(retired['capture_failures'] if retired else 0),
                shutdown_before_seal=request['phase']!='seal')
        if writer is None:
            from core.steering_replay import AsyncReplayExporter
            writer=plugin._replay_export_writer=AsyncReplayExporter()
        directory=getattr(plugin,'_diagnostic_part_directory',None)
        if not directory:
            from core.paths import app_dir
            import os
            directory=os.path.join(app_dir(),'route-diagnostics')
        frozen=self.frozen
        from core.steering_replay import export_autopilot_part_isolated
        self.submitted=writer.submit(lambda:export_autopilot_part_isolated(directory,frozen))

    def close(self):
        writer=getattr(self.plugin,'_replay_export_writer',None)
        if writer is not None:writer.wait(30.)
        self.end(shutdown=True)
        writer=getattr(self.plugin,'_replay_export_writer',None)
        if writer is not None:writer.wait(30.)


def diagnostic_autopilot_begin(plugin):
    assembler=getattr(plugin,'_diagnostic_part_assembler',None)
    if assembler is not None:
        try:assembler.begin()
        except Exception:pass  # never replace a control result


def diagnostic_autopilot_end(plugin):
    assembler=getattr(plugin,'_diagnostic_part_assembler',None)
    if assembler is not None:
        try:assembler.end()
        except Exception:
            ring=getattr(getattr(plugin,'_steering_replay',None),'_diagnostic_inputs',None)
            if ring is not None:ring.failures+=1


def diagnostic_autopilot_close(plugin):
    assembler=getattr(plugin,'_diagnostic_part_assembler',None)
    if assembler is not None:
        try:assembler.close()
        except Exception:
            ring=getattr(getattr(plugin,'_steering_replay',None),'_diagnostic_inputs',None)
            if ring is not None:ring.failures+=1


def diagnostic_autopilot_locals(plugin, values):
    """Actual locals even on early wait/launch returns; no new getter calls."""
    assembler=getattr(plugin,'_diagnostic_part_assembler',None)
    if assembler is None:return
    names=('snapshot','accepted_packet','packet_read_finished_at','forward_history',
        'launch','service_resume','truck','system_state','danger_level','lane_offset',
        'maneuver_approach','vehicle_snapshot','mode_evidence','acc','traffic','policy',
        'curve','radius','curve_distance','requests','decision','input_failure',
        'navigation_unreliable','active_requested','autopilot_engaged')
    try:
        assembler.consume('consumer_control_locals',{k:values[k] for k in names if k in values},time.monotonic())
    except Exception:
        assembler.local.failures=getattr(assembler.local,'failures',0)+1
