"""Offline Phase 5F compiler for explicitly supplied normalized collision data.

No native PMC decoder has been verified. Consequently ALL outputs remain
candidates, even when synthetic or externally supplied geometry is complete.
Raw SDK poses/times are never included in the portable cache. No controls.
"""
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import tempfile
import time

from core.navigation.production_evidence import canonical
from core.navigation.profile_catalog import BODY_PROFILE_FRAME, BODY_PROFILE_UNITS, DIMENSIONS, wheel_fingerprint
from core.swept_envelope import EnvelopeError, finite, require
from core.vehicle_assets import asset_path
from core.vehicle_profile import configuration_fingerprint, fixed_axle_geometry

COMPILER_VERSION = '5f-candidate-1'
MAX_EXPORT_POINTS = 100000


def sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def vector(value):
    require(isinstance(value, (list, tuple)) and len(value) == 3
            and finite(*value) and all(abs(v) <= 1000 for v in value),
            'INVALID_ASSET_VECTOR')
    return value


def transform_points(points, transform):
    """target = translation + R * (scale * (point - source_pivot)).

    Both coordinate systems must be explicitly right-handed X right/Y up/Z
    back. Other source conventions require a separately proven converter.
    R must be a proper orthonormal rotation; reflections/shear are rejected.
    """
    t = transform
    require(t.get('units') == 'm' and t.get('source_axes') == 'X_RIGHT_Y_UP_Z_BACK'
            and t.get('target_axes') == 'X_RIGHT_Y_UP_Z_BACK'
            and t.get('handedness') == 'right', 'UNPROVEN_ASSET_FRAME')
    scale = t.get('scale')
    require(finite(scale) and 0 < scale <= 100, 'INVALID_ASSET_SCALE')
    require(isinstance(t.get('provenance_sha256'), str)
            and len(t['provenance_sha256']) == 64
            and all(c in '0123456789abcdef' for c in t['provenance_sha256']),
            'MISSING_TRANSFORM_PROVENANCE')
    require(finite(t.get('uncertainty_m')) and .0001 <= t['uncertainty_m'] <= .25,
            'INVALID_TRANSFORM_UNCERTAINTY')
    r = t.get('rotation')
    require(type(r) is list and len(r) == 3, 'INVALID_ASSET_ROTATION')
    for row in r:
        vector(row)
    for i in range(3):
        for j in range(3):
            require(abs(sum(r[i][k]*r[j][k] for k in range(3)) - (i == j)) < 1e-9,
                    'NONORTHOGONAL_ASSET_ROTATION')
    det = (r[0][0]*(r[1][1]*r[2][2]-r[1][2]*r[2][1])
           - r[0][1]*(r[1][0]*r[2][2]-r[1][2]*r[2][0])
           + r[0][2]*(r[1][0]*r[2][1]-r[1][1]*r[2][0]))
    require(abs(det-1) < 1e-9, 'ASSET_HANDEDNESS_MISMATCH')
    pivot, translation = vector(t.get('pivot')), vector(t.get('translation'))
    require(isinstance(points, (list, tuple)) and 0 < len(points) <= MAX_EXPORT_POINTS,
            'INVALID_COLLISION_VERTEX_COUNT')
    out = []
    for p in points:
        vector(p)
        q = [translation[i] + sum(r[i][j]*scale*(p[j]-pivot[j]) for j in range(3))
             for i in range(3)]
        vector(q)
        out.append(q)
    return out


