"""5E authenticated measurement imports. No controller or guessed geometry.

HMAC-SHA256 authenticates locally administered survey/catalog records; it is
not a public-key signature and cannot attest that a measurement was truthful.
Keys are supplied separately by the operator, never generated or trusted by an
imported document. Authenticity AND domain validation are mandatory.
All file I/O, hashing and geometry validation belong to a bounded worker.
"""
from dataclasses import asdict, dataclass, replace
import hashlib
import hmac
import json
import math
import time
from pathlib import Path

from core.navigation.drivable_surface import (
    COORDINATE_FRAME, DrivableSurfaceCatalog, build_confirmed_surface,
    digest, identity_fingerprint, lane_path_fingerprint,
)
from core.navigation.maneuver_integration import (
    GROUND_REFERENCE_FRAME, GroundReferenceEvidence,
)
from core.swept_envelope import EnvelopeError, Frame, Pose, finite, require, clearance
from core.vehicle_profile import (
    VehicleProfileProvider, configuration_fingerprint, fixed_axle_geometry,
)

MAX_ARTIFACT_BYTES = 4 * 1024 * 1024
MAX_CATALOG_RECORDS = 128
DIMENSIONS = ('width_m', 'front_m', 'rear_m', 'hitch_front_m', 'hitch_rear_m')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')


def _object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'DUPLICATE_EVIDENCE_JSON_KEY')
        result[key] = value
    return result


def read_document(path, *, max_bytes=MAX_ARTIFACT_BYTES):
    require(type(max_bytes) is int and 1 <= max_bytes <= 32*1024*1024,
            'INVALID_EVIDENCE_READ_BOUND')
    with Path(path).open('rb') as stream:
        raw = stream.read(max_bytes + 1)
    require(len(raw) <= max_bytes, 'EVIDENCE_ARTIFACT_TOO_LARGE')
    return json.loads(raw, object_pairs_hook=_object,
                      parse_constant=lambda _: (_ for _ in ()).throw(
                          EnvelopeError('NONFINITE_EVIDENCE_JSON')))


@dataclass(frozen=True)
class VerifiedArtifact:
    kind: str
    artifact_id: str
    revision: int
    sha256: str
    key_id: str
    payload_json: str

    def payload(self):
        return json.loads(self.payload_json)


