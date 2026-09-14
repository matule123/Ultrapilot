"""5E measurement-only recording and exact-plan tracking qualification.

No adaptation and no control outputs. A log of normal global-lane driving is
useful diagnostics, but cannot qualify an unobserved local maneuver.
"""
from collections import deque
from bisect import bisect_left
from dataclasses import asdict, is_dataclass, replace
import json
import math
from pathlib import Path
import threading
import time

from core.navigation.drivable_surface import digest
from core.navigation.lane_model import wrap_angle
from core.navigation.maneuver_runtime import TrackingEvidence, execution_timing
from core.swept_envelope import Frame, Pose, clearance, expand, finite, footprint, require, evaluate

MAX_TRACKING_SAMPLES = 12000
CALIBRATION_KEYS = ('schema_version', 'tyre_angle_per_input_rad', 'command_delay_s',
                    'observation_delay_s', 'source')


def calibration_binding(value):
    return tuple((value or {}).get(key) for key in CALIBRATION_KEYS)


TRACKING_FIELDS = (
    'sdk_frame_us', 'observed_at_s', 'application_sequence', 'applied_at_s',
    'steer_raw', 'steer_out', 'engine_steer', 'game_steer', 'speed_mps',
    'yaw_rate_rad_s', 'local_cte_m', 'heading_error_rad', 'curvature_reference',
    'actuator_delay_s', 'steering_gain_rad', 'tyre_angles_rad', 'articulation_rad',
    'plan_token', 'profile_configuration', 'ground_frame', 'reference_mode',
    'planned_point', 'planned_tangent', 'execution_start_s', 'initial_speed_mps',
)


def capture_application(state, steering, now, sequence):
    """Small event captured after the backend call returned, not before it.

    game_steer is a separate measured channel; backend_sent does not imply that
    the physical tyres instantly reached the commanded value.
    """
    applied = state.get('maneuver_applied_target', {}) or {}
    debug = applied.get('source_packet', {}) or {}
    telemetry = state.get('telemetry', {}) or {}
    truck = telemetry.get('truck', {}) or {}
    profile = state.get('vehicle_profile_snapshot')
    reference = state.get('active_navigation_reference', {}) or {}
    calibration = state.get('steering_actuator_calibration', {}) or {}
    ground = state.get('maneuver_ground_reference')
    command = state.get('ctl_steering')
    bound = bool(debug and applied.get('output') == command
                 and applied.get('target_fresh') and applied.get('executor_active')
                 and debug.get('sdk_frame_us') == truck.get('sdkFrameTimeUs')
                 and debug.get('maneuver_plan_token') == reference.get('plan_token')
                 and debug.get('production_evidence_receipt') == reference.get('production_evidence_receipt'))
    return {
        'schema_version': 1, 'measurement_domain': 'ets2_backend_observation',
        'backend_sent': True, 'application_sequence': sequence,
        'calculation_binding_proven': bound,
        'applied_at_s': now, 'engine_steer': float(steering),
        'sdk_frame_us': truck.get('sdkFrameTimeUs'),
        'article_observations': tuple((a.slot, a.vehicle_id, a.position_m, a.rotation_rad,
            tuple((w.index,w.on_ground,w.lift) for w in a.wheels))
            for a in getattr(getattr(profile, 'observation', None), 'articles', ()) if a.attached),
        'actuator_calibration': dict(calibration),
        'operating_conditions_fingerprint': getattr(
            state.get('maneuver_production_evidence'), 'operating_conditions', None),
        'profile_configuration': getattr(getattr(profile, 'token', None), 'configuration', None),
        'ground_frame': getattr(ground, 'frame', None),
        'observed_at_s': getattr(ground, 'observed_at', None),
        'reference_mode': reference.get('mode'), 'plan_token': reference.get('plan_token'),
        'reference_binding': reference.get('binding'),
        'reference_sequence': reference.get('sequence'),
        'execution_start_s': reference.get('execution_start_s'),
        'initial_speed_mps': reference.get('initial_speed_mps'),
        'calculation_sequence': debug.get('calculation_sequence'),
        'calculation_sdk_frame_us': debug.get('sdk_frame_us'),
        'calculation_identity': debug.get('trajectory_identity'),
        'steer_raw': debug.get('raw'),
        'steer_out': command,
        'game_steer': truck.get('gameSteer'), 'speed_mps': truck.get('speed'),
        'yaw_rate_rad_s': truck.get('yawRateRadS') if truck.get('yawRateValid') else None,
        'local_cte_m': debug.get('control_cte'),
        'heading_error_rad': debug.get('guidance_heading_error_rad'),
        'curvature_reference': debug.get('local_curvature'),
        'planned_point': debug.get('tracking_projection_xz'),
        'planned_tangent': debug.get('local_tangent_heading_rad'),
        'tracking_progress_m': debug.get('tracking_progress_m'),
        'ground_uncertainty_m': getattr(ground, 'position_uncertainty_m', None),
        'tyre_angles_rad': tuple(truck.get('roadWheelAnglesRad', ())),
        'articulation_rad': state.get('trailer_articulation'),
        'actuator_delay_s': calibration.get('command_delay_s'),
        'steering_gain_rad': calibration.get('tyre_angle_per_input_rad'),
    }


