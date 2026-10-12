"""Bounded directed-circulation proof for manoeuvre metadata, not geometry.

No steering/curvature classification. A qualifying component is one simple
directed cycle of one-way roads and authored three-port merges/splits, with
multiple external entrances and exits. Ambiguous cycles are not nominated.
"""
import hashlib

MAX_NODES = 256
MAX_EDGES = 768
MAX_PENDING = 1024


def components(network, segments):
    if network is None or not hasattr(network, '_road_pair_index'):
        return (), {}
    pending, seeds = [], set()
    for segment in segments:
        if segment.lane_id.prefab_token in (None, 'graph'):
            continue
        for uid in (segment.start_uid, segment.end_uid):
            if uid not in seeds:
                seeds.add(uid);pending.append(uid)
                if len(seeds) > MAX_NODES:
                    return (), {}
    if not pending:
        return (), {}  # do not build any graph/index for an ordinary-road path
    visited, graph, edges = set(), {}, {}
    roads = network._road_pair_index()
    while pending:
        uid = pending.pop()
        if uid in visited:
            continue
        if len(visited) >= MAX_NODES:
            return (), {}  # no incomplete graph promoted to a cycle proof
        visited.add(uid)
        graph.setdefault(uid, set())
        for other in network.adj.get(uid, ()):
            for index in roads.get(tuple(sorted((uid, other))), ()):
                look = network.road_looks.get(network._seg_look_tokens[index], {})
                left = any(network._drivable_lane_type(t) for t in look.get('lane_types_left', ()))
                right = any(network._drivable_lane_type(t) for t in look.get('lane_types_right', ()))
                if left == right:
                    continue  # bidirectional/unknown roads do not prove circulation
                a, b = network._seg_uids[index]
                if left:
                    a, b = b, a
                graph.setdefault(a, set()).add(b)
                graph.setdefault(b, set())
                edges[a, b] = dict(kind='road', road_uid=network._seg_road_uids[index])
                pending.extend((a, b))
                if len(graph) > MAX_NODES or len(edges) > MAX_EDGES or len(pending) > MAX_PENDING:
                    return (), {}
        position = network.nodes.get(uid)
        if position is None:
            continue
        cx, cz = network._cell(*position)
        instances = {i for dx in (-1, 0, 1) for dz in (-1, 0, 1)
                     for i in network._prefab_grid.get((cx+dx, cz+dz), ()) if uid in i[1]}
        for instance in instances:
            lane = network._prefab_lane_data.get(instance[0], {})
            nodes = lane.get('nodes', ())
            if (len(nodes) != 3 or any(bool(n.get('input_lanes')) == bool(n.get('output_lanes'))
                                      for n in nodes)):
                continue
            inputs = sum(bool(n.get('input_lanes')) for n in nodes)
            if inputs not in (1, 2):
                continue
            for a in instance[1]:
                for b in instance[1]:
                    if a == b:
                        continue
                    paths = network._prefab_connector_options(instance, a, b)
                    if not paths:
                        continue
                    graph.setdefault(a, set()).add(b)
                    graph.setdefault(b, set())
                    edges[a, b] = dict(kind='merge' if inputs == 2 else 'split',
                                       instance=instance)
            pending.extend(instance[1])
            if len(graph) > MAX_NODES or len(edges) > MAX_EDGES or len(pending) > MAX_PENDING:
                return (), {}

    # Kosaraju on an explicitly bounded graph. Work occurs only at publication.
    order, seen = [], set()
    def visit(u):
        if u in seen:
            return
        seen.add(u)
        for v in sorted(graph[u]):
            visit(v)
        order.append(u)
    for uid in sorted(graph):
        visit(uid)
    reverse = {u: set() for u in graph}
    for u, successors in graph.items():
        for v in successors:
            reverse[v].add(u)
    result, seen = [], set()
    for uid in reversed(order):
        if uid in seen:
            continue
        group, queue = set(), [uid]
        while queue:
            u = queue.pop()
            if u in seen:
                continue
            seen.add(u); group.add(u); queue.extend(reverse[u]-seen)
        if len(group) < 3:
            continue
        if any(len(graph[u] & group) != 1 or len(reverse[u] & group) != 1 for u in group):
            continue
        exits = {u for u in group if graph[u]-group}
        entries = {u for u in group if reverse[u]-group}
        if len(exits) < 2 or len(entries) < 2:
            continue
        digest = hashlib.sha256(repr(sorted(group)).encode()).hexdigest()[:24]
        result.append(dict(nodes=frozenset(group), exits=frozenset(exits),
                           entries=frozenset(entries), component_id='directed-cycle/'+digest))
    return tuple(result), edges


def events(network, lane_path, payload):
    groups, edges = components(network, lane_path.segments)
    result, owned = [], set()
    for group in groups:
        ring = group['nodes']
        entry_s = entry_start = previous_exit = None
        for index, segment in enumerate(lane_path.segments):
            a, b = segment.start_uid, segment.end_uid
            if not (a in ring or b in ring) or (a, b) not in edges:
                continue
            points = [p for p in lane_path.points if p.segment_index == index]
            if not points:
                continue
            owned.add(index)
            if a not in ring and b in ring:
                # Join is at the end of the entry connector, not before entry.
                entry_s = points[-1].s
                entry_start = points[0].s
                previous_exit = None
            elif a in ring and b in ring:
                if a in group['exits']:
                    previous_exit = points[-1].s  # wholly past the unchosen fork
            elif a in ring and b not in ring:
                eligible = (previous_exit if previous_exit is not None else entry_s
                            if entry_s is not None else points[0].s)
                target = payload(segment.lane_id)
                event_id = repr(('roundabout_exit', group['component_id'],
                                 tuple(sorted((k, repr(v)) for k, v in target.items()))))
                result.append(dict(event_id=event_id, kind='roundabout', direction='right',
                    start_s_m=entry_start if entry_start is not None else points[0].s,
                    end_s_m=points[-1].s, signal_s_m=points[0].s,
                    indication_not_before_s_m=float(eligible),
                    topology_basis='unique_directed_oneway_cycle',
                    circulation_id=group['component_id'], segment_index=index,
                    end_segment_index=index, gps_pair_start=segment.gps_pair_index,
                    gps_pair_end=segment.gps_pair_index, prefab_token=segment.lane_id.prefab_token,
                    source_lane_id=target, target_lane_id=target))
                entry_s = entry_start = previous_exit = None
    return result, owned
