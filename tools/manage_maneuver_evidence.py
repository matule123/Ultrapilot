"""Offline 5E measurement drafts and authenticated import validation.

Never writes settings or installs artifacts. A draft is deliberately rejected
until an operator supplies actual measurements and independently reviews them.
HMAC is local authentication, not a public-key signature or measurement truth.
"""
import argparse
import hashlib
import hmac
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.navigation.production_evidence import EvidenceTrust, canonical, read_document
from core.swept_envelope import require

KINDS = ('body_profile', 'ground_calibration', 'surface_survey', 'traffic_frame',
         'configuration_frame', 'tracking_run')


def draft(kind):
    value = {'schema_version': 1, 'kind': kind, 'artifact_id': None, 'revision': 1,
             'measurement_domain': 'UNMEASURED_DRAFT', 'reviewed': False,
             'source': None, 'tool_version': None, 'measured_at_utc': None,
             'confidence': None, 'measurements': []}
    if kind == 'body_profile':
        value.update(configuration_fingerprint=None, wheel_fingerprint=None,
            article_ids=[], article_slots=[], chassis_configuration=None,
            accessory_fingerprint=None, accessory_inventory_complete=False,
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
        value.update(configuration_fingerprint=None, coordinate_frame=None,
                     channel_contract=None, articles=[])
    elif kind == 'configuration_frame':
        value.update(session=None, sdk_frame_us=None, observed_at_s=None,
            configuration_fingerprint=None, chassis_configuration=None,
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
    args = parser.parse_args()
    if args.command == 'verify':
        artifact = EvidenceTrust(read_document(args.trust)).load(args.path, args.kind)
        print(json.dumps({'authenticated': True, 'runtime_authorized': False,
                          'kind': artifact.kind, 'sha256': artifact.sha256}))
        return
    value = (draft(args.kind) if args.command == 'draft' else
             authenticate(read_document(args.payload), read_document(args.trust), args.key_id))
    # Never overwrite a measurement or a previously authenticated artifact.
    with Path(args.output).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
    print('Created offline artifact; runtime authorization remains unchanged.')


if __name__ == '__main__':
    main()
