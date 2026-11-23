"""Bounded directed-prefab motion hypotheses, never measured future intent.

Authored lane curves constrain the declared model, not physical road edges.
Every compatible branch remains a hypothesis. Unknown map/branch coverage uses
the existing straight model and can never certify clearance.
"""
import bisect
from itertools import chain as iter_chain
import math
import numpy as np

MAX_CURVES=256
MAX_POINTS=4096
MAX_BRANCHES=8
MIN_MATCH_ALIGNMENT = math.cos(math.radians(30.))


def body_poses(actor, body, branch, *, count=None):
    """Measured cab/trailer offsets with explicitly fixed articulation."""
    result=[]
    poses=branch['poses'] if count is None else branch['poses'][:count]
    ox,oz=body['x']-actor['x'],body['z']-actor['z']
    for x,y,z,yaw in poses:
        angle=yaw-actor['yaw'];c,s=math.cos(angle),math.sin(angle)
        result.append(dict(body,x=x+c*ox+s*oz,y=body['y']+y-actor['y'],
            z=z-s*ox+c*oz,yaw=body['yaw']+angle))
    return result


def projected_bodies(actor, bodies, motion, *, horizontal_only=False, horizontal=None):
    """One read-only exact transform shared by crossing, AEB and its HUD.

    The selector can first use only X/Z and later complete Y/yaw in the same
    owned array. The published X/Z view stays read-only throughout. Ownership
    is bounded by the current native acquisition and its existing array limit.
    """
    branches = motion['branches']
    poses = np.asarray([branch['poses'] for branch in branches], dtype=float)
    raw = np.asarray([(b['x'], b['y'], b['z'], b['yaw']) for b in bodies], dtype=float)
    if horizontal is None:
        result = np.empty((len(bodies), *poses.shape), dtype=float)
        x, z = result[..., 0], result[..., 2]
        rotations = np.asarray([branch['rotations'] for branch in branches], dtype=float)
        ox = (raw[:, 0] - actor['x'])[:, None, None]
        oz = (raw[:, 2] - actor['z'])[:, None, None]
        cosine, sine = rotations[..., 0], rotations[..., 1]
        np.multiply(cosine, ox, out=x)
        np.add(poses[..., 0], x, out=x)
        x += sine * oz
        np.multiply(sine, ox, out=z)
        np.subtract(poses[..., 2], z, out=z)
        z += cosine * oz
    else:
        result = horizontal.base
        result.flags.writeable = True
    try:
        if not horizontal_only:
            y, yaw = result[..., 1], result[..., 3]
            np.add(raw[:, None, None, 1], poses[..., 1], out=y)
            y -= actor['y']
            np.add(raw[:, None, None, 3], poses[..., 3] - actor['yaw'], out=yaw)
    finally:
        result.flags.writeable = False
    if horizontal_only:
        return result[..., ::2]
    return result


class CrossingWindows:
    """Finite arrival envelopes shared by identical constraints in one crossing tick."""

    def __init__(self, arcs, ego_progress, speed, headway, bounds=None):
        arrivals = (np.asarray(arcs) - ego_progress) / speed
        self.earliest = arrivals[:-1]
        self.latest = arrivals[1:]
        self.headway = headway
        self.bounds = bounds
        self.cache = {}

    def envelope(self, segments, reserve):
        key = (segments, reserve)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        stop = self.earliest.searchsorted(segments * .25 + self.headway + reserve, side='right')
        start = np.arange(segments, dtype=float)[:, None] * .25
        mask = self.earliest[:stop] <= ((start + .25) + self.headway + reserve)
        mask &= self.latest[:stop] >= (start - self.headway - reserve)
        spatial = None
        if self.bounds is not None and np.isfinite(self.bounds[:stop]).all():
            # The union of eligible route-edge boxes encloses every possible
            # pair in this piece's time window. Empty windows have inverted
            # bounds and cannot reach the more expensive pair matrix.
            spatial = tuple(reduction(np.broadcast_to(self.bounds[:stop, axis], mask.shape), axis=1,
                                      where=mask, initial=initial)
                            for axis, reduction, initial in (
                                (0, np.min, np.inf), (1, np.max, -np.inf),
                                (2, np.min, np.inf), (3, np.max, -np.inf)))
        result = (stop, mask, spatial)
        if len(self.cache) < 16:
            self.cache[key] = result
        return result


