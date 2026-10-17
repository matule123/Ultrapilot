"""Optional bounded presentation of consumed control geometry, never authority.

No sensor reads, predictions or actuator calls. One display publication in
flight, no queue; two 192 KiB accounted geometry frames, one 64 KiB output
receipt. Byte accounting uses the existing diagnostic codec; Python allocator
overhead is measured separately. Old geometry is never rebound to a new ID.
"""
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import math
import time
import bisect

from core.navigation.longitudinal_diagnostics import bounded_copy

FRAME_BUDGET = 192 * 1024
RECEIPT_BUDGET = 64 * 1024
HISTORY_RECEIPT_BUDGET = 16 * 1024  # carved out of RECEIPT_BUDGET, not added
PERIOD_S = .1
COLORS = dict(passive='#929ba9', tracked='#50aaff', protective='#facc15',
              service='#ff982d', emergency='#ff4b57', invalid='#536071')


def acquisition(value):
    source = value or {}
    return tuple(source.get(k) for k in ('lifecycle', 'generation', 'frame_us', 'observed_at'))


def body_corners(body):
    """The SAME width/forward axes as swept SAT, in ETS2 world X/Z."""
    w,_,length=body['dimensions_whl']; yaw=body['yaw']; c,s=math.cos(yaw),math.sin(yaw)
    return [[body['x']+c*x-s*z,body['y'],body['z']-s*x-c*z]
        for x,z in ((-w/2,-length/2),(w/2,-length/2),(w/2,length/2),(-w/2,length/2),(-w/2,-length/2))]


