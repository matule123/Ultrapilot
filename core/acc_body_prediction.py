"""Protective observed-box AEB, NOT a certified complete swept envelope.

Actual native tractor/trailer boxes are transported in the same timed frame.
Own motion follows the existing directed reference at current speed, with fixed
articulation; actors keep observed speed/heading. These are explicit prediction
assumptions, not measured future motion, coverage or dimensional error bounds.
"""
import bisect
import math

HORIZON_S = 3.
STEP_S = .25


def contact_interval(a, b, va, vb, duration):
    """Exact 2-D swept SAT for fixed oriented boxes, including vertical gate."""
    aw, ah, al = a['dimensions_whl']; bw, bh, bl = b['dimensions_whl']
    if abs(a['y']-b['y']) > (ah+bh)*.5:
        return None
    def axes(body):
        yaw = body['yaw']
        return ((math.cos(yaw), -math.sin(yaw)), (-math.sin(yaw), -math.cos(yaw)))
    aa, ba = axes(a), axes(b)
    def dot(x, y):
        return x[0]*y[0]+x[1]*y[1]
    offset = b['x']-a['x'], b['z']-a['z']
    velocity = vb[0]-va[0], vb[1]-va[1]
    lo, hi = 0., duration
    for axis in (*aa, *ba):
        radius = (.5*aw*abs(dot(aa[0], axis))+.5*al*abs(dot(aa[1], axis))
                  +.5*bw*abs(dot(ba[0], axis))+.5*bl*abs(dot(ba[1], axis)))
        position, rate = dot(offset, axis), dot(velocity, axis)
        if abs(rate) < 1e-12:
            if abs(position) > radius:
                return None
        else:
            enter, leave = sorted(((-radius-position)/rate, (radius-position)/rate))
            lo, hi = max(lo, enter), min(hi, leave)
            if lo > hi:
                return None
    return lo


