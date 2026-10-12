"""Producer-timed signal sidecar. Route relevance remains a heuristic.

QPC seconds share Python's Windows monotonic clock domain. Reading memory does
not create an observation. Untimed legacy heads are detection only and cannot
assign signal control or authorize release.
"""
import math
import struct
import time

from core.sdk.existing_mapping import ExistingMapping
from core.sdk.ets2la_data import ETS2LAData
from core.acc_following import RouteLeadSelector

LAYOUT = struct.Struct('<IIIIQQQdII1920sI')
SIZE = LAYOUT.size
SCOPED_LAYOUT = struct.Struct('<IIIIQQQdII1920s2880sI')
OWNER_LAYOUT = struct.Struct('<Q6QQII')
UNASSIGNED_CONTROL_REASON = ('signal regulation coverage unverified; live approach head is not '
                             'assigned to a directed passage; driver takeover required')


def _control_heading(light):
    """Scoped native actor forward is the regulated navCurve direction.

    PPD 25 original head/curve quaternions and the producer's unchanged
    placement.rot (w,x,y,z) agree after the placed-prefab transform. Native
    yaw is NOT a visual lamp-facing normal; adding pi reverses its passage.
    Keep the unscoped legacy heuristic separate, not a native owner proof.
    """
    return float(light['yaw']) + (0. if light.get('scope_schema') == 1 else math.pi)


def compact(signal):
    result = {k: signal[k] for k in ('schema','valid','reason','lifecycle','generation',
              'frame_us','observed_at','relevance','prefab_binding_reason','prefab_required',
              'authority_lane_id','route_progress_m','route_publication_token') if k in signal}
    candidate = signal.get('candidate')
    if candidate:
        result['candidate'] = {k: candidate[k] for k in (
            'id','x','y','z','yaw','color','state','time_left','distance','distance_basis','stop_line_verified',
            'phase_plan','stop_required','passage_length_m','passage_speed_ms',
            'passage_key','stop_target_kind','entry_progress_m','entry_xyz',
            'front_allowance_m','junction_standoff_m','front_geometry_status','head_observed','binding_basis',
            'scope_schema','owner_prefab_uid','owner_node_uids','owner_origin_index','instance_slot',
            'ownership_valid','id_basis') if k in candidate}
    missing=signal.get('stop_candidate')
    if missing:
        result['stop_candidate']={k:missing[k] for k in ('id','color','x','y','z','passage_key','distance',
            'distance_basis','entry_progress_m','entry_xyz','stop_target_kind','stop_line_verified',
            'front_allowance_m','junction_standoff_m','front_geometry_status','head_observed') if k in missing}
    if isinstance(signal.get('coverage'), dict):
        result['coverage'] = dict(signal['coverage'])
    if isinstance(signal.get('unassigned_candidate'), dict):
        result['unassigned_candidate'] = {k:signal['unassigned_candidate'][k] for k in
            ('id','x','y','z','yaw','color','distance','distance_basis',
             'scope_schema','owner_prefab_uid','owner_node_uids','owner_origin_index',
             'instance_slot','ownership_valid','id_basis')
            if k in signal['unassigned_candidate']}
    return result