def compile_candidate(observation, manifest, resolver, exports, limits, *, timeout_s=30.):
    """Deterministic conservative geometry, without claiming asset authenticity.

    ``manifest`` must come from a future complete configuration-event producer
    or an independently bound configuration export. A saved game or old log
    alone is not sufficient. This function never upgrades that evidence.
    """
    require(finite(timeout_s) and 0 < timeout_s <= 120, 'INVALID_COMPILER_DEADLINE')
    deadline = time.monotonic() + timeout_s
    require(type(exports) is list and len(exports) <= 256
            and sum(len(e.get('vertices', [])) for e in exports) <= MAX_EXPORT_POINTS,
            'COLLISION_EXPORT_BUDGET_EXCEEDED')
    attached = tuple(a for a in observation.articles if a.attached)
    package_receipts = list(resolver.receipts)
    inputs = {'compiler': COMPILER_VERSION, 'manifest': manifest,
              'packages_low_to_high': package_receipts, 'exports': exports,
              'sdk_configuration': configuration_fingerprint(observation), 'limits': limits}
    fingerprint = sha(inputs)
    blockers = ['MISSING_VERIFIED_COLLISION_DECODER', 'MISSING_ATOMIC_ACTIVE_ASSET_BINDING']
    p = {'schema_version': 1, 'kind': 'body_profile', 'artifact_id': fingerprint,
        'revision': 1, 'compiler_version': COMPILER_VERSION,
        'status': 'candidate', 'reviewed': False, 'confirmed': False,
        'runtime_authorized': False, 'measurement_domain': 'UNVERIFIED_ASSET_EXPORT',
        'source': 'offline SCS asset candidate compiler', 'tool_version': COMPILER_VERSION,
        'asset_fingerprint': fingerprint, 'configuration_fingerprint': configuration_fingerprint(observation),
        'wheel_fingerprint': wheel_fingerprint(observation),
        'units': dict(BODY_PROFILE_UNITS), 'coordinate_frame': BODY_PROFILE_FRAME,
        'article_ids': [a.vehicle_id for a in attached], 'article_slots': [a.slot for a in attached],
        'cabin_configuration': None, 'chassis_configuration': None,
        'accessory_fingerprint': sha(manifest.get('articles', [])),
        'mod_fingerprint': sha(package_receipts), 'accessory_inventory_complete': False,
        'compatibility': {'game_id': 'ets2', 'sdk_game_version': list(observation.game_version),
                          'compatible_game_builds': [manifest.get('game_build')]},
        'provenance': {'source_kind': 'unverified_collision_export',
                       'source_sha256': fingerprint, 'license': 'source-specific; not redistributed',
                       'distribution': 'measurement_metadata_only'},
        'source_receipts': package_receipts, 'definition_receipts': [],
        'catalog_entry': {'bodies': [], 'limits': dict(limits)},
        'sdk_geometry': {}, 'geometry_complete': False, 'blockers': blockers}
    try:
        require(observation.stable_read and not observation.failure_reason,
                'UNSTABLE_SDK_CONFIGURATION')
        require(1 <= len(attached) <= 5 and attached[0].slot == -1, 'UNSUPPORTED_ARTICLE_COUNT')
        require(manifest.get('schema_version') == 1 and manifest.get('inventory_complete') is True
                and manifest.get('configuration_fingerprint') == configuration_fingerprint(observation),
                'INCOMPLETE_ACTIVE_CONFIGURATION')
        require(manifest.get('load_order') == [x['package'] for x in package_receipts]
                and bool(manifest.get('game_build')) and type(manifest.get('dlc')) is list,
                'UNPROVEN_PACKAGE_ORDER_OR_GAME_VERSION')
        articles = manifest.get('articles')
        require(type(articles) is list and len(articles) == len(attached), 'ARTICLE_ORDER_MISMATCH')
        require(type(exports) is list and len(exports) <= 256, 'INVALID_COLLISION_EXPORTS')
        require(len({(e['slot'], e['asset']) for e in exports}) == len(exports),
                'DUPLICATE_COLLISION_COMPONENT')
        require(all(e['slot'] in p['article_slots'] for e in exports), 'UNKNOWN_EXPORT_ARTICLE')
        bodies, axles = [], []
        for a, config in zip(attached, articles):
            require(time.monotonic() < deadline, 'COMPILER_DEADLINE_EXCEEDED')
            require(config.get('slot') == a.slot and config.get('vehicle_id') == a.vehicle_id,
                    'ARTICLE_ORDER_MISMATCH')
            require(config.get('accessories_complete') is True and config.get('chassis')
                    and (a.slot != -1 or config.get('cabin')), 'INCOMPLETE_ARTICLE_ACCESSORIES')
            require(not any(w.liftable for w in a.wheels), 'UNSUPPORTED_LIFTABLE_AXLE')
            axle = fixed_axle_geometry(a)
            axles.append(axle)
            graph = resolver.definition_graph(config.get('definitions'))
            p['definition_receipts'].append({'slot': a.slot, **graph})
            required_assets = set(graph['collision_assets'])
            components = [e for e in exports if e['slot'] == a.slot]
            require(required_assets and {asset_path(e['asset']) for e in components} == required_assets,
                    'MISSING_OR_UNRESOLVED_COLLISION_COMPONENT')
            points, errors, outgoing = [], [], []
            for component in components:
                require(time.monotonic() < deadline, 'COMPILER_DEADLINE_EXCEEDED')
                require(component.get('kind') == 'collision' and component.get('all_parts') is True,
                        'RENDER_OR_PARTIAL_GEOMETRY_IS_NOT_COLLISION')
                asset = resolver.resolve(component['asset'])
                require(asset.path.endswith(('.pmc', '.pic')) and asset.sha256 == component.get('asset_sha256'),
                        'COLLISION_ASSET_HASH_MISMATCH')
                require(bool(component.get('variant')), 'UNPROVEN_COLLISION_VARIANT')
                t = component['transform']
                vertices = transform_points(component['vertices'], t)
                require(len(vertices) >= 4, 'INCOMPLETE_COLLISION_VERTICES')
                geometry_error, motion = component.get('uncertainty_m'), component.get('motion_bound_m')
                require(finite(geometry_error, motion) and .0001 <= geometry_error <= .25
                        and 0 <= motion <= .25 and component.get('motion_bound_proven') is True,
                        'UNBOUNDED_COLLISION_MOTION_OR_UNCERTAINTY')
                error = geometry_error*t['scale'] + t['uncertainty_m'] + motion
                require(error <= .25, 'ASSET_UNCERTAINTY_EXCEEDED')
                wheels = transform_points(component['wheel_anchors'], t)
                require(len(wheels) == len(a.wheels), 'ASSET_WHEEL_COUNT_MISMATCH')
                for xyz, w in zip(wheels, a.wheels):
                    require(math.dist(xyz, w.position_m) <= geometry_error + t['uncertainty_m'],
                            'ASSET_WHEEL_SDK_CONFLICT')
                hook = transform_points([component['hook_local_m']], t)[0]
                require(math.dist(hook, a.hook_local_m) <= geometry_error + t['uncertainty_m'],
                        'ASSET_HITCH_SDK_CONFLICT')
                axle_point = transform_points([component['axle_local_m']], t)[0]
                require(math.dist(axle_point, axle.axle_local_m) <= geometry_error + t['uncertainty_m'],
                        'ASSET_AXLE_SDK_CONFLICT')
                out = transform_points([component['outgoing_hook_local_m']], t)[0]
                require(abs(out[0] - axle.axle_local_m[0]) <= .0001,
                        'UNSUPPORTED_OFF_AXIS_OUTGOING_HITCH')
                outgoing.append(axle.axle_local_m[2] - out[2])
                points.extend(vertices); errors.append(error)
            require(max(outgoing)-min(outgoing) <= .0001, 'INCONSISTENT_OUTGOING_HITCH')
            x, _, z = axle.axle_local_m
            err = max(errors)
            # Symmetric rectangle contains asymmetric accessories as well.
            width = 2*max(abs(v[0]-x) for v in points)
            front, rear = z-min(v[2] for v in points), max(v[2] for v in points)-z
            require(0 < width <= 5 and 0 < front <= 25 and 0 <= rear <= 15,
                    'INVALID_COMPILED_BODY_DIMENSIONS')
            require(width >= axle.track_m, 'BODY_NARROWER_THAN_WHEEL_CENTRES')
            require(-rear <= outgoing[0] <= front
                    and (a.slot == -1 or 0 < axle.hook_forward_m <= front),
                    'COMPILED_HITCH_OUTSIDE_BODY')
            require(a.slot != -1 or front >= axle.wheelbase_m,
                    'BODY_DOES_NOT_COVER_FRONT_AXLE')
            bodies.append({'slot': a.slot, 'axle_model': 'fixed_axle',
                'fixed_axle_local_m': list(axle.axle_local_m), 'width_m': width,
                'front_m': front, 'rear_m': rear,
                'hitch_front_m': 0. if a.slot == -1 else axle.hook_forward_m,
                'hitch_rear_m': axle.hook_forward_m if a.slot == -1 else outgoing[0],
                'body_width_without_mirrors_m': None,
                'body_height_m': max(v[1] for v in points)-min(v[1] for v in points),
                'collision_width_components_complete': False,
                'dimension_uncertainty_m': {key: 2*err if key == 'width_m' else err for key in DIMENSIONS},
                'dimension_provenance': {key: {'method': 'unverified_collision_export',
                                              'source_sha256': fingerprint} for key in DIMENSIONS},
                'axle_position_uncertainty_m': err})
        p['catalog_entry']['bodies'] = bodies
        total_error = sum(sum(b['dimension_uncertainty_m'].values())
                          + b['axle_position_uncertainty_m'] for b in bodies)
        p['required_uncertainty_m'] = total_error
        if not finite(limits.get('uncertainty_m')) or limits['uncertainty_m'] < total_error:
            blockers.append('CONFIGURED_UNCERTAINTY_BELOW_ASSET_BUDGET')
        p['cabin_configuration'] = articles[0]['cabin']
        p['chassis_configuration'] = articles[0]['chassis']
        p['sdk_geometry'] = {'wheelbase_m': axles[0].wheelbase_m,
                            'hitch_forward_m': [a.hook_forward_m for a in axles],
                            'comparison_uncertainty_m': max(b['axle_position_uncertainty_m'] for b in bodies)}
        p['geometry_complete'] = True
        blockers.extend(['UNVERIFIED_SII_UNIT_VARIANT_AND_ATTACHMENT_SEMANTICS',
                         'MISSING_BODY_WIDTH_WITHOUT_MIRRORS_PROOF'])
    except (EnvelopeError, KeyError, TypeError, ValueError, IndexError, AttributeError) as error:
        blockers.append(str(error) if isinstance(error, EnvelopeError)
                        else 'INVALID_COMPILER_INPUT:' + type(error).__name__)
    p['blockers'] = sorted(set(blockers))
    return p


