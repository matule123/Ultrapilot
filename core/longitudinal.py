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


def signal_phase_plan(light, truck, observed_at, checked_at):
    """Only a qualified current phase, never prediction of future green.

    Native time_left is state_time_remaining (float seconds in the existing
    reader/HUD contract). State 1 goes toward red, state 4 toward green; neither
    yellow permits departure. Original acquisition age is deducted once.
    Directed prefab extent and a 20 m unmeasured combination-clearance allowance
    are conservative planning assumptions, not bumper/conflict measurements.
    """
    plan = dict(stop_required=light.get('color') != 'green',
                status='current_non_green', observed_at=observed_at,
                native_state=light.get('state'), original_time_left_s=light.get('time_left'))
    if light.get('color') != 'green': return plan
    try:
        timer = float(light['time_left']); age = checked_at-float(observed_at)
        distance = max(0., float(light['distance']))
        speed = abs(float(truck['speed']))
        if (light.get('state') != 8 or not all(math.isfinite(x) for x in (timer,age,distance,speed))
                or timer<0 or not 0<=age<=LEASE_S):
            raise ValueError('invalid phase timer')
        # Legacy/schema-2 lacks native direction proof. Missing authored extent
        # cannot be represented as zero-length conflict travel.
        if light.get('scope_schema') != 1:
            return dict(plan, stop_required=False, status='phase_extent_not_verified')
        if 'passage_length_m' not in light:
            return dict(plan, stop_required=True, status='phase_extent_not_verified')
        length = float(light['passage_length_m']) + 20.
        cap = min(float(light.get('passage_speed_ms',40.)), float(truck.get('speedLimit') or 40.), 40.)
        if not math.isfinite(length) or length<=0 or not math.isfinite(cap) or cap<=0:
            raise ValueError('invalid phase extent')
        # Forecast from CURRENT speed and the authored passage/road ceiling.
        # A hypothetical red-stop ceiling must not slow this green forecast to
        # zero near its entrance: that circular assumption invents a dilemma
        # even with a long green. Explicit capped acceleration/deceleration uses
        # the existing 1 m/s² planning assumption, not measured SDK dynamics.
        travel = distance+light.get('front_allowance_m',0.)+light.get('junction_standoff_m',0.)+length
        accel = CURVE_APPROACH_DECEL_MS2
        if speed <= cap:
            ramp_distance = (cap*cap-speed*speed)/(2.*accel)
            eta = ((math.sqrt(speed*speed+2.*accel*travel)-speed)/accel
                if travel<=ramp_distance else (cap-speed)/accel+(travel-ramp_distance)/cap)
        else:
            ramp_distance = (speed*speed-cap*cap)/(2.*accel)
            eta = ((speed-math.sqrt(max(cap*cap,speed*speed-2.*accel*travel)))/accel
                if travel<=ramp_distance else (speed-cap)/accel+(travel-ramp_distance)/cap)
        remaining = max(0.,timer-age)
        required = eta+CURVE_BRAKE_RESPONSE_S+LEASE_S
        reserve = speed*1.5+speed*speed/(2.*CURVE_APPROACH_DECEL_MS2)
        # The preferred envelope is the point at which braking SHOULD start,
        # not proof that stopping has already become impossible. Using it as
        # the dilemma boundary suppresses anticipation precisely when its
        # speed ceiling first asks for deceleration. The existing yellow-light
        # 4 m/s² full-brake planning bound is separate; neither is measured grip.
        minimum_reserve = speed*1.5+speed*speed/(2.*4.)
        stop = remaining < required
        # Do not impose a new anticipatory hard stop inside the existing
        # full-brake planning reserve on a CURRENT green. This is an explicit
        # dilemma assumption, not permission to pass a later red.
        dilemma = stop and speed>.5 and distance<minimum_reserve
        return dict(plan, stop_required=stop and not dilemma,
            status='green_dilemma' if dilemma else 'ending_green_stop' if stop else 'green_reserve_sufficient',
            remaining_s=remaining, required_clearance_s=required,
            travel_time_s=eta, clearance_allowance_m=20., stopping_reserve_m=reserve,
            minimum_planning_reserve_m=minimum_reserve)
    except (KeyError, TypeError, ValueError, OverflowError):
        return dict(plan, stop_required=True, status='phase_timer_invalid')


def signal_stop_speed_limit(light, speed_ms):
    """Derived target already includes front allowance and junction stand-off.

    Share the existing 1 m/s² approach assumption. Reserve the existing 1 s
    vehicle response plus the full 0.5 s allowed evidence/transfer age. These
    are conservative planning allowances, not a measured ETS2 brake model.
    """
    if (not isinstance(light, dict) or light.get('stop_target_kind') != 'derived_directed_curve_entry'
            or not (light.get('stop_required') is True
                    or light.get('color') in ('red', 'yellow', 'unknown', 'off', 'sleep'))):
        return None
    return stopping_speed_ceiling(light['distance'], speed_ms)


def stopping_speed_ceiling(distance_m, speed_ms):
    """Shared distance envelope, independent of signal color/ownership."""
    distance = number(distance_m, -1e6, 1e7)
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
    return stopping_brake_request(light['distance'], speed_ms, continuing=continuing)


def stopping_brake_continuity_required(distance_m, speed_ms):
    """Existing slow terminal-write zone, separate from an exhausted envelope.

    This is NOT permission to seed a brake at standstill. Only an actual
    acknowledged forward-started positive write can own the continuing chain.
    """
    return abs(float(speed_ms)) < .5 and float(distance_m) <= 1.5