class TrackingRecorder:
    """Bounded in-memory events, export on a diagnostic/shutdown worker only."""
    def __init__(self, capacity=MAX_TRACKING_SAMPLES):
        require(type(capacity) is int and 1 <= capacity <= MAX_TRACKING_SAMPLES,
                'INVALID_TRACKING_CAPACITY')
        self._rows = deque(maxlen=capacity)
        self._lock = threading.Lock()
        self.dropped = 0

    def append(self, row):
        with self._lock:
            if len(self._rows) == self._rows.maxlen:
                self.dropped += 1
            self._rows.append(dict(row))

    def export(self, path):
        with self._lock:
            rows, dropped = tuple(self._rows), self.dropped
        def encode(value):
            if is_dataclass(value):
                return asdict(value)
            raise TypeError(type(value).__name__)
        document = {'schema_version': 1, 'source': 'UltraPilot Engine applied controls',
                    'measurement_domain': 'ets2_backend_observation',
                    'qualification': 'UNQUALIFIED_RAW_MEASUREMENT',
                    'dropped_samples': dropped, 'samples': rows}
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, default=encode, allow_nan=False,
                                   indent=2), encoding='utf-8')
        return len(rows)


def assess_tracking(rows, plan, profile, surface, *, corner_bound_m=.05,
                    time_bound_s=.05, speed_bound_mps=.05, timing=None):
    """Offline exact-plan measurement; synthetic/domain-mismatched rows reject.

    Bounds include measurement uncertainty. An observed maximum is not a
    universal prediction bound: the result remains exact to plan, body profile,
    surface and measured actuator conditions and requires trusted review.
    """
    require(plan.accepted and surface.surface is not None, 'MISSING_TRACKING_PLAN_OR_SURFACE')
    require(type(rows) in (list, tuple) and 30 <= len(rows) <= MAX_TRACKING_SAMPLES,
            'INSUFFICIENT_REAL_TRACKING_SAMPLES')
    require(finite(corner_bound_m, time_bound_s, speed_bound_mps)
            and 0 < corner_bound_m <= .25 and 0 < time_bound_s <= .5
            and 0 < speed_bound_mps <= .1, 'INVALID_TRACKING_BOUNDS')
    model = profile.model
    maxima = {'corner_error_m': 0., 'heading_error_rad': 0., 'speed_error_mps': 0.,
              'sample_gap_s': 0., 'steering_rate_rad_s': 0., 'steering_accel_rad_s2': 0.}
    minimum = math.inf
    previous = None
    indices, curve_cte, sign_changes = [], [], 0
    last_rates = None
    previous_curve_sign = None
    measured_frames = []
    maximum_uncertainty = 0.
    for row in rows:
        require(all(k in row and row[k] is not None for k in TRACKING_FIELDS),
                'INCOMPLETE_APPLIED_TRACKING_CHANNELS')
        require(row.get('measurement_domain') == 'ets2_backend_observation'
                and row.get('backend_sent') is True and row.get('calculation_binding_proven') is True
                and row['reference_mode'] == 'local_maneuver',
                'TRACKING_IS_NOT_REAL_LOCAL_APPLICATION')
        require(row['plan_token'] == plan.token
                and row['profile_configuration'] == profile.token.configuration,
                'TRACKING_PLAN_OR_CONFIGURATION_MISMATCH')
        numeric = ('observed_at_s', 'applied_at_s', 'steer_raw', 'steer_out', 'engine_steer',
                   'game_steer', 'speed_mps', 'yaw_rate_rad_s', 'local_cte_m',
                   'heading_error_rad', 'curvature_reference', 'actuator_delay_s',
                   'steering_gain_rad', 'articulation_rad')
        require(all(finite(row[k]) for k in numeric)
                and type(row['sdk_frame_us']) is int and row['sdk_frame_us'] > 0,
                'NONFINITE_TRACKING_CHANNEL')
        require(0 <= row['applied_at_s']-row['observed_at_s'] <= .1
                and .60 <= row['steering_gain_rad'] <= .95
                and 0 <= row['actuator_delay_s'] <= .5
                and all(abs(row[k]) <= 1 for k in ('steer_raw', 'steer_out', 'engine_steer', 'game_steer')),
                'TRACKING_ACTUATOR_LIMIT_EXCEEDED')
        frame = row['ground_frame']
        if isinstance(frame, dict):
            # Never replace the stored identity with the current one silently.
            require(canonical_identity(frame.get('identity')) == canonical_identity(asdict(plan.identity)),
                    'TRACKING_GROUND_IDENTITY_MISMATCH')
            frame = Frame(frame['time_s'], plan.identity,
                          tuple(Pose(**p) for p in frame['poses']))
        require(isinstance(frame, Frame) and frame.identity == plan.identity
                and frame.time_s == row['observed_at_s'], 'TRACKING_GROUND_IDENTITY_MISMATCH')
        frame.validate(model)
        measured_frames.append(frame)
        require(timing is not None and len(timing.times_s) == len(plan.samples),
                'MISSING_MEASURED_EXECUTION_TIMING')
        require(row['execution_start_s'] == timing.start_s
                and row['initial_speed_mps'] == timing.initial_speed_mps,
                'TRACKING_EXECUTION_SCHEDULE_MISMATCH')
        right = min(len(timing.times_s)-1, bisect_left(timing.times_s, frame.time_s))
        index = min((max(0,right-1),right), key=lambda i: abs(timing.times_s[i]-frame.time_s))
        require(type(index) is int and 0 <= index < len(plan.samples),
                'MISSING_MEASURED_PLAN_SAMPLE_BINDING')
        require(not indices or index >= indices[-1], 'REGRESSING_TRACKING_PROGRESS')
        indices.append(index)
        target = plan.samples[index]
        require(abs(timing.times_s[index]-frame.time_s) <= time_bound_s,
                'TRACKING_TIME_BOUND_EXCEEDED')
        error = max(math.dist(a, b) for body, actual, expected in
                    zip(model.bodies, frame.poses, target.frame.poses)
                    for a, b in zip(footprint(body, actual), footprint(body, expected)))
        measured_uncertainty = row.get('ground_uncertainty_m')
        require(finite(measured_uncertainty) and measured_uncertainty > 0,
                'MISSING_TRACKING_MEASUREMENT_UNCERTAINTY')
        error += measured_uncertainty
        maximum_uncertainty = max(maximum_uncertainty, measured_uncertainty)
        require(error <= corner_bound_m, 'TRACKING_CORNER_BOUND_EXCEEDED')
        speed_error = abs(row['speed_mps']-timing.speed_at(frame.time_s))
        require(speed_error <= speed_bound_mps, 'TRACKING_SPEED_BOUND_EXCEEDED')
        require(abs(row['yaw_rate_rad_s']-row['speed_mps']*target.curvature_right_m_inv)
                <= .01, 'TRACKING_YAW_RESPONSE_MISMATCH')
        require(abs(wrap_angle(row['heading_error_rad'])) <= math.radians(1),
                'TRACKING_HEADING_BOUND_EXCEEDED')
        angles = row['tyre_angles_rad']
        require(bool(angles) and all(finite(v) and abs(v) <= model.max_tyre_rad for v in angles),
                'TRACKING_TYRE_LIMIT_EXCEEDED')
        angle = sum(angles)/len(angles)
        if previous:
            dt = frame.time_s-previous['observed_at_s']
            require(0 < dt <= .1 and row['sdk_frame_us'] > previous['sdk_frame_us']
                    and row['application_sequence'] > previous['application_sequence'],
                    'STALE_OR_GAPPED_TRACKING_MEASUREMENT')
            require(len(angles)==len(previous['tyre_angles_rad']), 'TRACKING_WHEEL_CONFIGURATION_CHANGED')
            rates = tuple((a-b)/dt for a,b in zip(angles,previous['tyre_angles_rad']))
            require(all(abs(rate) <= .12 for rate in rates), 'TRACKING_STEERING_RATE_EXCEEDED')
            maxima['steering_rate_rad_s'] = max(maxima['steering_rate_rad_s'], *map(abs,rates))
            if last_rates is not None:
                acceleration = max(abs(a-b)/dt for a,b in zip(rates,last_rates))
                require(acceleration <= .20, 'TRACKING_STEERING_ACCELERATION_EXCEEDED')
                maxima['steering_accel_rad_s2'] = max(maxima['steering_accel_rad_s2'], acceleration)
            last_rates = rates
            maxima['sample_gap_s'] = max(maxima['sample_gap_s'], dt)
        if abs(target.curvature_right_m_inv) > .001:
            curve_cte.append(abs(row['local_cte_m']))
            sign = 1 if angle > .001 else -1 if angle < -.001 else 0
            if sign:
                if previous_curve_sign is not None and sign != previous_curve_sign:
                    sign_changes += 1
                previous_curve_sign = sign
                require(all(a*target.curvature_right_m_inv >= 0 for a in angles),
                        'TRACKING_UNEXPECTED_STEERING_SIGN')
        for body, pose in zip(model.bodies, frame.poses):
            margin = model.safety_margin_m+model.uncertainty_m+surface.boundary_uncertainty_m+measured_uncertainty
            minimum = min(minimum, clearance(expand(footprint(body, pose), margin), surface.surface))
        maxima['corner_error_m'] = max(maxima['corner_error_m'], error)
        maxima['heading_error_rad'] = max(maxima['heading_error_rad'], abs(row['heading_error_rad']))
        maxima['speed_error_mps'] = max(maxima['speed_error_mps'], speed_error)
        previous = row
    require(indices[0] == 0 and indices[-1] == len(plan.samples)-1 and len(curve_cte) >= 10,
            'TRACKING_ENTRY_CURVE_EXIT_NOT_MEASURED')
    require(sign_changes == 0, 'TRACKING_UNEXPECTED_SIGN_CHANGE')
    quarters = [max(curve_cte[i*len(curve_cte)//4:(i+1)*len(curve_cte)//4]) for i in range(4)]
    require(not all(b > a+.001 for a, b in zip(quarters, quarters[1:])),
            'TRACKING_CTE_GROWS_CYCLE_BY_CYCLE')
    require(minimum > 0, 'TRACKING_SWEPT_CLEARANCE_VIOLATION')
    swept = evaluate(replace(model, uncertainty_m=model.uncertainty_m
                             + surface.boundary_uncertainty_m + maximum_uncertainty),
                     tuple(measured_frames), surface.surface, plan.identity)
    require(swept.accepted, swept.failure_reason)
    return {'accepted': True, 'production_authorized': False,
            'plan_token': plan.token, 'profile_configuration': profile.token.configuration,
            'surface_token': surface.token, 'sample_count': len(rows),
            'minimum_observed_clearance_m': minimum, 'maxima': maxima,
            'minimum_swept_clearance_m': swept.minimum_clearance_m,
            'sign_changes': sign_changes, 'corner_bound_m': corner_bound_m,
            'time_bound_s': time_bound_s, 'speed_bound_mps': speed_bound_mps}


def canonical_identity(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def qualify_tracking(artifact, rows, plan, profile, surface):
    require(artifact.kind == 'tracking_run', 'WRONG_TRACKING_ARTIFACT_KIND')
    p = artifact.payload()
    require(p.get('samples_sha256') == digest(rows), 'TRACKING_SAMPLES_INTEGRITY_MISMATCH')
    bounds = TrackingEvidence(p['source'], artifact.sha256, True,
        p['corner_bound_m'], p['time_bound_s'], p['speed_bound_mps'])
    calibration = calibration_binding(p.get('actuator_calibration'))
    require(all(value is not None for value in calibration)
            and all(calibration_binding(row.get('actuator_calibration')) == calibration for row in rows),
            'TRACKING_ACTUATOR_CALIBRATION_MISMATCH')
    conditions = p.get('operating_conditions_fingerprint')
    require(type(conditions) is str and len(conditions) == 64
            and all(row.get('operating_conditions_fingerprint') == conditions for row in rows),
            'TRACKING_LOAD_OR_ACTUATOR_DOMAIN_MISMATCH')
    timing = execution_timing(plan, p['execution_start_s'], p['initial_speed_mps'], bounds)
    report = assess_tracking(rows, plan, profile, surface,
        corner_bound_m=p['corner_bound_m'], time_bound_s=p['time_bound_s'],
        speed_bound_mps=p['speed_bound_mps'], timing=timing)
    require(p.get('plan_token') == plan.token
            and p.get('surface_token') == surface.token
            and p.get('profile_configuration') == profile.token.configuration,
            'TRACKING_ARTIFACT_SCOPE_MISMATCH')
    return TrackingEvidence(p['source'], artifact.sha256, True,
        report['corner_bound_m'], report['time_bound_s'], report['speed_bound_mps']), report