def decode(data, now, sequence_after=None):
    result = dict(valid=False, reason='signal snapshot unavailable', schema=2)
    try:
        scoped = len(data)==SCOPED_LAYOUT.size
        if scoped:
            seq,magic,version,size,lifecycle,generation,frame,observed,flags,count,payload,owners,end=SCOPED_LAYOUT.unpack(data)
        else:
            seq, magic, version, size, lifecycle, generation, frame, observed, flags, count, payload, end = LAYOUT.unpack(data)
        if seq == 0 or seq % 2 or seq != end or (sequence_after is not None and seq != sequence_after):
            raise ValueError('torn signal snapshot')
        expected=(0x33535055,3,SCOPED_LAYOUT.size) if scoped else (0x32535055,2,SIZE)
        if (magic, version, size) != expected:
            raise ValueError('unsupported signal schema')
        result.update(lifecycle=lifecycle, generation=generation, frame_us=frame,
                      observed_at=observed, sequence=seq,schema=3 if scoped else 2)
        if flags != 3 or not lifecycle or not generation or not frame or not 0 <= count <= 40:
            raise ValueError('inactive or incomplete signal producer')
        if not math.isfinite(observed) or not 0 <= now-observed <= .5:
            raise ValueError('signal producer observation stale or incoherent')
        reader = ETS2LAData()
        reader._ensure = lambda: None
        reader._sem_buf = payload
        lights = reader.read_traffic_lights(include_index=True) if scoped else reader.read_traffic_lights()
        # IDs come from semaphore_instances of nearby prefabs, not a global
        # actor allocator. Distinct placements can share an ID; exact duplicate
        # ID/placement rows remain ambiguous, including conflicting colours.
        keys = {(x['id'],x['x'],x['y'],x['z']) for x in lights}
        if len(lights) > count or len(keys) != len(lights):
            raise ValueError('ambiguous signal placements or count')
        for light in lights:
            if not all(math.isfinite(light[k]) for k in ('x', 'y', 'z', 'yaw')):
                raise ValueError('invalid signal pose')
            if scoped:
                owner=OWNER_LAYOUT.unpack_from(owners,light.pop('source_index')*OWNER_LAYOUT.size)
                nodes=[v for v in owner[1:7] if v]
                owned=(owner[9]==1 and bool(owner[0]) and 2<=len(nodes)<=6
                       and len(nodes)==len(set(nodes)) and owner[7]<len(nodes))
                light.update(scope_schema=1,owner_prefab_uid=owner[0],owner_node_uids=nodes,
                    owner_origin_index=owner[7],instance_slot=owner[8],ownership_valid=owned,
                    id_basis='prefab_segment_instance_id')
        for i in range(count):
            row = struct.unpack_from('<fffhhffffifii', payload, i*48)
            if row[9] == 1 and not .9 <= sum(v*v for v in row[5:9]) <= 1.1:
                raise ValueError('invalid signal quaternion')
        result.update(valid=True, reason='', lights=lights)
    except (ValueError, struct.error) as error:
        result['reason'] = str(error)
    return result


class SignalReader:
    def __init__(self):
        self.buffer = None
        self.retry_at = 0.
        self.last = None
        self.last_bytes = None
        self.mapping_size=SIZE

    def read(self):
        now = time.monotonic()
        if self.buffer is None and now >= self.retry_at:
            self.retry_at = now+1.
            try:
                self.buffer = ExistingMapping(r'Local\UltraPilotSemaphoreV3',SCOPED_LAYOUT.size)
                self.mapping_size=SCOPED_LAYOUT.size
            except OSError:
                try:
                    self.buffer = ExistingMapping(r'Local\UltraPilotSemaphoreV2', SIZE)
                    self.mapping_size=SIZE
                except OSError:pass
        if self.buffer is None:
            return dict(valid=False, schema=2, reason='producer-timed signal plugin unavailable')
        try:
            data = self.buffer[:self.mapping_size]
            after = struct.unpack('<I', self.buffer[:4])[0]
            result = decode(data, time.monotonic(), after)
            if result.get('valid'):
                current = tuple(result[k] for k in ('lifecycle','generation','frame_us','observed_at'))
                if self.last and current[0] == self.last[0]:
                    if (any(a < b for a,b in zip(current[1:],self.last[1:]))
                            or (current[1] == self.last[1] and data != self.last_bytes)):
                        return dict(result, valid=False, reason='signal producer frame/generation regressed or changed in place')
                self.last, self.last_bytes = current, data
            return result
        except (OSError, struct.error):
            self.buffer = None
            return dict(valid=False, schema=2, reason='signal mapping read failed')


