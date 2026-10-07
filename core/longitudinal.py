"""Bounded longitudinal arbitration, not a speed controller.

Each producer owns one immutable value in IPC. Autopilot retains its speed
controller/ramps and publishes one paired pedal decision; Engine is the only
physical owner. Timestamps refer to the original vehicle observation.
"""
import math
import time
from dataclasses import dataclass

from core.transmission_mode import vehicle_control_observation, vehicle_control_observation_rejection

SCHEMA = 1
LEASE_S = .5
# Two 60 Hz executor opportunities plus one producer period and RPC reserve.
# This is a zero-drive handoff budget, NOT an extension of any input lease.
HANDOFF_RESERVE_S = .05
HANDOFF_WAIT_S = .1
COMMAND_KEY = "longitudinal_command"
PRIORITY = {"emergency": 100, "safety": 90, "obstacle": 80, "traffic": 70,
            "maneuver": 60, "curve": 50, "acc": 40, "cruise": 10}

# Existing Autopilot curve-entry envelope, now shared with the speed planner.
# These are planning assumptions, not measured grip or an ETS2 brake model.
CURVE_LATERAL_ACCEL_MS2 = 1.8
CURVE_APPROACH_DECEL_MS2 = 1.0
CURVE_BRAKE_RESPONSE_S = 1.0
CURVE_STEERING_SETUP_M = 20.0
ROUNDABOUT_ENTRY_SPEED_KMH = 35.0


def signal_stop_speed_limit(light, speed_ms):
    """Derived target already includes front allowance and junction stand-off.

    Share the existing 1 m/s² approach assumption. Reserve the existing 1 s
    vehicle response plus the full 0.5 s allowed evidence/transfer age. These
    are conservative planning allowances, not a measured ETS2 brake model.
    """
    if (not isinstance(light, dict) or light.get('stop_target_kind') != 'derived_directed_curve_entry'
            or light.get('color') not in ('red', 'yellow', 'unknown', 'off', 'sleep')):
        return None
    distance = number(light['distance'], -1e6, 1e6)
    speed = number(abs(float(speed_ms)), 0., 100.)
    usable = max(0., distance-speed*(CURVE_BRAKE_RESPONSE_S+LEASE_S))
    return math.sqrt(2.*CURVE_APPROACH_DECEL_MS2*usable)


def signal_stop_brake_request(light, speed_ms, *, continuing=False):
    """Distance/deceleration feed-forward for the existing traffic request.

    4 m/s² is the existing yellow-light full-brake planning assumption, not a
    measured gain or an extra feedback controller. The current pedal arbiter
    and Autopilot comfort ramp still own execution; emergencies still win.
    """
    cap = signal_stop_speed_limit(light, speed_ms)
    if cap is None:
        return 0.
    speed = abs(float(speed_ms));distance = float(light['distance'])
    if distance <= 0. or (speed < .5 and distance <= 1.5):
        return 1.
    if speed <= cap and not continuing:
        return 0.
    usable = max(.5, distance-speed*(CURVE_BRAKE_RESPONSE_S+LEASE_S))
    required_decel = speed*speed/(2.*usable)
    return min(1.,required_decel/4.)


def planned_braking_input(state):
    """Current planned stop evidence, never an authorization for zero-ratio drive.

    Used by the shared drivetrain gate before the first physical brake receipt.
    An old positive ratio alone is insufficient. Only a still-valid identified
    stop request can bridge the first braking write; the ordinary pedal arbiter
    and final write check remain authoritative.
    """
    binding = context(state)
    traffic, _ = read(state, 'traffic', binding=binding)
    policy, _ = read(state, 'policy', binding=binding)
    acc, _ = read(state, 'acc', binding=binding)
    try:
        values = [number(value,0.,1.) for value in (
            (traffic or {}).get('light_brake',0.), (traffic or {}).get('traffic_brake',0.),
            (acc or {}).get('brake',0.), (policy or {}).get('brake',0.))]
    except (TypeError, ValueError, OverflowError):
        return False
    light_brake, traffic_brake, acc_brake, policy_brake = values
    light = (traffic or {}).get('light') or {}
    signal_stop = bool(light.get('color') in ('red', 'yellow', 'unknown', 'off', 'sleep')
        and (light_brake > 0
             or light.get('stop_target_kind') == 'derived_directed_curve_entry'))
    traffic_stop = signal_stop or bool(traffic_brake > 0
        or ((traffic or {}).get('following') or {}).get('status') == 'candidate'
        )
    policy_stop = (policy or {}).get('reason') == 'toll stop/payment'
    required = [p for p,used in ((traffic,traffic_stop),(policy,policy_stop),(acc,acc_brake>0)) if p and used]
    current = context(state)
    checked_at = time.monotonic()
    return bool((traffic_stop or policy_stop) and max(values)>0 and current==binding
        and all(not rejection(p,binding,checked_at) for p in required))


def curve_speed_envelope(radius_m, distance_m, speed_ms):
    from core.navigation.route import curve_speed_limit_ms
    radius = number(radius_m, 1e-9, 1e12)
    distance = number(distance_m, 0., 1e12)
    speed = number(abs(float(speed_ms)), 0., 100.)
    setup = CURVE_STEERING_SETUP_M if radius < 45.0 else 0.0
    usable = max(0., distance - setup - speed * CURVE_BRAKE_RESPONSE_S)
    return curve_speed_limit_ms(radius, usable, CURVE_LATERAL_ACCEL_MS2,
                                CURVE_APPROACH_DECEL_MS2), usable


