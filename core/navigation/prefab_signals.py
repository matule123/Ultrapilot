"""Prepare directed PPD control entries once during LanePath construction.

Independent implementation. Authored semaphore ID is local to a placed prefab;
live attachment still needs spatial/directional checks. Navigation curves are
not painted stop lines. No game input or lateral geometry is changed here.
"""
import math
import hashlib
from core.acc_following import RouteLeadSelector

FRONT_ALLOWANCE_M = 6.0  # planning assumption, NOT an SDK-measured body extent
JUNCTION_STANDOFF_M = 2.0
MAX_PASSAGES = 128


def prepare_signal_passages(network, path):
    result = dict(schema_version=1, status='prepared', passages=[], blockers=[])
    if not path.valid or len(path.points) < 2:
        return dict(result, status='unavailable', blockers=['invalid LanePath'])
    route = RouteLeadSelector()
    try:
        route.prepare([[p.x,p.y,p.z] for p in path.points], 'preparation')
    except ValueError as error:
        return dict(result, status='unavailable', blockers=[str(error)])
    for segment_index, segment in enumerate(path.segments):
        token = segment.lane_id.prefab_token
        if token in (None, 'graph'):
            continue
        indices = tuple(segment.connector_curve_indices or segment.lane_id.connector_path)
        data = getattr(network,'_prefab_lane_data',{}).get(token) or {}
        if '/tollgate/' in str(data.get('path','')).replace('\\','/').lower():
            # This task binds intersection lights. The dedicated tollgate
            # namespace also uses semaphoreId for barriers (SDK kind 2), whose
            # release/payment contract remains owned by the existing toll flow.
            # Any actual light keeps the explicitly unconfirmed geometric path.
            result['blockers'].append('dedicated tollgate delegated to existing toll flow');continue
        curves = data.get('curves') or ()
        owned = [i for i,p in enumerate(path.points) if p.segment_index == segment_index]
        if not owned:
            result['blockers'].append('prefab has no owned control points'); continue
        low, high = route.arcs[max(0,owned[0]-1)], route.arcs[owned[-1]]
        pair = tuple(sorted((segment.start_uid,segment.end_uid)))
        instances = {tuple(item) for item in network._prefab_pairs.get(pair,())
                     if item[0] == token and min(item[1]) == segment.lane_id.road_uid}
        if len(instances) != 1 or not network._curve_chain_is_valid(data, indices):
            result['blockers'].append('unproven prefab instance or directed curve chain'); continue
        instance = next(iter(instances))
        missing = any(curves[i].get('semaphore_id') is None for i in indices)
        if missing:
            result['blockers'].append('authored semaphore metadata unavailable')
            if token not in network._prefab_desc:
                continue  # No descriptor transform; never invent its entrance.
        controlled = [(i,curves[i]['semaphore_id']) for i in indices
                      if curves[i].get('semaphore_id') is not None and curves[i]['semaphore_id'] >= 0]
        if missing:
            controlled.insert(0,(indices[0],None))  # known entry, NO observed signal ID/colour
        if not controlled:
            continue
        # The same transform/elevation code as steering, never a new yaw formula.
        # Use the already transformed selected path plus placed descriptor
        # nodes as a scope gate, not a physical prefab boundary. Sampling all
        # sibling curves here would evict steering's bounded geometry cache.
        all_points = list(segment.centerline)
        from core.navigation.lane_model import LanePoint
        all_points.extend(LanePoint(network.nodes[uid][0],network.node_alt[uid],network.nodes[uid][1])
            for uid in instance[1] if uid in network.nodes and uid in network.node_alt)
        if not all_points:
            result['blockers'].append('placed prefab geometry unavailable'); continue
        bounds = [min(getattr(p,k) for p in all_points) for k in ('x','y','z')]
        bounds += [max(getattr(p,k) for p in all_points) for k in ('x','y','z')]
        seen = set()
        try:
            entry_curve=network._prefab_curve_chain_3d(instance,(indices[0],))
        except (KeyError,IndexError,TypeError,ValueError):
            result['blockers'].append('directed passage entrance unavailable');continue
        if len(entry_curve)<2:
            result['blockers'].append('directed passage entrance unavailable');continue
        for index, semaphore_id in controlled:
            if semaphore_id in seen:
                continue  # same control group over consecutive pieces of this passage
            seen.add(semaphore_id)
            # A control ID on an inner curve still regulates this selected
            # passage: stop before its directed entrance, never inside it.
            start = entry_curve[0]  # authored direction, never the nearer endpoint
            projected = route._project(dict(x=start.x,y=start.y,z=start.z,yaw=start.heading),low,high)
            if projected is None or projected[0] > .5:
                result['blockers'].append('directed control entry absent from current LanePath'); continue
            identity = [token,list(instance[1]),list(indices),index,semaphore_id]
            result['passages'].append(dict(passage_key=hashlib.sha256(repr(identity).encode()).hexdigest(), semaphore_id=semaphore_id,
                prefab_token=token, instance_node_uids=list(instance[1]), curve_indices=list(indices),
                controlled_curve_index=index, entry_xyz=[start.x,start.y,start.z],
                entry_heading_rad=start.heading, entry_progress_m=projected[1], bounds_xyz=bounds,
                stop_target_kind='derived_directed_curve_entry',stop_line_verified=False,
                front_allowance_m=FRONT_ALLOWANCE_M,junction_standoff_m=JUNCTION_STANDOFF_M,
                front_geometry_status='conservative_unmeasured_allowance'))
            if len(result['passages']) > MAX_PASSAGES:
                return dict(result,status='unavailable',passages=[],blockers=['passage capacity exceeded'])
    result['passages'].sort(key=lambda p:(p['entry_progress_m'],p['passage_key']))
    if result['blockers']:
        result['status']='partial'
    return result
