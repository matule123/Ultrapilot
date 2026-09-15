"""Narrow regressions for portable Phase 5E profile evidence.

All dimensions and trust keys are synthetic fixtures.  Nothing in this file is
a certificate for a real ETS2 vehicle.
"""
from dataclasses import replace
import copy
import json
from types import SimpleNamespace

import pytest

from core.navigation.profile_catalog import (
    BODY_PROFILE_FRAME, BODY_PROFILE_UNITS, BodyProfileCatalog,
    validate_ground_calibration_payload, validate_profile_payload,
)
from core.navigation.production_evidence import EvidenceTrust, compile_measured_profile
from core.navigation.evidence_worker import ProductionEvidenceWorker
from core.swept_envelope import EnvelopeError
from tests.test_stage5b1_vehicle_profile import observation
from tests.test_stage5e_production_evidence import TEST_KEYS, artifact, measured_profile
from tools.manage_maneuver_evidence import authenticate, draft, transition_profile


def changed_artifact(original, mutate):
    payload = original.payload()
    mutate(payload)
    return artifact('body_profile', **{key: value for key, value in payload.items()
                                      if key != 'kind'})


def test_valid_explicit_profile_uses_only_existing_vehicle_model():
    observed = observation()
    profile = compile_measured_profile(measured_profile(observed), observed).update(observed, 10.)
    assert profile.model is not None
    assert profile.model.bodies[0].width_m == 2.5
    assert profile.live_maneuver_ready is False


@pytest.mark.parametrize(('field', 'value', 'reason'), [
    ('units', {'length': 'cm', 'angle': 'rad'}, 'UNSUPPORTED_BODY_PROFILE_UNITS'),
    ('coordinate_frame', 'visual_model_bbox', 'UNSUPPORTED_BODY_PROFILE_FRAME'),
])
def test_units_and_axes_are_exact(field, value, reason):
    payload = measured_profile(observation()).payload()
    payload[field] = value
    with pytest.raises(EnvelopeError, match=reason):
        validate_profile_payload(payload, observation(), usable=True)


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -1., True])
def test_nonfinite_negative_and_boolean_dimensions_are_rejected(value):
    payload = measured_profile(observation()).payload()
    payload['catalog_entry']['bodies'][0]['front_m'] = value
    with pytest.raises(EnvelopeError, match='INVALID_BODY_PROFILE_DIMENSIONS'):
        validate_profile_payload(payload, observation(), usable=True)


def test_wheel_track_cannot_claim_body_width():
    payload = measured_profile(observation()).payload()
    payload['catalog_entry']['bodies'][0]['dimension_provenance']['width_m']['method'] = 'sdk_wheel_track'
    with pytest.raises(EnvelopeError, match='WHEEL_TRACK_IS_NOT_BODY_WIDTH'):
        validate_profile_payload(payload, observation(), usable=True)


def test_wrong_cabin_or_chassis_binding_never_falls_back():
    observed = observation()
    profile = measured_profile(observed)
    catalog = BodyProfileCatalog((profile,))
    for field in ('cabin_configuration', 'chassis_configuration'):
        binding = {
            'cabin_configuration': profile.payload()['cabin_configuration'],
            'chassis_configuration': profile.payload()['chassis_configuration'],
            'accessory_fingerprint': profile.payload()['accessory_fingerprint'],
            'mod_fingerprint': profile.payload()['mod_fingerprint'],
        }
        binding[field] = 'other'
        with pytest.raises(EnvelopeError, match='MISSING_CONFIRMED_BODY_PROFILE'):
            catalog.select(observed, binding)


def test_same_vehicle_name_with_different_mod_or_accessories_is_ambiguous():
    observed = observation()
    first = measured_profile(observed)
    second = changed_artifact(first, lambda payload: payload.update(
        artifact_id='second', mod_fingerprint='c'*64,
        accessory_fingerprint='d'*64))
    catalog = BodyProfileCatalog((first, second))
    with pytest.raises(EnvelopeError, match='AMBIGUOUS_CONFIRMED_BODY_PROFILE'):
        catalog.select(observed)
    selected = catalog.select(observed, {
        'cabin_configuration': second.payload()['cabin_configuration'],
        'chassis_configuration': second.payload()['chassis_configuration'],
        'accessory_fingerprint': second.payload()['accessory_fingerprint'],
        'mod_fingerprint': second.payload()['mod_fingerprint'],
    })
    assert selected.sha256 == second.sha256


