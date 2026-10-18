"""Bounded passive pedal provenance for the existing evidence collector.

This journal cannot send controls. Contexts belong to a single Engine flush;
calls outside that flush remain explicitly unbound. No game consumption proof.
"""
from collections import deque
import copy
import json
import math
import threading
import time
import zlib

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
        if len(blob)>self.ROW_LIMIT or len(identity_blob)>4096:
            self.failures+=1;return
        # Fixed-value summaries repeat nulls/labels, not full producer packets.
        # Lossless bounded compression retains the thirty-second reservation
        # even with long real identities and physical-edge aggregate fields.
        blob=zlib.compress(blob,1)
        size=len(blob)+256  # Owned bytes/tuple/deque and reference accounting.
        while getattr(self,kind) and (len(getattr(self,kind))>=capacity or self.bytes[kind]+size>budget):
            self._release(kind,capacity=True)
        identity_id=self.identity_keys.get(identity_blob)
        if identity_id is None:
            identity_size=len(identity_blob)+512
            if self.identity_bytes+identity_size>self.IDENTITY_BYTES:
                self.failures+=1;return  # No guessed identity or growing pool.
            self.next_identity+=1;identity_id=self.next_identity
            self.identities[identity_id]=dict(blob=identity_blob,uses=0,size=identity_size)
            self.identity_keys[identity_blob]=identity_id;self.identity_bytes+=identity_size
        self.identities[identity_id]['uses']+=1
        self.sequence+=1
        getattr(self,kind).append((self.sequence,now,identity_id,blob,size))
        self.bytes[kind]+=size

    def observe(self,now,row,identity):
        if not math.isfinite(now) or self.last_time is not None and now<self.last_time:
            self.regressions+=1;return
        if row.get('capture_incomplete'):self.failures+=1
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
            byte_budget=self.MAX_BYTES,retained_bytes=sum(self.bytes.values())+self.identity_bytes,
            regular_byte_budget=self.REGULAR_BYTES,change_byte_budget=self.CHANGE_BYTES,
            identity_byte_budget=self.IDENTITY_BYTES,regular_capacity=self.REGULAR_CAPACITY,change_capacity=self.CHANGE_CAPACITY,
            requested_window_s=self.WINDOW_S,regular_period_s=self.PERIOD_S,
            window_start_s=None if end is None else end-self.WINDOW_S,window_end_s=end,
            observed_range_s=dict(start=start,end=end,duration=None if start is None else end-start),
            regular_dropped_capacity=self.dropped['regular'],change_dropped_capacity=self.dropped['changes'],
            regular_aged_out=self.aged_out['regular'],change_aged_out=self.aged_out['changes'],
            capture_failures=self.failures,time_regressions=self.regressions,
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

    def begin_decision(self):
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
        with self._lock:
            row.update(written_throttle=self._held['throttle'],written_brake=self._held['brake'])
            try:self._history.observe(now,row,identity)
            except Exception:self._history.failures+=1
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
            with self._lock:
                try:self._history.intervention(fault,time.monotonic())
                except Exception:self._history.failures+=1

    def _pair_mode(self):
        t,b=self._held['throttle'],self._held['brake']
        return ('unknown' if t is None or b is None else 'overlap' if t>0 and b>0
                else 'brake' if b>0 else 'drive' if t>0 else 'coast')

    def bind(self, value):
        self._local.summary=None
        if value is not None:
            try:self._local.summary=_decision_summary(value)
            except Exception:self._history.failures+=1
        # Keep the rare first intervention beside the decision, not repeated
        # inside its already bounded producer snapshots. Both allocations count
        # against the unchanged total journal byte budget.
        intervention = value.get('intervention') if isinstance(value, dict) else None
        if intervention is not None:
            value = {k: v for k, v in value.items() if k != 'intervention'}
        self._local.intervention, extra = bounded_copy(_pack_intervention(intervention), limit=16384)
        try:
            self._local.source, self._local.size = bounded_copy(pack_source(pack_journal_inputs(compact_decision(value))), limit=32768) if value is not None else (None, 64)
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
    for event in result['events']:
        event['source'] = expand_decision(unpack_source(event['source']))
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