def geometry(observed, selector, truck, progress, binding, result, prediction, *, applied=None):
    """Copy only existing decoded bodies/reference and actual prediction work."""
    actors = []
    previous = selector._native_previous if selector is not None else None
    for actor in observed.get('actors', ())[:80]:
        row = {k:actor.get(k) for k in ('id','slot','source','record_fingerprint','speed','speed_source')}
        row['bodies'] = [{k:b.get(k) for k in ('x','y','z','yaw','dimensions_whl')}
                         for b in actor.get('bodies', ())[:4]]
        old = previous[1].get(actor['id']) if previous else None
        row['observed_history'] = None
        if (old and old.get('source') == actor['source'] and old.get('slot') == actor['slot']
                and 0 < observed['source']['observed_at']-previous[0][3] <= .5
                and math.hypot(old['x']-actor['x'],old['z']-actor['z'])
                   <= max(old['speed'],actor['speed'])*(observed['source']['observed_at']-previous[0][3])+1.):
            row['observed_history'] = [[previous[0][3],old['x'],old['y'],old['z']],
                [observed['source']['observed_at'],actor['x'],actor['y'],actor['z']]]
        actors.append(row)
    # Retain a local, ordered portion of the actual projection reference.
    first=bisect.bisect_left(selector.arcs,progress-20) if selector is not None else 0
    last=bisect.bisect_right(selector.arcs,progress+150) if selector is not None else 0
    selected=range(first,min(first+256,last))
    raw_source=observed.get('source') or {}
    crossing=result.get('crossing') or {}
    conflicts=crossing.get('conflicts') or ()
    crossing=dict(status=crossing.get('status'),brake=crossing.get('brake'),
        conflicts=[{k:c.get(k) for k in ('id','point_xyz','distance_m','actor_arrival_s',
            'ego_arrival_earliest_s','brake')} for c in conflicts[:64]],
        omitted_conflicts=max(0,len(conflicts)-64))
    frame = dict(schema=1, context=binding, source={k:raw_source.get(k) for k in
        ('valid','reason','lifecycle','generation','frame_us','observed_at')},
        receiver_time=observed.get('receiver_time'), status=observed.get('status'),
        detections_valid=observed.get('status') in ('observed','empty_unproven_coverage'),
        ego={k:truck.get(k) for k in ('x','y','z','rotation','speed','gear','sdkFrameTimeUs','_control_observation')},
        actors=actors, omitted_actors=max(0,len(observed.get('actors',()))-80),
        reference=[selector.points[i] for i in selected],
        reference_truncated=last-first>256, corridor_status='REFERENCE_ONLY; physical edges unverified',
        prediction=prediction, crossing=crossing,
        body_prediction={k:(result.get('body_prediction') or {}).get(k) for k in
            ('status','brake','model','prediction_duration_s','unsupported_actors')},
        following={k:result.get(k) for k in ('status','target_id','gap_m','speed_cap_mps','emergency')})
    # Budget admission is per immutable object, not all-or-nothing scene loss.
    # Use exact intermediate owners first. Priority affects display only; it
    # cannot grant authority or bind a new record to an old physical write.
    applied=applied or {}
    body=result.get('body_prediction') or {}
    decisive=(result.get('display_brake_basis') or {}).get('decisive') or {}
    emergency={str(c['id']) for c in body.get('conflicts',()) if c.get('brake',0.)>.7}
    emergency.update(str(i) for i in result.get('emergency_actor_ids',()))
    if (applied.get('source') or {}).get('emergency'):
        emergency.update(str(i) for i in applied.get('braking_actor_ids') or ())
    braking={str(c['id']) for c in body.get('conflicts',()) if c.get('brake',0.)>0.}
    braking.update(str(i) for i in applied.get('braking_actor_ids') or ())
    if decisive.get('id') is not None:braking.add(str(decisive['id']))
    targets={str(t['id']) for t in (result.get('motion_constraint') or {}).get('targets',())}
    targets.update(str(t['id']) for t in applied.get('targets') or ())
    targets.update(str(i) for i in (result.get('target_id'),applied.get('target_id')) if i is not None)
    def rank(actor):
        aid=str(actor['id']);b=(actor.get('bodies') or [{}])[0]
        distance=math.hypot(b.get('x',truck.get('x',0.))-truck.get('x',0.),
            b.get('z',truck.get('z',0.))-truck.get('z',0.))
        return (0 if aid in emergency else 1 if aid in braking else 2 if aid in targets else 3,
                distance,aid,str(actor.get('source')),actor.get('slot',-1))
    actors.sort(key=rank)
    def record_key(actor):
        return tuple(actor.get(k) for k in ('id','source','slot','record_fingerprint'))
    # Preserve a small exact local reference; the classic HUD already draws
    # the full live road path. No geometry is interpolated for this reduction.
    frame.update(actors=[],prediction=None,reference=frame['reference'][::4],
        reference_sample_stride=4,reference_incomplete=len(frame['reference'])>1,
        crossing=dict(crossing,conflicts=[]),budget_reduced=True,
        omitted_actors=len(observed.get('actors',())),omitted_bodies=0,
        omitted_prediction_paths=0,omitted_prediction_points=0,
        omitted_history_points=0,omitted_priority_actors=0)
    base,cost=bounded_copy(frame,limit=FRAME_BUDGET)
    if base.get('snapshot_status'):
        # Pathological identity strings cannot cause a fabricated empty scene.
        return dict(schema=1,snapshot_status='UNVERIFIED_IDENTITY_BUDGET_EXCEEDED',
            actors=[],omitted_actors=len(actors),omitted_priority_actors=sum(rank(a)[0]<3 for a in actors))
    remaining=FRAME_BUDGET-cost-4096
    actor_budget=max(0,int(remaining*.75)) if prediction else remaining
    admitted=[];used=0
    for actor in actors:
        row=dict(actor,observed_history=None)
        owned,charge=bounded_copy(row,limit=max(1,actor_budget-used))
        if owned.get('snapshot_status'):
            frame['omitted_priority_actors']+=rank(actor)[0]<3
            continue
        admitted.append(owned);used+=charge
        frame['omitted_history_points']+=len(actor.get('observed_history') or ())
    frame['actors']=admitted
    frame['omitted_actors']=len(observed.get('actors',()))-len(admitted)
    admitted_keys={record_key(a) for a in admitted}
    frame['omitted_bodies']=sum(len(a.get('bodies') or ()) for a in observed.get('actors',())
        if record_key(a) not in admitted_keys)+sum(max(0,len(a.get('bodies') or ())-4)
            for a in observed.get('actors',()) if record_key(a) in admitted_keys)
    frame['omitted_history_points']+=sum(len(a.get('observed_history') or ())
        for a in actors if record_key(a) not in admitted_keys)
    remaining-=used
    # Admit original prediction samples and history only AFTER actual bodies.
    prediction=prediction or {}
    reduced={k:prediction.get(k) for k in ('status','model','horizon_s','step_s') if k in prediction}
    reduced.update(actor_paths=[],ego_samples=[],sampling='exact_subset; no new prediction')
    paths=prediction.get('actor_paths') or ()
    priorities={record_key(a):i for i,a in enumerate(actors)}
    for path in sorted(paths,key=lambda p:(priorities.get(record_key(p),80),p.get('body_index',0))):
        original=path.get('points') or ()
        points=original[::4]
        row=dict(path,points=points,sample_stride=4)
        owned,charge=bounded_copy(row,limit=max(1,remaining))
        if record_key(path) not in admitted_keys or owned.get('snapshot_status'):
            frame['omitted_prediction_paths']+=1
            frame['omitted_prediction_points']+=len(original)
        else:
            reduced['actor_paths'].append(owned);remaining-=charge
            frame['omitted_prediction_points']+=len(original)-len(points)
    frame['omitted_prediction_paths']+=prediction.get('omitted_actor_paths',0)
    for sample in (prediction.get('ego_samples') or ())[::4]:
        owned,charge=bounded_copy(sample,limit=max(1,remaining))
        if isinstance(owned,dict) and owned.get('snapshot_status'):break
        reduced['ego_samples'].append(owned);remaining-=charge
    frame['omitted_ego_samples']=len(prediction.get('ego_samples') or ())-len(reduced['ego_samples'])
    for conflict in crossing['conflicts']:
        owned,charge=bounded_copy(conflict,limit=max(1,remaining))
        if owned.get('snapshot_status'):continue
        frame['crossing']['conflicts'].append(owned);remaining-=charge
    frame['crossing']['omitted_conflicts']=len(conflicts)-len(frame['crossing']['conflicts'])
    original_records={record_key(a):a for a in actors}
    for row in admitted:
        original=original_records[record_key(row)]
        history=original.get('observed_history')
        if history:
            owned,charge=bounded_copy(history,limit=max(1,remaining))
            if isinstance(owned,list):
                row['observed_history']=owned;remaining-=charge
                frame['omitted_history_points']-=len(history)
    frame['prediction']=reduced
    frame['prediction_incomplete']=bool(frame['omitted_prediction_paths'] or frame['omitted_prediction_points'])
    owned=bounded_copy(frame,limit=FRAME_BUDGET)[0]
    # Scalar metadata/container overhead has a reserved 4 KiB. Preserve an
    # explicit nonempty priority subset even if future optional fields grow.
    if owned.get('snapshot_status'):
        frame['omitted_prediction_paths']+=len(reduced['actor_paths'])
        frame['omitted_prediction_points']+=sum(len(p.get('points') or ()) for p in reduced['actor_paths'])
        frame['omitted_ego_samples']+=len(reduced['ego_samples'])
        frame['omitted_history_points']+=sum(len(r.get('observed_history') or ()) for r in frame['actors'])
        frame.update(prediction=None,prediction_incomplete=True)
        frame['crossing']['conflicts']=[]
        frame['crossing']['omitted_conflicts']=len(conflicts)
        for row in frame['actors']:row['observed_history']=None
        owned=bounded_copy(frame,limit=FRAME_BUDGET)[0]
    return owned


