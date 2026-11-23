"""Saved directed route/cache + actual rejected head; explicitly missing fields."""
import json
import math
import ast
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.navigation.road_network import RoadNetwork
from core.navigation.prefab_signals import prepare_signal_passages
from core.navigation.lane_model import LaneLocator
from core.navigation.lane_model import LaneId, GpsCorridorEdge
from core.navigation.lane_trajectory import build_lane_trajectory
from core.sdk.signal_snapshot import RouteSignalSelector
from tools.profile_oct9_map import window


def physical_flow(points,plan,truck,progress,snapshot,selector_class):
    """Real production interfaces; SDK/native ownership remain modeled inputs.

    Map's prepared geometry above is consumed unchanged. No live mapping or
    game control is opened; the real Controller writes to the fixture backend.
    """
    from tests.test_activation_observation_binding import flow
    from tests.signals.test_stop_lifecycle import directed_stop
    from core.longitudinal import context,publish
    from tests.test_roundabout_intervention_reporting import pedal
    generator=flow.__wrapped__();harness=next(generator)
    try:
        values,_=directed_stop(harness,start=False)
        state,vehicle,engine,ap,tick,n,clock,writes,collected=values
        vehicle.update(truck)
        lane=state.get('lane_trajectory');lane.update(points=points,signal_passages=plan)
        state.set('lane_trajectory',lane);state.set('lane_trajectory_publication_token','actual-logged-route-model')
        engine._signal_selector=selector_class();engine._signal_route_token=None
        # The immutable decoded source is injected at the reader boundary.
        # It is not a newly acquired DLL observation or historical SDK Y.
        engine._signal_reader.read=lambda:dict(snapshot)
        clock[0]=snapshot['observed_at']+.01
        def step():
            harness[4](4,truck['speed'],dt=.02)
            packet=state.get('nav_steering_debug');packet['tracking_progress_m']=progress
            state.set('nav_steering_debug',packet)
            actual=state.get('telemetry')['truck']
            signal=engine._signal_observation(actual,context(state))
            light=signal.get('candidate') if signal.get('valid') else signal.get('stop_candidate')
            publish(state,actual,'traffic',signal=signal,light=light,
                    light_brake=engine._light_brake(light),traffic_brake=0.,following=None)
            tick.policy.on_tick(.02);tick.acc.on_tick(.02);ap.on_tick(.02);engine._flush_controls()
            return signal
        step();n();selected=step()
        return dict(active=state.get('autopilot_active'),pending=state.get('auto_drive_pending'),
            control_state=state.get('autopilot_control_state'),
            reason=state.get('automatic_safety_stop_reason'),
            throttle=pedal(engine,'aforward'),brake=pedal(engine,'abackward'),
            coverage=selected['coverage'],writes=writes,
            limitation='Original head/time and reconstructed map; owner/Y/speed and downstream SDK response are explicitly modeled.')
    finally:generator.close()