def stopping_brake_request(distance_m, speed_ms, *, continuing=False):
    """Same feed-forward for an already qualified planned stop."""
    cap = stopping_speed_ceiling(distance_m, speed_ms)
    speed = abs(float(speed_ms));distance = float(distance_m)
    terminal_approach = stopping_brake_continuity_required(distance, speed)
    if cap == 0. or distance <= 0. or (terminal_approach and speed == 0.):
        # Exhausted reserve/target retains full demand. At terminal standstill
        # the v² request must not disappear either; Engine still requires its
        # own brake ownership/hold authorization before any physical write.
        return 1.
    # A low measured speed inside 1.5 m is NOT an exhausted envelope:
    # e.g. v=.39, d=1.49 still has a positive 1.35 m/s ceiling. A full pedal
    # there invents an earlier stop, opposed to the same distance trajectory.
    # Continue its calculated positive brake; acknowledged standstill holding
    # is owned by service_brake_hold, never by a new distance-only brake edge.
    # Removing the full-pedal jump must not also remove the FIRST positive
    # brake at a slow red approach. Without that write the physical service
    # chain never starts; ACC can propel the truck and gear=0 then rejects the
    # subsequent stop. Use the same distance demand, not a new full-brake edge.
    # This is only a pedal request: Engine still owns standstill authorization.
    if speed <= cap and not continuing and not terminal_approach:
        return 0.
    usable = max(.5, distance-speed*(CURVE_BRAKE_RESPONSE_S+LEASE_S))
    required_decel = speed*speed/(2.*usable)
    return min(1.,required_decel/4.)


def signal_speed_control(traffic, speed_ms):
    """Qualified distance constraint owned by the existing speed PID.

    No inferred color/owner. Unknown coverage keeps its independent protective
    brake. The terminal zone uses the same response/age and near-stop reserve
    already used by the stop envelope, not a new target offset or speed floor.
    """
    signal = (traffic or {}).get('signal') or {}
    light = (traffic or {}).get('light') or {}
    candidate = signal.get('candidate') or {}
    if (not signal.get('valid') or not light.get('passage_key')
            or candidate.get('id') != light.get('id')
            or candidate.get('passage_key') != light.get('passage_key')):
        return None
    cap = signal_stop_speed_limit(candidate, speed_ms)
    if cap is None:
        return None
    # A nonzero envelope is still an approach, even inside the old +1.5 m
    # band. That band used to reset ACC via an independent Traffic pedal and
    # permanently latch a tiny brake before the actual stopping reserve.
    return dict(cap_ms=cap, terminal=cap == 0.,
        brake_chain_required=stopping_brake_continuity_required(light['distance'],speed_ms),
        passage_key=light['passage_key'])


def destination_stop_control(state, truck):
    """A positive GPS remainder on this observation, never inferred arrival.

    Zero cannot distinguish manual removal, automatic cancellation or loss.
    No cached distance is reissued and no local corridor end is a destination.
    """
    try:
        distance = number(truck['routeDistance'], 0., 1e7)
        if distance <= 0.:
            return None
        if (state.get('navigation_source') != 'gps_lane'
                or state.get('game_gps_navigation_active') is not True):
            return None
        cap = stopping_speed_ceiling(distance, truck['speed'])
        return dict(distance_m=distance, cap_ms=cap,
                    terminal=distance <= abs(float(truck['speed'])) *
                        (CURVE_BRAKE_RESPONSE_S+LEASE_S)+1.5,
                    target_kind='positive_scs_gps_remainder',
                    stop_line_verified=False)
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def signal_approach_speed_limit(traffic, speed_ms):
    """Unresolved owned entry uses the SAME existing stopping envelope.

    This is a protective ceiling, not red/green qualification or clearance.
    The original signal lease still bounds it and the selector escalates to
    takeover before its stopping reserve is exhausted.
    """
    signal=(traffic or {}).get('signal') or {}
    coverage=signal.get('coverage') or {}
    if coverage.get('requires_approach') is not True:return None
    return signal_stop_speed_limit(coverage.get('approach_target'),speed_ms)


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
    signal_stop = bool((light.get('stop_required') is True or light.get('color') in ('red', 'yellow', 'unknown', 'off', 'sleep'))
        and (light_brake > 0
             or light.get('stop_target_kind') == 'derived_directed_curve_entry'))
    traffic_stop = signal_stop or bool(traffic_brake > 0
        or ((traffic or {}).get('following') or {}).get('status') == 'candidate'
        )
    policy_stop = ((policy or {}).get('reason') == 'toll stop/payment'
        or (acc or {}).get('destination_brake_selected') is True)
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
    if not isinstance(value, dict):
        return True  # Malformed published evidence must not escape validation.
    following = value.get('following') or {}
    light = value.get('light') or {}
    if not isinstance(following,dict) or not isinstance(light,dict):
        return True
    try:
        demand = max(number(value.get('traffic_brake', 0.)), number(value.get('light_brake', 0.))) > 0
    except (TypeError, ValueError, OverflowError):
        return True
    return bool(demand
        or value.get('motion_constraint')
        or signal_coverage_required(value)
        or signal_approach_required(value)
        or following.get('status') == 'candidate' or value.get('lead_distance')
        or light.get('color') in ('red', 'yellow')
        or light.get('stop_target_kind') == 'derived_directed_curve_entry')


def signal_coverage_required(value):
    if not isinstance(value,dict) or not isinstance(value.get('signal'),dict):
        return False
    coverage = value['signal'].get('coverage') or {}
    return isinstance(coverage,dict) and coverage.get('requires_takeover') is True


def signal_approach_required(value):
    if not isinstance(value,dict) or not isinstance(value.get('signal'),dict):return False
    coverage=value['signal'].get('coverage') or {}
    return isinstance(coverage,dict) and coverage.get('requires_approach') is True


def signal_coverage_rejection(value):
    if not signal_coverage_required(value):
        return ''
    return str(value['signal']['coverage'].get('reason') or
               'signal regulation coverage unverified; driver takeover required')


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
    if source == 'traffic' and isinstance(signal,dict) and (
            signal.get('valid') is True or signal_coverage_required(values) or signal_approach_required(values)):
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
    if isinstance(value.get('refresh_protocol'), dict):
        result['refresh_protocol'] = value['refresh_protocol']
    actual = value.get('context')
    if value.get('source') == 'traffic':
        following = value.get('following') or {}
        signal = value.get('signal') or {}
        following = following if isinstance(following,dict) else {}
        signal = signal if isinstance(signal,dict) else {}
        result['traffic_comparison'] = dict(
            following_status=following.get('status'), actor_identity=following.get('actor_identity'),
            departure=following.get('departure'),
            availability=value.get('traffic_availability'),
            signal_valid=signal.get('valid'), signal_reason=signal.get('reason'),
            signal_observed_at=signal.get('observed_at'), signal_generation=signal.get('generation'),
            signal_frame_us=signal.get('frame_us'),
            signal_requires_takeover=signal_coverage_required(value),
            traffic_brake=value.get('traffic_brake'), light_brake=value.get('light_brake'))
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