def predict(route, ego_bodies, actors, speed, progress, anchor, *, source_age=0., debug_geometry=None):
    result = dict(status='unavailable_ego_body_or_prediction', brake=0., conflicts=[],
        complete_envelope_verified=False, coverage_confirmed=False,
        model='native_boxes_directed_reference_fixed_articulation_constant_actor_motion')
    if (not ego_bodies or not 1 <= len(ego_bodies) <= 4 or not 0 <= speed <= 70. or len(actors) > 80
            or not math.isfinite(source_age) or not 0 <= source_age <= .5):
        return result
    root = ego_bodies[0]
    projected = route._project(dict(root,x=anchor[0],y=anchor[1],z=anchor[2]),
        max(0., progress-20.), progress+20., aligned=False)
    if projected is None or projected[0] > 2.6 or not route.arcs:
        return result
    def pose(s):
        if s > route.arcs[-1]:
            return None  # a rolling horizon end is not extrapolated geometry
        i = max(0, min(len(route.edges)-1, bisect.bisect_right(route.arcs, s)-1))
        x, y, z, dx, dy, dz, length, inv, _, start = route.edges[i]
        f = (s-start)*inv
        return x+f*dx, y+f*dy, z+f*dz, math.atan2(-dx, -dz)
    initial = pose(projected[1])
    samples = []
    for i in range(13):
        at = i*STEP_S
        target = pose(projected[1]+speed*at)
        if target is None:
            break
        # Rotate measured offsets with reference heading. Trailer articulation
        # stays at its actually observed angle; no future hitch dynamics claim.
        angle = target[3]-initial[3]; c, s = math.cos(angle), math.sin(angle)
        bodies = []
        for body in ego_bodies:
            ox, oz = body['x']-anchor[0], body['z']-anchor[2]
            bodies.append(dict(body, x=anchor[0]+target[0]-initial[0]+c*ox+s*oz,
                y=body['y']+target[1]-initial[1],
                z=anchor[2]+target[2]-initial[2]-s*ox+c*oz, yaw=body['yaw']+angle))
        samples.append(bodies)
    if debug_geometry is not None:
        debug_geometry.update(ego_samples=samples, actor_paths=[], omitted_actor_paths=0, horizon_s=HORIZON_S,
            step_s=STEP_S, model=result['model'])
    missing = 0
    for actor in actors:
        parked = (actor.get('source') == 'parked'
                  and actor.get('speed_source') == 'parked_classification')
        if actor.get('temporary') or (actor.get('speed_source') != 'buffer' and not parked):
            missing += 1
            continue  # native TMP speed=0 is a placeholder, never a measurement
        # Native parked records have no speed measurement. Their existing
        # classification permits a protective stationary obstacle model only;
        # it cannot authorize clearance, lead prediction or an empty road.
        v = 0. if parked else actor['speed']
        if not math.isfinite(v) or not 0 <= v <= 70.:
            missing += 1; continue
        contact = None
        contact_basis = 'swept_constant_motion_model'
        for body_index, body in enumerate(actor['bodies']):
            dims = body.get('dimensions_whl') or ()
            if len(dims) != 3 or not all(math.isfinite(n) and n > 0 for n in dims):
                missing += 1; continue
            # Observed overlap must survive a truncated future route horizon.
            # This is the original source frame, never an inferred current pose
            # or proof of game consumption of a brake write.
            if any(contact_interval(e, body, (0., 0.), (0., 0.), 0.) is not None
                   for e in ego_bodies):
                contact = 0.
                contact_basis = 'observed_overlap_at_source_frame'
                break
            # Broad phase from measured extents and the finite prediction range.
            extent = .5*math.hypot(dims[0], dims[2])
            own_extent = max(math.hypot(e['x']-root['x'], e['z']-root['z'])+
                .5*math.hypot(e['dimensions_whl'][0], e['dimensions_whl'][2]) for e in ego_bodies)
            if math.hypot(body['x']-root['x'], body['z']-root['z']) > (speed+v)*HORIZON_S+extent+own_extent:
                continue
            bv = -math.sin(body['yaw'])*v, -math.cos(body['yaw'])*v
            path = None
            if debug_geometry is not None and len(debug_geometry['actor_paths']) < 64:
                path = dict(id=actor['id'], source=actor['source'], slot=actor['slot'],
                    record_fingerprint=actor.get('record_fingerprint'), body_index=body_index, points=[])
                debug_geometry['actor_paths'].append(path)
            elif debug_geometry is not None:
                debug_geometry['omitted_actor_paths'] += 1
            for i, (before, after) in enumerate(zip(samples, samples[1:])):
                at = i*STEP_S
                other = dict(body, x=body['x']+bv[0]*at, z=body['z']+bv[1]*at)
                if path is not None:
                    path['points'].append([at, other['x'], other['y'], other['z']])
                for a, b in zip(before, after):
                    av = (b['x']-a['x'])/STEP_S, (b['z']-a['z'])/STEP_S
                    # Rotation envelope around the segment-start orientation;
                    # contact is conservative for the declared segment model.
                    w,h,length=a['dimensions_whl']
                    turn=abs(math.remainder(b['yaw']-a['yaw'],2*math.pi))
                    margin=math.hypot(w,length)*math.sin(turn*.5)
                    conservative=dict(a,dimensions_whl=(w+2*margin,h,length+2*margin))
                    t = contact_interval(conservative, other, av, bv, STEP_S)
                    if t is not None:
                        contact = min(contact if contact is not None else math.inf, at+t)
                if contact is not None:
                    break
        if contact is not None:
            current_contact=max(0.,contact-source_age)
            brake = 1. if current_contact <= 1. else ((5.-current_contact)/4.)**2
            result['conflicts'].append(dict(id=actor['id'], predicted_contact_s=current_contact,
                contact_from_source_observation_s=contact, source_age_s=source_age,
                brake=brake, route_progress_m=projected[1]+speed*contact,
                contact_basis=contact_basis,
                actor={k:actor.get(k) for k in ('id','source','slot','record_fingerprint',
                    'x','y','z','yaw','speed','dimensions_whl')},
                ego_bodies=[dict(e) for e in ego_bodies],
                ego_anchor_xyz=list(anchor), ego_observed_speed_mps=speed,
                actor_motion_basis=('native_parked_classification_static_model' if parked
                                    else 'native_observed_speed_constant_heading_model')))
    result.update(status='protective_observed_body_prediction', unsupported_actors=missing,
        prediction_duration_s=max(0.,(len(samples)-1)*STEP_S),
        brake=max((c['brake'] for c in result['conflicts']), default=0.))
    return result