class DevHUDFeed:
    """Display adapter for the existing Engine and PedalJournal, not a collector."""
    def __init__(self):
        self.frames = deque(maxlen=2)
        self.latest = None
        self.next_at = 0.
        self.write_next_at = 0.
        self.future = None
        self.worker = None
        self.skipped = 0
        self.active = True
        self.geometry_next_at = 0.
        self.last_intervention = None
        self.last_fault = None

    def wants_geometry(self, now):
        if not self.active or now < self.geometry_next_at:
            return False
        self.geometry_next_at = now+PERIOD_S
        return True

    def pause(self):
        self.active = False
        self.frames.clear(); self.latest = None
        self.last_intervention = self.last_fault = None

    def resume(self):
        self.active = True

    def capture(self, frame):
        # Engine traffic thread owns frames. Repeated source reads cannot
        # renew frame freshness and do not add history entries.
        if self.active and (not self.frames or acquisition(self.frames[-1].get('source')) != acquisition(frame.get('source'))):
            old=(self.frames[-1].get('context') or ()) if self.frames else ()
            if old and tuple(old[:5]) != tuple((frame.get('context') or ())[:5]):
                self.last_intervention=self.last_fault=None
                self.latest=None
            self.frames.append(frame)
            latest=self.latest
            if (latest and not self.last_fault and latest.get('context')==frame.get('context')
                    and acquisition(latest.get('traffic_source'))==acquisition(frame.get('source'))
                    and self._positive_brake(latest)):
                self._remember_intervention(latest,frame)
            # The retained historical frame shares the SAME two-frame budget.
            # Keep one live frame when history is no longer in the live deque.
            history=(self.last_intervention or {}).get('geometry')
            if history is not None and all(history is not f for f in self.frames):
                while len(self.frames)>1:self.frames.popleft()

    def record_fault(self, fault):
        if not self.active or not isinstance(fault,dict):return
        binding=(self.frames[-1].get('context') or ()) if self.frames else ()
        if binding and binding[0] not in (None,fault.get('epoch')):return
        if self.last_fault and self.last_fault.get('epoch')==fault.get('epoch'):return
        from core.control_timing import fault_explanation
        value={k:fault.get(k) for k in ('epoch','observed_at','producer','kind','sdk_frame_us')}
        value['explanation']=fault_explanation(fault)[:384]
        latest=self.latest or {}
        value['brake_geometry_unavailable']=bool(self._positive_brake(latest) and not any(
            f.get('context')==latest.get('context') and
            acquisition(f.get('source'))==acquisition(latest.get('traffic_source')) for f in self.frames))
        self.last_fault=bounded_copy(value,limit=4096)[0]

    @staticmethod
    def _positive_brake(value):
        stats=value.get('write_stats') or {}
        return (stats.get('write_error_count',0)==0 and (stats.get('backend_brake_max') or 0.)>0.
            and (value.get('backend_pair') or {}).get('brake',0.)>0.)

    def _remember_intervention(self,value,matched):
        if matched is None and (self.last_intervention or {}).get('geometry') is not None:
            return  # keep the last exact scene; current unmatched receipt stays explicit
        summary={k:value[k] for k in ('context','activation','source','sequence',
            'sdk_frame_us','observation_timestamp','traffic_source','target_id','braking_actor_ids',
            'brake_basis','write_stats','backend_pair','recorded_at','game_consumption_verified')}
        summary.update({k:value.get(k) for k in ('candidate_id','constraint_owner_id',
            'constraint_kind','brake_actor_id','continuity_reason')})
        summary['source']={k:value['source'].get(k) for k in ('source','reason','emergency')}
        summary['write_stats']={k:value['write_stats'].get(k) for k in ('write_success_count','write_error_count',
            'backend_brake_max','write_last_sequence','write_last_returned_at_s')}
        compact=bounded_copy(summary,limit=HISTORY_RECEIPT_BUDGET-4096)[0]
        if not compact.get('snapshot_status'):
            self.last_intervention=dict(applied=compact,geometry=matched,recorded_at=value['recorded_at'],
                attribution='EXACT_NATIVE_ACQUISITION_AND_ROUTE' if matched else 'CONSUMED_GEOMETRY_UNAVAILABLE')
            if matched is not None:
                while len(self.frames)>1 and all(matched is not f for f in self.frames):self.frames.popleft()

    def written(self, trace, journal, fault, now):
        if fault:self.record_fault(fault)
        if not self.active or now < self.write_next_at:
            return
        self.write_next_at = now+PERIOD_S
        if not isinstance(trace, dict):
            return
        inputs = trace.get('inputs') or {}
        traffic = inputs.get('traffic') or {}
        following = traffic.get('following') or {}
        acc = inputs.get('acc') or {}
        fields=('source','decision_source','reason','throttle','brake','emergency','sequence',
            'computed_at','observation_timestamp','sdk_frame_us','expires_at')
        selected=trace.get('selected') or {}
        basis=traffic.get('brake_basis') or {}
        decisive=basis.get('decisive') or {}
        original_acc=(((trace.get('requested') or {}).get('producer_trace') or {}).get('inputs') or {}).get('acc') or {}
        written_summary=getattr(journal._local,'written_summary',None)
        row=written_summary[0] if written_summary else {}
        value = dict(context=trace.get('context'), activation=trace.get('activation'),
            source={k:selected.get(k) for k in fields},
            requested={k:(trace.get('requested') or {}).get(k) for k in fields},
            output_intent={k:row.get('requested_'+k) for k in ('throttle','brake')},
            written_phase=row.get('phase'), sequence=trace.get('decision_sequence'),
            sdk_frame_us=trace.get('sdk_frame_us'), observation_timestamp=trace.get('observation_timestamp'),
            traffic_source=((original_acc.get('braking_acquisition') or acc.get('braking_acquisition'))
                if selected.get('source') == 'acc' and selected.get('brake',0.) > 0.
                else following.get('source_acquisition')),
            target_id=acc.get('following_target_id') or following.get('target_id'),
            candidate_id=following.get('target_id'),constraint_owner_id=acc.get('following_target_id'),
            constraint_kind=acc.get('following_kind'),brake_actor_id=decisive.get('id'),
            continuity_reason=next((w.get('continuity_reason') for w in following.get('owner_witnesses',())
                if w.get('target_id')==acc.get('following_target_id')),'unavailable'),
            observed_reference_gap_m=following.get('gap_m'),
            targets=(traffic.get('motion_constraint') or {}).get('targets'),
            braking_actor_ids=(original_acc.get('braking_actor_ids')
                if original_acc else acc.get('braking_actor_ids')),
            brake_basis=dict(kind=basis.get('kind'), decisive={k:decisive.get(k)
                for k in ('id','distance_m','predicted_contact_s','contact_basis')}),
            first_fault={k:(fault or {}).get(k) for k in ('reason','producer','observed_at','sdk_frame_us')},
            requested_speed_kmh=acc.get('requested_speed_kmh'),
            constrained_speed_kmh=acc.get('constrained_speed_kmh'),
            control_target_kmh=acc.get('control_target_kmh'),
            regulator_mode=acc.get('speed_control_reason'), refresh=(trace.get('selected') or {}).get('refresh_protocol'),
            write_stats=dict(getattr(journal._local,'writes',{})),
            backend_pair=dict(journal._held), last_successful_pair=dict(journal._last_successful),
            game_consumption_verified=False, recorded_at=now)
        self.latest = bounded_copy(value, limit=RECEIPT_BUDGET-HISTORY_RECEIPT_BUDGET)[0]
        if self.latest.get('snapshot_status'):return
        value=self.latest  # same immutable list/tuple normalization as geometry
        stats=value['write_stats']
        # Only a returned positive BRAKE-channel call establishes this receipt.
        # The aggregate pair or a successful throttle call alone cannot do so.
        if (stats.get('write_error_count',0)==0 and stats.get('backend_brake_max',0.) is not None
                and stats.get('backend_brake_max',0.)>0. and value['backend_pair'].get('brake',0.)>0.
                and not fault):
            matched=next((f for f in self.frames if f.get('context')==value['context']
                and acquisition(f.get('source'))==acquisition(value['traffic_source'])),None)
            # Hold the exact immutable frame; never attach today's same-ID box.
            self._remember_intervention(value,matched)

    def snapshot(self):
        latest = self.latest
        frames = tuple(self.frames)
        matched = None
        if latest:
            for frame in frames:
                if (frame.get('context') == latest.get('context')
                        and acquisition(frame.get('source')) == acquisition(latest.get('traffic_source'))):
                    matched = frame
        return dict(schema=1, detection=frames[-1] if frames else None,
            consumed_geometry=matched, applied=latest, skipped_publications=self.skipped,
            last_intervention=self.last_intervention,last_fault=self.last_fault,
            attribution='EXACT_NATIVE_ACQUISITION_AND_ROUTE' if matched else 'CONSUMED_GEOMETRY_UNAVAILABLE',
            limits=dict(frames=2, frame_accounted_bytes=FRAME_BUDGET, receipt_accounted_bytes=RECEIPT_BUDGET,
                history_shares_frame_budget=True,history_receipt_bytes=HISTORY_RECEIPT_BUDGET,
                actors=80, bodies_per_actor=4, actor_paths=64, reference_points=256, publication_hz=10))

    def offer(self, state, now):
        if not self.active or now < self.next_at:
            return
        self.next_at = now+PERIOD_S
        if self.future is not None and not self.future.done():
            self.skipped += 1
            return
        if self.worker is None:
            self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix='dev-hud-presentation')
        snapshot = self.snapshot()  # References already owned, never mutated.
        def publish():
            try:
                if self.active and state.get('dev_hud_enabled', False):
                    state.set('dev_hud_snapshot', snapshot)
            except Exception:
                pass  # Presentation failure cannot revoke or restore controls.
        self.future = self.worker.submit(publish)

    def close(self):
        self.pause()
        if self.worker:
            self.worker.shutdown(wait=False, cancel_futures=True)