class RouteSignalSelector:
    """Match authored directed passages to actually observed placed heads.

    XYZ bounds and direction qualify a local ID; proximity alone never assigns
    control. These geometry gates do not establish a physical road edge.
    """
    def __init__(self):
        self.route = RouteLeadSelector()
        self.lock = None
        self._observed_controls = set()
        self._control_authority = None
        self._uncertain_approach = None

    def select(self, snapshot, points, publication, authority, truck, progress, passages=None):
        result = {k: v for k, v in snapshot.items() if k != 'lights'}
        result.update(authority=authority, relevance='route_geometry_heuristic', candidate=None)
        self._stop_target = None
        self._passages=passages
        self._coverage_speed = truck.get('speed')
        lifecycle = snapshot.get('lifecycle')
        previous = self._control_authority
        # A failed/unavailable read supplies no evidence of a new lifecycle.
        # Retain only the known stop dependency, never a colour or clearance.
        # An actual new lifecycle or route authority discards the admission.
        if not lifecycle and previous and previous[0] == authority:
            lifecycle = previous[1]
        control_authority = (authority, lifecycle)
        if control_authority != self._control_authority:
            self._observed_controls.clear()
            self._uncertain_approach = None
            self._control_authority = control_authority
        try:
            if isinstance(passages, dict):
                # Fixed capacity, discarded on route/session/producer changes.
                # Malformed identities belong to the same fail-closed path as
                # geometry validation, never an uncaught set-operation error.
                records = passages.get('passages')
                if isinstance(records, (list, tuple)) and len(records) <= 128:
                    self._observed_controls.intersection_update(
                        p.get('passage_key') for p in records if isinstance(p, dict))
            self.route.prepare(points, publication)
            progress = float(progress)
            if not math.isfinite(progress) or not 0 <= progress <= self.route.arcs[-1]:
                raise ValueError('invalid route progress')
            ego = self.route._project(dict(truck, yaw=truck['rotation']), max(0., progress-20.), progress+20.)
            if ego is None or ego[0] > 1.2:
                raise ValueError('signal route localization unavailable')
            if passages is None:
                result.update(valid=False, relevance='detected_only_unassigned',
                    reason='authored directed signal passage unavailable; detection only')
                return self._coverage(result, snapshot, ego[1])
            assigned = self._prefab_candidate(snapshot, passages, authority, ego[1])
            if assigned is not None:
                if not snapshot.get('valid'):
                    raise ValueError(snapshot.get('reason') or 'signal producer unavailable')
                from core.longitudinal import signal_phase_plan
                assigned = dict(assigned, phase_plan=signal_phase_plan(
                    assigned, truck, snapshot['observed_at'], time.monotonic()))
                assigned['stop_required'] = assigned['phase_plan']['stop_required']
                result.update(candidate=assigned, relevance='directed_prefab_curve_id_and_placement')
                return self._coverage(result, snapshot, ego[1], assigned)
            if self.lock and self.lock['candidate'].get('passage_key'):
                raise ValueError('locked prefab passage unavailable')
            # Explicit map metadata has no regulated directed passage in this
            # horizon. A nearby head cannot override that selection.
            result.update(valid=False, relevance='detected_only_unassigned',
                reason='no prepared regulated passage; nearby heads are detection only',
                prefab_binding_reason='no prepared regulated passage')
            return self._coverage(result, snapshot, ego[1])
        except (KeyError, TypeError, ValueError, OverflowError) as error:
            result.update(valid=False, reason=str(error))
            if self._stop_target is not None:
                # This is stable map geometry with NO observed colour/head. It
                # may constrain approach; it can never confirm green clearance.
                result.update(prefab_required=True,stop_candidate=dict(self._stop_target,
                    color='unknown',head_observed=False), relevance='directed_prefab_control_unobserved')
        if self._stop_target is None and self.route.binding == publication:
            return self._coverage(result, snapshot, progress)
        return result

    def _coverage(self, result, snapshot, progress, assigned=None):
        """A live unassigned approach head is uncertainty, never a red control.

        Projection does not prove lane/signal ownership. A native-owned entry
        may support a bounded approach; unresolved regulation requires takeover
        before the existing stopping reserve is exhausted. No entry evidence
        means immediate takeover instead of a fabricated stop line/clearance.
        All heads are checked within the existing bounded producer capacity;
        no nearest-head substitute is handed to the brake/green-release flow.
        """
        result['coverage'] = dict(status='QUALIFIED_CONTROL' if assigned else 'NOT_VERIFIED',
                                  requires_takeover=False)
        pending=self._uncertain_approach
        if assigned and pending and assigned.get('passage_key')==pending['target']['passage_key']:
            self._uncertain_approach=None
        if assigned is not None and self.lock:
            return result  # Keep the same proven control while its stop is locked.
        if not snapshot.get('valid') or not self.route.binding:
            if pending and self.route.binding:
                return self._retain_uncertain_approach(result, progress)
            return result
        try:
            if not math.isfinite(float(progress)):
                return result
            heads = snapshot.get('lights', ())
            if not isinstance(heads,(list,tuple)) or len(heads)>40:
                return result
            assigned_progress = None
            if assigned is not None:
                if assigned.get('binding_basis')=='native_prefab_owner_and_directed_group':
                    assigned_progress=assigned['entry_progress_m']
                else:
                    projected = self.route._project(dict(assigned,yaw=_control_heading(assigned)),
                        max(0.,progress-.5),min(self.route.arcs[-1],progress+120.))
                    if projected is not None:assigned_progress = projected[1]
            conflicts = []
            high = min(self.route.arcs[-1],progress+120.,
                       assigned_progress+.5 if assigned_progress is not None else float('inf'))
            for head in heads:
                if assigned and head['id'] == assigned['id'] and all(
                        head[k] == assigned[k] for k in ('x','y','z','yaw','color')):
                    continue  # The actually qualified observation, not another group.
                owned=[]
                owned_records=[]
                if head.get('scope_schema')==1 and isinstance(self._passages,dict):
                    records=self._passages.get('passages',())
                    if isinstance(records,(list,tuple)) and len(records)<=128:
                        for passage in records:
                            if not self._native_owner_matches(head,passage):continue
                            yaw_delta=(_control_heading(head)-passage['controlled_heading_rad']+math.pi)%(2*math.pi)-math.pi
                            position=passage['entry_progress_m']
                            if abs(yaw_delta)<=math.pi/4 and progress+.5<=position<=high:
                                owned.append(position)
                                owned_records.append(passage)
                if owned:
                    if (assigned and head['id']==assigned['id'] and head['color']==assigned['color']
                            and head.get('owner_prefab_uid')==assigned.get('owner_prefab_uid')
                            and head.get('owner_node_uids')==assigned.get('owner_node_uids')
                            and head.get('owner_origin_index')==assigned.get('owner_origin_index')):
                        continue  # Same scoped control group, another physical lamp.
                    entry=min(owned_records,key=lambda p:(p['entry_progress_m'],p['passage_key']))
                    conflicts.append((min(owned),head,'sdk_reference_to_unassigned_native_passage_entry',entry))
                    continue
                scopes=(self._passages or {}).get('route_scopes') if isinstance(self._passages,dict) else None
                if (head.get('scope_schema')==1 and head.get('ownership_valid')
                        and self._passages.get('status')=='prepared'
                        and isinstance(scopes,(list,tuple)) and 0<len(scopes)<=128
                        and not any(self._native_owner_matches(head,p) for p in scopes)):
                    continue  # Proven different placement; never geometric fallback.
                projected = self.route._project(dict(head,yaw=_control_heading(head)),
                    max(0.,progress+.5),high)
                if (projected is not None and projected[0] <= 6.
                        and (assigned_progress is None or projected[1] <= assigned_progress+.5)):
                    conflicts.append((projected[1],head,'sdk_reference_to_unassigned_head_projection',None))
            if not conflicts:
                if self._uncertain_approach:
                    return self._retain_uncertain_approach(result,progress)
                return result  # Empty/foreign detection is NOT certified coverage.
            conflicts.sort(key=lambda v:(v[0],str(v[1]['id'])))
            position, head, basis, entry = conflicts[0]
            result['unassigned_candidate'] = dict(head,distance=position-progress,
                distance_basis=basis,
                detection_basis='producer_timed_unassigned',observation_timestamp=snapshot['observed_at'],
                producer_generation=snapshot['generation'],producer_frame_us=snapshot['frame_us'])
            result['coverage'] = dict(status='LIVE_APPROACH_HEAD_UNASSIGNED',
                requires_takeover=True, candidate_count=len(conflicts),
                distance_m=position-progress,
                reason=UNASSIGNED_CONTROL_REASON)
            if entry is not None:
                target=dict(passage_key=entry['passage_key'],entry_progress_m=position,
                    entry_xyz=list(entry['entry_xyz']),color='unknown',
                    distance=position-progress-entry['front_allowance_m']-entry['junction_standoff_m'],
                    distance_basis='sdk_reference_to_derived_stop_target',
                    stop_target_kind='derived_directed_curve_entry',stop_line_verified=False,
                    front_allowance_m=entry['front_allowance_m'],junction_standoff_m=entry['junction_standoff_m'])
                self._uncertain_approach=dict(target=target,head=dict(result['unassigned_candidate']),
                    source={k:snapshot[k] for k in ('lifecycle','generation','frame_us','observed_at')},
                    candidate_count=len(conflicts))
                result=self._retain_uncertain_approach(result,progress)
            if assigned is None:
                result.update(valid=False,candidate=None,relevance='detected_only_unassigned')
        except (KeyError,TypeError,ValueError,OverflowError):
            pass  # Malformed display geometry cannot manufacture authority.
        return result

    def _retain_uncertain_approach(self,result,progress):
        """One bounded unresolved entry, not a signal lock or green authority.

        Distance comes from an existing directed map entry; no stop line or
        group correspondence is invented. Source disappearance retains the
        original acquisition/lease, never a new read timestamp. Unknown entries
        reach takeover while the existing stopping reserve still fits.
        """
        pending=self._uncertain_approach
        records=(self._passages or {}).get('passages',())
        entries=[p for p in records if p.get('passage_key')==pending['target']['passage_key']]
        if len(entries)!=1:
            self._uncertain_approach=None
            result['coverage']=dict(status='UNRESOLVED_ENTRY_IDENTITY_LOST',requires_takeover=True,
                reason=UNASSIGNED_CONTROL_REASON)
            return result
        entry=entries[0]
        distance=entry['entry_progress_m']-progress-entry['front_allowance_m']-entry['junction_standoff_m']
        target=dict(pending['target'],entry_progress_m=entry['entry_progress_m'],distance=distance)
        try:
            speed=float(self._coverage_speed)
            if not math.isfinite(speed) or speed<0:raise ValueError('invalid approach speed')
            from core.longitudinal import CURVE_APPROACH_DECEL_MS2,CURVE_BRAKE_RESPONSE_S,LEASE_S
            reserve=speed*speed/(2*CURVE_APPROACH_DECEL_MS2)+speed*(CURVE_BRAKE_RESPONSE_S+LEASE_S)
            takeover=distance<=reserve
        except (TypeError,ValueError,OverflowError):
            reserve=None;takeover=True
        result.update(pending['source'])
        result['unassigned_candidate']=dict(pending['head'],
            distance=entry['entry_progress_m']-progress)
        result['coverage']=dict(status='LIVE_APPROACH_HEAD_UNASSIGNED' if takeover else 'UNASSIGNED_APPROACH_PENDING',
            requires_takeover=takeover,requires_approach=True,approach_target=target,
            stopping_reserve_m=reserve,distance_m=entry['entry_progress_m']-progress,
            candidate_count=pending['candidate_count'],clearance_confirmed=False,reason=UNASSIGNED_CONTROL_REASON)
        if result.get('candidate') is None:
            result.update(valid=False,relevance='detected_only_unassigned')
        return result

    @staticmethod
    def _native_owner_matches(light,passage):
        from core.navigation.road_network import _uid
        return (isinstance(passage,dict) and light.get('ownership_valid')
            and light.get('id_basis')=='prefab_segment_instance_id' and passage.get('prefab_uid')
            and _uid(light.get('owner_prefab_uid'))==passage['prefab_uid']
            and {_uid(v) for v in light.get('owner_node_uids',())}==set(passage.get('native_node_uids',()))
            and light.get('owner_origin_index')==passage.get('origin_node_index'))

    def _prefab_candidate(self, snapshot, plan, authority, progress):
        if not isinstance(plan,dict) or plan.get('schema_version') != 1 or plan.get('status') not in ('prepared','partial'):
            raise ValueError('prefab signal metadata unavailable or unsupported')
        records = plan.get('passages')
        if not isinstance(records,(list,tuple)) or len(records)>128:
            raise ValueError('invalid prefab passage capacity')
        if any(not isinstance(p,dict) for p in records):
            raise ValueError('invalid directed prefab passage record')
        locked = self.lock['candidate'].get('passage_key') if self.lock else None
        choices = [p for p in records if (p.get('passage_key') == locked if locked else
            progress-.5 <= p['entry_progress_m'] <= progress+200.)]
        if not choices:
            return None
        choices.sort(key=lambda p:(p['entry_progress_m'],p['passage_key']))
        passage = choices[0]
        if locked and len(choices) != 1:
            raise ValueError('ambiguous locked prefab passage')
        if locked and passage['entry_progress_m'] < progress-20.:
            raise ValueError('locked prefab entry passed outside bounded lookup')
        matches=[]
        bounds=passage['bounds_xyz']; entry=passage['entry_xyz']; heading=passage['entry_heading_rad']
        if len(bounds)!=6 or len(entry)!=3 or not all(math.isfinite(v) for v in (*bounds,*entry,heading,passage['entry_progress_m'])):
            raise ValueError('invalid placed prefab signal geometry')
        front=passage['front_allowance_m'];standoff=passage['junction_standoff_m']
        if not all(math.isfinite(v) and 0<=v<=20 for v in (front,standoff)):
            raise ValueError('invalid stop reference allowance')
        target=dict(passage_key=passage['passage_key'],id=passage['semaphore_id'],
            x=entry[0],y=entry[1],z=entry[2],
            entry_progress_m=passage['entry_progress_m'],entry_xyz=list(entry),
            distance=passage['entry_progress_m']-progress-front-standoff,
            distance_basis='sdk_reference_to_derived_stop_target',
            stop_target_kind='derived_directed_curve_entry',stop_line_verified=False,
            front_allowance_m=front,junction_standoff_m=standoff,
            front_geometry_status=passage['front_geometry_status'])
        for key in ('passage_length_m','passage_speed_ms'):
            if key in passage: target[key] = passage[key]
        # A PPD ID is a prospective control group, not proof that this placed
        # template actually has a live traffic head. In particular template
        # IDs and missing metadata must not manufacture a red/unknown stop.
        # Once a head was qualified on this exact passage, its loss remains a
        # stop dependency; neither disappearance nor another head clears it.
        corroborated = (passage['passage_key'] in self._observed_controls
                        or bool(locked and self.lock['authority'] == authority))
        if corroborated:
            self._stop_target=target
        if not locked and len(choices)>1 and abs(choices[1]['entry_progress_m']-passage['entry_progress_m']) < 1.:
            raise ValueError('ambiguous regulated prefab passages')
        if self.lock and (self.lock['authority'] != authority or self.lock['lifecycle'] != snapshot.get('lifecycle')):
            raise ValueError('locked signal authority or producer lifecycle changed')
        if not snapshot.get('valid'):
            raise ValueError(snapshot.get('reason') or 'signal producer unavailable')
        for light in snapshot.get('lights',()):
            if light['id'] != passage['semaphore_id']:
                continue
            native=light.get('scope_schema')==1
            if native:
                if not self._native_owner_matches(light,passage):
                    continue
            yaw=_control_heading(light)
            control_heading=passage.get('controlled_heading_rad',heading) if native else heading
            delta=(yaw-control_heading+math.pi)%(2*math.pi)-math.pi
            if (abs(delta)>math.pi/4 or (not native and not bounds[0]-10 <= light['x'] <= bounds[3]+10)
                    or (not native and not bounds[2]-10 <= light['z'] <= bounds[5]+10)
                    or (not native and not bounds[1]-1.5 <= light['y'] <= bounds[4]+1.5)
                    or (not native and math.hypot(light['x']-entry[0],light['z']-entry[2])>40.)):
                continue
            if locked and math.dist([light[k] for k in ('x','y','z')],
                    [self.lock['candidate'][k] for k in ('x','y','z')])>1.:
                continue
            matches.append(light)
        if not matches and not corroborated and not locked and len(choices)>1:
            # Prospective template groups cannot occlude a later live-qualified
            # control. At most 128 records, strictly reduced on each step.
            remaining = dict(plan, passages=choices[1:])
            return self._prefab_candidate(snapshot, remaining, authority, progress)
        if len(matches)>1 and all(m.get('scope_schema')==1 for m in matches):
            if len({m.get('color') for m in matches})==1:
                matches=[min(matches,key=lambda m:(m['x'],m['y'],m['z']))]
        if len(matches)!=1:
            raise ValueError('prefab semaphore ID missing or spatially ambiguous')
        self._observed_controls.add(passage['passage_key'])
        self._stop_target=target
        return dict(matches[0],**{k:v for k,v in target.items() if k not in ('id','x','y','z')},head_observed=True,
            binding_basis='native_prefab_owner_and_directed_group' if matches[0].get('scope_schema')==1 else 'legacy_id_pose_heuristic')