def signal_drive_write_guard(state, truck, value, binding, *, diagnostic=None,
                            rejection_info=None):
    """A newer distance ceiling may revoke drive, never authorize it.

    One source read at the positive-drive boundary reuses the ordinary traffic
    contract. It cannot renew the pinned decision or manufacture a new brake
    chain; the next controller tick owns the updated service-brake trajectory.
    """
    traffic, reason = read(state, 'traffic', binding=binding,
                           diagnostic=diagnostic, rejection_info=rejection_info)
    if reason or traffic is None:
        if traffic is None and value.get('moving_target_ids'):
            return value,'ACC moving traffic unavailable before write'
        return value, reason
    control = signal_speed_control(traffic, float(truck['speed']))
    cap = signal_approach_speed_limit(traffic, float(truck['speed']))
    if control is not None:
        cap = min(cap, control['cap_ms']) if cap is not None else control['cap_ms']
    destination = destination_stop_control(state, truck)
    if destination:
        cap = min(cap, destination['cap_ms']) if cap is not None else destination['cap_ms']
    scope=traffic.get('motion_constraint')
    original_ids=value.get('moving_target_ids') or ()
    if scope is not None:
        from core.service_brake_hold import moving_speed_constraint
        qualified=moving_speed_constraint(dict(source='acc',context=binding,
            stopping_evidence=dict(traffic=traffic)))
        if qualified is None:
            return value,'invalid positive moving traffic constraint before write'
        if not set(original_ids)<={t['id'] for t in qualified['targets']}:
            return value,'ACC original moving target unavailable before write'
        moving_cap=min(t['cap_mps'] for t in qualified['targets'])
        cap=min(cap,moving_cap) if cap is not None else moving_cap
    elif original_ids:
        # Do not accept disappearance between arbitration and positive write.
        return value,'ACC moving constraint unavailable before write'
    if cap is None or float(truck['speed']) <= cap:
        return value, ''
    result = dict(value, throttle=0., source='speed_constraint',
                  reason='current signal ceiling inhibits drive before write')
    result['lease_dependencies'] = [*value.get('lease_dependencies', ()), dependency(traffic)]
    if traffic['expires_at'] < value['expires_at']:
        result.update(expires_at=traffic['expires_at'],
                      deadline_basis=dependency(traffic)['deadline_basis'])
    if diagnostic is not None:
        from core.navigation.longitudinal_diagnostics import bounded_input
        diagnostic['signal_write_guard'] = bounded_input(traffic)
        diagnostic.setdefault('inputs', {})['traffic'] = diagnostic['signal_write_guard']
        diagnostic['selected'] = {k: v for k, v in result.items()
            if k not in ('emergency_evidence', 'stopping_evidence', 'lease_dependencies')}
    return result, ''


def publish(state, truck, source, **values):
    value = packet(state, truck, source, **values)
    state.set("longitudinal_" + source, value)
    return value


def initialization_record(state, activation, started_at, deadline):
    """Engine's existing first-command/launch bound, never an input lease."""
    return dict(context=(activation, *context(state)[1:]), started_at=started_at,
                expires_at=deadline)


def initialization_request(state, binding, now):
    value = state.get('longitudinal_initialization')
    if (not isinstance(value, dict) or tuple(value.get('context', ())) != tuple(binding)
            or tuple(binding) != context(state)
            or not (state.get('autopilot_active') or state.get('auto_drive_pending'))
            or state.get('autopilot_control_state') == 'controlled_stop'):
        return None
    try:
        if not 0 < float(value['started_at']) <= now <= float(value['expires_at']):
            return None
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    return value


def _initialization_input_reason(state, source, value, binding, now, reason):
    """Quarantine an old activation during initialization; never consume it.

    Validate against its OWN original identity/time before classifying the
    scheduling transition. All non-activation authority fields must agree.
    A zero invalid retired ACC result is not an acknowledgement of the new N.
    """
    retired_zero_acc = bool(source == 'acc' and isinstance(value, dict)
        and reason == 'invalid longitudinal observation' and value.get('valid') is False
        and value.get('throttle') == 0. and value.get('brake') == 0.
        and value.get('emergency') is False)
    if (reason != 'longitudinal identity or activation changed' and not retired_zero_acc) or not isinstance(value, dict):
        return reason
    original = value.get('context')
    if (not isinstance(original, (tuple,list)) or len(original) != len(binding)
            or original[0] == binding[0] or tuple(original[1:]) != tuple(binding[1:])
            or value.get('source') != source):
        return reason
    request = state.get('longitudinal_initialization')
    if (isinstance(request,dict) and tuple(request.get('context', ())) == tuple(binding)
            and isinstance(request.get('expires_at'), (int,float))
            and now > request['expires_at']):
        return 'longitudinal initialization timed out waiting for ' + source
    # This classification NEVER returns the retired packet as usable. Its zero
    # invalid result can be quarantined only in the existing initialization
    # bound of another epoch, with every original time/route field checked.
    # A fault from the current epoch, nonzero request or stale/future packet
    # still follows the ordinary rejection path.
    original_failure = rejection(dict(value, valid=True) if retired_zero_acc else value, original, now)
    if original_failure:
        return original_failure  # Stale/future/invalid data are never benign.
    try:
        for field in {'traffic':('traffic_brake','light_brake'),
                      'acc':('throttle','brake'), 'policy':('brake','planned_speed_ms')}.get(source, ()):
            number(value[field], 0., 200. if field=='planned_speed_ms' else 1.)
        if source == 'traffic' and traffic_contract_rejection(value):
            return reason
    except (KeyError,TypeError,ValueError,OverflowError):
        return reason
    if initialization_request(state, binding, now):
        return 'longitudinal initialization pending'
    return reason