def actor_style(actor, snapshot, now, *, stale=False):
    """Colour requires the SAME consumed owner, not mere presence in a buffer."""
    applied = snapshot.get('applied') or {}
    consumed = snapshot.get('consumed_geometry') or {}
    source = ((snapshot.get('detection') or {}).get('source') if snapshot.get('control_current') is False
        else consumed.get('source')) or (snapshot.get('detection') or {}).get('source') or {}
    history=snapshot.get('history_only') is True
    if (not history and (stale or snapshot.get('detection_current') is False
            or (snapshot.get('detection') or {}).get('detections_valid') is False
            or not 0 <= now-source.get('observed_at', float('-inf')) <= .5)):
        return 'invalid', 'stale / unverified'
    if snapshot.get('control_current') is False and not history:
        return 'passive', 'fresh detection; control inactive/unverified'
    own = next((a for a in consumed.get('actors', ()) if
        all(a.get(k) == actor.get(k) for k in ('id','source','slot','record_fingerprint'))), None)
    if own is None:
        return 'passive', 'detection only; no consumed attribution'
    selected = applied.get('source') or {}
    stats = applied.get('write_stats') or {}
    pair = applied.get('backend_pair') or {}
    basis = applied.get('brake_basis') or {}
    cause = str((basis.get('decisive') or {}).get('id')) == str(actor['id'])
    target = str(applied.get('target_id')) == str(actor['id'])
    actual = (stats.get('write_success_count',0)>0 and pair.get('brake') is not None
              and pair['brake']>0 and stats.get('write_error_count',0)==0
              and stats.get('backend_brake_max') is not None and stats['backend_brake_max']>0.)
    acc_cause = str(actor['id']) in {str(v) for v in applied.get('braking_actor_ids') or ()}
    if selected.get('emergency') and selected.get('source') in ('acc','traffic','traffic_emergency') and actual and (cause or selected.get('source')=='acc' and acc_cause):
        return 'emergency', selected.get('reason') or 'selected emergency'
    if actual and ((selected.get('source')=='acc' and acc_cause) or
                   (selected.get('source') in ('traffic','traffic_emergency','continuous_service_hold') and cause)):
        return 'service', selected.get('reason') or 'selected service brake'
    if any(str(t.get('id'))==str(actor['id']) for t in applied.get('targets') or ()):
        return 'protective', 'positive protective speed constraint'
    if target:
        return 'tracked', 'ACC target; no attributed brake'
    return 'passive', 'observed; no selected intervention'