def curve_preview_horizon_m(speed_ms, requested_speed_kmh=None):
    """Bounded distance query over existing geometry, not invented free space.

    Retain the requested cruise-speed horizon as the vehicle slows; otherwise
    the approaching curve could disappear from a shrinking speed-only query.
    Route clips this query to its actual remaining directed geometry.
    """
    speed = number(abs(float(speed_ms)), 0., 100.)
    try:
        requested = number(requested_speed_kmh, 0., 160.) / 3.6
    except (TypeError, ValueError, OverflowError):
        # Only a query size fallback, never a speed authorization or limit.
        requested = 60. / 3.6
    speed = max(speed, requested)
    return min(400., max(60., speed * speed / (2. * CURVE_APPROACH_DECEL_MS2)
                        + speed * CURVE_BRAKE_RESPONSE_S
                        + CURVE_STEERING_SETUP_M + 4.))


def curve_constraint_speed(curve, speed_ms):
    """Existing curvature envelope plus a semantic roundabout upper ceiling.

    Distance is directed LanePath progress, not distance to an island. Keep
    the existing response/setup allowance and deceleration planning assumption.
    Tighter curvature, traffic and posted constraints still win separately.
    """
    limit, _ = curve_speed_envelope(curve['radius_m'], curve['distance_m'], speed_ms)
    if 'roundabout_entry_distance_m' in curve:
        distance = number(curve['roundabout_entry_distance_m'], 0., 1e12)
        speed = number(abs(float(speed_ms)), 0., 100.)
        usable = max(0., distance - CURVE_STEERING_SETUP_M
                     - speed * CURVE_BRAKE_RESPONSE_S)
        entry = ROUNDABOUT_ENTRY_SPEED_KMH / 3.6
        limit = min(limit, math.sqrt(entry * entry + 2. * CURVE_APPROACH_DECEL_MS2 * usable))
    return limit


def context(state):
    # Small metadata is atomically published with LanePath by SharedState.
    # Never copy/unpickle the large geometry at every pedal/control boundary.
    lane = state.get("lane_trajectory_longitudinal_identity")
    if lane is not None:
        geometry = lane.get("geometry_token")
    else:
        lane = state.get("lane_trajectory_identity")
        geometry = state.get("lane_trajectory_publication_token")
    if lane is None:  # Pre-schema isolated clients only.
        lane = state.get("lane_trajectory", {}) or {}
    return (state.get("autopilot_failure_epoch"), state.get("game_session_id"),
            state.get("active_map_key"), state.get("active_dataset_fingerprint"),
            state.get("navigation_intent_id"), state.get("lane_trajectory_revision"),
            lane.get("route_build_id"), geometry)


def number(value, low=0., high=1.):
    if isinstance(value, bool):
        raise ValueError("boolean is not a control value")
    result = float(value)
    if not math.isfinite(result) or not low <= result <= high:
        raise ValueError("non-finite or out-of-range control value")
    return result


def exclusive(throttle, brake):
    throttle, brake = number(throttle), number(brake)
    return (0. if brake > 0 else throttle), brake


def dependency(value):
    """Small immutable lease receipt; a read time is never an observation."""
    if not isinstance(value, dict):
        return None
    basis = value.get('deadline_basis')
    if not isinstance(basis, dict):
        basis = {k: value.get(k) for k in ('source', 'sdk_frame_us',
                  'observation_timestamp', 'expires_at')}
        basis['kind'] = ('spatial_observation' if value.get('source') in ('road', 'curve')
                         else 'dynamic_evidence' if value.get('source') == 'traffic'
                         else 'decision')
    return dict(source=value.get('source'), expires_at=value['expires_at'],
                deadline_basis=dict(basis))


def traffic_required(value):
    """No empty/uncovered buffer proves clear road; it also authorizes no drive.

    A positive demand, latched candidate or actual light/lead constraint remains
    required evidence. Empty optional perception isn't a cruise lease owner.
    """
    if not value:
        return False
    following = value.get('following') or {}
    light = value.get('light') or {}
    return bool(max(value.get('traffic_brake', 0.), value.get('light_brake', 0.)) > 0
        or following.get('status') == 'candidate' or value.get('lead_distance')
        or light.get('color') in ('red', 'yellow')
        or light.get('stop_target_kind') == 'derived_directed_curve_entry')


