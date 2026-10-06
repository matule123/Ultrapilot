"""Producer-timed signal sidecar. Route relevance remains a heuristic.

QPC seconds share Python's Windows monotonic clock domain. Reading memory does
not create an observation. Legacy buffers may brake, never authorize release.
"""
import math
import struct
import time

from core.sdk.existing_mapping import ExistingMapping
from core.sdk.ets2la_data import ETS2LAData
from core.acc_following import RouteLeadSelector

LAYOUT = struct.Struct('<IIIIQQQdII1920sI')
SIZE = LAYOUT.size


def compact(signal):
    result = {k: signal[k] for k in ('valid','reason','lifecycle','generation',
              'frame_us','observed_at','relevance','prefab_binding_reason','prefab_required') if k in signal}
    candidate = signal.get('candidate')
    if candidate:
        result['candidate'] = {k: candidate[k] for k in (
            'id','x','y','z','color','distance','distance_basis','stop_line_verified',
            'passage_key','stop_target_kind','entry_progress_m','entry_xyz',
            'front_allowance_m','junction_standoff_m','front_geometry_status','head_observed') if k in candidate}
    missing=signal.get('stop_candidate')
    if missing:
        result['stop_candidate']={k:missing[k] for k in ('id','color','passage_key','distance',
            'stop_target_kind','stop_line_verified','front_allowance_m','junction_standoff_m',
            'front_geometry_status','head_observed') if k in missing}
    return result