def for_display(snapshot, expected, active):
    """Presentation check only; never relabel a source with the current route."""
    def freeze(value):
        return tuple(freeze(v) for v in value) if isinstance(value,(list,tuple)) else value
    value=dict(snapshot)
    frame=value.get('detection') or {}
    applied=value.get('applied') or {}
    value['control_current']=bool(active and freeze(frame.get('context'))==freeze(expected)
        and freeze(applied.get('context'))==freeze(expected))
    value['detection_current']=freeze(frame.get('context'))==freeze(expected)
    historical=value.get('last_intervention') or {}
    # Display a separate immutable historical scene, never recolour live actors.
    # A new activation is cleared by capture(); an absent exact frame stays absent.
    value['history_only']=bool(not active and historical.get('geometry'))
    if value['history_only']:
        value.update(live_detection=frame,detection=historical['geometry'],
            consumed_geometry=historical['geometry'],applied=historical['applied'])
    return value


def draw_overlay(qp, rect, snapshot, project, now=None, *, test_data=False):
    """Decorate the CLASSIC 3-D HUD using its exact world/camera projection.

    Roads, lane ribbons, ego and camera remain the ordinary HUD. All developer
    bodies/paths are actual consumed intermediates, never an independent model.
    """
    from PyQt6.QtCore import Qt, QPointF, QRectF
    from PyQt6.QtGui import QColor, QFont, QPen, QPolygonF
    now = time.monotonic() if now is None else now
    qp.save(); qp.setClipRect(rect)
    frame=snapshot.get('detection') or {}
    source=frame.get('source') or {}
    age=None if source.get('observed_at') is None else now-source['observed_at']
    invalid_data=bool(frame.get('detections_valid') is False or frame.get('snapshot_status'))
    source_stale=bool(age is None or not 0<=age<=.5)
    stale=source_stale or invalid_data or snapshot.get('detection_current') is False or snapshot.get('history_only') is True
    qp.setFont(QFont('Consolas',9))
    def poly(points, colour, dashed=False, width=1.4):
        qp.setPen(QPen(QColor(colour),width,Qt.PenStyle.DashLine if dashed else Qt.PenStyle.SolidLine))
        qp.setBrush(Qt.BrushStyle.NoBrush)
        run=[]
        for x,y,z in points:
            p=project(x,y,z)
            if p is None:
                if len(run)>1:qp.drawPolyline(QPolygonF(run))
                run=[]
            else:run.append(p)
        if len(run)>1:qp.drawPolyline(QPolygonF(run))
    prediction=frame.get('prediction') or {}
    # Faint actual ego-body samples: a modelled swept strip, not road edges.
    for sample in prediction.get('ego_samples') or ():
        for body in sample:
            if len(body.get('dimensions_whl') or ())==3:
                poly(body_corners(body),'#456b83',stale,.65)
    actors=frame.get('actors') or ()
    # Painter order follows existing perspective depth, including camera orbit.
    ordered=sorted(actors,key=lambda a:
        min((p.y() for b in a.get('bodies') or ()
             if (p:=project(b['x'],b['y'],b['z'])) is not None),default=-1))
    labels=[];omitted=0
    for actor in ordered:
        style,why=actor_style(actor,snapshot,now,stale=stale)
        colour=COLORS[style]
        for body in actor.get('bodies') or ():
            if len(body.get('dimensions_whl') or ())!=3:continue
            corners=body_corners(body);half_height=body['dimensions_whl'][1]/2
            bottom=[[x,y-half_height,z] for x,y,z in corners]
            top=[[x,y+half_height,z] for x,y,z in corners]
            roof=[project(x,y,z) for x,y,z in top[:-1]]
            if all(p is not None for p in roof):
                fill=QColor(colour);fill.setAlpha(55 if stale else 95)
                qp.setPen(Qt.PenStyle.NoPen);qp.setBrush(fill);qp.drawPolygon(QPolygonF(roof))
            poly(bottom,colour,stale,1.5);poly(top,colour,stale,1.5)
            for a,b in zip(bottom[:4],top[:4]):poly([a,b],colour,stale,1.)
        history=actor.get('observed_history') or ()
        poly([p[1:] for p in history],colour,True,.9)
        for path in prediction.get('actor_paths') or ():
            if all(path.get(k)==actor.get(k) for k in ('id','slot','source','record_fingerprint')):
                poly([p[1:] for p in path['points']],colour,stale)
                for t,x,y,z in path['points'][::4]:
                    at=project(x,y,z)
                    if at is not None:
                        qp.setPen(QColor(colour));qp.drawEllipse(at,2.,2.)
                        qp.drawText(at+QPointF(3,-3),f'{t:g}s')
        body=(actor.get('bodies') or [{}])[0]
        if 'x' not in body:continue
        at=project(body['x'],body['y']+body['dimensions_whl'][1]/2,body['z'])
        if at is None:continue
        label=f"{actor['id']} [{actor.get('source','?')}:{actor.get('slot','?')}]"
        if actor.get('speed_source')=='parked_classification':label+=' static model'
        elif isinstance(actor.get('speed'),(int,float)):label+=f" {actor['speed']:.1f}m/s"
        cap=next((t.get('cap_mps') for t in (snapshot.get('applied') or {}).get('targets') or ()
            if str(t.get('id'))==str(actor['id'])),None)
        if isinstance(cap,(int,float)):label+=f' cap {cap:.1f}'
        for offset in (0,-16,16,-32,32,-48,48):
            box=QRectF(at.x()+5,at.y()+offset-14,235,16)
            if rect.contains(box) and not any(box.intersects(b) for b in labels):
                labels.append(box)
                qp.fillRect(box,QColor(13,20,29,205));qp.setPen(QColor(colour));qp.drawText(box,label)
                break
        else:omitted+=1
    for conflict in (frame.get('crossing') or {}).get('conflicts') or ():
        p=conflict.get('point_xyz')
        if p:
            actor=next((a for a in actors if a['id']==conflict['id']),{})
            style,_=actor_style(actor,snapshot,now,stale=stale) if actor else ('invalid','unavailable')
            at=project(*p)
            if at is not None:
                qp.setPen(QPen(QColor(COLORS[style]),1,Qt.PenStyle.DashLine));qp.setBrush(Qt.BrushStyle.NoBrush)
                qp.drawEllipse(at,4.,4.)
                body=(actor.get('bodies') or [{}])[0]
                if 'x' in body:poly([[body['x'],body['y'],body['z']],p],COLORS[style],True,.8)
    applied=snapshot.get('applied') or {};selected=applied.get('source') or {}
    pair=applied.get('backend_pair') or {};stats=applied.get('write_stats') or {}
    ctx=applied.get('context') or frame.get('context') or ()
    def fmt(v):return '?' if v is None else f'{v:.3f}' if isinstance(v,float) else str(v)
    read_age=None if frame.get('receiver_time') is None else now-frame['receiver_time']
    title=('DEV / HISTORY — NOT LIVE' if snapshot.get('history_only') else
        'DEV / TEST DATA' if test_data else 'DEV / CONTROL EVIDENCE')
    lines=[title+(' / INVALID' if invalid_data else ' / STALE' if source_stale else
        ' / CONTROL UNVERIFIED' if snapshot.get('control_current') is False else ''),
        f"native frame {fmt(source.get('frame_us'))} gen {fmt(source.get('generation'))}",
        f"source at {fmt(source.get('observed_at'))} / age {fmt(None if age is None else age*1000)}ms",
        f"read age {fmt(None if read_age is None else read_age*1000)}ms (not producer time)",
        f"session {fmt(ctx[1] if len(ctx)>1 else None)} / rev {fmt(ctx[5] if len(ctx)>5 else None)}",
        f"intent {str(ctx[4])[:9] if len(ctx)>4 else '?'} build {str(ctx[6])[:9] if len(ctx)>6 else '?'}",
        f"SDK {fmt(applied.get('sdk_frame_us'))} decision {fmt(applied.get('sequence'))}",
        f"request T/B {fmt((applied.get('output_intent') or {}).get('throttle'))}/{fmt((applied.get('output_intent') or {}).get('brake'))}",
        f"written T/B {fmt(pair.get('throttle'))}/{fmt(pair.get('brake'))} #{fmt(stats.get('write_last_sequence'))}",
        f"owner {fmt(selected.get('source'))} / ACC {fmt(applied.get('target_id'))}",
        f"candidate {fmt(applied.get('candidate_id'))} / constraint {fmt(applied.get('constraint_owner_id'))} {fmt(applied.get('constraint_kind'))}",
        f"brake object {fmt(applied.get('brake_actor_id'))}",
        f"continuity {fmt(applied.get('continuity_reason'))}",
        f"target req/cap {fmt(applied.get('requested_speed_kmh'))}/{fmt(applied.get('constrained_speed_kmh'))}km/h",
        f"ref gap {fmt(applied.get('observed_reference_gap_m'))}m / contact {fmt(((applied.get('brake_basis') or {}).get('decisive') or {}).get('predicted_contact_s'))}s",
        str(selected.get('reason') or 'reason unavailable')[:54],
        f"refresh {fmt((applied.get('refresh') or {}).get('state'))} / AEB {bool(selected.get('emergency'))}",
        str((applied.get('first_fault') or {}).get('reason') or 'first fault not captured')[:54],
        'constant native motion: bodies 3s / crossing rays 8s',
        ('EXACT consumed acquisition' if snapshot.get('consumed_geometry') else 'consumed geometry unavailable'),
        f"omitted labels/actors {omitted}/{frame.get('omitted_actors',0)}; priority {frame.get('omitted_priority_actors',0)}",
        f"omitted bodies/paths/points {frame.get('omitted_bodies',0)}/{frame.get('omitted_prediction_paths',0)}/{frame.get('omitted_prediction_points',0)}; backend != game"]
    if snapshot.get('last_fault'):
        lines[0]+=' / TECHNICAL STOP' if snapshot['last_fault'].get('kind')=='technical' else ' / INTERVENTION'
    if (snapshot.get('last_intervention') or {}).get('geometry') is None and snapshot.get('last_intervention'):
        lines.insert(1,'Brake intervention — exact object geometry unavailable')
    if (snapshot.get('last_fault') or {}).get('brake_geometry_unavailable'):
        lines.insert(1,'Latest brake geometry unavailable; HISTORY is older')
    explanation=(snapshot.get('last_fault') or {}).get('explanation')
    if explanation:
        alert=QRectF(rect.left()+12,rect.top()+8,max(160,min(640,rect.width()-375)),76)
        qp.setPen(QPen(QColor('#facc15'),1));qp.setBrush(QColor(13,20,29,235));qp.drawRoundedRect(alert,7,7)
        qp.setFont(QFont('Segoe UI',9));qp.setPen(QColor('#f7e3ab'))
        qp.drawText(alert.adjusted(9,6,-9,-6),Qt.TextFlag.TextWordWrap,explanation)
    card=QRectF(rect.right()-345,rect.top()+6,337,312)
    qp.setPen(QPen(QColor('#435365'),1));qp.setBrush(QColor(13,20,29,220));qp.drawRoundedRect(card,8,8)
    qp.setPen(QColor('#dce8f5'));qp.setFont(QFont('Consolas',8))
    qp.drawText(card.adjusted(9,6,-8,-4),Qt.AlignmentFlag.AlignTop,'\n'.join(lines))
    qp.setFont(QFont('Consolas',8));qp.setPen(QColor('#cbd9e8'))
    legend='gray observed | blue ACC | yellow cap | orange selected brake | red AEB | dashed stale/history'
    qp.drawText(rect.adjusted(12,rect.height()-25,-12,-3),Qt.TextFlag.TextWordWrap,legend)
    qp.restore()
