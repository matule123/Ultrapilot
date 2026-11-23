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


def rear_contact_not_brake_mitigable(body, ego_bodies, samples):
    """Narrow straight, parallel, fully-behind catch-up case, not clearance.

    Braking our vehicle cannot avert a faster follower's rear contact. Keep
    this model warning separate from forward/crossing AEB. Every box and the
    entire available reference prediction must remain aligned within 10 degrees;
    current overlap, turning, a crossing side or uncertain shape never qualify.
    """
    if not samples or len(samples)!=13:return False
    root=ego_bodies[0];fw=(-math.sin(root['yaw']),-math.cos(root['yaw']))
    aligned=math.cos(math.radians(10.))
    def extent(b):
        delta=b['yaw']-root['yaw'];w,_,length=b['dimensions_whl']
        return .5*(abs(math.sin(delta))*w+abs(math.cos(delta))*length)
    def along(b):return (b['x']-root['x'])*fw[0]+(b['z']-root['z'])*fw[1]
    if (math.cos(body['yaw']-root['yaw'])<aligned
            or any(math.cos(b['yaw']-root['yaw'])<aligned for row in samples for b in row)
            or along(body)+extent(body)>=min(along(b)-extent(b) for b in ego_bodies)):
        return False
    return True


def _axes(yaw):
    c,s=math.cos(yaw),math.sin(yaw)
    return ((c,-s),(-s,-c))


def contact_interval(a, b, va, vb, duration, *, axes_a=None, axes_b=None):
    """Exact 2-D swept SAT for fixed oriented boxes, including vertical gate."""
    aw, ah, al = a['dimensions_whl']; bw, bh, bl = b['dimensions_whl']
    if abs(a['y']-b['y']) > (ah+bh)*.5:
        return None
    aa = axes_a if axes_a is not None else _axes(a['yaw'])
    ba = axes_b if axes_b is not None else _axes(b['yaw'])
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


def _outside_segment(position, travel, radius):
    """A whole fixed-orientation interval lies outside the projected radius."""
    end = position + travel
    if not math.isfinite(end) or not math.isfinite(radius):
        return False
    # Leave rounding at a touching or numerically uncertain boundary to SAT.
    margin = 16 * math.ulp(max(abs(position), abs(travel), radius))
    return min(position, end) > radius + margin or max(position, end) < -radius - margin


