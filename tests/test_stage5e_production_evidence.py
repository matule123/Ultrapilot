"""Synthetic contract exercises ONLY; no artifacts/keys are installed as trust."""
from concurrent.futures import Future
from dataclasses import asdict, replace
import copy
import hashlib
import json
import struct
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core.navigation.production_evidence import (
    BODY_PROFILE_FRAME, BODY_PROFILE_UNITS, DIMENSIONS, EvidenceTrust,
    GroundReferenceProducer, bind_survey, canonical,
    compile_measured_profile, read_document, survey_scope, wheel_fingerprint,
)
from core.navigation.profile_catalog import GROUND_CHANNEL_CONTRACT
from core.navigation.evidence_worker import (
    EvidenceBundle, IDENTITY_KEYS, ProductionEvidenceWorker, ProductionPublicationSink,
    production_reference_rejection, state_identity,
)
from core.navigation.traffic_producer import (
    CompleteTrafficProducer, LegacyTrafficProducer, TrafficCapture, capture_traffic,
)
from core.navigation.tracking_evidence import TrackingRecorder, assess_tracking, capture_application
from core.navigation.drivable_surface import identity_fingerprint
from core.navigation.maneuver_reference import ManeuverReferenceMux
from core.navigation.maneuver_integration import GROUND_REFERENCE_FRAME
from core.sdk.ets2la_data import ETS2LAData, _TRAFFIC_FMT, _TRAFFIC_SIZE, _PARKED_SIZE
from core.sdk.existing_mapping import ExistingMapping
from core.swept_envelope import EnvelopeError
from core.vehicle_profile import configuration_fingerprint, fixed_axle_geometry
from tests.test_stage5b1_vehicle_profile import observation, entry, provider
from tests.maneuver_runtime_cases import runtime_request, clear_traffic, actor
from tools.manage_maneuver_evidence import authenticate, draft, KINDS

TEST_KEYS = {'test-only-never-installed': {'key_hex': '12'*32, 'enabled': True, 'kinds': KINDS}}


def artifact(kind, **fields):
    p = dict(schema_version=1, kind=kind, artifact_id='unit-test-only', revision=1,
             measurement_domain='ets2_measured', reviewed=True, confirmed=False,
             runtime_authorized=False, source='contract test, not real measurement',
             tool_version='test-v1', measured_at_utc='2026-09-14T00:00:00Z', confidence=1.,
             measurements=[{'name': 'measurement.txt', 'sha256': hashlib.sha256(b'test-only').hexdigest()}])
    p.update(fields)
    return EvidenceTrust(TEST_KEYS).verify(authenticate(p, TEST_KEYS, 'test-only-never-installed'), kind)


def measured_profile(o):
    row = entry(o)
    source_hash = hashlib.sha256(b'test-only').hexdigest()
    attached = tuple(a for a in o.articles if a.attached)
    for body, article in zip(row['bodies'], (a for a in o.articles if a.attached)):
        body.update(fixed_axle_local_m=list(fixed_axle_geometry(article).axle_local_m),
            dimension_uncertainty_m={k: .0001 for k in DIMENSIONS},
            dimension_provenance={k: {'method': 'physical_measurement',
                                      'source_sha256': source_hash} for k in DIMENSIONS},
            axle_position_uncertainty_m=.0001,
            body_width_without_mirrors_m=2.4,
            collision_width_components_complete=True,
            body_height_m=None)
    axles = [fixed_axle_geometry(a) for a in attached]
    return artifact('body_profile', status='confirmed', confirmed=True,
        units=BODY_PROFILE_UNITS,
        coordinate_frame=BODY_PROFILE_FRAME,
        configuration_fingerprint=configuration_fingerprint(o),
        wheel_fingerprint=wheel_fingerprint(o), article_ids=[a.vehicle_id for a in attached],
        article_slots=[a.slot for a in attached], chassis_configuration='measured-test-only',
        cabin_configuration='measured-cabin-test-only', mod_fingerprint='b'*64,
        accessory_fingerprint='a'*64, accessory_inventory_complete=True,
        compatibility={'game_id':'ets2','sdk_game_version':list(o.game_version),
                       'compatible_game_builds':['test-build-only']},
        provenance={'source_kind':'physical_measurement','source_sha256':source_hash,
                    'license':'test fixture','distribution':'measurement_metadata_only'},
        sdk_geometry={'wheelbase_m':axles[0].wheelbase_m,
                      'hitch_forward_m':[a.hook_forward_m for a in axles],
                      'comparison_uncertainty_m':.0001}, catalog_entry=row)