def test_worker_uses_full_configuration_when_selecting_profile():
    observed = observation()
    profile = measured_profile(observed)
    binding = {name: profile.payload()[name] for name in (
        'cabin_configuration', 'chassis_configuration',
        'accessory_fingerprint', 'mod_fingerprint')}
    selected_with = []

    class Catalog:
        def select(self, _observation, configuration_evidence=None):
            selected_with.append(configuration_evidence)
            raise EnvelopeError('TEST_STOP_AFTER_EXACT_SELECTION')

    class Trust:
        def load(self, _path, kind, **_options):
            assert kind == 'configuration_frame'
            return SimpleNamespace(payload=lambda: copy.deepcopy(binding))

    worker = ProductionEvidenceWorker(
        {'configuration_frame_file': 'synthetic-config'}, clock=lambda: 10.)
    try:
        worker._load = lambda: None
        worker._trust = Trust()
        worker._profile_catalog = Catalog()
        source = SimpleNamespace(observation=observed,
                                 observed_at=observed.captured_at,
                                 token=SimpleNamespace(configuration='unused'))
        worker._produce(None, None, {}, source, None, None, 1, None)
        assert selected_with == [binding]
    finally:
        worker.close()


@pytest.mark.parametrize('field', ['wheelbase_m', 'hitch_forward_m'])
def test_sdk_wheelbase_and_hitch_conflict_is_fail_closed(field):
    observed = observation()
    payload = measured_profile(observed).payload()
    if field == 'wheelbase_m':
        payload['sdk_geometry'][field] += .5
    else:
        payload['sdk_geometry'][field][0] += .5
    with pytest.raises(EnvelopeError, match='PROFILE_SDK_GEOMETRY_CONFLICT'):
        validate_profile_payload(payload, observed, usable=True)


def test_configuration_change_invalidates_profile():
    original = observation()
    changed = observation(1)
    with pytest.raises(EnvelopeError, match='MEASURED_PROFILE_CONFIGURATION_MISMATCH'):
        validate_profile_payload(measured_profile(original).payload(), changed, usable=True)


def test_revocation_removes_exact_artifact_from_catalog():
    observed = observation()
    confirmed = measured_profile(observed)
    payload = confirmed.payload()
    payload.update(status='revoked', confirmed=False, revokes_sha256=confirmed.sha256,
                   revocation_reason='synthetic regression')
    revoked = artifact('body_profile', **{key: value for key, value in payload.items()
                                         if key != 'kind'})
    catalog = BodyProfileCatalog((confirmed, revoked))
    with pytest.raises(EnvelopeError, match='MISSING_CONFIRMED_BODY_PROFILE'):
        catalog.select(observed)
    with pytest.raises(EnvelopeError, match='REVOKED_BODY_PROFILE'):
        validate_profile_payload(revoked.payload(), observed, usable=True)


def test_candidate_never_compiles_or_authorizes_runtime():
    observed = observation()
    payload = measured_profile(observed).payload()
    payload.update(status='candidate', reviewed=False, confirmed=False)
    candidate = SimpleNamespace(kind='body_profile',
                                payload=lambda: copy.deepcopy(payload), sha256='e'*64)
    with pytest.raises(EnvelopeError, match='BODY_PROFILE_NOT_CONFIRMED'):
        compile_measured_profile(candidate, observed)
    assert payload['runtime_authorized'] is False


def test_profile_document_cannot_grant_runtime_authority():
    payload = measured_profile(observation()).payload()
    payload['runtime_authorized'] = True
    with pytest.raises(EnvelopeError, match='BODY_PROFILE_CANNOT_AUTHORIZE_RUNTIME'):
        validate_profile_payload(payload, observation(), usable=True)