def packet(state, truck, source, *, binding=None, evidence_valid=True, **values):
    """Do not make an old/missing observation fresh at publication time."""
    binding = context(state) if binding is None else binding
    observed, reason = vehicle_control_observation(state, truck)
    observed_at = observed.get("observed_at")
    expires = (float(observed_at) + LEASE_S) if isinstance(observed_at, (int, float)) else 0.
    own_expiry = expires
    inputs = [dependency(v) for v in values.pop('dependencies', ()) if v is not None]
    signal_stamp = None
    signal = values.get('signal')
    if source == 'traffic' and isinstance(signal,dict) and signal.get('valid') is True:
        # The truck's fresh observation cannot renew a previously acquired
        # red/green. Keep the producer render-frame/time separate from the
        # command's SDK frame and carry its original deadline to the writer.
        try:
            signal_stamp = number(signal['observed_at'],1e-9,1e12)
            frame = signal['frame_us']
            if type(frame) is not int or frame<=0:
                raise ValueError('invalid signal render frame')
            deadline = signal_stamp+LEASE_S
            inputs.append(dict(source='traffic_signal',expires_at=deadline,
                deadline_basis=dict(source='traffic_signal',kind='signal_render_observation',
                    sdk_frame_us=frame,observation_timestamp=signal_stamp,expires_at=deadline)))
        except (KeyError,TypeError,ValueError,OverflowError):
            evidence_valid = False
    inherited = values.pop('expires_at', expires)
    expires = min(expires, inherited, *(v['expires_at'] for v in inputs))
    basis = dict(source=source,
                 kind=('spatial_observation' if source in ('road', 'curve') else
                       'dynamic_evidence' if source == 'traffic' else 'vehicle_observation'),
                 sdk_frame_us=truck.get('sdkFrameTimeUs'),
                 observation_timestamp=observed_at, expires_at=own_expiry)
    winners = [v for v in inputs if v['expires_at'] == expires]
    if winners:
        basis = dict(sorted(winners, key=lambda v: str(v['source']))[0]['deadline_basis'])
    elif expires < own_expiry:
        basis = dict(source='unattributed_input', kind='legacy_deadline', expires_at=expires)
    computed = time.monotonic()
    if signal_stamp is not None and signal_stamp>computed:
        evidence_valid = False
    return dict(schema_version=SCHEMA, source=source, context=binding,
                sdk_frame_us=truck.get("sdkFrameTimeUs"),
                observation_timestamp=observed_at, expires_at=expires,
                computed_at=computed, deadline_basis=basis, lease_dependencies=inputs,
                remaining_at_computation_s=expires-computed,
                handoff_required=(source in ('acc', 'autopilot')
                    and not values.get('emergency') and expires-computed < HANDOFF_RESERVE_S),
                valid=evidence_valid is True and not reason and observed.get("valid") is True
                    and binding == context(state), **values)


def rejection(value, binding, now):
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA:
        return "missing or unsupported longitudinal packet"
    if value.get("valid") is not True:
        return "invalid longitudinal observation"
    if not isinstance(value.get("context"), (tuple, list)) or tuple(value["context"]) != tuple(binding):
        return "longitudinal identity or activation changed"
    try:
        frame = value["sdk_frame_us"]
        observation = float(value["observation_timestamp"])
        computed = float(value["computed_at"])
        if isinstance(frame, bool) or not isinstance(frame, int) or frame <= 0:
            return "invalid longitudinal SDK frame"
        if not (math.isfinite(observation) and math.isfinite(computed)
                and 0 < observation <= computed <= now
                and now - observation <= LEASE_S
                and now <= float(value["expires_at"]) <= observation + LEASE_S):
            return "longitudinal observation is stale or incoherent"
    except (KeyError, TypeError, ValueError, OverflowError):
        return "incomplete longitudinal observation"
    if value.get('handoff_required') is True:
        return 'longitudinal decision needs refresh'
    return ""


def rejection_details(value, binding, now):
    """Small immutable description of the actually compared command, not a reread."""
    fields = ('activation', 'session', 'map', 'dataset', 'intent', 'revision', 'build', 'geometry')
    result = dict(checked_at=now, expected_context=list(binding))
    if not isinstance(value, dict):
        return dict(result, packet_status='MISSING')
    result.update({k: value.get(k) for k in ('sdk_frame_us', 'observation_timestamp',
        'computed_at', 'expires_at', 'valid', 'source', 'decision_source', 'reason',
        'deadline_basis', 'handoff_required', 'remaining_at_computation_s')})
    actual = value.get('context')
    result['actual_context'] = actual
    if isinstance(actual, (tuple, list)):
        result['different_fields'] = [name for i, name in enumerate(fields)
            if i >= len(actual) or i >= len(binding) or actual[i] != binding[i]]
    else:
        result['different_fields'] = ['context_missing']
    for key, dest in (('observation_timestamp', 'observation_age_s'),
                      ('computed_at', 'decision_age_s'), ('expires_at', 'lease_overrun_s')):
        try:
            result[dest] = now - float(value[key])
        except (KeyError, TypeError, ValueError, OverflowError):
            result[dest] = None
    return result


def write_rejection(value, binding, now):
    """Physical-boundary check, including time spent binding diagnostics/IPC."""
    if tuple(value['context']) != tuple(binding):
        return 'longitudinal identity or activation changed before write'
    if not 0. <= now - value['observation_timestamp'] <= LEASE_S:
        return 'longitudinal observation expired or incoherent before write'
    if now > value['expires_at']:
        return 'longitudinal input lease expired before write'
    return ''


def publish(state, truck, source, **values):
    value = packet(state, truck, source, **values)
    state.set("longitudinal_" + source, value)
    return value


def read(state, source, now=None, *, required=False, binding=None, diagnostic=None, rejection_info=None):
    """One IPC read per producer, never combine scalar throttle/brake reads."""
    value = state.get("longitudinal_" + source)
    compared_binding = context(state) if binding is None else binding
    checked_at = time.monotonic() if now is None else now
    reason = rejection(value, compared_binding, checked_at)
    if reason in ('longitudinal decision needs refresh', 'longitudinal observation is stale or incoherent'):
        # One bounded reread: publication may have overtaken the first RPC.
        # Validate the returned immutable value after reading, never retimestamp.
        newer = state.get('longitudinal_' + source)
        rechecked = time.monotonic() if now is None else now
        if not rejection(newer, compared_binding, rechecked):
            value, reason, checked_at = newer, '', rechecked
    if not reason:
        fields = {"acc": ("throttle", "brake"), "policy": ("brake",),
                  "traffic": ("traffic_brake", "light_brake"), "eco": ("smoothing",)}
        try:
            if value.get("source") != source:
                raise ValueError("producer source does not match its slot")
            if "emergency" in value and not isinstance(value["emergency"], bool):
                raise ValueError("emergency flag is not boolean")
            for key in fields.get(source, ()):
                number(value[key])
            for key in {"road": ("speed_cap_kmh",), "policy": ("planned_speed_ms",)}.get(source, ()):
                number(value[key], 0., 200.)
            for key in ("planned_speed_ms", "speed_cap_kmh"):
                if key in value:
                    number(value[key], 0., 200.)
        except (KeyError, TypeError, ValueError, OverflowError):
            reason = "invalid longitudinal producer values"
    if diagnostic is not None:
        from core.navigation.longitudinal_diagnostics import bounded_input
        diagnostic.setdefault('input_rejections', {})[source] = reason
        if reason:
            diagnostic.setdefault('rejected_inputs', {})[source] = bounded_input(value)
    if reason:
        if required and rejection_info is not None and not rejection_info:
            rejection_info.update(rejection_details(value, compared_binding, checked_at))
            rejection_info['rejected_source'] = source
        return None, (source + ": " + reason if required else "")
    return value, ""


