"""Bounded protective ACC candidates; no clearance/coverage certification.

SDK world forward is (-sin yaw, -cos yaw); XYZ and gaps are metres,
speed is the legacy buffer's m/s channel, yaw radians. Receiver time is NOT
publisher freshness. Only lower speed demands are generated here, never pedals.
"""
import bisect
import math
import struct
import hashlib

from core.sdk.ets2la_data import _TRAFFIC_FMT, _PARKED_FMT, _TRAFFIC_SIZE, _PARKED_SIZE, _yaw

MIN_GAP_M = 12.
HEADWAY_S = 2.
HORIZON_M = 120.
LATERAL_GATE_M = 1.2  # centreline relevance, NOT a physical corridor width
PROTECTIVE_REFERENCE_GATE_M = 2.6  # existing legacy caution band, NOT lane ownership
HEIGHT_GATE_M = 1.5  # uncertain chassis/path origins, NOT deck certification
RETENTION_M = 2.


def observation(capture, now):
    """Decode the very same bounded byte capture, without display fallbacks."""
    result = dict(status='unavailable', actors=[], receiver_time=capture.observed_at,
                  source_timestamp=None, source_sequence=None, complete=False,
                  atomic=False, confirmed=False)
    source = getattr(capture, 'source', None)
    if source is not None:
        result.update(source=dict(source), source_timestamp=source.get('observed_at'),
            source_sequence=source.get('generation'), atomic=source.get('valid') is True)
        if not source.get('valid') or not 0 <= now-source.get('observed_at', float('-inf')) <= .5:
            result['status'] = source.get('reason') or 'stale_source_capture'
            return result
        payload = source.get('ego_body_payload')
        count = source.get('ego_body_count', 0)
        if (source.get('ego_body_flags') == 1 and type(count) is int and 1 <= count <= 4 and payload
                and all(math.isfinite(v) for v in source['ego_anchor'])
                and math.isfinite(source['ego_speed_mps']) and 0 <= source['ego_speed_mps'] <= 70.
                and 0 <= now-source['ego_speed_observed_at'] <= .5):
            bodies = []
            for i in range(count):
                row = struct.unpack_from('<10f', payload, i*40)
                if (not all(math.isfinite(v) for v in row) or min(row[7:10]) <= 0.
                        or not .9 <= sum(v*v for v in row[3:7]) <= 1.1):
                    break
                bodies.append(dict(x=row[0], y=row[1], z=row[2], yaw=_yaw(*row[3:7]),
                    dimensions_whl=tuple(row[7:10])))
            if len(bodies) == count:
                result['ego_bodies'] = bodies
        # Raw transport bytes are not a command/prediction metadata field.
        result['source'].pop('ego_body_payload', None)
    if not 0 <= now - capture.observed_at <= .1:
        result['status'] = 'stale_receiver_capture'
        return result
    if capture.moving is None or capture.parked is None:
        result['status'] = 'incomplete_buffers'
        return result
    if not capture.stable:
        result['status'] = 'changing_buffers'
        return result
    try:
        for source, data, stride, raw, record_size in (
                ('moving', struct.unpack(_TRAFFIC_FMT, capture.moving), 46, capture.moving, _TRAFFIC_SIZE//40),
                ('parked', struct.unpack(_PARKED_FMT, capture.parked), 12, capture.parked, _PARKED_SIZE//40)):
            for i in range(40):
                r = data[i*stride:(i+1)*stride]
                if r[0] == 0 and r[2] == 0:
                    continue
                q = r[3:7]
                if not all(math.isfinite(v) for v in r[:12]) or not .9 <= sum(v*v for v in q) <= 1.1:
                    result['status'] = 'invalid_actor'
                    return result
                bodies = [dict(x=r[0], y=r[1], z=r[2], yaw=_yaw(*q), dimensions_whl=tuple(r[7:10]))]
                count = int(r[12]) if source == 'moving' else 0
                if not 0 <= count <= 3:
                    result['status'] = 'invalid_actor'
                    return result
                for j in range(count):
                    body = r[16+j*10:26+j*10]
                    if (not all(math.isfinite(v) for v in body)
                            or not .9 <= sum(v*v for v in body[3:7]) <= 1.1):
                        result['status'] = 'invalid_actor'
                        return result
                    bodies.append(dict(x=body[0], y=body[1], z=body[2], yaw=_yaw(*body[3:7]),
                                       dimensions_whl=tuple(body[7:10])))
                result['actors'].append(dict(id=int(r[13] if source == 'moving' else r[10]),
                    x=r[0], y=r[1], z=r[2], yaw=_yaw(*q),
                    speed=r[10] if source == 'moving' else 0.,
                    speed_source='buffer' if source == 'moving' else 'parked_classification',
                    acceleration=r[11] if source == 'moving' else None,
                    temporary=bool(r[14]) if source == 'moving' else False,
                    dimensions_whl=tuple(r[7:10]), source=source, slot=i, bodies=bodies,
                    record_fingerprint=hashlib.sha256(raw[i*record_size:(i+1)*record_size]).hexdigest()))
    except (ValueError, struct.error):
        result['status'] = 'invalid_buffer'
        return result
    identity = actor_identity(result['actors'])
    result['actor_identity'] = identity
    # Moving/parked overlap is ambiguous, not resolved by list order.
    if identity['missing_count'] or identity['duplicate_count']:
        result['status'] = 'ambiguous_actor_id'
        return result
    result['status'] = 'observed' if result['actors'] else 'empty_unproven_coverage'
    return result


def actor_identity(actors):
    """Bounded diagnosis, never guessed IDs or content-based deduplication.

    The native ABI carries a signed short allocated by a pointer map. It does
    not carry the pointer or a cross-buffer generation. Equal values in two
    slots therefore cannot prove one source object, even if poses match.
    """
    seen, missing, duplicates, examples = {}, 0, 0, []
    for actor in actors:
        aid = actor.get('id')
        invalid = type(aid) is not int or not -32768 <= aid <= 32767 or aid in (0,-1)
        previous = seen.get(aid) if not invalid else None
        if invalid: missing += 1
        elif previous is not None: duplicates += 1
        else: seen[aid] = actor
        if (invalid or previous is not None) and len(examples) < 4:
            examples.append(dict(id=aid, source=actor.get('source'), slot=actor.get('slot'),
                prior_source=previous.get('source') if previous else None,
                prior_slot=previous.get('slot') if previous else None,
                position_xyz=[actor.get(k) for k in ('x','y','z')], yaw=actor.get('yaw'),
                prior_position_xyz=[previous.get(k) for k in ('x','y','z')] if previous else None,
                same_source_record=False,
                equal_decoded_values=(all(actor.get(k)==previous.get(k) for k in
                    ('x','y','z','yaw','speed','dimensions_whl','source')) if previous else None)))
    return dict(missing_count=missing, duplicate_count=duplicates, examples=examples,
        omitted_examples=max(0,missing+duplicates-len(examples)))


class RouteLeadSelector:
    """One cached unchanged LanePath, bounded local projections, one target ID."""
    def __init__(self):
        self.binding = None
        self.points = ()
        self.arcs = ()
        self.edges = ()
        self.target_id = None
        self._last_target_observation = None
        self._departure_observation = None
        self._native_previous = None
        self._native_current = None

    def reset(self):
        self.target_id = None
        self._last_target_observation = None
        self._departure_observation = None
        self._native_previous = None
        self._native_current = None

    def source_motion(self, actors, source):
        """One immutable native frame pair; duplicate reads never advance it."""
        if not source or source.get('valid') is not True:
            self._native_previous = self._native_current = None
            return {}
        stamp = (source['lifecycle'], source['generation'], source['frame_us'], source['observed_at'])
        current = self._native_current
        if current and stamp == current[0]:
            return self._native_predictions()
        self._native_previous = current if current and stamp[0] == current[0][0] else None
        self._native_current = (stamp, {a['id']: dict(a) for a in actors})
        return self._native_predictions()

    def _native_predictions(self):
        if not self._native_previous or not self._native_current:
            return {}
        previous, current = self._native_previous, self._native_current
        dt = current[0][3]-previous[0][3]
        if not .02 <= dt <= .5 or current[0][1] <= previous[0][1] or current[0][2] <= previous[0][2]:
            return {}
        result = {}
        for aid, actor in current[1].items():
            old = previous[1].get(aid)
            if (old is None or actor.get('temporary') or old.get('temporary')
                    or actor['source'] != old['source'] or actor['source'] != 'moving'
                    or actor['slot'] != old['slot']):
                continue  # TMP speed/acceleration fields are explicitly placeholders.
            acceleration = (actor['speed']-old['speed'])/dt
            displacement=math.hypot(actor['x']-old['x'],actor['z']-old['z'])
            if (not math.isfinite(acceleration) or abs(acceleration) > 15.
                    or displacement > max(old['speed'],actor['speed'])*dt+1.):
                continue  # Unsupported discontinuity, not an invented measurement.
            result[str(aid)] = dict(basis='native_source_speed_difference',
                acceleration_mps2=acceleration, raw_acceleration_mps2=actor.get('acceleration'),
                lifecycle=current[0][0], generation=current[0][1], frame_us=current[0][2],
                observed_at=current[0][3], previous_observed_at=previous[0][3],
                previous_frame_us=previous[0][2], accuracy_verified=False)
        return result

    def stop_clearance(self, lock, crossing, truck, progress, body_prediction=None):
        """Clear only observed original bodies receding from this local route.

        Two source frames establish movement; Engine additionally confirms two
        clearance acquisitions. No absence, no new target and no coverage claim.
        """
        if not lock or not self._native_previous or not self._native_current:
            return None
        previous, current = self._native_previous, self._native_current
        if (lock.get('lifecycle') != current[0][0] or current[0][1] <= lock['generation']
                or current[0][2] <= lock['frame_us'] or not 0 < current[0][3]-previous[0][3] <= .5
                or crossing.get('status') == 'crossing_projection_unavailable'
                or crossing.get('brake', 0.) > 0.
                or (body_prediction or {}).get('brake', 0.) > 0.):
            return None
        witnesses = []
        for target in lock['targets']:
            aid = target['id']; old, actor = previous[1].get(aid), current[1].get(aid)
            if (not old or not actor or old['source'] != actor['source']
                    or old['slot'] != actor['slot'] or actor.get('temporary')
                    or old['record_fingerprint'] == actor['record_fingerprint']
                    or len(old['bodies']) != len(actor['bodies'])):
                return None
            dt=current[0][3]-previous[0][3]
            displacement=math.hypot(actor['x']-old['x'],actor['z']-old['z'])
            if displacement > max(old['speed'],actor['speed'])*dt+1.:
                return None  # discontinuity/reassigned native short is not clearance
            distances = []
            for old_body, body in zip(old['bodies'], actor['bodies']):
                dims = body.get('dimensions_whl') or ()
                if len(dims) != 3 or not all(math.isfinite(v) and v > 0 for v in dims):
                    return None
                low, high = max(0., progress-20.), min(self.arcs[-1], progress+HORIZON_M)
                old_distance = self._body_clearance(old_body, low, high)
                distance = self._body_clearance(body, low, high)
                if (old_distance is None or distance is None or distance <= PROTECTIVE_REFERENCE_GATE_M
                        or distance <= old_distance):
                    return None
                distances.append(distance)
            witnesses.append(dict(id=aid, record=actor['record_fingerprint'],
                previous_record=old['record_fingerprint'], minimum_reference_clearance_m=min(distances)))
        return dict(kind='traffic', authority=lock['authority'], lifecycle=current[0][0],
            generation=current[0][1], frame_us=current[0][2], observed_at=current[0][3],
            targets=witnesses, status='observed_original_bodies_receding',
            stop_lock=dict(lock),
            coverage_confirmed=False, game_consumption_verified=False)

    def prepare(self, points, binding, *, preserve_target=False):
        if binding == self.binding:
            return
        previous = (self.target_id, self._last_target_observation) if preserve_target else None
        self.binding = None
        self.reset()
        if not 2 <= len(points) <= 20000:
            raise ValueError('unsupported ACC route size')
        pts = tuple(tuple(float(v) for v in p) for p in points)
        if any(len(p) != 3 or not all(math.isfinite(v) for v in p) for p in pts):
            raise ValueError('ACC requires original finite XYZ route')
        arcs, edges = [0.], []
        for a, b in zip(pts, pts[1:]):
            length = math.hypot(b[0]-a[0], b[2]-a[2])
            if length <= 1e-6:
                raise ValueError('degenerate ACC route edge')
            edges.append((*a, b[0]-a[0], b[1]-a[1], b[2]-a[2], length,
                          1./length, 1./(length*length), arcs[-1]))
            arcs.append(arcs[-1]+length)
        self.points, self.arcs, self.edges, self.binding = pts, tuple(arcs), tuple(edges), binding
        if previous:
            self.target_id, self._last_target_observation = previous

    def _body_clearance(self, body, low, high):
        """Exact native oriented-box/reference distance, not physical lane clearance."""
        x,y,z,yaw=(float(body[k]) for k in ('x','y','z','yaw'))
        width,height,length=body['dimensions_whl']
        extent=.5*math.hypot(width,length)
        first=max(0,bisect.bisect_right(self.arcs,max(0.,low-extent))-1)
        last=min(len(self.edges),bisect.bisect_left(self.arcs,high+extent)+1)
        if last-first>512: return None
        fw=(-math.sin(yaw),-math.cos(yaw));side=(math.cos(yaw),-math.sin(yaw))
        half=(width*.5,length*.5);best=math.inf
        for ax,ay,az,dx,dy,dz,_,_,_,_ in self.edges[first:last]:
            if not min(ay,ay+dy)-HEIGHT_GATE_M<=y<=max(ay,ay+dy)+HEIGHT_GATE_M:
                continue
            def local(px,pz):
                ox,oz=px-x,pz-z
                return ox*side[0]+oz*side[1],ox*fw[0]+oz*fw[1]
            a=local(ax,az);b=local(ax+dx,az+dz)
            delta=(b[0]-a[0],b[1]-a[1]);lo,hi=0.,1.
            for i in (0,1):
                if abs(delta[i])<1e-12:
                    if abs(a[i])>half[i]: lo,hi=1.,0.;break
                else:
                    u,v=sorted(((-half[i]-a[i])/delta[i],(half[i]-a[i])/delta[i]))
                    lo,hi=max(lo,u),min(hi,v)
            if lo<=hi: return 0.
            for p in (a,b):
                best=min(best,math.hypot(max(0.,abs(p[0])-half[0]),max(0.,abs(p[1])-half[1])))
            norm=delta[0]**2+delta[1]**2
            for cx in (-half[0],half[0]):
                for cz in (-half[1],half[1]):
                    t=max(0.,min(1.,((cx-a[0])*delta[0]+(cz-a[1])*delta[1])/norm))
                    best=min(best,math.hypot(cx-a[0]-t*delta[0],cz-a[1]-t*delta[1]))
        return best if math.isfinite(best) else None

    def _project(self, actor, low, high, *, aligned=True):
        x, y, z, yaw = (float(actor[k]) for k in ('x', 'y', 'z', 'yaw'))
        if not all(math.isfinite(v) for v in (x, y, z, yaw)):
            return None
        first = max(0, bisect.bisect_right(self.arcs, low)-1)
        last = min(len(self.points)-1, bisect.bisect_left(self.arcs, high)+1)
        if last-first > 512:
            return None  # bounded work; never silently simplify dense geometry
        projections = []
        forward_x, forward_z = -math.sin(yaw), -math.cos(yaw)
        minimum_alignment = math.cos(math.radians(45.))
        for i in range(first, last):
            ax, ay, az, dx, dy, dz, length, inverse, inverse2, start = self.edges[i]
            alignment = (forward_x*dx+forward_z*dz)*inverse
            if aligned and alignment < minimum_alignment:
                continue
            offset_x, offset_z = x-ax, z-az
            raw_t = (offset_x*dx+offset_z*dz)*inverse2
            if raw_t*length < -.5 or (raw_t-1.)*length > .5:
                continue  # cannot clip a behind/end-of-horizon actor onto us
            t = max(0., min(1., raw_t))
            distance = math.hypot(offset_x-t*dx, offset_z-t*dz)
            height = abs(y-ay-t*dy)
            progress = start+t*length
            if height <= HEIGHT_GATE_M and low <= progress <= high:
                projections.append((distance, progress, height))
        if not projections:
            return None
        projections.sort()
        best = projections[0]
        if any(abs(p[1]-best[1]) > 8. and p[0] <= best[0]+.2 for p in projections[1:]):
            return None  # repeated loop/crossing occurrence cannot be resolved
        return best

    def _departure(self, actors, ego, receiver_time):
        previous = self._last_target_observation
        if previous is None or receiver_time is None:
            return None
        old, at = previous
        if not 0 < receiver_time-at <= .5:
            return None
        old_projection=self._project(old,max(0.,ego[1]-20.),ego[1]+HORIZON_M)
        if old_projection is None or old_projection[0]>PROTECTIVE_REFERENCE_GATE_M:
            return None  # retained receiver history must still relate to this route
        actor = next((a for a in actors if a['id'] == old['id']), None)
        if (actor is None or actor.get('source') != old.get('source')
                or actor.get('slot') != old.get('slot')
                or not actor.get('record_fingerprint')
                or actor['record_fingerprint'] == old.get('record_fingerprint')):
            return None  # absent/unchanged/reassigned records are not departure
        speed = actor.get('speed')
        if not isinstance(speed, (int, float)) or not math.isfinite(speed) or not 0 <= speed <= 70.:
            return None  # the same kinematics contract as ordinary candidates
        cached = self._departure_observation
        if cached and cached['record'] == actor['record_fingerprint']:
            # Re-reading this changed record cannot renew its first witnessed
            # receiver time. There is still no native producer timestamp.
            return cached if 0 <= receiver_time-cached['receiver_time'] <= .5 else None
        clearances = []
        for body in actor.get('bodies', ()):
            dims = body.get('dimensions_whl') or ()
            if len(dims) != 3 or not all(math.isfinite(v) and v > 0 for v in dims):
                return None
            projected = self._project(body, max(0., ego[1]-20.), ego[1]+HORIZON_M, aligned=False)
            if projected is None:
                return None  # outside observed route range / ambiguous occurrence
            clearance=self._body_clearance(body,max(0.,ego[1]-20.),ego[1]+HORIZON_M)
            if clearance is None: return None
            clearances.append(clearance)
        if not clearances or min(clearances) <= PROTECTIVE_REFERENCE_GATE_M:
            return None
        proof = dict(schema_version=1, target_id=str(old['id']),
            status='observed_body_outside_route', confirmed=False,
            observation_kind='changed_receiver_record_not_producer_timestamp',
            previous_receiver_time=at, receiver_time=receiver_time,
            previous_record=old['record_fingerprint'], record=actor['record_fingerprint'],
            previous_position_xyz=[old[k] for k in ('x','y','z')],
            position_xyz=[actor[k] for k in ('x','y','z')],
            minimum_body_reference_clearance_m=min(clearances),
            source=actor['source'], slot=actor['slot'], coverage_confirmed=False)
        self._departure_observation = proof
        return proof

    def select(self, actors, truck, progress, *, receiver_time=None, source=None):
        if not math.isfinite(progress) or not 0 <= progress <= self.arcs[-1]:
            return dict(status='invalid_route_progress', confirmed=False)
        if len(actors) > 80:
            return dict(status='unsupported_actor_count', confirmed=False)
        ego = self._project(dict(truck, yaw=truck['rotation']), max(0., progress-20.), progress+20.)
        if ego is None or ego[0] > LATERAL_GATE_M:
            return dict(status='route_localization_unavailable', confirmed=False)
        candidates = []
        protective = []
        identity = actor_identity(actors)
        if identity['missing_count'] or identity['duplicate_count']:
            return dict(status='ambiguous_actor_id', confirmed=False, actor_identity=identity)
        departure = self._departure(actors, ego, receiver_time)
        for actor in actors:
            try:
                speed = float(actor['speed'])
                if not math.isfinite(speed) or not 0 <= speed <= 70.:
                    continue
                projected = self._project(actor, max(0., ego[1]-5.), ego[1]+HORIZON_M)
                if projected is None or projected[0] > PROTECTIVE_REFERENCE_GATE_M:
                    continue
                gap = projected[1]-ego[1]
                if gap < 0.:
                    continue
                if projected[0] <= LATERAL_GATE_M:
                    candidates.append((gap, str(actor['id']), speed))
                else:
                    protective.append((gap,str(actor['id']),speed))
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
        caution = [following_demand(c[0],c[2],float(truck['speed']),include_brake=True) for c in protective]
        caution_brake = max((c['protective_brake'] for c in caution),default=0.)
        # A moving speed constraint is not itself a full-stop obligation.
        # This remains protective reference relevance, not lane/road clearance.
        moving_scope = None
        related = candidates+protective
        if source and source.get('valid') is True and 0 < len(related) <= 16:
            targets = []
            for gap, aid, speed in related:
                actor = next(a for a in actors if str(a['id']) == aid)
                cap = following_demand(gap, speed, float(truck['speed']))['speed_cap_mps']
                if (actor.get('source') != 'moving' or actor.get('temporary')
                        or actor.get('speed_source') != 'buffer' or speed <= .1 or cap <= 1.):
                    break
                targets.append(dict(id=aid, speed_mps=speed, cap_mps=cap,
                                    source=actor['source'], slot=actor['slot']))
            if len(targets) == len(related):
                moving_scope = dict(schema=1, kind='observed_positive_motion_speed_constraint',
                    targets=sorted(targets,key=lambda t:t['id']), complete=True,
                    source_acquisition={k:source[k] for k in ('lifecycle','generation','frame_us','observed_at')},
                    coverage_confirmed=False)
        caution_fields = dict(unassigned_protective_brake=caution_brake,
            protective_target_id=min(protective)[1] if protective else None,
            departure=departure, motion_constraint=moving_scope)
        if not candidates:
            if moving_scope and protective:
                # Keep the existing departure witness for the controlling
                # protective constraint too. This never certifies a lane.
                selected=min(protective)
                retained=next((c for c in protective if c[1]==self.target_id),None)
                if retained and retained[0]<=selected[0]+RETENTION_M:selected=retained
                self.target_id=selected[1]
                actor=next(a for a in actors if str(a['id'])==selected[1])
                self._last_target_observation=(dict(actor),receiver_time)
            return dict(status='no_candidate_unproven_coverage', confirmed=False,
                protective_brake=caution_brake, emergency=any(c['emergency'] for c in caution),**caution_fields)
        candidates.sort()
        nearest = candidates[0]
        retained = next((c for c in candidates if c[1] == self.target_id), None)
        selected = retained if retained and retained[0] <= nearest[0]+RETENTION_M else nearest
        # Retention changes attribution only: all relevant candidates always cap
        # speed and emergency response, so a closer cut-in is never hidden.
        self.target_id = selected[1]
        if receiver_time is not None:
            actor = next(a for a in actors if str(a['id']) == selected[1])
            self._last_target_observation = (dict(actor), receiver_time)
            self._departure_observation = None
        predictions = self.source_motion(actors, source)
        constraints = [following_demand(c[0], c[2], float(truck['speed']),include_brake=True) for c in candidates]
        # Negative anticipation only, over the existing 500 ms evidence horizon.
        # It can lower a cap but cannot relax TTC/AEB or certify lane membership.
        for candidate, demand in zip(candidates, constraints):
            motion = predictions.get(candidate[1])
            if motion:
                predicted = max(0., candidate[2]+max(-2., min(0., motion['acceleration_mps2']))*.5)
                demand['speed_cap_mps'] = min(demand['speed_cap_mps'],
                    following_demand(candidate[0], predicted, float(truck['speed']))['speed_cap_mps'])
        return dict(status='candidate', target_id=selected[1], gap_m=selected[0],
                    speed_mps=selected[2], confirmed=False,
                    gap_kind='route_reference_points',
                    leader_prediction=predictions.get(selected[1]),
                    speed_cap_mps=min(c['speed_cap_mps'] for c in constraints),
                    emergency=any(c['emergency'] for c in constraints+caution),
                    protective_brake=max([c['protective_brake'] for c in constraints]+[caution_brake]),
                    **caution_fields,
                    reason='projected receiver observation; publisher freshness and lane membership unproven')

    def crossing(self, actors, truck, progress):
        """All observed crossing candidates on the directed local reference.

        Constant actor velocity and 0..2 m/s² nominal ego acceleration define
        a protective arrival window, NOT a measured acceleration bound or a
        certified gap. The 2 s reserve is the existing ACC headway. No result,
        including an empty buffer, can authorize entry or release a stop.
        """
        result = dict(status='no_conflict_unproven_coverage', conflicts=[], brake=0.,
            clearance_confirmed=False, producer_timestamp=None,
            coverage_confirmed=False, confirmed_route_conflict=False)
        try:
            speed = float(truck['speed'])
            if (not self.arcs or not math.isfinite(progress) or not 0 <= progress <= self.arcs[-1]
                    or not math.isfinite(speed) or speed < 0 or len(actors) > 80):
                raise ValueError('invalid route kinematics')
            ego = self._project(dict(truck, yaw=truck['rotation']), max(0.,progress-20.), progress+20.)
            if ego is None or ego[0] > LATERAL_GATE_M:
                raise ValueError('invalid ego projection')
            first = max(0, bisect.bisect_right(self.arcs, ego[1])-1)
            last = min(len(self.edges), bisect.bisect_left(self.arcs, ego[1]+HORIZON_M)+1)
            if last-first > 512:
                raise ValueError('unsupported edge count')
            identity = actor_identity(actors)
            if identity['missing_count'] or identity['duplicate_count']:
                raise ValueError('ambiguous actor identity')
            for original in actors:
                for body_index, body in enumerate(original.get('bodies') or [original]):
                    actor = dict(original, **body)
                    x,y,z,yaw,v = (float(actor[k]) for k in ('x','y','z','yaw','speed'))
                    if not all(math.isfinite(n) for n in (x,y,z,yaw,v)) or not 0 <= v <= 70.:
                        raise ValueError('invalid actor kinematics')
                    if v <= .1:
                        continue  # standing actors remain the lead/obstacle path
                    lead = self._project(actor,max(0.,ego[1]-5.),ego[1]+HORIZON_M)
                    if lead is not None and lead[0] <= LATERAL_GATE_M:
                        continue  # directed same-lane lead already uses ACC
                    vx,vz = -math.sin(yaw)*v, -math.cos(yaw)*v
                    candidates = []
                    for i in range(first,last):
                        ax,ay,az,dx,dy,dz,length,inv,_,start = self.edges[i]
                        den = vx*dz-vz*dx
                        if abs(den)*inv/v < math.sin(math.radians(20.)):
                            continue  # parallel/oncoming reference is not crossing
                        ox,oz = ax-x,az-z
                        t = (ox*dz-oz*dx)/den
                        u = (ox*vz-oz*vx)/den
                        distance = start+u*length-ego[1]
                        if not (0 <= t <= 8. and 0 <= u <= 1. and 0 <= distance <= HORIZON_M
                                and abs(y-ay-u*dy) <= HEIGHT_GATE_M):
                            continue
                        earliest = (math.sqrt(speed*speed+4.*distance)-speed)/2.
                        latest = distance/speed if speed > .1 else float('inf')
                        # The immutable buffer dimensions remain explicitly raw;
                        # no cab/trailer outline or bumper distance is invented.
                        dims = actor.get('dimensions_whl')
                        body_time = (float(dims[2])/(2*v) if dims and len(dims)==3
                            and all(math.isfinite(float(n)) and n > 0 for n in dims) else 0.)
                        if earliest > t+HEADWAY_S+body_time or latest < t-HEADWAY_S-body_time:
                            continue
                        urgency = min(t,earliest)
                        brake = 1. if urgency <= 1. else ((5.-min(5.,urgency))/4.)**2
                        candidates.append(dict(id=actor['id'], route_progress_m=start+u*length,
                            distance_m=distance, actor_arrival_s=t, ego_arrival_earliest_s=earliest,
                            ego_arrival_latest_s=latest if math.isfinite(latest) else None,
                            reserve_s=HEADWAY_S, assumed_ego_acceleration_mps2=2.,
                            dimensions_whl=dims, brake=brake))
                    if candidates:
                        conflict = max(candidates,key=lambda c:c['brake'])
                        conflict.update(body_index=body_index,
                            motion_model='constant_tractor_speed_raw_body_heading',
                            ego_body_envelope_confirmed=False)
                        result['conflicts'].append(conflict)
            result['conflicts'].sort(key=lambda c:(c['actor_arrival_s'],str(c['id'])))
            result['brake'] = max((c['brake'] for c in result['conflicts']),default=0.)
            if result['conflicts']:
                result['status'] = 'protective_crossing_candidates'
        except (KeyError, TypeError, ValueError, OverflowError):
            result.update(status='crossing_projection_unavailable',conflicts=[],brake=0.)
        return result


def observed_departure(following, target_id, now):
    """Release only the acquired lead dependency, never certify an empty road.

    Same contract as protective candidates: changed, uniquely decoded receiver
    records. Producer freshness/coverage are still unproven. Parent packet must
    already pass identity, vehicle and original lease checks in read().
    """
    proof = following.get('departure') if isinstance(following, dict) else None
    try:
        return bool(isinstance(proof,dict) and proof.get('schema_version') == 1
            and proof.get('status') == 'observed_body_outside_route'
            and proof.get('target_id') == target_id and target_id
            and proof.get('record') and proof.get('previous_record')
            and proof['record'] != proof['previous_record']
            and 0 < proof['receiver_time']-proof['previous_receiver_time'] <= .5
            and 0 <= now-proof['receiver_time'] <= .5
            and math.isfinite(proof['minimum_body_reference_clearance_m'])
            and proof['minimum_body_reference_clearance_m'] > PROTECTIVE_REFERENCE_GATE_M)
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def following_demand(gap_m, lead_speed_mps, ego_speed_mps, *, include_brake=False):
    """Time-gap speed constraint for the existing PID, not another controller."""
    if not all(math.isfinite(v) and v >= 0 for v in (gap_m, lead_speed_mps, ego_speed_mps)):
        raise ValueError('invalid following kinematics')
    desired = MIN_GAP_M + HEADWAY_S*ego_speed_mps
    closing = max(0., ego_speed_mps-lead_speed_mps)
    cap = max(0., lead_speed_mps + (gap_m-desired)/HEADWAY_S)
    # Preserve Engine's existing emergency boundary (>0.7 legacy TTC demand),
    # now measured along the route rather than the straight cab strip. Ordinary
    # distance braking is replaced by the existing speed PID, not safety floors.
    safety_gap = max(0., gap_m-(6.+.4*ego_speed_mps))
    if closing >= .5:
        ttc = safety_gap/closing
        legacy_demand = 1. if ttc <= 1. else ((5.-ttc)/4.)**2 if ttc < 5. else 0.
    else:
        legacy_demand = max(0., 1.-safety_gap/40.)
    emergency = legacy_demand > .7
    result=dict(speed_cap_mps=cap, desired_gap_m=desired, emergency=emergency)
    if include_brake:result['protective_brake']=legacy_demand
    return result