@pytest.fixture(scope='module')
def request5d():
    return runtime_request()


def bundle(r):
    context = r.result.context
    surface = r.surface_catalog.resolve(context.local_lane_path, context.identity, context.identity)
    return EvidenceBundle(1, state_identity(r.snapshot), 1_000_000, 10., 10.1, (), (),
        r.profile, r.ground, surface, clear_traffic(context.identity), r.tracking,
        context, r.surface_catalog, 'a'*64, r.result.plan.token, 'b'*64,
        tracking_calibration=(None,)*5)


@pytest.mark.parametrize('kind', KINDS)
def test_drafts_cannot_be_authenticated(kind):
    with pytest.raises(EnvelopeError):
        authenticate(draft(kind), TEST_KEYS, 'test-only-never-installed')


@pytest.mark.parametrize('change', ['payload', 'hash', 'signature', 'key', 'scope', 'domain'])
def test_authentication_rejects_tampering(change):
    a = artifact('body_profile')
    doc = authenticate(a.payload(), TEST_KEYS, 'test-only-never-installed')
    kind = 'body_profile'
    if change == 'payload': doc['payload']['revision'] += 1
    if change == 'hash': doc['sha256'] = '0'*64
    if change == 'signature': doc['hmac_sha256'] = '0'*64
    if change == 'key': doc['key_id'] = 'untrusted'
    if change == 'scope': kind = 'unknown'
    if change == 'domain':
        doc['payload']['measurement_domain'] = 'synthetic'
        with pytest.raises(EnvelopeError):
            authenticate(doc['payload'], TEST_KEYS, 'test-only-never-installed')
        return
    with pytest.raises(EnvelopeError): EvidenceTrust(TEST_KEYS).verify(doc, kind)
    with pytest.raises(EnvelopeError): EvidenceTrust().verify(doc, kind)


def test_measured_attachment_integrity_and_deadline(tmp_path):
    a = artifact('body_profile')
    path = tmp_path/'record.json'
    path.write_text(json.dumps(authenticate(a.payload(), TEST_KEYS, 'test-only-never-installed')))
    measure = tmp_path/'measurement.txt'
    measure.write_bytes(b'test-only')
    assert EvidenceTrust(TEST_KEYS).load(path, 'body_profile').sha256 == a.sha256
    with pytest.raises(EnvelopeError, match='DEADLINE'):
        EvidenceTrust(TEST_KEYS).load(path, 'body_profile', deadline=0.)
    measure.write_bytes(b'changed')
    with pytest.raises(EnvelopeError, match='INTEGRITY'):
        EvidenceTrust(TEST_KEYS).load(path, 'body_profile')


@pytest.mark.parametrize('text', ['{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}'])
def test_strict_document(text, tmp_path):
    path = tmp_path/'bad.json'; path.write_text(text)
    with pytest.raises(EnvelopeError): read_document(path)


@pytest.mark.parametrize('trailers', [0, 1, 3])
def test_profile_exact_articles_and_conservative_uncertainty(trailers):
    o = observation(trailers)
    a = measured_profile(o)
    profile = compile_measured_profile(a, o).update(o, 10.)
    assert len(profile.model.bodies) == trailers+1
    p = a.payload(); p['catalog_entry']['limits']['uncertainty_m'] = .0001
    with pytest.raises(EnvelopeError, match='UNCERTAINTY'):
        compile_measured_profile(artifact('body_profile', **{k:v for k,v in p.items() if k!='kind'}), o)


@pytest.mark.parametrize('field,value', [
    ('wheel_fingerprint','f'*64), ('configuration_fingerprint','f'*64),
    ('article_ids',['unknown']), ('article_slots',[9]),
    ('accessory_inventory_complete',False), ('accessory_fingerprint','unknown')])
def test_profile_unknown_configuration_never_qualifies(field, value):
    o = observation(); p = measured_profile(o).payload(); p[field] = value
    with pytest.raises(EnvelopeError):
        compile_measured_profile(artifact('body_profile', **{k:v for k,v in p.items() if k!='kind'}), o)