def crossing_pairs(actor,bodies,motion,edge_bounds,first,*,prepared=None,edge_values=None,
                   arrival_windows=None):
    """Batch the SAME exact body transform and AABB admission.

    <=4 bodies * 8 branches * 32 segments * 512 route edges. Only admitted
    pairs become Python rows; original scalar intersection/brake rules decide
    them. No actor identity, hypothesis or time horizon is discarded.
    """
    if (not 1<=len(bodies)<=4 or not 1<=len(motion['branches'])<=MAX_BRANCHES
            or any(not 2<=len(b['poses'])<=33 for b in motion['branches'])
            or len(edge_bounds)>512):raise ValueError('unsupported motion batch')
    arrival_mask = spatial = None
    if arrival_windows is not None and edge_values is not None:
        speed = float(actor['speed'])
        if (math.isfinite(speed) and speed > .1
                and all(body.get('speed', actor['speed']) == actor['speed'] for body in bodies)):
            lengths = [body.get('dimensions_whl', actor.get('dimensions_whl')) for body in bodies]
            reserve = max((float(dims[2]) / (2 * speed) if dims and len(dims) == 3
                           and all(math.isfinite(float(n)) and n > 0. for n in dims) else 0.)
                          for dims in lengths)
            # For u in [0, 1], the scalar edge arrival cannot precede its
            # start or exceed its end. Use the same ordered arithmetic as
            # the scalar arrival-window test, including equality at the ends.
            segments = max(len(branch['poses']) - 1 for branch in motion['branches'])
            stop, arrival_mask, spatial = arrival_windows.envelope(segments, reserve)
            edge_bounds, edge_values = edge_bounds[:stop], edge_values[:stop]
    if not len(edge_bounds):return {}
    prepared=projected_bodies(actor,bodies,motion) if prepared is None else prepared
    horizontal_only = prepared.shape[-1] == 2
    x, z = prepared[..., 0], prepared[..., 1 if horizontal_only else 2]
    px=x[:,:,:-1].reshape(-1);pz=z[:,:,:-1].reshape(-1)
    vx=((x[:,:,1:]-x[:,:,:-1])/.25).reshape(-1)
    vz=((z[:,:,1:]-z[:,:,:-1])/.25).reshape(-1)
    # Reconstruct endpoints in the same operation order used by the scalar
    # finite-segment test (rather than silently changing roundoff at a join).
    ex=px+vx*.25;ez=pz+vz*.25
    xmin=np.minimum(px,ex);xmax=np.maximum(px,ex)
    zmin=np.minimum(pz,ez);zmax=np.maximum(pz,ez)
    # A pair admitted by the original four comparisons must overlap BOTH
    # aggregate boxes. Prune only rows/columns which cannot pass those same
    # comparisons; keep original indices, arithmetic and scalar decisions.
    segments = prepared.shape[2] - 1
    if spatial is None:
        route_xmin, route_xmax, route_zmin, route_zmax = (
            edge_bounds[:,0].min(), edge_bounds[:,1].max(), edge_bounds[:,2].min(), edge_bounds[:,3].max())
    else:
        # Piece indices have the same order in each body and hypothesis.
        block_shape = (-1, segments)
        xmin, xmax, zmin, zmax = (value.reshape(block_shape) for value in (xmin, xmax, zmin, zmax))
        route_xmin, route_xmax, route_zmin, route_zmax = spatial
    selected = np.flatnonzero((xmin <= route_xmax) & (xmax >= route_xmin)
                              & (zmin <= route_zmax) & (zmax >= route_zmin))
    if not len(selected):return {}
    xmin, xmax, zmin, zmax = (value.ravel() for value in (xmin, xmax, zmin, zmax))
    columns=np.flatnonzero((edge_bounds[:,0]<=xmax[selected].max()) &
        (edge_bounds[:,1]>=xmin[selected].min()) &
        (edge_bounds[:,2]<=zmax[selected].max()) &
        (edge_bounds[:,3]>=zmin[selected].min()))
    if not len(columns):return {}
    bounds=edge_bounds[columns]
    mask=xmin[selected,None]<=bounds[:,1]
    mask&=xmax[selected,None]>=bounds[:,0]
    mask&=zmin[selected,None]<=bounds[:,3]
    mask&=zmax[selected,None]>=bounds[:,2]
    if arrival_mask is not None:
        mask &= arrival_mask[(selected % segments)[:, None], columns]
    local_rows,local_columns=np.nonzero(mask)
    rows, cols = selected[local_rows], columns[local_columns]
    if edge_values is not None and len(rows) and all(
            b.get('speed',actor['speed'])==actor['speed'] for b in bodies):
        # The scalar path below still computes the contact and arrival
        # windows. Cull exact parallel and nonintersecting candidate pairs
        # before allocating their Python records.
        edges = edge_values[cols]
        rx, rz = vx[rows], vz[rows]
        den = rx*edges[:,5]-rz*edges[:,3]
        admitted = np.abs(den)*edges[:,7] >= math.sin(math.radians(20.))*max(actor['speed'],1e-6)
        ox, oz = edges[:,0]-px[rows], edges[:,2]-pz[rows]
        time = np.divide(ox*edges[:,5]-oz*edges[:,3],den,out=np.zeros_like(den),where=admitted)
        along = np.divide(ox*rz-oz*rx,den,out=np.zeros_like(den),where=admitted)
        admitted &= (time>=0.) & (time<=.25) & (along>=0.) & (along<=1.)
        rows, cols = rows[admitted], cols[admitted]
    grouped={}
    for row,column in zip(rows.tolist(),cols.tolist()):
        grouped.setdefault(row,[]).append(first+column)
    branches=len(motion['branches']);result={}
    for row,indices in grouped.items():
        body_index,local=divmod(row,branches*segments);branch_index,index=divmod(local,segments)
        if horizontal_only:
            y = bodies[body_index]['y'] + motion['branches'][branch_index]['poses'][index][1] - actor['y']
        else:
            y = prepared[body_index, branch_index, index, 1]
        piece=(index*.25,float(px[row]),float(y),float(pz[row]),
            float(vx[row]),float(vz[row]),.25,branch_index)
        result.setdefault(body_index,[]).append((piece,indices))
    return result