def read(state, source, now=None, *, required=False, binding=None, diagnostic=None, rejection_info=None):
    """One IPC read per producer, never combine scalar throttle/brake reads."""
    read_started_at = time.monotonic() if now is None else now
    value = state.get("longitudinal_" + source)
    read_returned_at = time.monotonic() if now is None else now
    reread_count = 0
    explicit_required = required
    if source == 'traffic' and traffic_required(value):
        required = True
    compared_binding = context(state) if binding is None else binding
    checked_at = time.monotonic() if now is None else now
    reason = rejection(value, compared_binding, checked_at)
    original_reason = reason
    reason = _initialization_input_reason(state, source, value, compared_binding, checked_at, reason)
    if reason != original_reason:
        required = True  # An old optional packet must not silently permit launch.
    if reason in ('longitudinal decision needs refresh', 'longitudinal observation is stale or incoherent'):
        # One bounded reread: publication may have overtaken the first RPC.
        # Validate the returned immutable value after reading, never retimestamp.
        newer = state.get('longitudinal_' + source)
        rechecked = time.monotonic() if now is None else now
        reread_count = 1
        if not rejection(newer, compared_binding, rechecked):
            read_returned_at = rechecked
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
    coverage_reason = signal_coverage_rejection(value) if not reason and source == 'traffic' else ''
    if not reason and source == 'traffic':
        try:
            reason = traffic_contract_rejection(value, required=explicit_required)
        except (KeyError, TypeError, ValueError, OverflowError):
            reason = 'invalid traffic evidence roles'
    if coverage_reason and reason.startswith('traffic actor evidence unavailable:'):
        # A valid envelope with unqualified regulation has its own takeover
        # cause, independent of unrelated optional actor identity failures.
        reason = ''
    if diagnostic is not None:
        from core.navigation.longitudinal_diagnostics import bounded_input
        # Fixed-size receiver timing of the value actually validated. This is
        # a sampled read, never a claim about first delivery/producer creation.
        diagnostic.setdefault('input_read_timing', {})[source] = [read_started_at,
            read_returned_at, checked_at, reread_count,
            *[value.get(k) if isinstance(value, dict) else None for k in
              ('sdk_frame_us', 'observation_timestamp', 'computed_at', 'expires_at')]]
        diagnostic.setdefault('input_rejections', {})[source] = reason or coverage_reason
        if reason or coverage_reason:
            diagnostic.setdefault('rejected_inputs', {})[source] = bounded_input(value)
    if reason or coverage_reason:
        if required and rejection_info is not None and not rejection_info:
            rejection_info.update(rejection_details(value, compared_binding, checked_at))
            rejection_info['rejected_source'] = source
            rejection_info['rejection_cause'] = reason or coverage_reason
            if source == 'traffic' and signal_coverage_required(value):
                from core.sdk.signal_snapshot import compact
                rejection_info['signal'] = compact(value['signal'])
    if reason:
        return None, (source + ": " + reason if required else "")
    # Valid urgent brake evidence remains available to the existing safety
    # stop, while the authoritative owners reject propulsion/clearance.
    return value, (source + ': ' + coverage_reason if coverage_reason else '')