def test_ground_requires_atomic_contact_frame(request5d):
    o = observation(); prof = provider(o).update(o, 10.)
    a = artifact('ground_calibration')
    with pytest.raises(EnvelopeError, match='SDK_FRAME_NOT_ATOMIC'):
        GroundReferenceProducer().produce(prof, request5d.result.context.identity,
                                          bundle(request5d).surface, a, 10.)


@pytest.mark.parametrize('fault', [None,'contact','lift','tilt','deck','time','reused_frame'])
def test_calibrated_ground_transform_and_loss(request5d, fault):
    o=observation(); axle=fixed_axle_geometry(o.articles[0]).axle_local_m
    pose=request5d.result.plan.samples[0].frame.poses[0]
    cab=replace(o.articles[0],position_m=(pose.x,pose.y-axle[1],pose.z-axle[2]),rotation_rad=(0.,0.,0.))
    o=replace(o,atomic=True,articles=(cab,)+o.articles[1:])
    prof=provider(o).update(o,10.)
    surface=bundle(request5d).surface
    a=artifact('ground_calibration', status='confirmed', confirmed=True,
        units=BODY_PROFILE_UNITS,
        configuration_fingerprint=prof.token.configuration,
        coordinate_frame=GROUND_REFERENCE_FRAME,channel_contract=GROUND_CHANNEL_CONTRACT,
        profile_artifact_sha256='a'*64, support_surface_sha256=surface.evidence_sha256,
        articles=[{'slot':-1,'axle_local_m':list(axle),'position_uncertainty_m':.001,
                   'support_height_tolerance_m':.001,'ground_y_offset_m':0.,
                   'reference_pitch_rad':0.,'reference_roll_rad':0.,
                   'pitch_residual_bound_rad':0.,'roll_residual_bound_rad':0.,
                   'calibration_residual_m':0.,'sample_count':30,
                   'independent_sample_count':30,'sdk_frame_us_range':[1,30]}])
    g=GroundReferenceProducer(); ident=request5d.result.context.identity
    result=g.produce(prof,ident,surface,a,10.)
    assert result.sdk_frame_us==o.sdk_frame_us and result.frame.poses[0].y==surface.surface.y_m
    if fault is None: return
    if fault=='contact': cab=replace(cab,wheels=tuple(replace(w,on_ground=False) for w in cab.wheels))
    if fault=='lift': cab=replace(cab,wheels=tuple(replace(w,lift=1.) for w in cab.wheels))
    if fault=='tilt': cab=replace(cab,rotation_rad=(0.,.01,0.))
    if fault=='deck': cab=replace(cab,position_m=(pose.x,10.,pose.z))
    changed=replace(o,articles=(cab,)+o.articles[1:],captured_at=10.01 if fault=='reused_frame' else 10.)
    current=replace(prof,observation=changed,observed_at=changed.captured_at)
    with pytest.raises(EnvelopeError): g.produce(current,ident,surface,a,11. if fault=='time' else 10.01)


def survey_artifact(r):
    b = bundle(r); context = r.result.context; s = b.surface.surface
    return artifact('surface_survey', scope=survey_scope(context.local_lane_path, context.identity),
        method='independent_drivable_surface_survey_v1',
        survey_coverage={k: True for k in ('outer_boundary','islands','curbs','barriers',
                                         'fixed_obstacles','support_layer','interior_inspected')},
        surface={'horizontal':True, 'elevation_layer':context.local_lane_path.segments[0].elevation_layer,
                 'boundary_uncertainty_m':b.surface.boundary_uncertainty_m,
                 'exterior_xyz':[[x,s.y_m,z] for x,z in s.exterior],
                 'holes_xyz':[[[x,s.y_m,z] for x,z in ring] for ring in s.holes]})


def test_survey_preserves_geometry_and_holes(request5d):
    r = request5d; c = r.result.context
    result, _ = bind_survey(survey_artifact(r), c.local_lane_path, c.identity)
    expected=bundle(r).surface.surface
    assert result.surface.exterior == expected.exterior
    assert result.surface.holes == expected.holes
    assert result.surface.identity == expected.identity
    assert result.evidence_sha256 == survey_artifact(r).sha256