def prepare_prefab_motion(network, path):
    """Once per immutable LanePath, using the existing placed PPD transform."""
    instances={}
    for segment in path.segments:
        token=segment.lane_id.prefab_token
        if token in (None,'graph'):continue
        pair=tuple(sorted((segment.start_uid,segment.end_uid)))
        for instance in network._prefab_pairs.get(pair,()):
            if instance[0]==token:instances[repr(instance)]=instance
    curves=[];points=0
    for instance in instances.values():
        data=network._prefab_lane_data.get(instance[0]) or {}
        authored=data.get('curves') or ()
        prefix=str(len(curves))+':'+str(instance[0])+':'
        if len(curves)+len(authored)>MAX_CURVES:
            return dict(schema=1,status='capacity_unavailable',curves=[])
        for index,curve in enumerate(authored):
            sampled=network._prefab_curve_chain_3d(instance,(index,))
            xyz=[[p.x,p.y,p.z] for p in sampled]
            points+=len(xyz)
            if points>MAX_POINTS:return dict(schema=1,status='capacity_unavailable',curves=[])
            curves.append(dict(id=prefix+str(index),points=xyz,
                next=[prefix+str(i) for i in curve['next_lines'] if 0<=i<len(authored)],
                instance_node_uids=list(instance[1]),prefab_token=instance[0],curve_index=index))
    return dict(schema=1,status='prepared',curves=curves,
        source='authored_directed_ppd_navigation_curves',physical_edges_verified=False,
        route_membership_verified=False)