def traffic_contract_rejection(value, *, required=False):
    """Validate new separate evidence roles; legacy valid-bit guards remain.

    Unknown optional actors create no demand and no clearance. Required target
    loss is also enforced by ACC/Engine's existing following latch; a signal
    stop/hold cannot be cleared by an actor feed becoming empty/unusable.
    """
    availability = value.get('traffic_availability')
    if signal_approach_required(value):
        signal=value['signal'];coverage=signal['coverage'];target=coverage.get('approach_target')
        if (not isinstance(target,dict) or target.get('color')!='unknown'
                or target.get('stop_target_kind')!='derived_directed_curve_entry'
                or not isinstance(target.get('passage_key'),str) or not target['passage_key']
                or signal_approach_speed_limit(value,0.) is None
                or not 0 < number(signal.get('observed_at'),0.,1e12) <= value['computed_at']
                or value['expires_at'] > signal['observed_at']+LEASE_S
                or any(type(signal.get(k)) is not int or signal[k]<=0
                       for k in ('generation','frame_us','lifecycle'))):
            return 'invalid unresolved signal approach target or source lease'
    if availability is None:
        return ''  # Existing legacy producers still require their valid bit.
    following, signal = value.get('following') or {}, value.get('signal') or {}
    if not isinstance(following,dict) or not isinstance(signal,dict):
        return 'invalid traffic evidence roles'
    if (not isinstance(availability,dict) or availability.get('schema_version')!=1
            or type(availability.get('actors_usable')) is not bool):
        return 'invalid traffic availability contract'
    usable = availability['actors_usable']
    if usable != (following.get('status') in ('candidate','no_candidate_unproven_coverage')):
        return 'incoherent traffic actor availability'
    if usable and (availability.get('buffers_present') is not True
            or availability.get('stable_read') is not True
            or not 0 < number(availability.get('receiver_time'),0.,1e12) <= value['computed_at']
            or value['expires_at'] > availability['receiver_time']+LEASE_S):
        return 'incoherent traffic receiver capture'
    if not usable and number(value['traffic_brake']) > 0:
        return 'traffic braking lacks usable actor evidence'
    light = value.get('light')
    control = signal.get('candidate') if signal.get('valid') is True else signal.get('stop_candidate')
    if number(value['light_brake']) > 0 and (not isinstance(light,dict) or light!=control):
        return 'signal braking lacks qualified control evidence'
    if required and not usable and not isinstance(control,dict) and not signal_approach_required(value):
        return 'traffic actor evidence unavailable: ' + str(following.get('status') or 'missing')
    return ''


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
    request = state.get('longitudinal_refresh_request')
    response_to_publish = False
    publication = None
    if (isinstance(request, dict) and request.get('token')
            and tuple(request.get('context', ())) == tuple(binding)):
        if value.get('refresh_pending'):
            value['refresh_protocol'] = refresh_receipt(request, 'pending')
            if value['expires_at'] == request['expires_at']:
                value['deadline_basis'] = dict(source='decision_refresh', kind='bounded_refresh',
                    expires_at=request['expires_at'], token=request['token'])
        elif value.get('valid') and not value.get('handoff_required'):
            completed = state.get('longitudinal_refresh_completed') or {}
            if completed.get('token') != request['token']:
                prior = state.get('longitudinal_refresh_response') or {}
                proof = prior.get('publication') if prior.get('token') == request['token'] else None
                local = getattr(state, '_longitudinal_owner_publication', None)
                if (not proof and isinstance(local, dict)
                        and refresh_response_qualifies(local['command'], request)
                        and local['command']['computed_at'] <= local['returned_at'] <= request['expires_at']):
                    proof = dict({k:v for k,v in local['command'].items() if k != 'context'},
                        publish_completed_at=local['returned_at'])
                value['refresh_protocol'] = refresh_receipt(request, 'response')
                if proof:
                    value['refresh_protocol']['publication'] = proof
                if not refresh_response_qualifies(value, request):
                    value.pop('refresh_protocol')
                else:
                    # Preserve the FIRST actual publication witness across AP
                    # ticks while Engine has not yet acknowledged application.
                    response_to_publish = prior.get('token') != request['token']
                    publication = proof
    # Manager.dict assigns this complete dictionary as one value. Scalars are
    # compatibility/UI mirrors; the production Engine never mixes them.
    observed = truck.get('_control_observation') or {}
    trace = decision.get('producer_trace')
    if isinstance(trace, dict):
        value['producer_trace'] = dict(trace, truck=dict(
            sdk_frame_us=truck.get('sdkFrameTimeUs'), observation_timestamp=observed.get('observed_at'),
            observation_valid=observed.get('valid'), gear=truck.get('gear'), speed_mps=truck.get('speed')),
            decision_sequence=decision.get('diagnostic_sequence'))
        eco = decision.get('eco_observation')
        if isinstance(eco,dict):
            from core.navigation.longitudinal_diagnostics import bounded_input
            value['producer_trace']['eco'] = bounded_input(eco)
    state.set(COMMAND_KEY, value)
    returned_at = time.monotonic()
    if response_to_publish:
        if publication is not None or returned_at <= request['expires_at']:
            state.set('longitudinal_refresh_response', dict(token=request['token'],
                publication=publication or dict(
                    {k:value.get(k) for k in ('source','valid','computed_at','expires_at',
                        'sdk_frame_us','observation_timestamp','throttle','brake','decision_source')},
                    publish_completed_at=returned_at)))
    if value.get('valid') and not value.get('refresh_pending') and not value.get('handoff_required'):
        # One publisher-local receipt, not another IPC read or command history.
        # Retain across pending ticks, never across a different authority match.
        state._longitudinal_owner_publication = dict(returned_at=returned_at,
            command={k:value.get(k) for k in ('source','valid','context','computed_at','expires_at',
                'sdk_frame_us','observation_timestamp','throttle','brake','decision_source')})
    return value


def refresh_receipt(request, status):
    """Fixed-size protocol provenance, not a mutable shared-slot reference."""
    original = request['rejected']
    return dict(token=request['token'], state=status, started_at=request['started_at'],
        expires_at=request['expires_at'], cause=dict(original['deadline_basis']),
        original={k: original.get(k) for k in ('source', 'sdk_frame_us',
            'observation_timestamp', 'computed_at', 'expires_at')})


