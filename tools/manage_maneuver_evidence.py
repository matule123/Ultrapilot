"""Offline 5E measurement drafts and authenticated import validation.

Never writes settings or installs artifacts. A draft is deliberately rejected
until an operator supplies actual measurements and independently reviews them.
HMAC is local authentication, not a public-key signature or measurement truth.
"""
import argparse
import copy
import hashlib
import hmac
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.navigation.production_evidence import EvidenceTrust, canonical, read_document
from core.navigation.profile_catalog import (
    BODY_PROFILE_FRAME, BODY_PROFILE_UNITS, GROUND_CHANNEL_CONTRACT,
    validate_ground_calibration_payload, validate_profile_payload,
)
from core.swept_envelope import require

KINDS = ('body_profile', 'ground_calibration', 'surface_survey', 'traffic_frame',
         'configuration_frame', 'tracking_run')


def draft(kind):
    value = {'schema_version': 1, 'kind': kind, 'artifact_id': None, 'revision': 1,
             'measurement_domain': 'UNMEASURED_DRAFT', 'reviewed': False,
             'confirmed': False, 'runtime_authorized': False,
             'source': None, 'tool_version': None, 'measured_at_utc': None,
             'confidence': None, 'measurements': []}
    if kind == 'body_profile':
        value.update(status='candidate', units=BODY_PROFILE_UNITS,
            coordinate_frame=BODY_PROFILE_FRAME,
            configuration_fingerprint=None, wheel_fingerprint=None,
            article_ids=[], article_slots=[], chassis_configuration=None,
            cabin_configuration=None, mod_fingerprint=None,
            accessory_fingerprint=None, accessory_inventory_complete=False,
            compatibility={'game_id': 'ets2', 'sdk_game_version': [],
                           'compatible_game_builds': []},
            provenance={'source_kind': None, 'source_sha256': None,
                        'license': None, 'distribution': None},
            sdk_geometry={'wheelbase_m': None, 'hitch_forward_m': [],
                          'comparison_uncertainty_m': None},
            catalog_entry={'bodies': [], 'limits': {}})
    elif kind == 'surface_survey':
        value.update(method='independent_drivable_surface_survey_v1',
            scope={'map_key': None, 'dataset': None, 'layer': None,
                   'geometry_sha256': None, 'lanes': [], 'gps_pairs': []},
            survey_coverage={k: False for k in ('outer_boundary', 'islands', 'curbs',
                'barriers', 'fixed_obstacles', 'support_layer', 'interior_inspected')},
            surface={'horizontal': None, 'elevation_layer': None,
                     'boundary_uncertainty_m': None, 'exterior_xyz': [], 'holes_xyz': []})
    elif kind == 'ground_calibration':
        value.update(status='candidate', units=BODY_PROFILE_UNITS,
            configuration_fingerprint=None, coordinate_frame=None,
            channel_contract=GROUND_CHANNEL_CONTRACT,
            profile_artifact_sha256=None, support_surface_sha256=None,
            articles=[])
    elif kind == 'configuration_frame':
        value.update(session=None, sdk_frame_us=None, observed_at_s=None,
            configuration_fingerprint=None, chassis_configuration=None,
            cabin_configuration=None, mod_fingerprint=None,
            accessory_fingerprint=None, inventory_complete=False,
            operating_conditions_fingerprint=None, load_and_actuator_domain_confirmed=False)
    elif kind == 'traffic_frame':
        value.update(identity_sha256=None, clock_domain=None, sensor_contract=None,
            all_entries_observed=False, history_includes_departed_actors=False,
            elevation_layer=None, actors=[], snapshot_id=None, sequence=None,
            observed_at_s=None, valid_until_s=None, coverage_xz=[], complete=False,
            unseen_speed_bound_mps=None, coverage_since_s=None)
    else:
        value.update(samples_sha256=None, plan_token=None, surface_token=None,
            profile_configuration=None, corner_bound_m=None, time_bound_s=None,
            speed_bound_mps=None, execution_start_s=None, initial_speed_mps=None,
            actuator_calibration=None, operating_conditions_fingerprint=None)
    return value