def predict(route, ego_bodies, actors, speed, progress, anchor, *, source_age=0., debug_geometry=None,
            prefilter=True):
    result = dict(status='unavailable_ego_body_or_prediction', brake=0., conflicts=[],
        complete_envelope_verified=False, coverage_confirmed=False,
        model='native_boxes_directed_reference_fixed_articulation_constant_actor_motion')
    if (not ego_bodies or not 1 <= len(ego_bodies) <= 4 or not -70. <= speed <= 70. or len(actors) > 80
            or not math.isfinite(source_age) or not 0 <= source_age <= .5):
        return result
    root = ego_bodies[0]
    projected = route._project(dict(root,x=anchor[0],y=anchor[1],z=anchor[2]),
        max(0., progress-20.), progress+20., aligned=False)
    if projected is None or projected[0] > 2.6 or not route.arcs:
        return result
    def pose(s):
        if s < 0. or s > route.arcs[-1]:
            return None  # a rolling horizon end is not extrapolated geometry
        i = max(0, min(len(route.edges)-1, bisect.bisect_right(route.arcs, s)-1))
        x, y, z, dx, dy, dz, length, inv, _, start = route.edges[i]
        f = (s-start)*inv
        return x+f*dx, y+f*dy, z+f*dz, math.atan2(-dx, -dz)
    initial = pose(projected[1])
    samples = []
    for i in range(13):
        at = i*STEP_S
        # Body availability is independent of forward-drive permission. A
        # signed backward displacement uses the observed heading, not a clamp
        # to zero or invented geometry behind a rolling route's left edge.
        # Engine/ACC still reject R / backward drive at their original gates.
        target = ((initial[0]-math.sin(root['yaw'])*speed*at, initial[1],
                   initial[2]-math.cos(root['yaw'])*speed*at, initial[3])
                  if speed < 0. else pose(projected[1]+speed*at))
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
    rear_contacts=[]
    own_extent = max(math.hypot(e['x']-root['x'], e['z']-root['z'])+
        .5*math.hypot(e['dimensions_whl'][0], e['dimensions_whl'][2]) for e in ego_bodies)
    observed_ego = [(body, .5 * (body['dimensions_whl'][0] + body['dimensions_whl'][2]))
                    for body in ego_bodies]
    # Identical ego enclosure for every actor/hypothesis: prepare it once,
    # retaining all measured boxes and the original swept-contact model.
    ego_segments=[]
    for before,after in zip(samples,samples[1:]):
        segment=[]
        for a,b in zip(before,after):
            av=(b['x']-a['x'])/STEP_S,(b['z']-a['z'])/STEP_S
            w,h,length=a['dimensions_whl']
            turn=abs(math.remainder(b['yaw']-a['yaw'],2*math.pi))
            margin=math.hypot(w,length)*math.sin(turn*.5)
            conservative=dict(a,dimensions_whl=(w+2*margin,h,length+2*margin))
            segment.append((conservative,av,math.hypot(w+2*margin,length+2*margin),_axes(a['yaw'])))
        ego_segments.append(segment)
    for actor in actors:
        motion=route.actor_motion(actor) if hasattr(route,'actor_motion') else None
        prepared = None
        if motion:
            result['model']='native_boxes_directed_reference_fixed_articulation_actor_hypotheses'
            if debug_geometry is not None:debug_geometry['model']=result['model']
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
        rear_only = True
        contact_basis = 'swept_constant_motion_model'
        for body_index, body in enumerate(actor['bodies']):
            dims = body.get('dimensions_whl') or ()
            if len(dims) != 3 or not all(math.isfinite(n) and n > 0 for n in dims):
                rear_only = False  # incomplete actor shape cannot qualify
                missing += 1; continue
            # Observed overlap must survive a truncated future route horizon.
            # This is the original source frame, never an inferred current pose
            # or proof of game consumption of a brake write.
            observed_extent = .5 * (dims[0] + dims[2])
            if any((not prefilter or (not _outside_segment(body['x'] - e['x'], 0., own + observed_extent)
                                      and not _outside_segment(body['z'] - e['z'], 0., own + observed_extent)))
                   and contact_interval(e, body, (0., 0.), (0., 0.), 0.) is not None
                   for e, own in observed_ego):
                contact = 0.
                contact_basis = 'observed_overlap_at_source_frame'
                break
            # Broad phase from measured extents and the finite prediction range.
            extent = .5*math.hypot(dims[0], dims[2])
            if math.hypot(body['x']-root['x'], body['z']-root['z']) > (abs(speed)+v)*HORIZON_S+extent+own_extent:
                continue
            if motion and prepared is None and hasattr(route, 'actor_body_motion'):
                prepared = route.actor_body_motion(actor, motion)
            hypotheses=motion['branches'] if motion else [None]
            rear_only = rear_only and motion is None and rear_contact_not_brake_mitigable(body,ego_bodies,samples)
            # Directed exits share an exact already-generated prefix. Its
            # contact with the SAME ego segment/body is independent of which
            # future branch follows it. Reuse only exact pose keys, local to
            # this observed body and this invocation (<=8 * 12 entries).
            segment_contacts={}
            for hypothesis_index,branch in enumerate(hypotheses):
                if branch is not None:
                    if prepared is not None:
                        positions = prepared[body_index,hypothesis_index,:len(samples)].tolist()
                    else:
                        from core.actor_motion import body_poses
                        poses=body_poses(actor,body,branch,count=len(samples))
                        positions = [(p['x'],p['y'],p['z'],p['yaw']) for p in poses]
                else:
                    bv=-math.sin(body['yaw'])*v,-math.cos(body['yaw'])*v
                    positions=[(body['x']+bv[0]*i*STEP_S,body['y'],body['z']+bv[1]*i*STEP_S,body['yaw'])
                        for i in range(len(samples))]
                path = None
                if debug_geometry is not None and len(debug_geometry['actor_paths']) < 64:
                    path = dict(id=actor['id'], source=actor['source'], slot=actor['slot'],
                        record_fingerprint=actor.get('record_fingerprint'), body_index=body_index,
                        hypothesis_index=hypothesis_index,model=motion['model'] if motion else 'constant_observed_heading',
                        branch_count=len(hypotheses),exit_intent_verified=False,
                        points=[[i*STEP_S,x,y,z] for i,(x,y,z,_) in enumerate(positions)])
                    debug_geometry['actor_paths'].append(path)
                elif debug_geometry is not None:debug_geometry['omitted_actor_paths'] += 1
                bw,bh,bl = dims
                diagonal = math.hypot(bw,bl)
                for i, (before, after) in enumerate(zip(positions,positions[1:])):
                    at = i*STEP_S
                    x,y,z,heading = before
                    next_x,next_y,next_z,next_heading = after
                    key=(i,x,y,z,heading,next_x,next_y,next_z,next_heading)
                    if key in segment_contacts:
                        prior=segment_contacts[key]
                        if prior is not None:contact=min(contact if contact is not None else math.inf,prior)
                        if contact is not None and contact<=at+STEP_S:break
                        continue
                    bv=(next_x-x)/STEP_S,(next_z-z)/STEP_S
                    actor_turn=abs(math.remainder(next_heading-heading,2*math.pi))
                    actor_margin=diagonal*math.sin(actor_turn*.5)
                    ow,ol = bw+2*actor_margin,bl+2*actor_margin
                    other_diagonal = math.hypot(ow,ol)
                    segment_contact=None
                    other = None
                    for conservative,av,own_diagonal,axes in ego_segments[i]:
                        # Circumscribed swept discs can only reject a pair
                        # whose exact oriented boxes cannot meet this segment.
                        radius=.5*(own_diagonal+other_diagonal)
                        if (abs(x-conservative['x'])>radius+abs(bv[0]-av[0])*STEP_S
                                or abs(z-conservative['z'])>radius+abs(bv[1]-av[1])*STEP_S):continue
                        if prefilter and (_outside_segment(x-conservative['x'], (bv[0]-av[0])*STEP_S, radius)
                                          or _outside_segment(z-conservative['z'], (bv[1]-av[1])*STEP_S, radius)):
                            continue
                        if other is None:
                            other = dict(x=x,y=y,z=z,yaw=heading,dimensions_whl=(ow,bh,ol))
                            other_axes = _axes(heading)
                        t = contact_interval(conservative, other, av, bv, STEP_S,
                            axes_a=axes, axes_b=other_axes)
                        if t is not None:
                            segment_contact=min(segment_contact if segment_contact is not None else math.inf,at+t)
                    segment_contacts[key]=segment_contact
                    if segment_contact is not None:
                        contact=min(contact if contact is not None else math.inf,segment_contact)
                    if contact is not None and contact<=at+STEP_S:break
        if contact is not None:
            if contact>0. and rear_only:
                if len(rear_contacts)<16:
                    rear_contacts.append(dict(id=actor['id'],record=actor.get('record_fingerprint'),
                        reason='parallel_fully_behind_contact_not_mitigated_by_ego_braking',
                        contact_from_source_observation_s=contact))
                continue
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
                ego_motion_basis=('observed_signed_reverse_heading' if speed<0. else 'directed_route_forward'),
                actor_motion_basis=('native_parked_classification_static_model' if parked
                                    else motion['model'] if motion else 'native_observed_speed_constant_heading_model'),
                actor_motion_hypotheses=motion['branch_count'] if motion else 1,
                exit_intent_verified=False))
    result.update(status='protective_observed_body_prediction', unsupported_actors=missing,
        non_braking_rear_contacts=rear_contacts,
        prediction_duration_s=max(0.,(len(samples)-1)*STEP_S),
        brake=max((c['brake'] for c in result['conflicts']), default=0.))
    return result