class EvidenceTrust:
    """Operator-configured, kind-scoped keys; no trust-on-first-use."""
    def __init__(self, keys=None):
        self._keys = {}
        for key_id, row in (keys or {}).items():
            key = bytes.fromhex(row['key_hex'])
            require(len(key) >= 32 and row.get('enabled') is True,
                    'INVALID_EVIDENCE_TRUST_KEY')
            self._keys[str(key_id)] = (key, tuple(row['kinds']))

    def verify(self, document, kind):
        require(type(document) is dict
                and set(document) == {'schema_version', 'key_id', 'payload',
                                     'sha256', 'hmac_sha256'}
                and type(document['schema_version']) is int
                and document['schema_version'] == 1,
                'INVALID_SIGNED_EVIDENCE_SCHEMA')
        key_id = document['key_id']
        require(key_id in self._keys, 'UNTRUSTED_EVIDENCE_SIGNER')
        key, kinds = self._keys[key_id]
        require(kind in kinds, 'EVIDENCE_SIGNER_KIND_NOT_ALLOWED')
        payload = document['payload']
        raw = canonical(payload)
        require(len(raw) <= MAX_ARTIFACT_BYTES, 'EVIDENCE_ARTIFACT_TOO_LARGE')
        sha = hashlib.sha256(raw).hexdigest()
        require(hmac.compare_digest(sha, str(document['sha256'])),
                'EVIDENCE_INTEGRITY_MISMATCH')
        signed = canonical({'schema_version': 1, 'key_id': key_id,
                            'sha256': sha, 'payload': payload})
        require(hmac.compare_digest(hmac.new(key, signed, hashlib.sha256).hexdigest(),
                                    str(document['hmac_sha256'])),
                'EVIDENCE_AUTHENTICATION_FAILED')
        require(type(payload) is dict and payload.get('kind') == kind
                and payload.get('schema_version') == 1
                and type(payload.get('schema_version')) is int
                and type(payload.get('revision')) is int and payload['revision'] > 0
                and bool(payload.get('artifact_id')),
                'INVALID_EVIDENCE_PAYLOAD')
        require(payload.get('measurement_domain') == 'ets2_measured'
                and payload.get('reviewed') is True
                and bool(payload.get('source')) and bool(payload.get('tool_version'))
                and bool(payload.get('measured_at_utc')),
                'UNREVIEWED_OR_SYNTHETIC_EVIDENCE')
        require(finite(payload.get('confidence'))
                and .99 <= payload['confidence'] <= 1.,
                'INSUFFICIENT_EVIDENCE_CONFIDENCE')
        attachments = payload.get('measurements')
        require(type(attachments) is list and 1 <= len(attachments) <= 64,
                'MISSING_MEASUREMENT_ARTIFACTS')
        for row in attachments:
            require(type(row) is dict and bool(row.get('name'))
                    and type(row.get('sha256')) is str
                    and len(row['sha256']) == 64
                    and all(c in '0123456789abcdef' for c in row['sha256']),
                    'INVALID_MEASUREMENT_ARTIFACT')
        return VerifiedArtifact(kind, str(payload['artifact_id']),
                                payload['revision'], sha, key_id,
                                raw.decode('utf-8'))

    def load(self, path, kind, *, deadline=None, clock=time.monotonic):
        """Verify the authenticated document and its actual measurement files."""
        artifact = self.verify(read_document(path), kind)
        root = Path(path).resolve().parent
        deadline = clock()+10. if deadline is None else deadline
        total_bytes = 0
        for row in artifact.payload()['measurements']:
            require(clock() < deadline, 'EVIDENCE_IMPORT_DEADLINE_EXCEEDED')
            target = (root / row['name']).resolve()
            require(target.is_relative_to(root) and target != Path(path).resolve(),
                    'MEASUREMENT_PATH_ESCAPES_ARTIFACT_DIRECTORY')
            require(target.is_file() and target.stat().st_size <= 32*1024*1024,
                    'MISSING_OR_OVERSIZED_MEASUREMENT_FILE')
            total_bytes += target.stat().st_size
            require(total_bytes <= 32*1024*1024, 'EVIDENCE_ATTACHMENTS_TOO_LARGE')
            with target.open('rb') as stream:
                hasher = hashlib.sha256()
                count = 0
                while chunk := stream.read(65536):
                    count += len(chunk)
                    require(count <= 32*1024*1024 and clock() < deadline,
                            'EVIDENCE_IMPORT_DEADLINE_EXCEEDED')
                    hasher.update(chunk)
                sha = hasher.hexdigest()
            require(hmac.compare_digest(sha, row['sha256']),
                    'MEASUREMENT_FILE_INTEGRITY_MISMATCH')
        return artifact


def wheel_fingerprint(observation):
    return digest([{'slot': a.slot, 'id': a.vehicle_id,
                    'wheels': [(w.index, w.position_m, w.radius_m, w.steerable,
                                w.simulated, w.powered, w.liftable) for w in a.wheels]}
                   for a in observation.articles if a.attached])