def main():
    root=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')
    out=Path('docs/steering-audit/oct10-signal')
    summary=json.loads((out/'summary.json').read_text())
    incident=next(e for e in summary['exports'] if e['first_intervention'])
    fault=incident['first_intervention'];signal=fault['details']['signal']
    head=signal['unassigned_candidate']
    dense=json.loads((out/'steering-replay-20261010T164111.194118Z-automatic_disable-decoded.json').read_text())
    rows=[r for r in dense['samples'] if r.get('packet_binding_valid')]
    network=RoadNetwork();assert network._try_load_cache(str(root/'map-cache/promods-1.59'))
    uids=window(network,root/'ultrapilot.log',fault['context'][6])
    row=next(r for r in rows if r['calculation_sdk_frame_us']==fault['details']['sdk_frame_us'])
    first=rows[0];x,z=first['observation_xz'];y=network.altitude_near((x,z))
    path,match=network.build_lane_path(uids,(x,z),first['observation_heading_rad'],altitude=y,speed_mps=first['speed_kmh']/3.6)
    assert path.valid,path.failure_reason
    lines=(root/'ultrapilot.log').read_text(errors='replace').splitlines()
    line=next(line for line in lines if fault['context'][6] in line and 'phase=select_lane_sequence status=ok' in line)
    ids=json.loads(line.split('details=',1)[1])['lane_ids']
    exact=[]
    for index,value in enumerate(ids):
        parsed=ast.parse(value,mode='eval').body
        lane=LaneId(**{k.arg:ast.literal_eval(k.value) for k in parsed.keywords})
        if lane.prefab_token is None:
            options=network._build_lane_segments(network._road_segment_by_uid[lane.road_uid])
            segment=next(s for s in options if s.lane_id==lane)
            from dataclasses import replace
            segment=replace(segment,gps_pair_index=index)
        else:
            instances={tuple(p[:3]):p for group in network._prefab_pairs.values() for p in group
                if p[0]==lane.prefab_token and min(p[1])==lane.road_uid}
            assert len(instances)==1
            instance=next(iter(instances.values()))
            edge=GpsCorridorEdge(uids[index],uids[index+1],'prefab',index,prefab_instance=instance)
            pts=network._prefab_curve_chain_3d(instance,lane.connector_path)
            segment=network._make_prefab_lane_segment(edge,instance,lane.connector_path,pts)
            assert segment.lane_id==lane
        exact.append(segment)
    from dataclasses import replace
    for index in range(len(exact)-1):
        connection=network._lane_connection(exact[index],exact[index+1])
        assert connection is not None,('original logged boundary cannot be re-proven',index)
        exact[index]=replace(exact[index],successors=(connection,))
    path=network.connect_lane_sequence(exact,uids)
    assert path.valid,path.failure_reason
    path=build_lane_trajectory(path)
    assert path.valid,path.failure_reason
    plan=prepare_signal_passages(network,path)
    points=[[p.x,p.y,p.z] for p in path.points]
    selector=RouteSignalSelector();selector.route.prepare(points,'offline-reconstructed')
    x,z=row['observation_xz'];y=network.altitude_near((x,z))
    # Native SDK Y was not exported. Use the selected map path's own Y for
    # this explicit geometric model, not a possibly neighbouring road level.
    nearest_point=min(path.points,key=lambda p:math.hypot(p.x-x,p.z-z))
    y=nearest_point.y
    truck=dict(x=x,y=y,z=z,rotation=row['observation_heading_rad'],speed=row['speed_kmh']/3.6)
    # The saved full UID sequence and rolling replay use different arc origins.
    # Localize on the same physical placement, recording the offset explicitly.
    nearest_index=min(range(len(points)),key=lambda i:math.hypot(points[i][0]-x,points[i][2]-z))
    progress=selector.route.arcs[nearest_index]
    ego=selector.route._project(dict(truck,yaw=truck['rotation']),max(0.,progress-20.),progress+20.);assert ego
    nearest=sorted(plan['passages'],key=lambda p:abs(p['entry_progress_m']-ego[1]-head['distance']))[:3]
    # Historical owner fields remain absent. Match the ORIGINAL PPD object's
    # transformed pose independently; entry distance cannot prove regulation.
    # Supplemental geometric experiment only: the rebuilt full path differs
    # from the saved rolling geometry. Preserve the residual instead of making
    # its arc lengths look historically exact.
    matched=[p for p in plan['passages'] if abs(p['entry_progress_m']-ego[1]-head['distance'])<.5]
    from tests.signals.test_native_signal_direction import authored_heads
    _,authored=authored_heads()
    pose_matches=[h for h in authored if h['id']==head['id']
        and math.dist([h[k] for k in ('x','y','z')],[head[k] for k in ('x','y','z')])<.001
        and abs(math.atan2(math.sin(h['yaw']-head['yaw']),math.cos(h['yaw']-head['yaw'])))<1e-5]
    original_head=dict(head);original_head.pop('distance');original_head.pop('distance_basis')
    result=dict(gps_uids=uids,original_row=row,original_head=original_head,
        points=points,plan=plan,truck=truck,reconstructed_progress_m=ego[1],
        entry_distance_residuals_m=[p['entry_progress_m']-ego[1]-head['distance'] for p in matched],
        original_progress_m=row['tracking_progress_m'],nearest_entries=nearest,
        matching_entry_records=matched,original_signal={k:signal[k] for k in ('lifecycle','generation','frame_us','observed_at')},
        authority=fault['context'],limitations=['Original owner fields and full native array not retained in first fault.',
            'Altitude in this reconstruction is map-derived, not original SDK Y.'])
    result.update(distance_correspondence_is_regulation=False,authored_pose_matches=pose_matches,
                  authored_pose_match_is_historical_owner_record=False)
    from core.navigation.drivable_surface import lane_path_fingerprint
    from dataclasses import replace
    result['reconstructed_fingerprint']=lane_path_fingerprint(replace(path,revision=fault['context'][5]))
    if len(pose_matches)==1:
        p=pose_matches[0]
        modeled=dict(original_head,scope_schema=1,ownership_valid=True,id_basis='prefab_segment_instance_id',
            owner_prefab_uid=p['owner_prefab_uid'],owner_node_uids=p['owner_node_uids'],
            owner_origin_index=p['owner_origin_index'],instance_slot=p['instance_slot'])
        snapshot=dict(result['original_signal'],valid=True,schema=3,lights=[modeled])
        selected=selector.select(snapshot,points,'offline-reconstructed',tuple(fault['context']),truck,ego[1],plan)
        import importlib.util
        spec=importlib.util.spec_from_file_location('installed_signal_selector',root/'core/sdk/signal_snapshot.py')
        installed=importlib.util.module_from_spec(spec);spec.loader.exec_module(installed)
        before=installed.RouteSignalSelector().select(snapshot,points,'offline-reconstructed',tuple(fault['context']),truck,ego[1],plan)
        result.update(supplemental_head=modeled,baseline_selection=before,candidate_selection=selected)
        result['physical_flow_before']=physical_flow(points,plan,truck,ego[1],snapshot,installed.RouteSignalSelector)
        result['physical_flow_after']=physical_flow(points,plan,truck,ego[1],snapshot,RouteSignalSelector)
    (out/'place-reproduction.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(gps_uids=len(uids),points=len(points),passages=len(plan['passages']),
        progress=ego[1],logged_progress=row['tracking_progress_m'],matching_entries=matched,
        nearest_entries=nearest,baseline_selection=result.get('baseline_selection'),
        candidate_selection=result.get('candidate_selection'),
        residuals_m=result['entry_distance_residuals_m'],
        physical_before=result.get('physical_flow_before'),physical_after=result.get('physical_flow_after')),indent=2))

if __name__=='__main__':main()
