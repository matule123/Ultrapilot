"""Bounded longitudinal arbitration, not a speed controller.

Each producer owns one immutable value in IPC. Autopilot retains its speed
controller/ramps and publishes one paired pedal decision; Engine is the only
physical owner. Timestamps refer to the original vehicle observation.
"""
import math
import time

from core.transmission_mode import vehicle_control_observation, vehicle_control_observation_rejection

SCHEMA = 1
LEASE_S = .5
COMMAND_KEY = "longitudinal_command"
PRIORITY = {"emergency": 100, "safety": 90, "obstacle": 80, "traffic": 70,
            "maneuver": 60, "curve": 50, "acc": 40, "cruise": 10}

# Existing Autopilot curve-entry envelope, now shared with the speed planner.
# These are planning assumptions, not measured grip or an ETS2 brake model.
CURVE_LATERAL_ACCEL_MS2 = 1.8
CURVE_APPROACH_DECEL_MS2 = 1.0
CURVE_BRAKE_RESPONSE_S = 1.0
CURVE_STEERING_SETUP_M = 20.0


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


def packet(state, truck, source, *, binding=None, evidence_valid=True, **values):
    """Do not make an old/missing observation fresh at publication time."""
    binding = context(state) if binding is None else binding
    observed, reason = vehicle_control_observation(state, truck)
    observed_at = observed.get("observed_at")
    expires = (float(observed_at) + LEASE_S) if isinstance(observed_at, (int, float)) else 0.
    expires = min(expires, values.pop("expires_at", expires))
    return dict(schema_version=SCHEMA, source=source, context=binding,
                sdk_frame_us=truck.get("sdkFrameTimeUs"),
                observation_timestamp=observed_at, expires_at=expires,
                computed_at=time.monotonic(),
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
    return ""


def rejection_details(value, binding, now):
    """Small immutable description of the actually compared command, not a reread."""
    fields = ('activation', 'session', 'map', 'dataset', 'intent', 'revision', 'build', 'geometry')
    result = dict(checked_at=now, expected_context=list(binding))
    if not isinstance(value, dict):
        return dict(result, packet_status='MISSING')
    result.update({k: value.get(k) for k in ('sdk_frame_us', 'observation_timestamp',
        'computed_at', 'expires_at', 'valid', 'source', 'decision_source', 'reason')})
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
                   expires_at=decision.get("expires_at", float("inf")))
    # Manager.dict assigns this complete dictionary as one value. Scalars are
    # compatibility/UI mirrors; the production Engine never mixes them.
    state.set(COMMAND_KEY, value)
    return value


def engine_decision(state, truck, now=None, *, diagnostic=None, rejection_info=None):
    """Final fail-closed pedal boundary, including newer emergency evidence."""
    # A producer can publish during any RPC. A clock captured before the read
    # must not label that complete, genuinely newer packet as future-dated.
    # Explicit `now` remains an injected decision clock for isolated clients.
    decision_time = lambda: time.monotonic() if now is None else now
    binding = context(state)
    value = state.get(COMMAND_KEY)
    def reject(reason, compared=value, expected=binding):
        if rejection_info is not None and not rejection_info:
            rejection_info.update(rejection_details(compared, expected, decision_time()))
            rejection_info['vehicle_sdk_frame_us'] = truck.get('sdkFrameTimeUs')
            rejection_info['vehicle_observation'] = truck.get('_control_observation')
        return None, reason
    if diagnostic is not None:
        from core.navigation.longitudinal_diagnostics import bounded_input
        diagnostic['requested'] = bounded_input(value)
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
            return reject('ACC target unavailable or unconfirmed departure', traffic)
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
    result.update(context=binding, sdk_frame_us=value["sdk_frame_us"],
                  observation_timestamp=value["observation_timestamp"],
                  computed_at=value["computed_at"],
                  expires_at=min([value["expires_at"], *(p["expires_at"]
                      for p in (traffic, current_acc, policy) if p is not None)]))
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
        for source, consumed in (("traffic", traffic), ("acc", current_acc), ("policy", policy)):
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
    if diagnostic is not None:
        # The same immutable traffic evidence already resides in inputs. Do
        # not duplicate actor fields in the bounded journal's selected command.
        diagnostic['selected'] = {k: v for k, v in result.items() if k != 'emergency_evidence'}
    return result, ""


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
    return dict(radius_m=radius, distance_m=distance, expires_at=candidate["expires_at"])


def speed_ceiling(state, *, binding=None, diagnostic=None):
    if diagnostic is not None:
        from core.navigation.longitudinal_diagnostics import bounded_input
    limits, expiries = [], []
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
            limits.append(float(value[key]) * factor)
            expiries.append(value["expires_at"])
    if diagnostic is not None:
        diagnostic['speed_ceiling_mps'] = min(limits) if limits else None
    return (min(limits) if limits else None,
            min(expiries) if expiries else float("inf"))


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