def compile_measured_profile(artifact, observation):
    """Adapter into the existing 5B1 model, with per-dimension error bounds."""
    require(artifact.kind == 'body_profile', 'WRONG_PROFILE_ARTIFACT_KIND')
    p = artifact.payload()
    articles = tuple(a for a in observation.articles if a.attached)
    require(p.get('configuration_fingerprint') == configuration_fingerprint(observation)
            and p.get('wheel_fingerprint') == wheel_fingerprint(observation)
            and p.get('article_ids') == [a.vehicle_id for a in articles]
            and p.get('article_slots') == [a.slot for a in articles]
            and bool(p.get('chassis_configuration')),
            'MEASURED_PROFILE_CONFIGURATION_MISMATCH')
    require(type(p.get('accessory_fingerprint')) is str
            and len(p['accessory_fingerprint']) == 64
            and all(c in '0123456789abcdef' for c in p['accessory_fingerprint'])
            and p.get('accessory_inventory_complete') is True,
            'UNPROVEN_FULL_ACCESSORY_CONFIGURATION')
    entry = p.get('catalog_entry')
    require(type(entry) is dict and len(entry.get('bodies', ())) == len(articles),
            'MISSING_ARTICLE_BODY_PROFILE')
    definitions = entry['bodies']
    total_error = 0.
    for article, definition in zip(articles, definitions):
        axle = fixed_axle_geometry(article)  # never average tandems/lifted axles
        require(definition.get('fixed_axle_local_m') == list(axle.axle_local_m),
                'MEASURED_FIXED_AXLE_MISMATCH')
        errors = definition.get('dimension_uncertainty_m', {})
        require(set(errors) == set(DIMENSIONS)
                and all(finite(v) and .0001 <= v <= .25 for v in errors.values()),
                'MISSING_DIMENSION_UNCERTAINTY')
        require(finite(definition.get('axle_position_uncertainty_m'))
                and .0001 <= definition['axle_position_uncertainty_m'] <= .25,
                'MISSING_AXLE_POSITION_UNCERTAINTY')
        # Sum across the chain is deliberately conservative for hitch errors.
        total_error += sum(errors.values()) + definition['axle_position_uncertainty_m']
    entry = json.loads(json.dumps(entry))
    entry.update(schema_version=1, confirmed=True, source=p['source'],
                 evidence_sha256=artifact.sha256,
                 configuration_fingerprint=p['configuration_fingerprint'])
    require(finite(entry.get('limits', {}).get('uncertainty_m'))
            and entry['limits']['uncertainty_m'] >= total_error,
            'PROFILE_UNCERTAINTY_DOES_NOT_COVER_MEASUREMENTS')
    provider = VehicleProfileProvider({'schema_version': 1, 'profiles': [entry]})
    profile = provider.update(observation, observation.captured_at)
    require(profile.model is not None, profile.model_failure)
    return provider


def survey_scope(lane_path, identity):
    """Persistent survey scope omits transient session/revision, not geometry.

    Binding still creates the ordinary exact 5B2 identity/path tokens each run.
    GPS occurrence order and every XYZ source point remain in the scope hash.
    """
    path = replace(lane_path, revision=0)
    return {'map_key': identity.map_key, 'dataset': identity.dataset,
            'layer': identity.layer, 'geometry_sha256': lane_path_fingerprint(path),
            'lanes': [list(l.sort_key()) for l in identity.lanes],
            'gps_pairs': [list(pair) for pair in identity.gps_pairs]}


def bind_survey(artifact, lane_path, identity):
    require(artifact.kind == 'surface_survey', 'WRONG_SURVEY_ARTIFACT_KIND')
    p = artifact.payload()
    require(canonical(p.get('scope')) == canonical(survey_scope(lane_path, identity)),
            'SURVEY_SCOPE_MISMATCH')
    require(p.get('method') == 'independent_drivable_surface_survey_v1',
            'UNIMPLEMENTED_COLLISION_EXPORT_PROOF')
    coverage = p.get('survey_coverage', {})
    require(all(coverage.get(k) is True for k in (
        'outer_boundary', 'islands', 'curbs', 'barriers', 'fixed_obstacles',
        'support_layer', 'interior_inspected')),
        'SURVEY_OBSTACLE_COVERAGE_INCOMPLETE')
    record = dict(p['surface'])
    record.update(schema_version=1, confirmed=True, method=p['method'],
                  source=p['source'], evidence_sha256=artifact.sha256,
                  coordinate_frame=COORDINATE_FRAME,
                  identity_fingerprint=identity_fingerprint(identity),
                  lane_path_fingerprint=lane_path_fingerprint(lane_path))
    snapshot = build_confirmed_surface(record, lane_path, identity, identity)
    require(snapshot.surface is not None, snapshot.failure_reason)
    return snapshot, DrivableSurfaceCatalog({'schema_version': 1, 'surfaces': [record]})


