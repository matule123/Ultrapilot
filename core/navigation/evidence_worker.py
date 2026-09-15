"""5E bounded production evidence owner; never writes actuator requests.

One in-flight operation, no hidden queue. Geometry, disk, authentication and
profile lookup are off the Map/Engine control tick. Results are immutable;
harvest checks current identity and frame without refreshing their timestamp.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
import time

from core.navigation.drivable_surface import digest
from core.navigation.maneuver_integration import build_maneuver_route_context, _sensitive
from core.navigation.production_evidence import (
    BodyProfileCatalog, EvidenceTrust, GroundReferenceProducer, bind_survey,
    compile_measured_profile, read_document,
)
from core.navigation.traffic_producer import CompleteTrafficProducer, LegacyTrafficProducer
from core.navigation.tracking_evidence import qualify_tracking, calibration_binding
from core.swept_envelope import EnvelopeError, finite, require

EVIDENCE_DEADLINE_S = .1
IDENTITY_KEYS = ('navigation_intent_id', 'route_build_id', 'revision',
                 'source_game_session_id', 'source_map_key', 'source_dataset_fingerprint')


def state_identity(snapshot):
    return tuple((snapshot or {}).get(k) for k in IDENTITY_KEYS)


@dataclass(frozen=True)
class EvidenceLease:
    """Constant-size IPC receipt; geometry never crosses the control boundary."""
    sequence: int
    identity: tuple
    sdk_frame_us: int
    observed_at: float
    valid_until: float
    receipt: str
    plan_token: str
    profile_configuration: str
    tracking_calibration: tuple
    operating_conditions: str = ''

    def rejection(self, snapshot, sdk_frame_us, now):
        if self.identity != state_identity(snapshot):
            return 'STALE_PRODUCTION_EVIDENCE_IDENTITY'
        if self.sdk_frame_us != sdk_frame_us:
            return 'STALE_PRODUCTION_EVIDENCE_FRAME'
        if not finite(now) or not self.observed_at <= now < self.valid_until:
            return 'EXPIRED_PRODUCTION_EVIDENCE'
        if (not self.receipt or not self.plan_token or not self.profile_configuration
                or not 0 < self.valid_until-self.observed_at <= .1+1e-12):
            return 'INCOMPLETE_PRODUCTION_EVIDENCE'
        return ''


@dataclass(frozen=True)
class EvidenceBundle:
    sequence: int
    identity: tuple
    sdk_frame_us: int
    observed_at: float
    valid_until: float
    blockers: tuple
    metrics: tuple
    profile: object = None
    ground: object = None
    surface: object = None
    traffic: object = None
    tracking: object = None
    context: object = None
    surface_catalog: object = None
    receipt: str = ''
    plan_token: str = ''
    configuration_confirmation_source: str = ''
    legacy_traffic: object = None
    tracking_calibration: tuple = ()
    operating_conditions: str = ''

    @property
    def ready(self):
        return (not self.blockers and len(self.receipt) == 64 and bool(self.plan_token)
                and bool(self.configuration_confirmation_source)
                and self.sdk_frame_us > 0 and all(v is not None for v in (
            self.profile, self.ground, self.surface, self.traffic, self.tracking,
            self.context, self.surface_catalog)))

    def rejection(self, snapshot, sdk_frame_us, now):
        if self.identity != state_identity(snapshot):
            return 'STALE_PRODUCTION_EVIDENCE_IDENTITY'
        if self.sdk_frame_us != sdk_frame_us:
            return 'STALE_PRODUCTION_EVIDENCE_FRAME'
        if not finite(now) or not self.observed_at <= now < self.valid_until:
            return 'EXPIRED_PRODUCTION_EVIDENCE'
        return self.blockers[0] if self.blockers else ('' if self.ready else 'INCOMPLETE_PRODUCTION_EVIDENCE')

    def diagnostic(self):
        return {'schema_version': 1, 'sequence': self.sequence,
                'runtime_activation_ready': self.ready,
                'blockers': list(self.blockers), 'sdk_frame_us': self.sdk_frame_us,
                'observed_at': self.observed_at, 'valid_until': self.valid_until,
                'latencies_s': dict(self.metrics), 'receipt': self.receipt,
                'plan_token': self.plan_token, 'identity': self.identity}

    def lease(self):
        require(self.ready, 'INCOMPLETE_PRODUCTION_EVIDENCE')
        return EvidenceLease(self.sequence, self.identity, self.sdk_frame_us,
            self.observed_at, self.valid_until, self.receipt, self.plan_token,
            self.profile.token.configuration, self.tracking_calibration, self.operating_conditions)


class ProductionEvidenceWorker:
    def __init__(self, config=None, *, clock=time.monotonic):
        self.config = dict(config or {})
        self.clock = clock
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='maneuver-evidence')
        self._future = None
        self._sequence = 0
        self._closed = False
        self._ground = GroundReferenceProducer()
        self._traffic = CompleteTrafficProducer()
        self._legacy = LegacyTrafficProducer()
        self._profile_provider = None
        self._profile_catalog = None
        self._active_profile_artifact = None
        self._profile_key = None
        self._artifacts = {}
        self._loaded = False
        self._load_failure = ''
        self._last_context = None
        self._last_offer = None
        self._deadline = None
        self._tracking_cache = None
        self._surface_cache = None
        self._trust_fingerprint = None

    def close(self):
        self._closed = True
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _load(self):
        # Cold import is a separate bounded preparation job. Even if successful,
        # its old SDK frame cannot gain an execution lease after the I/O wait.
        import_deadline = self.clock()+5.
        try:
            path = self.config.get('trust_file')
            keys = read_document(path) if path else {}
            fingerprint = digest(keys)
            if self._loaded and fingerprint == self._trust_fingerprint:
                return
            self._loaded = True
            self._trust_fingerprint = fingerprint
            self._artifacts = {}
            self._profile_catalog = None
            self._active_profile_artifact = None
            self._load_failure = ''
            self._profile_key = self._surface_cache = self._tracking_cache = None
            self._trust = EvidenceTrust(keys)
            files = self.config.get('artifacts', {})
            require(type(files) is dict and len(files) <= 16, 'INVALID_EVIDENCE_ARTIFACT_CONFIG')
            for kind, path in files.items():
                self._artifacts[kind] = self._trust.load(path, kind, deadline=import_deadline, clock=self.clock)
            catalog_paths = self.config.get('body_profile_catalog_files', []) or []
            require(type(catalog_paths) is list and len(catalog_paths) <= 128,
                    'INVALID_BODY_PROFILE_CATALOG_CONFIG')
            catalog_artifacts = ([self._artifacts['body_profile']]
                if 'body_profile' in self._artifacts else [])
            for profile_path in catalog_paths:
                catalog_artifacts.append(self._trust.load(
                    profile_path, 'body_profile', deadline=import_deadline,
                    clock=self.clock))
            if catalog_artifacts:
                self._profile_catalog = BodyProfileCatalog(catalog_artifacts)
        except (EnvelopeError, OSError, ValueError, TypeError, KeyError) as error:
            self._artifacts = {}
            self._loaded = False
            self._load_failure = str(error)

    def offer(self, network, lane_path, snapshot, observed_profile, traffic_capture,
              target_segment_index=None, *, tracking_plan=None):
        """Constant-size hand-off of immutable objects, at most one task."""
        if self._closed or self._future is not None:
            return False
        key = (state_identity(snapshot), getattr(getattr(observed_profile, 'observation', None),
                                                'sdk_frame_us', 0))
        if key == self._last_offer:
            return False
        self._last_offer = key
        self._sequence += 1
        self._future = self._executor.submit(
            self._produce, network, lane_path, dict(snapshot), observed_profile,
            traffic_capture, target_segment_index, self._sequence, tracking_plan)
        return True

    def harvest(self, snapshot, sdk_frame_us, now):
        future = self._future
        if future is None or not future.done():
            return None
        self._future = None
        try:
            result = future.result()
        except Exception as error:
            return EvidenceBundle(self._sequence, state_identity(snapshot), sdk_frame_us,
                                  now, now, ('PRODUCTION_EVIDENCE_WORKER_FAILED:'+type(error).__name__,), ())
        reason = result.rejection(snapshot, sdk_frame_us, now)
        if reason and not result.blockers:
            return replace(result, blockers=(reason,))
        if result.identity != state_identity(snapshot) or result.sdk_frame_us != sdk_frame_us:
            return replace(result, blockers=(reason,))
        return result

    def _produce(self, network, lane_path, snapshot, observed, capture, target, sequence, plan):
        started = self.clock()
        self._deadline = started+EVIDENCE_DEADLINE_S
        blockers, metrics = [], []
        profile = ground = surface = traffic = tracking = context = catalog = legacy = None
        confirmation_source = ''
        operating_conditions = ''
        now = self.clock()
        observed_at = getattr(observed, 'observed_at', now)
        observation = getattr(observed, 'observation', None)
        frame = getattr(observation, 'sdk_frame_us', 0)

        def run(name, operation):
            begin = self.clock()
            try:
                require(self.clock() < self._deadline, 'PRODUCTION_EVIDENCE_DEADLINE_EXCEEDED')
                return operation()
            except (EnvelopeError, AttributeError, OSError, KeyError, TypeError, ValueError,
                    OverflowError, IndexError) as error:
                blockers.append(str(error) if isinstance(error, EnvelopeError)
                                else name.upper()+'_PRODUCER_FAILED:'+type(error).__name__)
                return None
            finally:
                metrics.append((name, self.clock()-begin))

        run('artifact_load', self._load)
        if self._load_failure:
            blockers.append('EVIDENCE_IMPORT_FAILED:'+self._load_failure)

        def load_configuration_artifact():
            path = self.config.get('configuration_frame_file')
            require(path and self._trust is not None,
                    'UNPROVEN_FULL_ACCESSORY_CONFIGURATION')
            return self._trust.load(path, 'configuration_frame',
                                    deadline=self._deadline, clock=self.clock)
        configuration_artifact = run('configuration_frame_load',
                                     load_configuration_artifact)
        configuration_payload = (configuration_artifact.payload()
                                 if configuration_artifact is not None else None)

        def load_profile():
            require(self._profile_catalog is not None and observation is not None,
                    'MISSING_CONFIRMED_BODY_PROFILE')
            require(configuration_payload is not None,
                    'UNPROVEN_FULL_ACCESSORY_CONFIGURATION')
            artifact = self._profile_catalog.select(observation,
                                                    configuration_payload)
            self._active_profile_artifact = artifact
            key = (artifact.sha256, getattr(observed.token, 'configuration', None))
            if self._profile_key != key:
                self._profile_provider = compile_measured_profile(artifact, observation)
                self._profile_key = key
            result = self._profile_provider.update(observation, now)
            require(result.model is not None, result.model_failure)
            return result
        profile = run('profile_lookup', load_profile)
        # Selection and the complete source proof are worker work, never a tick scan.
        # This is a diagnostic candidate only; no lane transition is invented.
        if target is None and lane_path is not None:
            target = next((i for i, segment in enumerate(lane_path.segments)
                           if _sensitive(segment)), None)
        if lane_path is not None and target is not None:
            context = run('route_context', lambda: build_maneuver_route_context(
                network, lane_path, snapshot, target))
        else:
            blockers.append('NO_CURRENT_MANEUVER_ROUTE_CONTEXT')

        def load_surface():
            artifact = self._artifacts.get('surface_survey')
            require(artifact is not None and context is not None,
                    'MISSING_CONFIRMED_DRIVABLE_SURFACE_PRODUCER')
            key = (artifact.sha256, context.snapshot_fingerprint)
            if self._surface_cache is None or self._surface_cache[0] != key:
                self._surface_cache = (key, bind_survey(artifact, context.local_lane_path, context.identity))
            return self._surface_cache[1]
        result = run('surface_lookup', load_surface)
        if result:
            surface, catalog = result

        def live_configuration():
            nonlocal operating_conditions
            require(configuration_artifact is not None and profile,
                    'UNPROVEN_FULL_ACCESSORY_CONFIGURATION')
            artifact = configuration_artifact
            p = artifact.payload()
            conditions = p.get('operating_conditions_fingerprint')
            require(type(conditions) is str and len(conditions) == 64
                    and all(c in '0123456789abcdef' for c in conditions)
                    and p.get('load_and_actuator_domain_confirmed') is True,
                    'MISSING_MEASURED_LOAD_AND_ACTUATOR_DOMAIN')
            require(context is not None and p.get('session') == context.identity.session
                    and p.get('sdk_frame_us') == frame
                    and p.get('configuration_fingerprint') == profile.token.configuration
                    and self._active_profile_artifact is not None
                    and p.get('accessory_fingerprint') == self._active_profile_artifact.payload()['accessory_fingerprint']
                    and p.get('chassis_configuration') == self._active_profile_artifact.payload()['chassis_configuration']
                    and p.get('cabin_configuration') == self._active_profile_artifact.payload()['cabin_configuration']
                    and p.get('mod_fingerprint') == self._active_profile_artifact.payload()['mod_fingerprint']
                    and p.get('inventory_complete') is True
                    and finite(p.get('observed_at_s')) and 0 <= now-p['observed_at_s'] < .1,
                    'STALE_FULL_CONFIGURATION_EVIDENCE')
            operating_conditions = conditions
            return artifact.sha256
        confirmation_source = run('configuration_frame', live_configuration) or ''

        def transform():
            require(profile and surface and context,
                    'MISSING_FIXED_AXLE_GROUND_REFERENCE_PRODUCER')
            scope = (context.identity, profile.token.configuration)
            if scope != self._last_context:
                self._ground = GroundReferenceProducer()
                self._last_context = scope
            return self._ground.produce(profile, context.identity, surface,
                self._artifacts.get('ground_calibration'), now)
        ground = run('ground_transform', transform)
        if capture is not None:
            legacy = run('legacy_traffic_observation', lambda: self._legacy.produce(capture, now))

        def traffic_frame():
            path = self.config.get('traffic_frame_file')
            require(path and context, 'MISSING_COMPLETE_TRAFFIC_HISTORY_COVERAGE_AND_BODY_PRODUCER')
            artifact = self._trust.load(path, 'traffic_frame', deadline=self._deadline, clock=self.clock)
            return self._traffic.produce(artifact, context.identity, now)
        traffic = run('traffic_snapshot', traffic_frame)

        def measured_tracking():
            artifact = self._artifacts.get('tracking_run')
            path = self.config.get('tracking_samples_file')
            require(artifact and path and plan and profile and surface,
                    'MISSING_VALIDATED_EXECUTION_TRACKING_BOUND')
            require(bool(operating_conditions)
                    and artifact.payload().get('operating_conditions_fingerprint') == operating_conditions,
                    'TRACKING_LOAD_OR_ACTUATOR_DOMAIN_MISMATCH')
            key = (artifact.sha256, plan.token, profile.token.configuration, surface.token)
            if self._tracking_cache is None or self._tracking_cache[0] != key:
                rows = read_document(path, max_bytes=32*1024*1024)['samples']
                self._tracking_cache = (key, qualify_tracking(artifact, rows, plan, profile, surface)[0])
            return self._tracking_cache[1]
        tracking = run('tracking_lookup', measured_tracking)
        elapsed = self.clock()-started
        metrics.append(('total', elapsed))
        if elapsed >= EVIDENCE_DEADLINE_S:
            blockers.append('PRODUCTION_EVIDENCE_DEADLINE_EXCEEDED')
        if not finite(observed_at) or not 0 <= self.clock()-observed_at < .1:
            blockers.append('EXPIRED_PRODUCTION_EVIDENCE')
        receipt = digest({'sequence': sequence, 'identity': state_identity(snapshot),
                          'frame': frame, 'observed_at': observed_at,
                          'artifacts': {k: v.sha256 for k, v in self._artifacts.items()},
                          'selected_body_profile': getattr(self._active_profile_artifact, 'sha256', None),
                          'configuration_frame': confirmation_source,
                          'traffic': getattr(traffic, 'evidence_sha256', None),
                          'ground': getattr(ground, 'evidence_sha256', None),
                          'plan': getattr(plan, 'token', None)})
        return EvidenceBundle(sequence, state_identity(snapshot), frame, observed_at,
            observed_at+.1, tuple(dict.fromkeys(blockers)), tuple(metrics), profile,
            ground, surface, traffic, tracking, context, catalog, receipt,
            getattr(plan, 'token', ''), confirmation_source, legacy,
            calibration_binding(self._artifacts['tracking_run'].payload().get('actuator_calibration'))
                if tracking else (), operating_conditions)


def production_reference_rejection(state, snapshot, packet, sdk_frame_us, now):
    """Cheap additional production-only check, before the unchanged 5D gate."""
    bundle = state.get('maneuver_production_evidence')
    if not isinstance(bundle, EvidenceLease):
        return 'MISSING_PRODUCTION_MANEUVER_EVIDENCE'
    reason = bundle.rejection(snapshot, sdk_frame_us, now)
    if reason:
        return reason
    if not snapshot.get('valid'):
        return 'INVALID_PRODUCTION_NAVIGATION_SNAPSHOT'
    for state_key, snapshot_key in (
            ('navigation_intent_id','navigation_intent_id'),
            ('active_map_key','source_map_key'),
            ('active_dataset_fingerprint','source_dataset_fingerprint')):
        current = state.get(state_key)
        if current is not None and current != snapshot.get(snapshot_key):
            return 'LOST_PRODUCTION_NAVIGATION_SOURCE'
    if bundle.tracking_calibration != calibration_binding(state.get('steering_actuator_calibration')):
        return 'STALE_PRODUCTION_TRACKING_CALIBRATION'
    observed = state.get('vehicle_profile_snapshot')
    if (observed is None or getattr(observed, 'observation_failure', True)
            or getattr(getattr(observed, 'token', None), 'configuration', None)
                != bundle.profile_configuration
            or getattr(getattr(observed, 'observation', None), 'sdk_frame_us', None) != sdk_frame_us):
        return 'LOST_PRODUCTION_VEHICLE_OBSERVATION'
    if (packet.get('production_evidence_receipt') != bundle.receipt
            or packet.get('plan_token', packet.get('maneuver_plan_token')) != bundle.plan_token):
        return 'STALE_PRODUCTION_MANEUVER_EVIDENCE_RECEIPT'
    return ''


class ProductionPublicationSink:
    """Adapter for the existing 5D publisher, called only on its worker.

    Receipts and all three 5D channels are committed in one update. It cannot
    bless a synthetic 5D request or refresh an old bundle. The control readers
    independently compare live identity/frame, covering races after this check.
    """
    def __init__(self, state, *, clock=time.monotonic):
        self.state, self.clock = state, clock
        self.bundle = None

    def bind(self, bundle):
        require(isinstance(bundle, EvidenceBundle) and bundle.ready,
                'INCOMPLETE_PRODUCTION_EVIDENCE')
        self.bundle = bundle

    def update_batch(self, values):
        values = dict(values)
        reference = dict(values.get('maneuver_reference_packet') or {})
        approach = dict(values.get('maneuver_approach_packet') or {})
        if reference or approach:
            bundle = self.bundle
            require(isinstance(bundle, EvidenceBundle), 'MISSING_PRODUCTION_MANEUVER_EVIDENCE')
            snapshot = self.state.get('lane_trajectory', {}) or {}
            frame = ((self.state.get('telemetry', {}) or {}).get('truck', {}) or {}).get('sdkFrameTimeUs')
            require(not bundle.rejection(snapshot, frame, self.clock()),
                    'STALE_PRODUCTION_PUBLICATION')
            require(reference.get('plan_token') == bundle.plan_token,
                    'PRODUCTION_PUBLICATION_PLAN_MISMATCH')
            for packet in (reference, approach):
                if packet:
                    packet['production_evidence_receipt'] = bundle.receipt
            values.update(maneuver_reference_packet=reference,
                          maneuver_approach_packet=approach,
                          maneuver_production_evidence=bundle.lease(),
                          maneuver_ground_reference=bundle.ground,
                          maneuver_surface_token=bundle.surface.token,
                          maneuver_traffic_sequence=bundle.traffic.sequence)
        else:
            values['maneuver_production_evidence'] = None
        self.state.update_batch(values)
