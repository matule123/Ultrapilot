import logging
import math
import time
import numpy as np
from sdk.base_plugin import BasePlugin
from core.pid import PID
from core.acc_acceleration import pedal_acceleration, DRIVE_GAIN_MS2
from core.longitudinal import (COMMAND_KEY, context, exclusive, read, publish,
                               rejection, curve_input, curve_speed_envelope, traffic_required)
from core.transmission_mode import vehicle_control_observation_rejection
from plugins.acc.settings import settings

class Plugin(BasePlugin):
    """
    Adaptive Cruise Control (ACC) Plugin.
    Maintains a safe distance from the vehicle in front by controlling speed,
    and (improvement over the original) automatically respects the in-game
    posted speed limit when ``obey_speed_limit`` is enabled.
    """

    NAME = "acc"
    VERSION = "1.3.0"

    def on_start(self):
        logging.info("ACC Plugin started with bounded speed PID control.")
        self.enabled = True
        self.sdk.set("longitudinal_acc_active", True)

        # Input error is km/h; output is normalized drive. Lower proportional
        # and measurement-derivative sensitivity are validated across the fixed
        # Phase 7.2 delay/load/noise matrix, not tuned from a single ETS2 run.
        # Existing PID in nominal acceleration units; no parallel loop. Only
        # its SDK speed derivative is estimated on a 150 ms ordinary-control
        # horizon. This avoids amplifying frame noise into alternating demand;
        # P/limits, source-loss withdrawal and emergency remain immediate.
        self.speed_pid = PID(kp=0.15*DRIVE_GAIN_MS2, ki=0.06*DRIVE_GAIN_MS2,
                             kd=0.015*DRIVE_GAIN_MS2,
                             output_limits=(-DRIVE_GAIN_MS2, DRIVE_GAIN_MS2),
                             derivative_on_measurement=True, anti_windup=True,
                             reset_on_setpoint=False, measurement_derivative_tau=.15)
        self.speed_pid.set_setpoint(settings.target_speed)
        self._control_target = None
        self._control_context = None
        self._last_observation = None
        self._speed_braking = False
        self._was_driving = False
        self._following_binding = None
        self._followed_target = False
        self._following_target_id = None
        self._following_fault = ''
        self._signal_control_active = False
        self._native_following_lifecycle = None

    def on_stop(self):
        logging.info("ACC Plugin stopped.")
        self.enabled = False
        self.speed_pid.reset()
        self._last_observation = None
        self._followed_target = False
        self._following_target_id = None
        self._following_binding = None
        self._following_fault = ''
        self.sdk.set('acc_following_status', 'disabled')
        self.sdk.set("longitudinal_acc_active", False)
        self.sdk.set("longitudinal_acc", None)
        self.sdk.shared_state.update_batch({"acc_throttle": None, "acc_brake": None})

    def on_tick(self, delta_time: float):
        if not self.enabled:
            return

        # 1. Telemetry & State
        binding = context(self.sdk.shared_state)
        # Epoch/session/intent ownership is revoked even if the first new SDK
        # acquisition is invalid. Invalid data still publish a zero invalid
        # request; they must not preserve another activation's private latch.
        if binding != self._following_binding:
            same_dependency = (isinstance(self._following_binding, (tuple, list))
                and len(self._following_binding) == len(binding) == 8
                and tuple(self._following_binding[:5]) == tuple(binding[:5]))
            self._following_binding = binding
            if not same_dependency:
                self._followed_target = False
                self._following_target_id = None
                self._following_fault = ''
                self._native_following_lifecycle = None
                self._reset_control()
        truck = self.sdk.telemetry.get("truck", {}) or {}
        strict = self.sdk.get("longitudinal_control_schema") == 1
        try:
            speed = float(truck["speed"])  # SDK speed is signed m/s, never km/h.
            gear = int(truck.get("gear", 0))
            dt = float(delta_time)
            invalid = not math.isfinite(speed) or not math.isfinite(dt) or not 0 < dt <= .5
        except (KeyError, TypeError, ValueError, OverflowError):
            invalid = True
            speed, dt, gear = 0., 0., 0
        if strict and vehicle_control_observation_rejection(self.sdk.shared_state, truck):
            invalid = True
        if invalid or speed < -.1 or gear < 0:
            self._reset_control()
            self._publish_pedals(truck, binding, 0., 0., valid=False,
                                 reason="invalid speed observation or control interval")
            return
        speed_kmh = abs(speed) * 3.6

        # Get danger level from perception/traffic analysis
        traffic, _ = read(self.sdk.shared_state, "traffic", binding=binding) if strict else (None, "")
        danger_level = (traffic["traffic_brake"] if traffic else 0.) if strict else self.sdk.get("danger_level", 0) or 0
        owns_activation = bool(self.sdk.get('autopilot_active', False)
                               or self.sdk.get('auto_drive_pending', False))
        if not owns_activation:
            self._followed_target = False
            self._following_target_id = None
            self._following_fault = ''
        following = traffic.get('following') if traffic else None
        native_lifecycle = ((following or {}).get('source_acquisition') or {}).get('lifecycle')
        if native_lifecycle is not None:
            if (self._followed_target and self._native_following_lifecycle is not None
                    and native_lifecycle != self._native_following_lifecycle):
                self._following_fault = 'ACC native producer lifecycle changed; driver takeover required'
            self._native_following_lifecycle = native_lifecycle
        following_cap = None
        following_reason = ('traffic unavailable; cruise only' if following is None
                            else 'no route candidate; traffic coverage unproven')
        if isinstance(following, dict) and following.get('status') == 'candidate':
            try:
                following_cap = float(following['speed_cap_mps']) * 3.6
                if (not math.isfinite(following_cap) or not 0 <= following_cap <= 500.
                        or not isinstance(following.get('target_id'), str)
                        or not following['target_id']):
                    raise ValueError('invalid following constraint')
                following_reason = 'observed route candidate; reliable sensor freshness unproven'
            except (KeyError, TypeError, ValueError, OverflowError):
                following_cap = None
        # No cached pedal/target lease is extended. After target loss the
        # existing required-producer guard removes drive and controls stopping.
        # Empty/uncovered buffers cannot prove that the old target departed.
        from core.acc_following import observed_departure
        if (strict and self._followed_target and not self._following_fault and traffic is not None
                and observed_departure(following,self._following_target_id,time.monotonic())):
            self._followed_target = False
            self._following_target_id = None
            self._following_fault = ''
            following_reason = 'observed lead left route; coverage remains unproven'
        if strict and self._followed_target and following_cap is None:
            self._following_fault = 'ACC target unavailable or unconfirmed departure; driver takeover required'
        self.sdk.set('acc_following_status', following_reason)

        # 2. Emergency Collision Avoidance
        if danger_level > settings.emergency_brake_threshold:
            self._reset_control()
            self.sdk.shared_state.set("acc_throttle", 0.0)
            self.sdk.shared_state.set("acc_brake", 1.0)
            publish(self.sdk.shared_state, truck, "acc", binding=binding,
                    throttle=0., brake=1., emergency=True, requested_speed_kmh=None,
                    constrained_speed_kmh=None, dependencies=[traffic] if traffic else [])
            self.sdk.shared_state.set("tts_message", "Collision alert! Emergency braking.")
            return

        if self._following_fault:
            self._reset_control()
            self._publish_pedals(truck, binding, 0., 0., valid=False,
                reason=self._following_fault)
            return

        # 3. Dynamic Target Speed Calculation
        # Start from the user's target (live override from the UI settings page,
        # falling back to the persisted default), never exceeding the posted limit.
        user_target = self.sdk.shared_state.get("acc_target_speed", None)
        try:
            base_target_speed = float(user_target) if user_target is not None else settings.target_speed
            if not math.isfinite(base_target_speed) or not 0 <= base_target_speed <= 160:
                raise ValueError("invalid preference")
        except (TypeError, ValueError, OverflowError):
            self._reset_control()
            self._publish_pedals(truck, binding, 0., 0., valid=False,
                                 reason="invalid requested speed target")
            return
        effective_target_speed = base_target_speed
        hard_limits = []
        from core.longitudinal import destination_stop_control
        destination_control = destination_stop_control(self.sdk.shared_state, truck)
        if destination_control:
            effective_target_speed = min(effective_target_speed, destination_control['cap_ms']*3.6)
            hard_limits.append(destination_control['cap_ms']*3.6)
        from core.longitudinal import signal_speed_control
        signal_control = signal_speed_control(traffic, speed)
        signal = (traffic or {}).get('signal') or {}
        candidate = signal.get('candidate') or {}
        if signal_control is not None:
            effective_target_speed = min(effective_target_speed, signal_control['cap_ms'] * 3.6)
            hard_limits.append(signal_control['cap_ms'] * 3.6)
        if traffic:
            from core.longitudinal import signal_approach_speed_limit
            approach_cap=signal_approach_speed_limit(traffic,speed)
            if approach_cap is not None:
                effective_target_speed=min(effective_target_speed,approach_cap*3.6)
                hard_limits.append(approach_cap*3.6)
        # The same proven-distance envelope as Autopilot must constrain this
        # existing PID. Otherwise cruise powers back toward a higher Policy
        # envelope each time the separate curve-brake demand releases.
        curve = curve_input(self.sdk.shared_state, binding=binding) if strict else None
        if curve is not None:
            from core.longitudinal import curve_constraint_speed
            curve_limit = curve_constraint_speed(curve, speed)
            effective_target_speed = min(effective_target_speed, curve_limit * 3.6)
            hard_limits.append(curve_limit * 3.6)
        obey_limit = self.sdk.shared_state.get("acc_obey_limit", None)
        obey_limit = bool(obey_limit) if obey_limit is not None else getattr(settings, "obey_speed_limit", True)
        if obey_limit:
            speed_limit_ms = truck.get("speedLimit", 0) or 0
            speed_limit_kmh = speed_limit_ms * 3.6 if speed_limit_ms < 200 else speed_limit_ms
            if speed_limit_kmh > 5:  # 0 means "unknown / no limit"
                effective_target_speed = min(effective_target_speed, speed_limit_kmh)
                hard_limits.append(speed_limit_kmh)

        # Road-class speed cap: slow down on narrow/local/dirt sectors. The map
        # plugin classifies the road under us and publishes road_speed_cap (km/h);
        # when present it overrides the user target (a truck can't do 90 on a
        # single-lane dirt road, regardless of what the driver set).
        road_packet, _ = read(self.sdk.shared_state, "road", binding=binding) if strict else (None, "")
        road_cap = (road_packet.get("speed_cap_kmh") if road_packet else None) if strict else self.sdk.get("road_speed_cap")
        if road_cap is not None:
            try:
                effective_target_speed = min(effective_target_speed, float(road_cap))
                hard_limits.append(float(road_cap))
            except (TypeError, ValueError):
                pass

        # Coherent plan from the speed planner (m/s → km/h). When present this
        # is the single combined "how fast is safe right now" value (curvature
        # + lead + light + caps); we never exceed it.
        policy, _ = read(self.sdk.shared_state, "policy", binding=binding) if strict else (None, "")
        plan_ms = (policy.get("planned_speed_ms") if policy else None) if strict else self.sdk.get("planned_speed_ms")
        if plan_ms is not None:
            try:
                effective_target_speed = min(effective_target_speed, float(plan_ms) * 3.6)
                hard_limits.append(float(plan_ms) * 3.6)
            except (TypeError, ValueError):
                pass

        if danger_level > 0.05:
            # Non-linear reduction for smoother approach: speed drops faster as danger increases
            reduction_factor = max(0.3, 1.0 - (danger_level ** 1.5 * 3))
            effective_target_speed = min(effective_target_speed,
                                         max(20.0, base_target_speed * reduction_factor))
            logging.debug(f"ACC: Adjusting target speed to {effective_target_speed:.1f} km/h due to traffic")

        if following_cap is not None:
            # A geometric candidate which cannot lower the current cruise/road/
            # curve plan is NOT an acquired protective following dependency.
            # Losing it is not loss of drive authority. A candidate which limits
            # us, is slower than us, or is hazardous still latches protection;
            # its absence is never clear-road evidence.
            if owns_activation and (following_cap < effective_target_speed
                    or following_cap < speed_kmh or following.get('emergency') is True):
                self._followed_target = True
                self._following_target_id = following['target_id']
            effective_target_speed = min(effective_target_speed, following_cap)
            hard_limits.append(following_cap)
            if following_cap < 3.6 and speed < 1.:
                # No unverified automatic stop-and-go at reference-point gaps.
                self._reset_control()
                self._following_fault = 'ACC low-speed following requires driver takeover; stop-and-go unavailable'
                self._publish_pedals(truck, binding, 0., 0., valid=False,
                    reason=self._following_fault)
                return

        # Invalid preferences are not an instruction to accelerate. SDK limits
        # remain hard ceilings; upward pacing never delays a lower current cap.
        if not math.isfinite(effective_target_speed) or not 0 <= effective_target_speed <= 160:
            self._reset_control()
            self._publish_pedals(truck, binding, 0., 0., valid=False,
                                 reason="invalid constrained speed target")
            return
        active = bool(self.sdk.get("autopilot_active", False))
        if binding != self._control_context or active != self._was_driving:
            self._reset_control()
        self._control_context, self._was_driving = binding, active
        signal_owns_plan = bool(signal_control and
            effective_target_speed >= signal_control['cap_ms']*3.6-1e-9)
        destination_owns_plan = bool(destination_control and
            effective_target_speed >= destination_control['cap_ms']*3.6-1e-9)
        if (self._signal_control_active and signal_control is None
                and signal.get('valid') and candidate.get('color') == 'green'
                and candidate.get('stop_required') is not True):
            # Remove only a ceiling that actually constrained this activation.
            # Engine still requires two locked acquisitions before release.
            self._reset_control()
        self._signal_control_active = signal_owns_plan
        externally_braking = (self.sdk.get("system_state") in ("EMERGENCY", "CONTROLLED_STOP", "PAY_TOLL")
            or truck.get("parkBrake") is True
            or (traffic is not None and max(traffic["traffic_brake"], traffic["light_brake"]) > 0)
            or (policy is not None and policy["brake"] > 0))
        if externally_braking:
            self._reset_control()
            self._publish_pedals(truck, binding, 0., 0., target=effective_target_speed,
                                 reason="external braking inhibits speed drive")
            return
        observation = truck.get("_control_observation", {})
        stamp = observation.get("observed_at") if strict else None
        frame = truck.get("sdkFrameTimeUs") if strict else None
        duplicate = False
        if strict and self._last_observation:
            previous_frame, previous_stamp, previous_speed, previous_target = self._last_observation
            if frame < previous_frame or stamp < previous_stamp or (frame == previous_frame
                    and (stamp != previous_stamp or speed != previous_speed)):
                self._reset_control()
                self._publish_pedals(truck, binding, 0., 0., valid=False,
                                     reason="regressing or incoherent speed observation")
                return
            duplicate = frame == previous_frame
            previous_packet = self.sdk.get('longitudinal_acc') if duplicate else None
            needs_refresh = bool(previous_packet and rejection(previous_packet, binding, time.monotonic()))
            if duplicate and effective_target_speed == previous_target and not needs_refresh:
                return  # No new evidence, controller step or renewed packet lease.
            if not duplicate:
                dt = stamp - previous_stamp
                if not 0 < dt <= .5:
                    self._reset_control()
                    self._publish_pedals(truck, binding, 0., 0., valid=False,
                                         reason="speed observation interval exceeds control budget")
                    return
        if self._control_target is None:
            self._control_target = effective_target_speed
        elif effective_target_speed < self._control_target:
            if self._control_target - effective_target_speed > 2.:
                self.speed_pid.reset()  # Old load demand must not fight a new reduction.
            self._control_target = effective_target_speed
        elif signal_control is not None or destination_control is not None:
            # The distance trajectory already specifies the current speed.
            # A second upward target lag would retain a cap from another position.
            self._control_target = effective_target_speed
        elif not duplicate:
            self._control_target = min(effective_target_speed, self._control_target + 6. * dt)
        self.speed_pid.set_setpoint(self._control_target)
        if not active:
            self.speed_pid.reset()  # A launch preference is not actuator ownership.
        previous_output = self.sdk.get(COMMAND_KEY) if strict else None
        if previous_output and rejection(previous_output, binding, time.monotonic()):
            previous_output = None
        try:
            previous_drive, previous_brake = exclusive(previous_output["throttle"], previous_output["brake"])
            limited = (self._last_requested_drive > 0 and
                       (previous_brake > 0 or previous_drive + .05 < self._last_requested_drive))
        except (KeyError, TypeError, ValueError, OverflowError):
            limited = False  # Missing optional feedback cannot create authority.
        acceleration_output = self.speed_pid.update(speed_kmh, dt,
            integrate=active and not duplicate and (not limited or speed_kmh > self._control_target))
        throttle_output = acceleration_output/DRIVE_GAIN_MS2

        # 4. Control Output Mapping
        # Map PID output to throttle (0 to 1) and brake (0 to 1).
        throttle_val = np.clip(throttle_output, 0.0, 1.0)
        if hard_limits and speed_kmh > min(hard_limits):
            throttle_val = 0.  # Cruise hysteresis never powers through a hard cap.

        over = speed_kmh - effective_target_speed
        was_speed_braking = self._speed_braking
        if over > 2. or (over > .5 and throttle_output < -.01):
            self._speed_braking = True
        elif throttle_output >= 0:
            self._speed_braking = False
        if self._speed_braking:
            # Gentle deceleration: a soft proportional brake, never a hard step.
            # The old (overspeed/15) clamped to 0.6 made the truck lurch from
            # 80 to 50 — the brake ramp in the autopilot smooths it further, but
            # we keep the requested value modest so it never slams.
            # The same signed PID handles downhill load. Preserve the earlier
            # overspeed safety floor above 2 km/h and its ordinary 0.35 maximum.
            brake_power = np.clip(max(-throttle_output * .35,
                                      over / 40.0 if over > 2. else 0.), 0.0, 0.35)
        if signal_owns_plan or destination_owns_plan:
            # Same distance/deceleration mapping previously executed by Traffic,
            # now inside the single speed-control output. The ordinary cruise
            # 0.35 cap must not weaken a short-distance required stop. Below the
            # current envelope there is no independent perpetual light brake.
            from core.longitudinal import signal_stop_brake_request
            # Reuse the existing 2 km/h pedal hysteresis, not a creep-speed
            # floor. Keep the positive distance request around its boundary;
            # release it if a moving vehicle is genuinely below the profile.
            continuing = was_speed_braking and over >= -2.
            if destination_owns_plan:
                from core.longitudinal import stopping_brake_request
                brake_power = stopping_brake_request(destination_control['distance_m'], speed,
                    continuing=continuing)
            else:
                brake_power = signal_stop_brake_request(candidate, speed, continuing=continuing)
            self._speed_braking = brake_power > 0.
            if self._speed_braking:
                self._signal_stop_started = True
                throttle_val = 0.
            elif getattr(self, '_signal_stop_started', False):
                from core.longitudinal import CURVE_APPROACH_DECEL_MS2, CURVE_BRAKE_RESPONSE_S, LEASE_S
                # Coast through the normal response-sized profile deficit,
                # rather than power/brake cycling after every delayed response.
                # Recovery is still allowed after substantial early slowing.
                # This uses the declared phase-planning acceleration and response
                # budget; it is neither a minimum speed nor a pedal floor.
                selected_cap = destination_control['cap_ms'] if destination_owns_plan else signal_control['cap_ms']
                coast_allowance = CURVE_APPROACH_DECEL_MS2*(CURVE_BRAKE_RESPONSE_S+LEASE_S)
                if selected_cap-speed <= coast_allowance:
                    throttle_val = 0.
        if signal_owns_plan and throttle_val == 0. and throttle_output > 0.:
            # Coast/feed-forward braking inhibits a computed positive drive.
            # Numeric output saturation alone cannot see this mapping. Preserve
            # negative integral/derivative state; discard only unexecuted drive.
            self.speed_pid.discard_unexecuted_positive_integral()
        if signal_owns_plan or destination_owns_plan:
            # A distance-based stop is already a planned deceleration demand;
            # do not lag that trajectory or retain an ordinary drive recovery.
            desired_acceleration = selected_acceleration = None
        else:
            raw_drive = float(throttle_val) if not self._speed_braking else 0.
            raw_brake = float(brake_power) if self._speed_braking else 0.
            throttle_val, brake_power, desired_acceleration = pedal_acceleration(raw_drive, raw_brake)
            selected_acceleration = desired_acceleration
            self._speed_braking = brake_power > 0.
        if self._speed_braking:
            self.sdk.shared_state.set("acc_throttle", 0.0)
            self.sdk.shared_state.set("acc_brake", brake_power)
        else:
            self.sdk.shared_state.set("acc_throttle", throttle_val)
            self.sdk.shared_state.set("acc_brake", 0.0)

        publish(self.sdk.shared_state, truck, "acc", binding=binding,
                throttle=float(throttle_val) if not self._speed_braking else 0.,
                brake=float(brake_power) if self._speed_braking else 0.,
                emergency=False, requested_speed_kmh=base_target_speed,
                constrained_speed_kmh=effective_target_speed,
                control_target_kmh=self._control_target,
                speed_control_reason=("GPS distance service brake" if self._speed_braking
                    else "GPS distance recovery" if throttle_val > 0 else "GPS distance coast")
                    if destination_owns_plan else ("signal distance service brake" if self._speed_braking
                    else "signal distance recovery" if throttle_val > 0 else "signal distance coast")
                    if signal_owns_plan else "speed service brake" if self._speed_braking else "speed tracking",
                following_status=following_reason,
                following_target_id=following.get('target_id') if isinstance(following, dict) else None,
                following_confirmed=False,
                leader_prediction=following.get('leader_prediction') if isinstance(following, dict) else None,
                requested_acceleration_ms2=desired_acceleration,
                selected_acceleration_ms2=selected_acceleration,
                acceleration_basis='nominal_actuator_mapping_not_measured_vehicle_acceleration',
                signal_stop_control=signal_control is not None,
                signal_brake_selected=bool(signal_owns_plan and self._speed_braking),
                destination_brake_selected=bool(destination_owns_plan and self._speed_braking),
                following_required=self._followed_target,
                dependencies=[v for v in (
                    traffic if traffic_required(traffic) or self._followed_target else None,
                    road_packet if road_cap is not None and float(road_cap) <= effective_target_speed else None,
                    policy if plan_ms is not None and float(plan_ms)*3.6 < base_target_speed else None,
                    curve if curve is not None and curve_constraint_speed(curve, speed)*3.6 <= effective_target_speed else None)
                    if v is not None])

        # Update UI tags
        self.tags.acc_speed = effective_target_speed
        self.tags.acc_status = ('Candidate following (unverified)' if following_cap is not None
                                else 'Cruise; traffic coverage unproven')
        self._last_requested_drive = float(throttle_val) if not self._speed_braking else 0.
        if strict:
            self._last_observation = (frame, stamp, speed, effective_target_speed)

    def _reset_control(self):
        self.speed_pid.reset()
        self._control_target = None
        self._last_observation = None
        self._speed_braking = False
        self._last_requested_drive = 0.
        self._signal_stop_started = False
        self._signal_control_active = False

    def _publish_pedals(self, truck, binding, throttle, brake, *, valid=True,
                        target=None, reason="speed controller reset"):
        if target is not None:
            self.tags.acc_speed = target
        self.tags.acc_status = reason
        self.sdk.set('acc_following_status', reason)
        self.sdk.shared_state.update_batch({"acc_throttle": throttle, "acc_brake": brake})
        publish(self.sdk.shared_state, truck, "acc", binding=binding, evidence_valid=valid,
                throttle=throttle, brake=brake, emergency=False,
                requested_speed_kmh=target, constrained_speed_kmh=target,
                speed_control_reason=reason, following_required=self._followed_target,
                following_target_id=self._following_target_id,
                following_confirmed=False)