class ProfileCache:
    """Authenticated candidate cache. The key is local trust, not a proof source.

    Readers supply the freshly rebuilt exact asset fingerprint. No raw poses,
    wall-clock timestamps or mutable runtime authority are cached.
    """
    def __init__(self, directory, key):
        require(type(key) is bytes and len(key) >= 32, 'INVALID_CACHE_KEY')
        self.directory, self.key = Path(directory), key

    def _path(self, fingerprint):
        require(type(fingerprint) is str and len(fingerprint) == 64
                and all(c in '0123456789abcdef' for c in fingerprint), 'INVALID_CACHE_FINGERPRINT')
        return self.directory / (fingerprint + '.json')

    def put(self, profile):
        require(profile.get('status') == 'candidate' and profile.get('confirmed') is False
                and profile.get('runtime_authorized') is False, 'CACHE_CANNOT_AUTHORIZE_PROFILE')
        path = self._path(profile['asset_fingerprint'])
        doc = {'profile': profile, 'sha256': sha(profile)}
        doc['hmac_sha256'] = hmac.new(self.key, canonical(doc), hashlib.sha256).hexdigest()
        raw = canonical(doc)
        require(len(raw) <= 4*1024*1024, 'CACHE_PROFILE_TOO_LARGE')
        self.directory.mkdir(parents=True, exist_ok=True)
        if path.exists():
            require(self.get(profile['asset_fingerprint']) == profile, 'CACHE_COLLISION')
            return path
        fd, temporary = tempfile.mkstemp(prefix='.candidate-', dir=self.directory)
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(raw); f.flush(); os.fsync(f.fileno())
            # Hard-link publication refuses replacement and is atomic on NTFS.
            os.link(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return path

    def get(self, fingerprint):
        path = self._path(fingerprint)
        require(path.is_file() and path.stat().st_size <= 4*1024*1024, 'MISSING_OR_STALE_PROFILE_CACHE')
        try:
            doc = json.loads(path.read_bytes())
            sig = doc.pop('hmac_sha256')
            require(hmac.compare_digest(sig, hmac.new(self.key, canonical(doc), hashlib.sha256).hexdigest()),
                    'CACHE_AUTHENTICATION_FAILED')
            p = doc['profile']
            require(doc['sha256'] == sha(p) and p['asset_fingerprint'] == fingerprint
                    and p['compiler_version'] == COMPILER_VERSION, 'STALE_OR_CORRUPT_PROFILE_CACHE')
            require(p['status'] == 'candidate' and p['confirmed'] is False
                    and p['runtime_authorized'] is False, 'CACHE_CANNOT_AUTHORIZE_PROFILE')
            return p
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, EnvelopeError):
                raise
            raise EnvelopeError('INVALID_PROFILE_CACHE') from error