def refresh_response_qualifies(value, request):
    """A complete newer owner decision, including publication/request races.

    Engine can issue the request after AP already computed the replacement.
    The response therefore need not carry an acknowledgement added by AP, but
    must supersede the original decision AND its deadline before the fixed bound.
    Ordinary schema/identity/vehicle/input checks still apply at every consumer.
    """
    try:
        proof = (value.get('refresh_protocol') or {}) if isinstance(value, dict) else {}
        publication = proof.get('publication') or {}
        timely_publication = (proof.get('token') == request.get('token')
            and request['rejected']['computed_at'] < publication.get('computed_at', 0.)
            <= publication.get('publish_completed_at', 0.) <= request['expires_at']
            and publication.get('expires_at', 0.) > request['rejected']['expires_at']
            and publication.get('computed_at', 0.) <= value['computed_at'])
        return (isinstance(value, dict) and value.get('source') == 'autopilot'
            and value.get('valid') is True and not value.get('refresh_pending')
            and not value.get('handoff_required')
            and tuple(value.get('context', ())) == tuple(request['context'])
            and request['rejected']['computed_at'] < value['computed_at']
            and (value['computed_at'] <= request['expires_at'] or timely_publication)
            and value['expires_at'] > request['rejected']['expires_at'])
    except (KeyError, TypeError, ValueError):
        return False


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
    if reason == 'longitudinal initialization pending':
        request = initialization_request(state, binding, now)
        if (request and not vehicle_control_observation_rejection(state, truck, now)
                and truck.get('gear', -1) >= 0 and truck.get('speed', -1.) >= -.10):
            return request
        return None
    if (reason not in ('longitudinal decision needs refresh',
                       'longitudinal observation is stale or incoherent',
                       'longitudinal input lease expired before write')
            or not isinstance(value, dict) or value.get('valid') is not True
            or tuple(value.get('context', value.get('actual_context', ()))) != tuple(binding)
            or vehicle_control_observation_rejection(state, truck, now)
            or truck.get('gear', -1) < 0 or truck.get('speed', -1.) < -.10
            or state.get('autopilot_control_state') == 'controlled_stop'):
        return None
    try:
        current = state.get('longitudinal_refresh_request')
        if value.get('refresh_pending'):
            # Both receipt and final-write recovery follow the SAME original
            # cause/bound, never the zero command's synthetic legacy deadline.
            proof = value.get('refresh_protocol') or {}
            if (not isinstance(current, dict) or not current.get('token')
                    or proof.get('token') != current['token']
                    or tuple(current.get('context', ())) != tuple(binding)):
                return None
            value = current['rejected']
        obs, computed, expiry = (float(value[k]) for k in (
            'observation_timestamp', 'computed_at', 'expires_at'))
        if not 0 < obs <= computed <= now or now-obs > LEASE_S or expiry > obs+LEASE_S:
            return None
        basis = value['deadline_basis']
        source = basis['source']
        same_request = (isinstance(current, dict)
            and tuple(current.get('context', ())) == tuple(binding))
        response = value.get('refresh_protocol') or {}
        completed = state.get('longitudinal_refresh_completed') or {}
        acknowledged = (same_request and completed.get('token') == current.get('token'))
        if (same_request and (acknowledged or response.get('state') == 'response'
                and response.get('token') == current.get('token'))
                and computed >= current['started_at']
                and expiry > current['rejected']['expires_at']):
            # A new complete response can itself encounter a later independent
            # dependency deadline. It is a new causal attempt, not rearming the
            # old producer's repeated expired candidate.
            same_request = False
        if source == 'curve':
            fresh = curve_input(state, binding=binding,
                handoff_deadline=expiry if now <= expiry else None)
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
        source_read_returned_at = time.monotonic()
        newer = fresh and fresh['expires_at'] > expiry and fresh['expires_at']-now >= HANDOFF_RESERVE_S
        expiring = (fresh and fresh['expires_at'] == expiry and now <= expiry
            and (source != 'curve' or (fresh['sdk_frame_us'] == basis.get('sdk_frame_us')
                and fresh['observation_timestamp'] == basis.get('observation_timestamp'))))
        if not (newer or expiring or same_request and now <= current['expires_at']):
            return None
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if not same_request:
        # Both processes can notice the SAME rejected decision concurrently.
        # Anchor the bound to its ORIGINAL deadline, not a racing read time.
        import hashlib
        import json
        token = hashlib.sha256(json.dumps([binding, basis], sort_keys=True,
            separators=(',', ':')).encode()).hexdigest()[:24]
        current = dict(context=binding, token=token, started_at=now, expires_at=expiry+HANDOFF_WAIT_S,
                       reason=reason, rejected=value, source=source)
        state.set('longitudinal_refresh_request', current)
    if now > current['expires_at']:
        return None  # Do not restart the wait on every rejected producer tick.
    if tuple(binding) != context(state):
        return None
    # A receiver witness for this bounded attempt, not fresh permission to use
    # the rejected pedals. Store only compact original provenance in export.
    return dict(current, refresh_evidence=dict(checked_at=now, source=source,
        rejected_deadline=expiry, source_read_returned_at=source_read_returned_at,
        replacement_deadline=fresh.get('expires_at') if fresh else None,
        newer_live_source=bool(newer)))


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
        if fresh['expires_at'] == traffic['expires_at']:
            fresh['deadline_basis'] = dependency(traffic)['deadline_basis']
    fresh['context'] = binding
    fresh['sdk_frame_us'] = truck['sdkFrameTimeUs']
    fresh['source'] = fresh['decision_source'] if not fresh['emergency'] else 'traffic_emergency'
    fresh['refresh_pending'] = True
    fresh['refresh_evidence'] = request.get('refresh_evidence')
    if request.get('token'):
        fresh['refresh_protocol'] = refresh_receipt(request, 'pending')
        if fresh['expires_at'] == request['expires_at']:
            fresh['deadline_basis'] = dict(source='decision_refresh', kind='bounded_refresh',
                expires_at=request['expires_at'], token=request['token'])
    return fresh