def choose(throttle, requests, *, drive_source="cruise"):
    """Service requests are minimum deceleration demands, not throttle owners.

    Emergency/safety have explicit precedence. Among compatible service-brake
    floors the strongest floor is required to satisfy all requests. Priority
    and source name give deterministic attribution for ties.
    """
    throttle = number(throttle)
    checked = []
    for source, kind, brake in requests:
        checked.append((source, kind, number(brake)))
    urgent = [r for r in checked if r[1] in ("emergency", "safety") and r[2] > 0]
    pool = urgent or [r for r in checked if r[2] > 0]
    if pool:
        winner = sorted(pool, key=lambda r: (
            -PRIORITY[r[1]] if urgent else -r[2],
            -r[2] if urgent else -PRIORITY[r[1]], r[0]))[0]
        return dict(throttle=0., brake=max(r[2] for r in pool + checked), source=winner[0],
                    reason=winner[1] + " brake demand", emergency=winner[1] == "emergency")
    return dict(throttle=throttle, brake=0., source=drive_source,
                reason="normal drive" if throttle > 0 else "coast", emergency=False)


def finalize(state, truck, throttle, brake, decision, binding):
    try:
        throttle, brake = exclusive(throttle, brake)
    except (TypeError, ValueError, OverflowError):
        state.set(COMMAND_KEY, {"schema_version": SCHEMA, "valid": False,
                               "reason": "invalid autopilot pedal values"})
        return None
    value = packet(state, truck, "autopilot", binding=binding,
                   throttle=throttle, brake=brake,
                   decision_source=decision.get("source", "autopilot"),
                   reason=decision.get("reason", "autopilot state"),
                   emergency=bool(decision.get("emergency", False)),
                   dependencies=decision.get('dependencies', ()),
                   refresh_pending=decision.get('refresh_pending', False),
                   expires_at=decision.get("expires_at", float("inf")))
    # Manager.dict assigns this complete dictionary as one value. Scalars are
    # compatibility/UI mirrors; the production Engine never mixes them.
    state.set(COMMAND_KEY, value)
    return value


def refresh_handoff(state, truck, value, binding, reason):
    """Same bounded, zero-drive transition for Plugin and physical Engine.

    A still-valid expiring leaf, or a demonstrably newer live leaf/SDK sample,
    permits a bounded ZERO-drive transition. It never permits expired pedals.
    A wait already started on valid evidence can finish within its fixed bound;
    missing/invalid sources, foreign identity and faults cannot start a wait.
    """
    now = time.monotonic()
    if reason.partition(': ')[0] in ('acc', 'policy', 'traffic'):
        reason = reason.partition(': ')[2]
    if (reason not in ('longitudinal decision needs refresh',
                       'longitudinal observation is stale or incoherent',
                       'longitudinal input lease expired before write')
            or not isinstance(value, dict) or value.get('valid') is not True
            or tuple(value.get('context', value.get('actual_context', ()))) != tuple(binding)
            or vehicle_control_observation_rejection(state, truck, now)
            or state.get('autopilot_control_state') == 'controlled_stop'):
        return None
    try:
        obs, computed, expiry = (float(value[k]) for k in (
            'observation_timestamp', 'computed_at', 'expires_at'))
        if not 0 < obs <= computed <= now or now-obs > LEASE_S or expiry > obs+LEASE_S:
            return None
        basis = value['deadline_basis']
        source = basis['source']
        current = state.get('longitudinal_refresh_request')
        same_request = (isinstance(current, dict)
            and tuple(current.get('context', ())) == tuple(binding))
        if source == 'curve':
            fresh = curve_input(state, binding=binding)
        elif source == 'route_projection':
            fresh = projection_input(state, binding=binding)
        elif source in ('road', 'traffic'):
            fresh, failure = read(state, source, binding=binding, required=True)
            if failure and not failure.endswith('longitudinal observation is stale or incoherent'):
                return None
        elif source == 'traffic_signal':
            traffic, failure = read(state, 'traffic', binding=binding, required=True)
            if failure or not traffic:
                return None
            signal = traffic.get('signal') or {}
            if (signal.get('valid') is not True
                    or tuple(signal.get('authority', ())) != tuple(binding)):
                return None
            # A vehicle observation must never renew the separate render-frame
            # lease. Preserve a locked head/lifecycle during brake continuity.
            hold = state.get('simple_auto_service_hold') or {}
            lock = hold.get('signal_lock') or {}
            if lock and (signal.get('lifecycle') != lock.get('lifecycle')
                    or (signal.get('candidate') or {}).get('id')
                        != (lock.get('candidate') or {}).get('id')
                    or (signal.get('candidate') or {}).get('passage_key')
                        != (lock.get('candidate') or {}).get('passage_key')):
                return None
            stamp = float(signal['observed_at'])
            frame = signal['frame_us']
            if (type(frame) is not int or frame <= 0
                    or not 0 <= now-stamp <= LEASE_S):
                return None
            original_stamp = float(basis['observation_timestamp'])
            original_frame = basis['sdk_frame_us']
            if (frame < original_frame or stamp < original_stamp
                    or (stamp > original_stamp and frame <= original_frame)):
                return None
            fresh = dict(expires_at=stamp + LEASE_S)
        elif basis.get('kind') == 'vehicle_observation':
            observed, invalid = vehicle_control_observation(state, truck)
            fresh = None if invalid else dict(expires_at=observed['observed_at'] + LEASE_S)
        else:
            return None
        newer = fresh and fresh['expires_at'] > expiry and fresh['expires_at']-now >= HANDOFF_RESERVE_S
        expiring = fresh and fresh['expires_at'] == expiry and now <= expiry
        if not (newer or expiring or same_request and now <= current['expires_at']):
            return None
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if not same_request:
        # Both processes can notice the SAME rejected decision concurrently.
        # Anchor the bound to its ORIGINAL deadline, not a racing read time.
        current = dict(context=binding, started_at=now, expires_at=expiry+HANDOFF_WAIT_S,
                       reason=reason, rejected=value, source=source)
        state.set('longitudinal_refresh_request', current)
    if now > current['expires_at']:
        return None  # Do not restart the wait on every rejected producer tick.
    if tuple(binding) != context(state):
        return None
    return current