def transition_profile(payload, target_status, reviewer, reason,
                       *, revoked_sha256=None):
    """Create an immutable next lifecycle revision; callers write a new file."""
    if type(payload) is not dict or payload.get('kind') != 'body_profile':
        raise ValueError('PROFILE_TRANSITION_REQUIRES_BODY_PROFILE')
    current = payload.get('status')
    allowed = {'candidate': 'reviewed', 'reviewed': 'confirmed',
               'confirmed': 'revoked'}
    if allowed.get(current) != target_status:
        raise ValueError('INVALID_BODY_PROFILE_STATUS_TRANSITION')
    if not isinstance(reviewer, str) or not reviewer.strip() or not isinstance(reason, str) or not reason.strip():
        raise ValueError('MISSING_PROFILE_REVIEW_RECORD')
    value = copy.deepcopy(payload)
    value['revision'] = int(value.get('revision', 0)) + 1
    value['status'] = target_status
    value['reviewed'] = target_status in ('reviewed', 'confirmed', 'revoked')
    value['confirmed'] = target_status == 'confirmed'
    value['runtime_authorized'] = False
    value['review_record'] = {'reviewer': reviewer, 'reason': reason}
    if target_status == 'reviewed':
        validate_profile_payload(value)
    elif target_status == 'confirmed':
        validate_profile_payload(value, usable=True)
    else:
        if not isinstance(revoked_sha256, str):
            raise ValueError('MISSING_REVOKED_PROFILE_HASH')
        value['revokes_sha256'] = revoked_sha256
        value['revocation_reason'] = reason
        validate_profile_payload(value)
    return value


def authenticate(payload, keys, key_id):
    require(payload.get('kind') in KINDS, 'UNKNOWN_EVIDENCE_KIND')
    key = bytes.fromhex(keys[key_id]['key_hex'])
    sha = hashlib.sha256(canonical(payload)).hexdigest()
    document = {'schema_version': 1, 'key_id': key_id, 'sha256': sha, 'payload': payload}
    document['hmac_sha256'] = hmac.new(key, canonical(document), hashlib.sha256).hexdigest()
    # Reject unreviewed drafts, wrong key scope, and synthetic measurement domain.
    EvidenceTrust(keys).verify(document, payload['kind'])
    return document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('draft')
    create.add_argument('kind', choices=KINDS)
    create.add_argument('--output', required=True)
    verify = commands.add_parser('verify')
    verify.add_argument('path')
    verify.add_argument('--kind', required=True, choices=KINDS)
    verify.add_argument('--trust', required=True)
    sign = commands.add_parser('authenticate')
    sign.add_argument('payload')
    sign.add_argument('--trust', required=True)
    sign.add_argument('--key-id', required=True)
    sign.add_argument('--output', required=True)
    transition = commands.add_parser('transition-profile')
    transition.add_argument('payload')
    transition.add_argument('--status', required=True,
                            choices=('reviewed', 'confirmed', 'revoked'))
    transition.add_argument('--reviewer', required=True)
    transition.add_argument('--reason', required=True)
    transition.add_argument('--revoked-sha256')
    transition.add_argument('--output', required=True)
    args = parser.parse_args()
    if args.command == 'verify':
        artifact = EvidenceTrust(read_document(args.trust)).load(args.path, args.kind)
        print(json.dumps({'authenticated': True, 'runtime_authorized': False,
                          'kind': artifact.kind, 'sha256': artifact.sha256}))
        return
    if args.command == 'draft':
        value = draft(args.kind)
    elif args.command == 'transition-profile':
        value = transition_profile(read_document(args.payload), args.status,
            args.reviewer, args.reason, revoked_sha256=args.revoked_sha256)
    else:
        payload = read_document(args.payload)
        if payload.get('kind') == 'body_profile':
            validate_profile_payload(payload, usable=payload.get('status') == 'confirmed')
        elif payload.get('kind') == 'ground_calibration':
            validate_ground_calibration_payload(payload, usable=True)
        value = authenticate(payload, read_document(args.trust), args.key_id)
    # Never overwrite a measurement or a previously authenticated artifact.
    with Path(args.output).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
    print('Created offline artifact; runtime authorization remains unchanged.')


if __name__ == '__main__':
    main()