def decode(data, now, sequence_after=None):
    result = dict(valid=False, reason='signal snapshot unavailable', schema=2)
    try:
        seq, magic, version, size, lifecycle, generation, frame, observed, flags, count, payload, end = LAYOUT.unpack(data)
        if seq == 0 or seq % 2 or seq != end or (sequence_after is not None and seq != sequence_after):
            raise ValueError('torn signal snapshot')
        if (magic, version, size) != (0x32535055, 2, SIZE):
            raise ValueError('unsupported signal schema')
        result.update(lifecycle=lifecycle, generation=generation, frame_us=frame,
                      observed_at=observed, sequence=seq)
        if flags != 3 or not lifecycle or not generation or not frame or not 0 <= count <= 40:
            raise ValueError('inactive or incomplete signal producer')
        if not math.isfinite(observed) or not 0 <= now-observed <= .5:
            raise ValueError('signal producer observation stale or incoherent')
        reader = ETS2LAData()
        reader._ensure = lambda: None
        reader._sem_buf = payload
        lights = reader.read_traffic_lights()
        # IDs come from semaphore_instances of nearby prefabs, not a global
        # actor allocator. Distinct placements can share an ID; exact duplicate
        # ID/placement rows remain ambiguous, including conflicting colours.
        keys = {(x['id'],x['x'],x['y'],x['z']) for x in lights}
        if len(lights) > count or len(keys) != len(lights):
            raise ValueError('ambiguous signal placements or count')
        for light in lights:
            if not all(math.isfinite(light[k]) for k in ('x', 'y', 'z', 'yaw')):
                raise ValueError('invalid signal pose')
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

    def read(self):
        now = time.monotonic()
        if self.buffer is None and now >= self.retry_at:
            self.retry_at = now+1.
            try:
                self.buffer = ExistingMapping(r'Local\UltraPilotSemaphoreV2', SIZE)
            except OSError:
                pass
        if self.buffer is None:
            return dict(valid=False, schema=2, reason='producer-timed signal plugin unavailable')
        try:
            data = self.buffer[:SIZE]
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
    """Bounded XYZ projection; 6 m relevance gate is NOT a physical road edge.

    Same-approach heads within 3 m progress are ambiguous. Orientation is used
    only when supplied; sidecar always supplies the source quaternion/yaw.
    """
    def __init__(self):
        self.route = RouteLeadSelector()
        self.lock = None

    def select(self, snapshot, points, publication, authority, truck, progress, passages=None):
        result = {k: v for k, v in snapshot.items() if k != 'lights'}
        result.update(authority=authority, relevance='route_geometry_heuristic', candidate=None)
        self._stop_target = None
        if not snapshot.get('valid') and passages is None:
            return result
        try:
            self.route.prepare(points, publication)
            progress = float(progress)
            if not math.isfinite(progress) or not 0 <= progress <= self.route.arcs[-1]:
                raise ValueError('invalid route progress')
            ego = self.route._project(dict(truck, yaw=truck['rotation']), max(0., progress-20.), progress+20.)
            if ego is None or ego[0] > 1.2:
                raise ValueError('signal route localization unavailable')
            if passages is not None:
                assigned = self._prefab_candidate(snapshot, passages, authority, ego[1])
                if assigned is not None:
                    if not snapshot.get('valid'):
                        raise ValueError(snapshot.get('reason') or 'signal producer unavailable')
                    result.update(candidate=assigned, relevance='directed_prefab_curve_id_and_placement')
                    return result
                if self.lock and self.lock['candidate'].get('passage_key'):
                    raise ValueError('locked prefab passage unavailable')
                result['prefab_binding_reason']='no prepared regulated passage; geometric fallback unconfirmed'
            candidates = []
            locked_id = self.lock['candidate']['id'] if self.lock else None
            for light in snapshot['lights']:
                # A traffic head faces against the directed approach tangent.
                actor = dict(light, yaw=float(light.get('yaw', truck['rotation']+math.pi))+math.pi)
                # Acquisition remains strictly ahead. Once braking locked this
                # same head, retain its actual fresh observation across passage
                # of the SDK reference. Do not acquire a different behind head,
                # jump to another route lap, or fabricate stop-line geometry.
                retained = bool(light['id'] == locked_id and self.lock and math.dist(
                    [light[k] for k in ('x','y','z')],
                    [self.lock['candidate'][k] for k in ('x','y','z')]) <= 1.)
                low = max(0., ego[1] - (20. if retained else .5))
                p = self.route._project(actor, low, ego[1]+120.)
                if p is not None and p[0] <= 6. and (retained or p[1] > ego[1]):
                    candidates.append(dict(light, distance=p[1]-ego[1], lateral_distance=p[0],
                        route_progress_m=p[1], distance_basis='sdk_reference_to_signal_head',
                        stop_line_verified=False))
            candidates.sort(key=lambda x: (x['distance'], x['id']))
            if self.lock:
                if self.lock['authority'] != authority or self.lock['lifecycle'] != snapshot['lifecycle']:
                    raise ValueError('locked signal authority or producer lifecycle changed')
                matches = [x for x in candidates if x['id'] == self.lock['candidate']['id']
                    and math.dist([x[k] for k in ('x','y','z')],
                        [self.lock['candidate'][k] for k in ('x','y','z')]) <= 1.]
                chosen = matches[0] if len(matches) == 1 else None
                if chosen is None:
                    raise ValueError('locked signal missing or no longer route relevant')
                original = self.lock['candidate']
                if math.dist([chosen[k] for k in ('x','y','z')], [original[k] for k in ('x','y','z')]) > 1.:
                    raise ValueError('locked signal placement changed')
            else:
                chosen = candidates[0] if candidates else None
            if chosen is None:
                raise ValueError('no relevant signal; coverage unproven')
            if any(x is not chosen and abs(x['distance']-chosen['distance']) <= 3. for x in candidates):
                raise ValueError('ambiguous route signal candidates')
            result['candidate'] = chosen
        except (KeyError, TypeError, ValueError, OverflowError) as error:
            result.update(valid=False, reason=str(error))
            if self._stop_target is not None:
                # This is stable map geometry with NO observed colour/head. It
                # may constrain approach; it can never confirm green clearance.
                result.update(prefab_required=True,stop_candidate=dict(self._stop_target,
                    color='unknown',head_observed=False), relevance='directed_prefab_control_unobserved')
        return result

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
            yaw=light['yaw']+math.pi
            delta=(yaw-heading+math.pi)%(2*math.pi)-math.pi
            if (abs(delta)>math.pi/4 or not bounds[0]-10 <= light['x'] <= bounds[3]+10
                    or not bounds[2]-10 <= light['z'] <= bounds[5]+10
                    or not bounds[1]-1.5 <= light['y'] <= bounds[4]+1.5
                    or math.hypot(light['x']-entry[0],light['z']-entry[2])>40.):
                continue
            if locked and math.dist([light[k] for k in ('x','y','z')],
                    [self.lock['candidate'][k] for k in ('x','y','z')])>1.:
                continue
            matches.append(light)
        if len(matches)!=1:
            raise ValueError('prefab semaphore ID missing or spatially ambiguous')
        return dict(matches[0],**{k:v for k,v in target.items() if k not in ('id','x','y','z')},head_observed=True)