def refresh_response_pair(state, previous, rejected, reason, *, diagnostic=None):
    """At most ONE actual owner reread; never compute/relabel drive in Engine.

    A complete response published within the fixed wait may be available when
    an older zero command reaches its write gate. Re-run the entire executor
    with the paired real SDK snapshot. If absent, foreign or late, fail closed.
    """
    if (not isinstance(rejected, dict) or not rejected.get('refresh_pending')
            or reason not in ('longitudinal input lease expired before write',
                              'longitudinal observation is stale or incoherent')):
        return None
    request = state.get('longitudinal_refresh_request')
    if not isinstance(request, dict) or not request.get('token'):
        return None
    pair = capture_command_observation(state, previous.truck)
    value = pair.command
    now = time.monotonic()
    if diagnostic is not None:
        diagnostic.update(request=refresh_receipt(request, 'response_checked'),
            checked_at=now, reason=reason, pairing=pair.provenance,
            candidate={k:value.get(k) for k in ('source', 'valid', 'context', 'sdk_frame_us',
                'observation_timestamp', 'computed_at', 'expires_at', 'refresh_pending',
                'refresh_protocol', 'throttle', 'brake')} if isinstance(value, dict) else None)
    if (not isinstance(value, dict) or value.get('refresh_pending')
            or value.get('source') != 'autopilot' or rejection(value, pair.binding, now)
            or vehicle_control_observation_rejection(state, pair.truck, now)
            or pair.truck.get('gear', -1) < 0 or pair.truck.get('speed', -1.) < -.10
            or tuple(request['context']) != pair.binding or pair.binding != context(state)
            or not refresh_response_qualifies(value, request)
            or state.get('autopilot_control_state') == 'controlled_stop'):
        return None
    return CommandObservation(pair.binding, value, pair.truck, dict(pair.provenance,
        refresh_recovery=dict(request=refresh_receipt(request, 'response_received'),
            rejected={k: rejected.get(k) for k in ('sdk_frame_us', 'observation_timestamp',
                'computed_at', 'expires_at', 'deadline_basis')},
            received_at=now, reason=reason)))


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
            and pair.command.get('refresh_pending')
            and (not request.get('token') or (pair.command.get('refresh_protocol') or {}).get('token')
                 == request.get('token'))):
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
    request = state.get('longitudinal_refresh_request')
    completed = state.get('longitudinal_refresh_completed') or {}
    response_receipt = None
    if (isinstance(request, dict) and request.get('token')
            and tuple(request.get('context', ())) == tuple(binding)
            and completed.get('token') != request['token']
            and refresh_response_qualifies(value, request)):
        response_receipt = refresh_receipt(request, 'response')
        original_proof = value.get('refresh_protocol') or {}
        if original_proof.get('token') == request['token'] and original_proof.get('publication'):
            response_receipt['publication'] = original_proof['publication']
    if (isinstance(request, dict) and request.get('token')
            and tuple(request.get('context', ())) == tuple(binding)
            and completed.get('token') != request['token']
            and not value.get('refresh_pending')
            and decision_time() > request['expires_at']
            and response_receipt is None):
        result = reject('longitudinal refresh response missed fixed deadline')
        if rejection_info is not None:
            rejection_info['refresh_protocol'] = refresh_receipt(request, 'timed_out')
        return result
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
    traffic, traffic_reason = read(state, "traffic", now, binding=binding, diagnostic=diagnostic,
        rejection_info=rejection_info)
    if traffic_reason:
        return reject(traffic_reason)
    current_acc, acc_reason = read(state, "acc", now, binding=binding,
        required=bool(state.get("longitudinal_acc_active")), diagnostic=diagnostic,
        rejection_info=rejection_info)
    policy, policy_reason = read(state, "policy", now, binding=binding,
        required=bool(state.get("longitudinal_policy_active")), diagnostic=diagnostic,
        rejection_info=rejection_info)
    if diagnostic is not None:
        from core.navigation.longitudinal_diagnostics import compact_traffic_cause
        diagnostic['traffic_cause'] = compact_traffic_cause(traffic)
        diagnostic['inputs'] = {k: bounded_input(v) for k, v in (
            ('traffic', traffic), ('acc', current_acc), ('policy', policy))}
        diagnostic['regulator_mode'] = current_acc.get('speed_control_reason') if current_acc else None
        diagnostic['regulator_mode_status'] = ('PRODUCER_SPEED_CONTROL_REASON'
                                               if current_acc else 'NOT_VERIFIED')
    if acc_reason or policy_reason:
        return reject(acc_reason or policy_reason)
    following = traffic.get('following') if traffic else None
    moving_scope = None
    if (traffic or {}).get('motion_constraint') is not None:
        from core.service_brake_hold import moving_speed_constraint
        moving_scope = moving_speed_constraint(dict(source='acc',context=binding,
            stopping_evidence=dict(traffic=traffic)))
        if moving_scope is None:
            return reject('invalid positive moving traffic constraint', traffic)
        if float(truck['speed']) > min(t['cap_mps'] for t in moving_scope['targets']):
            throttle = 0.  # Current hard cap applies even between ACC ticks.
    observed_lead_departure = False
    if current_acc and current_acc.get('following_required') is True:
        # Target loss is not clear-road evidence, including between ACC ticks.
        # The old candidate cannot outlive its source's original short lease.
        from core.acc_following import observed_departure
        candidate_present = isinstance(following, dict) and following.get('status') == 'candidate'
        moving_target_present = bool(moving_scope and current_acc.get('following_target_id')
                                    in {t['id'] for t in moving_scope['targets']})
        observed_lead_departure = observed_departure(
            following, current_acc.get('following_target_id'), decision_time())
        if not candidate_present and not moving_target_present and not observed_lead_departure:
            result = reject('ACC target unavailable or unconfirmed departure', traffic)
            if rejection_info is not None:
                rejection_info['following_target_id'] = current_acc.get('following_target_id')
                rejection_info['following_status'] = following.get('status') if isinstance(following, dict) else None
                rejection_info['following_confirmed'] = current_acc.get('following_confirmed')
            return result
        if candidate_present:
            try:
                cap = number(following['speed_cap_mps'], 0., 140.)
                if float(truck['speed']) > cap:
                    throttle = 0.
            except (KeyError, TypeError, ValueError, OverflowError):
                return reject('invalid ACC following constraint', traffic)
        elif not moving_target_present:
            # The new Traffic receipt can precede ACC's next independent tick.
            # It has no following cap; do not fabricate one or apply old drive.
            # Current braking/emergency floors remain effective below.
            throttle = 0.
    if traffic:
        approach_cap=signal_approach_speed_limit(traffic,float(truck['speed']))
        qualified = signal_speed_control(traffic, float(truck['speed']))
        if qualified is not None:
            approach_cap = min(qualified['cap_ms'], approach_cap) if approach_cap is not None else qualified['cap_ms']
        if approach_cap is not None and float(truck['speed'])>approach_cap:
            throttle=0.  # Fresh lower ceiling also wins between producer ticks.
    destination = destination_stop_control(state, truck)
    if destination and float(truck['speed']) > destination['cap_ms']:
        throttle = 0.
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
    if result['source'] == value['decision_source'] and not result['emergency']:
        result['reason'] = value['reason']  # preserve the selected producer's cause
    if binding != context(state):
        return reject("longitudinal identity changed during arbitration", value, context(state))
    dependencies = [value]
    if traffic_required(traffic) or observed_lead_departure:
        dependencies.append(traffic)
    if current_acc and (current_acc['brake'] > 0 or current_acc['throttle'] == 0):
        dependencies.append(current_acc)
    if policy and policy['brake'] > 0:
        dependencies.append(policy)
    result.update(context=binding, sdk_frame_us=value["sdk_frame_us"],
                  # Preserve the validated envelope through selection. The
                  # physical gate can discover expiry after this function;
                  # bounded recovery must receive the original qualification,
                  # not a pedal-only dict that looks like invalid evidence.
                  schema_version=value['schema_version'], valid=value['valid'],
                  decision_source=value['decision_source'],
                  observation_timestamp=value["observation_timestamp"],
                  computed_at=value["computed_at"],
                  refresh_pending=bool(value.get('refresh_pending')),
                  expires_at=min(p['expires_at'] for p in dependencies))
    if isinstance(value.get('refresh_protocol'), dict):
        result['refresh_protocol'] = value['refresh_protocol']
    if response_receipt is not None:
        result['refresh_protocol'] = response_receipt
    if moving_scope:
        result['moving_target_ids']=tuple(t['id'] for t in moving_scope['targets'])
    winner = min(dependencies, key=lambda p: (p['expires_at'], p.get('source', '')))
    result['deadline_basis'] = dependency(winner)['deadline_basis']
    result['lease_dependencies'] = [dependency(p) for p in dependencies]
    if pending_service and result["brake"] == 0 and not result["emergency"]:
        result.update(source=pending_source, reason="service brake pending autopilot ramp")
    elif pending_source == "acc_coast" and result["brake"] == 0 and not result["emergency"]:
        result.update(source="acc", reason="current ACC coast request")
    if observed_lead_departure and not candidate_present and result['brake'] == 0 and not result['emergency']:
        result.update(source='acc', reason='observed lead departure; awaiting current ACC decision')
    ceiling, _ = speed_ceiling(state, binding=binding, diagnostic=diagnostic)
    if ceiling is not None and float(truck.get("speed", 0.)) > ceiling and result["throttle"] > 0:
        result.update(throttle=0., source="speed_constraint", reason="speed ceiling coast")
    phase = ((traffic or {}).get('light') or {}).get('phase_plan') or {}
    if phase.get('status') == 'green_dilemma' and not result['emergency'] and result['brake'] == 0:
        # The current green does not have a demonstrated clearance reserve,
        # while the planning stop bound is already exhausted. Do not add drive
        # or invent a future green. Existing red/emergency demands still win;
        # this explicit coast is not certification of physical stop feasibility.
        result.update(throttle=0., source='traffic_signal_phase',
                      reason='current green planning dilemma; coast without clearance proof')
    # Recheck the SAME consumed snapshots after all IPC work. This also rejects
    # a decision that expires in transit instead of returning it as actionable.
    checked_at = decision_time()
    compared = value
    reason = vehicle_control_observation_rejection(state, truck, checked_at)
    if not reason:
        reason = rejection(value, binding, checked_at)
    if not reason:
        for source, consumed in (("traffic", traffic if traffic_required(traffic) or observed_lead_departure else None),
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
        from core.navigation.longitudinal_diagnostics import emergency_evidence
        result['emergency_evidence'] = emergency_evidence(
            traffic,value['decision_source'],value['observation_timestamp'])
    if result['brake'] > 0 or traffic_required(traffic) or destination:
        # Runtime stop witness, separate from the lossy diagnostic byte budget.
        # Only fixed scalar fields from the SAME consumed packets are retained;
        # no actor arrays, display geometry or later scalar IPC reads. A passive
        # journal may omit oversized data, but cannot erase the reason required
        # to establish continuous service braking in the physical control path.
        # Keep a recovered same-head observation even when its moving approach
        # profile requests zero brake. Engine's already acknowledged chain must
        # see that receipt to acquire clearance or release below the envelope.
        stop = dict(
            source=result['source'], reason=result['reason'], brake=result['brake'],
            traffic=traffic and {k: traffic.get(k) for k in ('sdk_frame_us',
                'observation_timestamp', 'traffic_brake', 'light_brake', 'motion_constraint')},
            acc=current_acc and {k: current_acc.get(k) for k in ('sdk_frame_us',
                'observation_timestamp', 'brake', 'following_status', 'signal_stop_control',
                'signal_brake_selected', 'control_target_kmh')},
            policy=policy and {k: policy.get(k) for k in ('sdk_frame_us',
                'observation_timestamp', 'brake', 'reason')},
            source_observation_timestamp=value['observation_timestamp'])
        basis = (traffic or {}).get('brake_basis')
        if isinstance(basis, dict) and stop.get('traffic') is not None:
            # Stop ownership needs the consumed cause, not unbounded actors or
            # forecast arrays. Missing provenance remains explicitly unknown.
            stop['traffic']['brake_basis'] = {k: basis[k] for k in
                ('kind', 'target_id', 'confirmed_route_conflict', 'stop_contract',
                 'source_acquisition', 'targets', 'targets_complete') if k in basis}
            decisive = basis.get('decisive')
            if isinstance(decisive, dict):
                stop['traffic']['brake_basis']['decisive'] = {k: decisive[k] for k in
                    ('id', 'distance_m', 'route_progress_m', 'actor_arrival_s',
                     'ego_arrival_earliest_s', 'ego_arrival_latest_s', 'brake',
                     'actor', 'ego_motion_basis') if k in decisive}
        if destination:
            stop['destination'] = {k: destination[k] for k in
                ('distance_m', 'cap_ms', 'terminal', 'target_kind', 'stop_line_verified')}
            stop['destination_brake_selected'] = bool(current_acc and
                current_acc.get('destination_brake_selected') is True)
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


def curve_input(state, *, binding=None, handoff_deadline=None):
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
    checked_at = time.monotonic()
    failure = rejection(candidate, context(state), checked_at)
    # A zero-drive transition may have begun on still-valid evidence and lose
    # the last few milliseconds during its own RPC. Only the EXACT leaf of
    # that deadline may witness the transition, within the existing 100 ms
    # bound. It is never returned to the planner as an executable constraint
    # and never renews an observation, deadline or propulsion command.
    transition_leaf = (handoff_deadline is not None
        and failure == 'longitudinal observation is stale or incoherent'
        and candidate['expires_at'] == handoff_deadline
        and 0 < candidate['observation_timestamp'] <= candidate['computed_at'] <= checked_at
        and handoff_deadline < checked_at <= handoff_deadline+HANDOFF_WAIT_S
        and type(candidate['sdk_frame_us']) is int and candidate['sdk_frame_us'] > 0
        and tuple(candidate['context']) == tuple(context(state)))
    if radius <= 0 or failure and not transition_leaf:
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