@pytest.mark.parametrize('change', ['layer','dataset','map_key','coverage','display'])
def test_surface_scope_and_complete_physical_boundary(request5d, change):
    r = request5d; c = r.result.context; p = survey_artifact(r).payload()
    if change in ('layer','dataset','map_key'): p['scope'][change] = 'other'
    elif change == 'coverage': p['survey_coverage']['curbs'] = False
    else: p['method'] = 'ppd_map_points'
    with pytest.raises(EnvelopeError):
        bind_survey(artifact('surface_survey', **{k:v for k,v in p.items() if k!='kind'}), c.local_lane_path,c.identity)


def test_open_missing_mapping_does_not_create_it():
    import uuid
    name = 'Local\\UltraPilot-Missing-Test-'+uuid.uuid4().hex
    with pytest.raises(OSError): ExistingMapping(name, 64)
    with pytest.raises(OSError): ExistingMapping(name, 64)


def test_sdk_reader_only_opens_existing_mapping():
    reader = ETS2LAData()
    with patch('core.sdk.ets2la_data.ExistingMapping', side_effect=OSError) as opening:
        reader._connect()
        assert opening.call_count == 3
        assert not reader.traffic_available


@pytest.mark.parametrize('case,status', [('absent','unavailable_buffer'),
    ('empty','readable_empty_unproven_coverage'), ('changing','incomplete_or_changing_buffers'),
    ('stale','stale_snapshot')])
def test_legacy_traffic_status_never_asserts_clear(case, status):
    capture = TrafficCapture('session',10.,bytes(_TRAFFIC_SIZE),bytes(_PARKED_SIZE),True)
    if case == 'absent': capture = replace(capture,moving=None,stable=False)
    if case == 'changing': capture = replace(capture,stable=False)
    value = LegacyTrafficProducer().produce(capture, 11. if case=='stale' else 10.)
    assert value.status == status and not value.complete and value.sensor_time_s is None


def test_raw_traffic_keeps_unknown_body_and_three_trailers():
    row = [0.]*12+[0,0,0,0]+[0.]*30
    row[0],row[12],row[13] = 3.,3,42
    rows = row+([0.]*12+[0,0,0,0]+[0.]*30)*39
    data = struct.pack(_TRAFFIC_FMT,*rows)
    capture = TrafficCapture('session',10.,data,bytes(_PARKED_SIZE),True)
    value = LegacyTrafficProducer().produce(capture,10.)
    assert len(value.actors[0].bodies)==4
    assert value.actors[0].bodies[0].dimensions_whl_m == (0.,0.,0.)
    assert value.status == 'unknown_actor_dimensions'
    assert not value.complete


def traffic_artifact(r, **changes):
    s = asdict(clear_traffic(r.result.context.identity))
    s.pop('identity'); s.pop('evidence_sha256'); s.pop('source')
    s.update(identity_sha256=identity_fingerprint(r.result.context.identity),
        clock_domain='host_monotonic',sensor_contract='complete_body_history_coverage_v1',
        all_entries_observed=True,history_includes_departed_actors=True,
        elevation_layer=r.result.context.identity.layer, actors=[])
    s.update(changes)
    return artifact('traffic_frame', **s)


def test_empty_complete_feed_needs_independent_coverage(request5d):
    c=CompleteTrafficProducer(); ident=request5d.result.context.identity
    valid=traffic_artifact(request5d)
    assert c.produce(valid,ident,10.).complete
    assert c.produce(valid,ident,10.).actors==()
    with pytest.raises(EnvelopeError): c.produce(traffic_artifact(request5d,complete=False),ident,10.)
    with pytest.raises(EnvelopeError): c.produce(traffic_artifact(request5d,sequence=0),ident,10.)
    with pytest.raises(EnvelopeError): c.produce(valid,ident,11.)


@pytest.mark.parametrize('field', IDENTITY_KEYS)
def test_production_receipt_rejects_every_navigation_identity(request5d, field):
    b=bundle(request5d); snap=dict(request5d.snapshot); snap[field]='changed'
    assert b.rejection(snap,1_000_000,10.)=='STALE_PRODUCTION_EVIDENCE_IDENTITY'