class ActorMotionGraph:
    def __init__(self,payload):
        self.curves = {}
        self.segments = {}
        self.match_grid = {}
        self.match_fallback = []
        self.joins = {}
        self.tails = {}
        memberships = 0
        if not isinstance(payload,dict) or payload.get('schema')!=1 or payload.get('status')!='prepared':return
        rows=payload.get('curves') or []
        if (not isinstance(rows,list) or len(rows)>MAX_CURVES
                or any(not isinstance(r,dict) or not isinstance(r.get('points'),list) for r in rows)
                or sum(len(r['points']) for r in rows)>MAX_POINTS):return
        try:
            for row in rows:
                if row['id'] in self.curves:raise ValueError('duplicate curve identity')
                points=tuple(tuple(float(v) for v in p) for p in row['points'])
                if len(points)<2:continue
                if any(len(p)!=3 or not all(math.isfinite(v) for v in p) for p in points):raise ValueError()
                arcs=[0.]
                for a,b in zip(points,points[1:]):arcs.append(arcs[-1]+math.dist(a,b))
                if any(b-a<1e-6 for a,b in zip(arcs,arcs[1:])):raise ValueError()
                self.curves[row['id']]=(points,tuple(arcs),tuple(row['next']))
                segments=[]
                for a,b in zip(points,points[1:]):
                    dx,dz=b[0]-a[0],b[2]-a[2]
                    segments.append((a,b,dx,dz,dx*dx+dz*dz,math.atan2(-dx,-dz)))
                    # Index segments rather than whole curves. Any point
                    # within the original 1.2 m match lies in this expanded
                    # box. Long segments still go through the exact test.
                    x0 = math.floor((min(a[0], b[0]) - 1.200001) / 4.)
                    x1 = math.floor((max(a[0], b[0]) + 1.200001) / 4.)
                    z0 = math.floor((min(a[2], b[2]) - 1.200001) / 4.)
                    z1 = math.floor((max(a[2], b[2]) + 1.200001) / 4.)
                    cells=(x1-x0+1)*(z1-z0+1)
                    entry = (row['id'], len(segments)-1)
                    if cells>64 or memberships+cells>65536:
                        self.match_fallback.append(entry)
                        continue
                    memberships+=cells
                    for x in range(x0,x1+1):
                        for z in range(z0,z1+1):self.match_grid.setdefault((x,z),[]).append(entry)
                self.segments[row['id']]=tuple(segments)
            if any(n not in self.curves for _,_,nexts in self.curves.values() for n in nexts):raise ValueError()
            for key,(points,arcs,nexts) in self.curves.items():
                self.joins[key] = all(math.dist(points[-1], self.curves[n][0][0]) <= .10 for n in nexts)
                tail = self.pose(points, arcs, arcs[-1])
                self.tails[key] = (*tail, math.sin(tail[3]), math.cos(tail[3]))
        except (KeyError,TypeError,ValueError,OverflowError):
            self.curves.clear()

    @staticmethod
    def pose(points,arcs,s):
        i=min(len(points)-2,max(0,bisect.bisect_right(arcs,s)-1))
        a,b=points[i:i+2];f=(s-arcs[i])/(arcs[i+1]-arcs[i])
        return (a[0]+f*(b[0]-a[0]),a[1]+f*(b[1]-a[1]),a[2]+f*(b[2]-a[2]),
                math.atan2(-(b[0]-a[0]),-(b[2]-a[2])))

    def hypotheses(self, actor, *, history_valid, horizon=8., step=.25):
        if not history_valid or not self.curves or actor.get('temporary') or actor['speed']<=.1:return None
        ax, ay, az, yaw = (actor[k] for k in ('x','y','z','yaw'))
        cell = math.floor(ax/4.), math.floor(az/4.)
        matches = {}
        for key,i in iter_chain(self.match_grid.get(cell,()), self.match_fallback):
            a,b,dx,dz,length2,heading = self.segments[key][i]
            if length2 < 1e-8:
                continue
            f = max(0., min(1., ((ax-a[0])*dx+(az-a[2])*dz)/length2))
            x,y,z = a[0]+f*dx,a[1]+f*(b[1]-a[1]),a[2]+f*dz
            distance = math.hypot(ax-x, az-z)
            if distance <= 1.2 and abs(ay-y) <= 1.5 and math.cos(yaw-heading) >= MIN_MATCH_ALIGNMENT:
                old = matches.get(key)
                if old is None or (distance,i) < old[:2]:
                    arcs = self.curves[key][1]
                    matches[key] = distance,i,arcs[i]+f*(arcs[i+1]-arcs[i]),(x,y,z,heading)
        seeds = [(key,matches[key][2],matches[key][3]) for key in sorted(matches)]
        if not seeds or len(seeds)>MAX_BRANCHES:return None
        results=[]
        count=int(horizon/step)+1
        if count <= 0:
            return None
        distances = tuple(actor['speed']*step*i for i in range(count))
        # Enumerate all authored branches. Never choose an exit by distance,
        # list order or a later actor pose. Bounded overflow falls back.
        for seed_key, distance, seed in seeds:
            ox, oz = ax - seed[0], az - seed[2]
            turns = {}
            pending = [(seed_key, distance, [], [], [seed_key])]
            while pending:
                key, offset, poses, rotations, chain = pending.pop()
                if len(results) >= MAX_BRANCHES or len(chain) > 65:
                    return None
                _, arcs, nexts = self.curves[key]
                segments = self.segments[key]
                end = arcs[-1]
                tangent = False
                while len(poses) < count:
                    local = offset + distances[len(poses)]
                    if local <= end:
                        i = min(len(segments) - 1, max(0, bisect.bisect_right(arcs, local) - 1))
                        a, b, dx, dz, _, heading = segments[i]
                        f = (local - arcs[i]) / (arcs[i + 1] - arcs[i])
                        x, y, z = a[0] + f * dx, a[1] + f * (b[1] - a[1]), a[2] + f * dz
                    elif nexts:
                        if not self.joins[key] or len(nexts) > MAX_BRANCHES - len(results) - len(pending):
                            return None
                        for nxt in reversed(nexts[1:]):
                            pending.append((nxt, offset - end, poses.copy(), rotations.copy(), chain + [nxt]))
                        pending.append((nexts[0], offset - end, poses, rotations, chain + [nexts[0]]))
                        break
                    else:
                        x, y, z, heading, sine, cosine = self.tails[key]
                        remaining = local - end
                        x, z = x - sine * remaining, z - cosine * remaining
                        tangent = True
                    turn = turns.get(heading)
                    if turn is None:
                        angle = heading - seed[3]
                        predicted = yaw + angle
                        cosine, sine = math.cos(angle), math.sin(angle)
                        turn = turns[heading] = (cosine * ox, sine * oz, sine * ox, cosine * oz, predicted,
                                                (math.cos(predicted - yaw), math.sin(predicted - yaw)))
                    x_first, x_second, z_first, z_second, predicted, rotation = turn
                    poses.append((x + x_first + x_second, ay + y - seed[1], z - z_first + z_second, predicted))
                    rotations.append(rotation)
                else:
                    results.append(dict(poses=poses, curve_chain=chain, terminal_tangent_assumed=tangent,
                                        rotations=rotations))
        return dict(model='directed_prefab_branch_hypotheses_fixed_articulation',
            branches=results,branch_count=len(results),exit_intent_verified=False,
            observed_history_valid=True,step_s=step,horizon_s=horizon)