class GroundReferenceProducer:
    """Calibrated fixed axle transform; legacy non-atomic SDK never qualifies."""
    def __init__(self):
        self._last = None
        self._digest = None

    def produce(self, profile, identity, surface, calibration, now):
        require(calibration is not None and calibration.kind == 'ground_calibration',
                'MISSING_FIXED_AXLE_GROUND_REFERENCE_PRODUCER')
        p = calibration.payload()
        o = profile.observation
        require(o is not None and profile.model is not None
                and not profile.observation_failure and not profile.model_failure,
                'MISSING_CONFIRMED_BODY_PROFILE')
        require(o.atomic is True and o.stable_read is True,
                'SDK_FRAME_NOT_ATOMIC_OR_CHANNEL_VALIDATED')
        require(p.get('configuration_fingerprint') == profile.token.configuration
                and p.get('coordinate_frame') == GROUND_REFERENCE_FRAME
                and p.get('channel_contract') == 'atomic_pose_contact_frame_v1',
                'GROUND_CALIBRATION_CONFIGURATION_MISMATCH')
        require(finite(now) and 0 <= now-profile.observed_at < .1,
                'STALE_LIVE_GROUND_REFERENCE')
        require(surface.surface is not None and surface.surface.identity == identity,
                'MISSING_CONFIRMED_DRIVABLE_SURFACE_PRODUCER')
        key = (identity.session, profile.token.configuration, o.sdk_frame_us, profile.observed_at)
        stamp = digest(asdict(o))
        if self._last is not None:
            require(key[:2] == self._last[:2], 'GROUND_SESSION_OR_CONFIGURATION_CHANGED')
            require(key[2] >= self._last[2] and key[3] >= self._last[3],
                    'REGRESSING_GROUND_SDK_FRAME')
            require(key[2] != self._last[2] or (stamp == self._digest and key[3] == self._last[3]),
                    'REUSED_SDK_FRAME_WITH_CHANGED_GROUND')
        rows = p.get('articles', [])
        attached = tuple(a for a in o.articles if a.attached)
        require(len(rows) == len(attached), 'MISSING_ARTICLE_GROUND_CALIBRATION')
        poses, uncertainty = [], 0.
        for a, row in zip(attached, rows):
            axle = fixed_axle_geometry(a)
            require(row.get('slot') == a.slot and row.get('axle_local_m') == list(axle.axle_local_m),
                    'GROUND_AXLE_CALIBRATION_MISMATCH')
            error = row.get('position_uncertainty_m')
            tolerance = row.get('support_height_tolerance_m')
            require(finite(error, tolerance) and .0001 <= tolerance <= error <= .25,
                    'INVALID_GROUND_REFERENCE_UNCERTAINTY')
            h, pitch, roll = a.rotation_rad
            require(pitch == 0. and roll == 0., 'UNSUPPORTED_BODY_TILT')
            x, y, z = axle.axle_local_m
            c, s = math.cos(h), math.sin(h)
            wx, wz = a.position_m[0]+x*c+z*s, a.position_m[2]-x*s+z*c
            offsets = row.get('ground_y_offset_m')
            require(finite(offsets), 'MISSING_MEASURED_GROUND_OFFSET')
            support_y = a.position_m[1]+y+offsets
            require(abs(support_y-surface.surface.y_m) <= tolerance,
                    'GROUND_SUPPORT_ELEVATION_MISMATCH')
            require(clearance(((wx-error,wz-error),(wx+error,wz-error),
                               (wx+error,wz+error),(wx-error,wz+error)), surface.surface) > 0,
                    'GROUND_SUPPORT_OUTSIDE_CONFIRMED_SURFACE')
            # Projection onto a measured horizontal deck is explicit and its
            # measured residual is bounded; no chassis Y is called ground Y.
            poses.append(Pose(wx, surface.surface.y_m, wz, h))
            uncertainty = max(uncertainty, error)
        frame = Frame(profile.observed_at, identity, tuple(poses))
        frame.validate(profile.model)
        result = GroundReferenceEvidence(1, p['source'], calibration.sha256,
            'scs_wheel_contact_ground_projection_v1', GROUND_REFERENCE_FRAME,
            True, profile.token, o.sdk_frame_us, profile.observed_at, frame, uncertainty)
        result.validate(profile, identity)
        self._last, self._digest = key, stamp
        return result