def handoff_decision(state, truck, value, binding, reason):
    request = refresh_handoff(state, truck, value, binding, reason)
    if request is None:
        return None
    fresh = packet(state, truck, 'engine_handoff', binding=binding,
        throttle=0., brake=0., decision_source='decision_refresh',
        reason='waiting for a new longitudinal decision', emergency=False,
        expires_at=request['expires_at'])
    # New ZERO-drive transition, not a relabeled prior pedal command.
    # A newer urgent demand always bypasses this wait.
    traffic, _ = read(state, 'traffic', binding=binding)
    if traffic and traffic['traffic_brake'] > .7:
        fresh.update(brake=1., emergency=True, source='traffic_emergency',
                     reason='emergency brake demand')
        fresh['expires_at'] = min(fresh['expires_at'], traffic['expires_at'])
    fresh['context'] = binding
    fresh['sdk_frame_us'] = truck['sdkFrameTimeUs']
    fresh['source'] = fresh['decision_source'] if not fresh['emergency'] else 'traffic_emergency'
    fresh['refresh_pending'] = True
    return fresh


def _vehicle_receipt(truck):
    """The exact control fields consumed, not a later diagnostic telemetry read."""
    observation = truck.get('_control_observation')
    observation = observation if isinstance(observation, dict) else {}
    return dict(sdk_frame_us=truck.get('sdkFrameTimeUs'), gear=truck.get('gear'),
        speed_mps=truck.get('speed'), park_brake=truck.get('parkBrake'),
        observation={k: observation.get(k) for k in
            ('schema_version', 'sdk_frame_us', 'observed_at', 'valid', 'reason')})


@dataclass(frozen=True)
class CommandObservation:
    binding: tuple
    command: object
    truck: dict
    provenance: dict


def capture_command_observation(state, truck, now=None):
    """Pin ONE command; at most one real truck read if publication overtook it.

    This pairs observations only. It grants no authority and changes neither
    packet nor SDK metadata. All ordinary validity/identity/deadline/drivetrain
    checks must run on the returned truck, after these IPC reads.
    """
    binding = context(state)
    initial = _vehicle_receipt(truck)
    read_started = time.monotonic() if now is None else now
    value = state.get(COMMAND_KEY)
    command_read_at = time.monotonic() if now is None else now
    retry = False
    try:
        retry = isinstance(value, dict) and int(value['sdk_frame_us']) > int(truck['sdkFrameTimeUs'])
    except (KeyError, TypeError, ValueError, OverflowError):
        pass  # The full validator retains its malformed-input rejection.
    if retry:
        telemetry = state.get('telemetry')
        truck = telemetry.get('truck') if isinstance(telemetry, dict) else None
        truck = truck if isinstance(truck, dict) else {}
    checked_at = time.monotonic() if now is None else now
    return CommandObservation(binding, value, truck, dict(
        initial_vehicle=initial, compared_vehicle=_vehicle_receipt(truck),
        command_read_started_at=read_started, command_read_at=command_read_at,
        checked_after_read_at=checked_at, reread_count=int(retry)))


def command_observation_details(pair, now, *, value=None, binding=None):
    command = pair.command if value is None else value
    result = rejection_details(command, pair.binding if binding is None else binding, now)
    result['vehicle_sdk_frame_us'] = pair.truck.get('sdkFrameTimeUs')
    observed = pair.provenance['compared_vehicle']['observation']
    result['vehicle_observation'] = {k: observed.get(k) for k in
        ('sdk_frame_us', 'observed_at', 'valid', 'reason')}
    result['command_observation_pairing'] = pair.provenance
    if isinstance(command, dict):
        result.update({k: command.get(k) for k in ('schema_version', 'throttle', 'brake', 'emergency')})
    return result