def test_profile_transfer_verifies_on_second_directory(tmp_path):
    observed = observation()
    verified = measured_profile(observed)
    document = authenticate(verified.payload(), TEST_KEYS, 'test-only-never-installed')
    transfer = tmp_path/'second-pc'
    transfer.mkdir()
    (transfer/'profile.json').write_text(json.dumps(document), encoding='utf-8')
    (transfer/'measurement.txt').write_bytes(b'test-only')
    loaded = EvidenceTrust(TEST_KEYS).load(transfer/'profile.json', 'body_profile')
    selected = BodyProfileCatalog((loaded,)).select(observed)
    assert compile_measured_profile(selected, observed).update(observed, 10.).model is not None


def test_lifecycle_is_immutable_and_cannot_skip_review():
    payload = measured_profile(observation()).payload()
    payload.update(status='reviewed', confirmed=False)
    confirmed = transition_profile(payload, 'confirmed', 'reviewer', 'synthetic review')
    assert confirmed['revision'] == payload['revision'] + 1
    assert payload['status'] == 'reviewed'
    revoked = transition_profile(confirmed, 'revoked', 'reviewer', 'synthetic revoke',
                                 revoked_sha256='e'*64)
    assert revoked['status'] == 'revoked'
    with pytest.raises(ValueError, match='INVALID_BODY_PROFILE_STATUS_TRANSITION'):
        transition_profile(draft('body_profile'), 'confirmed', 'reviewer', 'skip')


def test_ground_contract_rejects_stale_or_unbounded_candidate():
    payload = draft('ground_calibration')
    payload.update(status='confirmed', reviewed=True, confirmed=True,
        configuration_fingerprint='a'*64, profile_artifact_sha256='b'*64,
        support_surface_sha256='c'*64, coordinate_frame='ETS2_WORLD_FIXED_AXLE_GROUND',
        articles=[{'slot':-1, 'axle_local_m':[0., .5, 2.],
            'sample_count':30, 'independent_sample_count':30,
            'sdk_frame_us_range':[1,30], 'ground_y_offset_m':-.5,
            'reference_pitch_rad':0., 'reference_roll_rad':0.,
            'pitch_residual_bound_rad':.01, 'roll_residual_bound_rad':0.,
            'calibration_residual_m':.001, 'support_height_tolerance_m':.002,
            'position_uncertainty_m':.002}])
    with pytest.raises(EnvelopeError, match='GROUND_UNCERTAINTY_OMITS_TILT'):
        validate_ground_calibration_payload(payload, usable=True)
    payload['articles'][0]['position_uncertainty_m'] = .023
    validate_ground_calibration_payload(payload, usable=True)


def test_ground_projection_covers_static_attitude_and_full_lever_arm():
    payload = draft('ground_calibration')
    payload.update(status='confirmed', reviewed=True, confirmed=True,
        configuration_fingerprint='a'*64, profile_artifact_sha256='b'*64,
        support_surface_sha256='c'*64,
        coordinate_frame='ETS2_WORLD_FIXED_AXLE_GROUND',
        articles=[{'slot':-1, 'axle_local_m':[0., .5, 2.],
            'sample_count':30, 'independent_sample_count':30,
            'sdk_frame_us_range':[1,30], 'ground_y_offset_m':-.5,
            'reference_pitch_rad':.005, 'reference_roll_rad':0.,
            'pitch_residual_bound_rad':.002, 'roll_residual_bound_rad':0.,
            'calibration_residual_m':.001, 'support_height_tolerance_m':.002,
            'position_uncertainty_m':.01}])
    with pytest.raises(EnvelopeError, match='GROUND_UNCERTAINTY_OMITS_TILT'):
        validate_ground_calibration_payload(payload, usable=True)
    payload['articles'][0]['position_uncertainty_m'] = .017
    validate_ground_calibration_payload(payload, usable=True)


def test_ground_document_cannot_grant_runtime_authority():
    payload = draft('ground_calibration')
    payload['runtime_authorized'] = True
    with pytest.raises(EnvelopeError, match='GROUND_CALIBRATION_CANNOT_AUTHORIZE_RUNTIME'):
        validate_ground_calibration_payload(payload)


def test_unmeasured_cab_template_is_not_a_profile():
    candidate = draft('body_profile')
    assert candidate['status'] == 'candidate' and candidate['reviewed'] is False
    with pytest.raises(EnvelopeError):
        validate_profile_payload(candidate, usable=True)