def test_lease_frame_loss_and_receipt_never_refresh(request5d):
    b=bundle(request5d); packet={'plan_token':b.plan_token,'production_evidence_receipt':b.receipt}
    state={'maneuver_production_evidence':b.lease(),'vehicle_profile_snapshot':request5d.profile}
    assert not production_reference_rejection(state,request5d.snapshot,packet,1_000_000,10.)
    assert b.rejection(request5d.snapshot,1_000_001,10.)=='STALE_PRODUCTION_EVIDENCE_FRAME'
    assert b.rejection(request5d.snapshot,1_000_000,10.1)=='EXPIRED_PRODUCTION_EVIDENCE'
    state['vehicle_profile_snapshot']=None
    assert production_reference_rejection(state,request5d.snapshot,packet,1_000_000,10.)
    state['maneuver_production_evidence']=None
    assert production_reference_rejection(state,request5d.snapshot,packet,1_000_000,10.)


def test_worker_bounded_stale_callback_and_shutdown(request5d):
    worker=ProductionEvidenceWorker(clock=lambda:10.)
    try:
        future=Future(); worker._future=future
        assert not worker.offer(None,None,{},None,None)
        future.set_result(bundle(request5d))
        result=worker.harvest(dict(request5d.snapshot,revision=999),1_000_000,10.)
        assert not result.ready and result.blockers==('STALE_PRODUCTION_EVIDENCE_IDENTITY',)
        worker.close()
        assert not worker.offer(None,None,{},None,None)
    finally: worker.close()


def test_unconfigured_worker_reports_real_missing_producers():
    worker=ProductionEvidenceWorker(clock=lambda:10.)
    try:
        b=worker._produce(None,None,{},None,None,None,1,None)
        assert not b.ready
        assert 'MISSING_CONFIRMED_BODY_PROFILE' in b.blockers
        assert 'MISSING_COMPLETE_TRAFFIC_HISTORY_COVERAGE_AND_BODY_PRODUCER' in b.blockers
        assert 'MISSING_VALIDATED_EXECUTION_TRACKING_BOUND' in b.blockers
    finally: worker.close()


class State(dict):
    def set(self, key, value): self[key]=value

    def update_batch(self, values):
        self.calls=getattr(self,'calls',0)+1; self.update(values)


def test_atomic_production_publication_and_revoke(request5d):
    b=bundle(request5d)
    state=State(lane_trajectory=request5d.snapshot,telemetry={'truck':{'sdkFrameTimeUs':1_000_000}})
    sink=ProductionPublicationSink(state,clock=lambda:10.); sink.bind(b)
    sink.update_batch({'maneuver_reference_packet':{'plan_token':b.plan_token},
                       'maneuver_approach_packet':{'state':'WAITING_FOR_TRAFFIC'},
                       'maneuver_runtime_status':{'state':'WAITING_FOR_TRAFFIC'}})
    assert state.calls==1 and state['maneuver_production_evidence'] == b.lease()
    assert state['maneuver_reference_packet']['production_evidence_receipt']==b.receipt
    sink.update_batch({'maneuver_reference_packet':{},'maneuver_approach_packet':{},'maneuver_runtime_status':{}})
    assert state.calls==2 and state['maneuver_production_evidence'] is None


def test_loss_during_execution_latches_mux_without_global_jump():
    mux=ManeuverReferenceMux()
    try:
        mux._active_token='executing'
        result=mux.reject_production_evidence('LOST_SURFACE')
        assert result.route is None and not result.authority_valid and mux._faulted
    finally: mux.close()


def test_backend_capture_preserves_missing_data_and_no_synthetic_qualification(request5d):
    row=capture_application({'ctl_steering':.2},.18,10.,1)
    assert row['engine_steer']==.18 and row['steer_out']==.2
    assert row['ground_frame'] is None and row['game_steer'] is None
    with pytest.raises(EnvelopeError,match='INCOMPLETE_APPLIED_TRACKING_CHANNELS'):
        assess_tracking([row]*30,request5d.result.plan,request5d.profile,bundle(request5d).surface)