def engine_decision(state, truck, now=None, *, diagnostic=None, rejection_info=None,
                    command_observation=None):
    pair = (command_observation if command_observation is not None
            else capture_command_observation(state, truck, now))
    truck = pair.truck
    details = rejection_info if rejection_info is not None else {}
    result, reason = _engine_decision(state, truck, now, diagnostic=diagnostic,
        rejection_info=details, command_observation=pair)
    request = state.get('longitudinal_refresh_request') if reason else None
    if (reason and isinstance(request, dict) and isinstance(pair.command, dict)
            and pair.command.get('refresh_pending')):
        # Plugin already requested this SAME bounded transition. Do not use the
        # newly zeroed packet as provenance for the rejected original decision.
        compared, original = request['rejected'], request['reason']
    else:
        compared, original = details, reason
    if reason:
        result = handoff_decision(state, truck, compared, context(state), original)
        if result is not None:
            reason = ''
            if diagnostic is not None:
                diagnostic['selected'] = dict(result)
    return result, reason


def _engine_decision(state, truck, now=None, *, diagnostic=None, rejection_info=None,
                     command_observation=None):
    """Final fail-closed pedal boundary, including newer emergency evidence."""
    # A producer can publish during any RPC. A clock captured before the read
    # must not label that complete, genuinely newer packet as future-dated.
    # Explicit `now` remains an injected decision clock for isolated clients.
    decision_time = lambda: time.monotonic() if now is None else now
    pair = (command_observation if command_observation is not None
            else capture_command_observation(state, truck, now))
    truck = pair.truck
    binding, value = pair.binding, pair.command
    def reject(reason, compared=value, expected=binding):
        if rejection_info is not None and not rejection_info:
            rejection_info.update(command_observation_details(pair, decision_time(),
                value=compared, binding=expected))
        return None, reason
    if diagnostic is not None:
        from core.navigation.longitudinal_diagnostics import bounded_input
        diagnostic['requested'] = bounded_input(value)
        if pair.provenance['reread_count']:
            diagnostic['command_observation_pairing'] = pair.provenance
    vehicle_reason = vehicle_control_observation_rejection(state, truck, decision_time())
    if vehicle_reason:
        return reject(vehicle_reason)
    reason = rejection(value, binding, decision_time())
    if reason:
        return reject(reason)
    if (value.get("source") != "autopilot"
            or not isinstance(value.get("emergency"), bool)
            or not isinstance(value.get("decision_source"), str)
            or not value["decision_source"]
            or not isinstance(value.get("reason"), str) or not value["reason"]):
        return reject("invalid longitudinal decision source, reason or emergency flag")
    try:
        if int(value["sdk_frame_us"]) > int(truck["sdkFrameTimeUs"]):
            return reject("longitudinal command is ahead of vehicle observation")
        throttle, brake = exclusive(value["throttle"], value["brake"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return reject("invalid longitudinal pedal values")
    # Engine-owned traffic floors bypass a slow/unavailable Autopilot tick.
    # Unknown traffic is not free-space evidence. An unavailable legacy sensor
    # supplies no new brake request; the prior command still has its short lease.
    traffic, _ = read(state, "traffic", now, binding=binding, diagnostic=diagnostic)
    current_acc, acc_reason = read(state, "acc", now, binding=binding,
        required=bool(state.get("longitudinal_acc_active")), diagnostic=diagnostic,
        rejection_info=rejection_info)
    policy, policy_reason = read(state, "policy", now, binding=binding,
        required=bool(state.get("longitudinal_policy_active")), diagnostic=diagnostic,
        rejection_info=rejection_info)
    if diagnostic is not None:
        diagnostic['inputs'] = {k: bounded_input(v) for k, v in (
            ('traffic', traffic), ('acc', current_acc), ('policy', policy))}
        diagnostic['regulator_mode'] = current_acc.get('speed_control_reason') if current_acc else None
        diagnostic['regulator_mode_status'] = ('PRODUCER_SPEED_CONTROL_REASON'
                                               if current_acc else 'NOT_VERIFIED')
    if acc_reason or policy_reason:
        return reject(acc_reason or policy_reason)
    following = traffic.get('following') if traffic else None
    if current_acc and current_acc.get('following_required') is True:
        # Target loss is not clear-road evidence, including between ACC ticks.
        # The old candidate cannot outlive its source's original short lease.
        if not isinstance(following, dict) or following.get('status') != 'candidate':
            result = reject('ACC target unavailable or unconfirmed departure', traffic)
            if rejection_info is not None:
                rejection_info['following_target_id'] = current_acc.get('following_target_id')
                rejection_info['following_status'] = following.get('status') if isinstance(following, dict) else None
                rejection_info['following_confirmed'] = current_acc.get('following_confirmed')
            return result
        try:
            cap = number(following['speed_cap_mps'], 0., 140.)
            if float(truck['speed']) > cap:
                throttle = 0.
        except (KeyError, TypeError, ValueError, OverflowError):
            return reject('invalid ACC following constraint', traffic)
    requests = [(value.get("decision_source", "autopilot"),
                 "emergency" if value.get("emergency") else "acc", brake)]
    pending_service = False
    pending_source = "traffic"
    for source, current in (("policy", policy), ("acc", current_acc)):
        if current is None:
            continue
        if current.get("emergency") is True and current["brake"] > 0:
            requests.append((source, "emergency", current["brake"]))
        if current["brake"] > 0:
            throttle = 0.
            pending_service = True
            pending_source = source
        elif source == "acc" and current["throttle"] == 0:
            throttle = 0.
            pending_source = "acc_coast"
    if traffic:
        # Matches UltraPilotPlanner's existing >0.7 emergency threshold.
        # Ordinary traffic brake targets keep Autopilot's existing ramp;
        # a newer unmet service request inhibits drive until its next tick.
        if traffic["traffic_brake"] > .7:
            requests.append(("traffic_emergency", "emergency", 1.))
        traffic_service = max(traffic["traffic_brake"], traffic["light_brake"]) > 0
        if traffic_service:
            throttle = 0.
            pending_service = True
            pending_source = "traffic"
    if state.get("longitudinal_control_schema") != 1 and state.get("system_state") == "EMERGENCY":
        requests.append(("system_emergency", "emergency", 1.))
    try:
        result = choose(throttle, requests, drive_source=value.get("decision_source", "autopilot"))
    except (KeyError, TypeError, ValueError, OverflowError):
        return reject("invalid longitudinal safety demand")
    if binding != context(state):
        return reject("longitudinal identity changed during arbitration", value, context(state))
    dependencies = [value]
    if traffic_required(traffic):
        dependencies.append(traffic)
    if current_acc and (current_acc['brake'] > 0 or current_acc['throttle'] == 0):
        dependencies.append(current_acc)
    if policy and policy['brake'] > 0:
        dependencies.append(policy)
    result.update(context=binding, sdk_frame_us=value["sdk_frame_us"],
                  observation_timestamp=value["observation_timestamp"],
                  computed_at=value["computed_at"],
                  refresh_pending=bool(value.get('refresh_pending')),
                  expires_at=min(p['expires_at'] for p in dependencies))
    winner = min(dependencies, key=lambda p: (p['expires_at'], p.get('source', '')))
    result['deadline_basis'] = dependency(winner)['deadline_basis']
    result['lease_dependencies'] = [dependency(p) for p in dependencies]
    if pending_service and result["brake"] == 0 and not result["emergency"]:
        result.update(source=pending_source, reason="service brake pending autopilot ramp")
    elif pending_source == "acc_coast" and result["brake"] == 0 and not result["emergency"]:
        result.update(source="acc", reason="current ACC coast request")
    ceiling, _ = speed_ceiling(state, binding=binding, diagnostic=diagnostic)
    if ceiling is not None and float(truck.get("speed", 0.)) > ceiling and result["throttle"] > 0:
        result.update(throttle=0., source="speed_constraint", reason="speed ceiling coast")
    # Recheck the SAME consumed snapshots after all IPC work. This also rejects
    # a decision that expires in transit instead of returning it as actionable.
    checked_at = decision_time()
    compared = value
    reason = vehicle_control_observation_rejection(state, truck, checked_at)
    if not reason:
        reason = rejection(value, binding, checked_at)
    if not reason:
        for source, consumed in (("traffic", traffic if traffic_required(traffic) else None),
                                 ("acc", current_acc), ("policy", policy)):
            if consumed is not None:
                failure = rejection(consumed, binding, checked_at)
                if failure:
                    reason = source + ": " + failure
                    compared = consumed
                    break
    if not reason and binding != context(state):
        return reject("longitudinal identity changed during arbitration", value, context(state))
    if reason:
        return reject(reason, compared)
    if result['emergency']:
        from core.navigation.longitudinal_diagnostics import bounded_copy
        result['emergency_evidence'] = bounded_copy(dict(
            traffic=traffic and {k: traffic.get(k) for k in ('sdk_frame_us',
                'observation_timestamp', 'traffic_brake', 'following', 'brake_basis')},
            source=value['decision_source'], source_observation_timestamp=value['observation_timestamp']),
            limit=8192)[0]
    if result['brake'] > 0:
        # Runtime stop witness, separate from the lossy diagnostic byte budget.
        # Only fixed scalar fields from the SAME consumed packets are retained;
        # no actor arrays, display geometry or later scalar IPC reads. A passive
        # journal may omit oversized data, but cannot erase the reason required
        # to establish continuous service braking in the physical control path.
        stop = dict(
            source=result['source'], reason=result['reason'], brake=result['brake'],
            traffic=traffic and {k: traffic.get(k) for k in ('sdk_frame_us',
                'observation_timestamp', 'traffic_brake', 'light_brake')},
            acc=current_acc and {k: current_acc.get(k) for k in ('sdk_frame_us',
                'observation_timestamp', 'brake', 'following_status')},
            policy=policy and {k: policy.get(k) for k in ('sdk_frame_us',
                'observation_timestamp', 'brake', 'reason')},
            source_observation_timestamp=value['observation_timestamp'])
        # Keep the original producer receipt without duplicating route identity
        # or display fields; the command envelope already binds that identity.
        signal = (traffic or {}).get('signal')
        if isinstance(signal, dict) and stop.get('traffic') is not None:
            from core.sdk.signal_snapshot import compact
            stop['traffic']['signal'] = compact(signal)
        light = (traffic or {}).get('light')
        if isinstance(light, dict) and stop.get('traffic') is not None:
            stop['traffic']['light'] = {k: light[k] for k in (
                'id', 'color', 'distance', 'producer_timestamp', 'producer_generation',
                'stop_target_kind', 'passage_key') if k in light}
        for key in ('traffic', 'acc', 'policy'):
            if isinstance(stop.get(key), dict):
                stop[key] = {k: v for k, v in stop[key].items() if v is not None}
        result['stopping_evidence'] = stop
    if diagnostic is not None:
        # The same immutable traffic evidence already resides in inputs. Do
        # not duplicate actor fields in the bounded journal's selected command.
        diagnostic['selected'] = {k: v for k, v in result.items()
                                  if k not in ('emergency_evidence', 'stopping_evidence', 'lease_dependencies')}
    return result, ""


def projection_input(state, *, binding=None, debug=None):
    """Receipt for the actual Map observation used for traffic projection.

    This identifies a position-dependent navigation calculation, not the age
    of the traffic DLL buffer or a confirmed actor-to-lane association.
    """
    binding = context(state) if binding is None else binding
    debug = (state.get('nav_steering_debug') or {}) if debug is None else debug
    identity = debug.get('trajectory_identity')
    expected = dict(zip(('source_game_session_id', 'source_map_key',
        'source_dataset_fingerprint', 'navigation_intent_id', 'revision',
        'route_build_id'), binding[1:7]))
    if (debug.get('authority_valid') is not True or not isinstance(identity, dict)
            or any(v is None or identity.get(k) != v for k, v in expected.items())):
        return None
    result = dict(schema_version=SCHEMA, source='route_projection', valid=True,
        context=binding, sdk_frame_us=debug.get('sdk_frame_us'),
        observation_timestamp=debug.get('observation_timestamp'),
        computed_at=debug.get('computed_at'))
    try:
        result['expires_at'] = float(result['observation_timestamp']) + LEASE_S
    except (TypeError, ValueError, OverflowError):
        return None
    if rejection(result, context(state), time.monotonic()):
        return None
    result['deadline_basis'] = dict(source='route_projection', kind='spatial_observation',
        sdk_frame_us=result['sdk_frame_us'], observation_timestamp=result['observation_timestamp'],
        expires_at=result['expires_at'])
    return result


def curve_input(state, *, binding=None):
    """Read curvature from the same immutable, identified Map calculation.

    No scalar pairing and no new observation time for an old curve profile.
    Missing geometry supplies no anticipatory limit; the existing reactive
    fallback and navigation-authority rejection remain in effect.
    """
    debug = state.get("nav_steering_debug", {}) or {}
    lane = state.get("lane_trajectory_identity")
    if lane is None:
        lane = state.get("lane_trajectory", {}) or {}
    identity = debug.get("trajectory_identity")
    if (not isinstance(identity, dict) or not identity
            or any(lane.get(k) != v for k, v in identity.items())
            or debug.get("authority_valid") is False):
        return None
    binding = context(state) if binding is None else binding
    candidate = dict(schema_version=SCHEMA, valid=True, context=binding,
        sdk_frame_us=debug.get("sdk_frame_us"), computed_at=debug.get("computed_at"),
        observation_timestamp=debug.get("observation_timestamp"))
    try:
        candidate["expires_at"] = float(candidate["observation_timestamp"]) + LEASE_S
        profile = debug["longitudinal_curve_profile"]
        radius = number(profile["radius_m"], 0., 1e12)
        distance = number(profile["distance_m"], 0., 1e12)
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if radius <= 0 or rejection(candidate, context(state), time.monotonic()):
        return None
    result = dict(candidate, source='curve', radius_m=radius, distance_m=distance)
    result['deadline_basis'] = dict(source='curve', kind='spatial_observation',
        sdk_frame_us=candidate['sdk_frame_us'], observation_timestamp=candidate['observation_timestamp'],
        expires_at=candidate['expires_at'])
    if 'roundabout_entry_distance_m' in profile:
        try:
            result['roundabout_entry_distance_m'] = number(profile['roundabout_entry_distance_m'], 0., 1e12)
        except (TypeError, ValueError, OverflowError):
            return None
    return result


def speed_ceiling(state, *, binding=None, diagnostic=None, dependencies=None):
    if diagnostic is not None:
        from core.navigation.longitudinal_diagnostics import bounded_input
    limits = []
    for source, key, factor in (("road", "speed_cap_kmh", 1. / 3.6),
                                ("policy", "planned_speed_ms", 1.)):
        value, _ = read(state, source, binding=binding, diagnostic=diagnostic)
        if diagnostic is not None:
            # The policy/ACC bodies are already retained in inputs. Repeating
            # every unavailable field for each scalar ceiling exhausted the
            # bounded journal source budget during joint producer operation.
            diagnostic.setdefault('limits', {})[source] = (
                {k: value.get(k) for k in ('source', 'context', 'sdk_frame_us',
                    'observation_timestamp', 'computed_at', 'expires_at', 'valid', key)}
                if value is not None else None)
        if value is not None:
            limits.append((float(value[key]) * factor, value))
    ceiling = min((limit for limit, _ in limits), default=None)
    # Retain every tied winning constraint. A higher static cap neither
    # authorizes nor limits this decision and must not shrink its input lease.
    winners = [value for limit, value in limits if limit == ceiling]
    expiry = min((value['expires_at'] for value in winners),
                 default=float("inf"))
    if dependencies is not None:
        dependencies.extend(winners)
    if diagnostic is not None:
        diagnostic['speed_ceiling_mps'] = ceiling
    return ceiling, expiry


def launch_rejection(state):
    """Launch is a separate owner, but cannot bypass a current brake demand."""
    if state.get("longitudinal_control_schema") != SCHEMA:
        return ""
    if state.get("system_state") in ("EMERGENCY", "PAY_TOLL"):
        return "longitudinal safety state forbids launch"
    binding = context(state)
    for source, fields in (("traffic", ("traffic_brake", "light_brake")),
                           ("acc", ("brake",)), ("policy", ("brake",))):
        value, reason = read(state, source, binding=binding,
            required=source in ("acc", "policy") and bool(state.get("longitudinal_" + source + "_active")))
        if reason:
            return reason
        if value and any(value.get(k, 0.) > 0 for k in fields):
            return source + " braking forbids launch"
    return ""