def test_tracking_bounded_export_is_unqualified(tmp_path):
    recorder=TrackingRecorder(2)
    for i in range(3): recorder.append({'application_sequence':i})
    path=tmp_path/'tracking.json'; assert recorder.export(path)==2
    value=json.loads(path.read_text())
    assert value['dropped_samples']==1
    assert value['qualification']=='UNQUALIFIED_RAW_MEASUREMENT'


def test_producers_do_not_create_another_controller():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    for filename in ('production_evidence','traffic_producer','tracking_evidence','evidence_worker'):
        code=(root/'core/navigation'/f'{filename}.py').read_text()
        assert '.set_steering(' not in code and '.set_throttle(' not in code and '.set_brake(' not in code
        assert 'SteeringDynamics(' not in code and 'SteeringExecutor(' not in code


@pytest.mark.parametrize('manual', [True,False])
def test_engine_final_boundary_manual_and_missing_evidence(manual):
    from tests.test_stage4d_control_timing import EngineRealtimeBoundaryTests
    state=State(autopilot_active=not manual,telemetry_valid=True,
        active_navigation_reference={'mode':'local_maneuver','authority_valid':True},
        maneuver_production_evidence=object(),ctl_steering=.2,ctl_throttle=1.,ctl_brake=0.)
    e=EngineRealtimeBoundaryTests.bare_engine(state)
    e.controller=EngineRealtimeBoundaryTests.FakeController()
    e._was_active=True; e._last_output_steering=.2
    e._flush_controls_unlocked()
    assert state['maneuver_production_evidence'] is None
    assert state['maneuver_reference_packet']=={}
    if manual: assert e.controller.steering_writes==[]
    else:
        assert 0. <= e.controller.steering_writes[-1] < .2
        assert state['ctl_throttle']==0.


def test_executor_diagnostic_binding_does_not_change_output():
    from core.steering_executor import SteeringExecutor
    a=SteeringExecutor(clock=lambda:10.); b=SteeringExecutor(clock=lambda:10.)
    source={'calculation_sequence':42,'reference_mode':'local_maneuver'}
    a.submit(.1,speed_ms=2.,source_packet=source)
    b.submit(.1,speed_ms=2.)
    source['calculation_sequence']=99
    assert a.step(.02,now=10.)==b.step(.02,now=10.)
    assert a.last_debug['source_packet']['calculation_sequence']==42


def test_tracking_evaluator_measures_entry_curve_exit_without_granting_authority(request5d):
    from core.navigation.maneuver_runtime import execution_timing
    r=request5d; plan=r.result.plan
    timing=execution_timing(plan,10.,plan.speed_mps,r.tracking)
    rows=[]
    for i,sample in enumerate(plan.samples):
        now=timing.times_s[i]; steer=sample.tyre_rad/.78
        rows.append(dict(measurement_domain='ets2_backend_observation',backend_sent=True,
            calculation_binding_proven=True,sdk_frame_us=1_000_000+round((now-10.)*1e6),
            application_sequence=i+1,observed_at_s=now,applied_at_s=now,
            steer_raw=steer,steer_out=steer,engine_steer=steer,game_steer=-steer,
            speed_mps=plan.speed_mps,yaw_rate_rad_s=plan.speed_mps*sample.curvature_right_m_inv,
            local_cte_m=0.,heading_error_rad=0.,curvature_reference=sample.curvature_right_m_inv,
            actuator_delay_s=0.,steering_gain_rad=.78,tyre_angles_rad=(sample.tyre_rad,),
            articulation_rad=sample.frame.poses[0].heading-sample.frame.poses[-1].heading,
            plan_token=plan.token,profile_configuration=r.profile.token.configuration,
            ground_frame=replace(sample.frame,time_s=now),ground_uncertainty_m=.001,
            reference_mode='local_maneuver',planned_point=(sample.frame.poses[0].x,sample.frame.poses[0].z),
            planned_tangent=sample.frame.poses[0].heading,execution_start_s=10.,initial_speed_mps=plan.speed_mps))
    report=assess_tracking(rows,plan,r.profile,bundle(r).surface,timing=timing)
    assert report['accepted'] and not report['production_authorized']
    assert report['minimum_swept_clearance_m']>0
    rows[0]['measurement_domain']='synthetic'
    with pytest.raises(EnvelopeError,match='NOT_REAL_LOCAL'):
        assess_tracking(rows,plan,r.profile,bundle(r).surface,timing=timing)
