import logging
import math
import time
import numpy as np
from sdk.base_plugin import BasePlugin
from core.pid import PID
from core.longitudinal import COMMAND_KEY, context, exclusive, read, publish, rejection
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
    VERSION = "1.0.2"

    def on_start(self):
        logging.info("ACC Plugin started with bounded speed PID control.")
        self.enabled = True
        self.sdk.set("longitudinal_acc_active", True)

        # Input error is km/h; output is normalized drive. Lower proportional
        # and measurement-derivative sensitivity are validated across the fixed
        # Phase 7.2 delay/load/noise matrix, not tuned from a single ETS2 run.
        self.speed_pid = PID(kp=0.15, ki=0.06, kd=0.015, output_limits=(-1., 1.),
                             derivative_on_measurement=True, anti_windup=True,
                             reset_on_setpoint=False)
        self.speed_pid.set_setpoint(settings.target_speed)
        self._control_target = None
        self._control_context = None
        self._last_observation = None
        self._speed_braking = False
        self._was_driving = False

    def on_stop(self):
        logging.info("ACC Plugin stopped.")
        self.enabled = False
        self.speed_pid.reset()
        self._last_observation = None
        self.sdk.set("longitudinal_acc_active", False)
        self.sdk.set("longitudinal_acc", None)
        self.sdk.shared_state.update_batch({"acc_throttle": None, "acc_brake": None})

    def on_tick(self, delta_time: float):
        if not self.enabled:
            return

        # 1. Telemetry & State
        binding = context(self.sdk.shared_state)
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

        # 2. Emergency Collision Avoidance
        if danger_level > settings.emergency_brake_threshold:
            self._reset_control()
            self.sdk.shared_state.set("acc_throttle", 0.0)
            self.sdk.shared_state.set("acc_brake", 1.0)
            publish(self.sdk.shared_state, truck, "acc", binding=binding,
                    throttle=0., brake=1., emergency=True, requested_speed_kmh=None,
                    constrained_speed_kmh=None, expires_at=traffic["expires_at"] if traffic else float("inf"))
            self.sdk.shared_state.set("tts_message", "Collision alert! Emergency braking.")
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
            if duplicate and effective_target_speed == previous_target:
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
        throttle_output = self.speed_pid.update(speed_kmh, dt,
            integrate=active and not duplicate and (not limited or speed_kmh > self._control_target))

        # 4. Control Output Mapping
        # Map PID output to throttle (0 to 1) and brake (0 to 1).
        throttle_val = np.clip(throttle_output, 0.0, 1.0)
        if hard_limits and speed_kmh > min(hard_limits):
            throttle_val = 0.  # Cruise hysteresis never powers through a hard cap.

        over = speed_kmh - effective_target_speed
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
                speed_control_reason="speed service brake" if self._speed_braking else "speed tracking",
                expires_at=min((v["expires_at"] for v in (traffic, road_packet, policy)
                                if v is not None), default=float("inf")))

        # Update UI tags
        self.tags.acc_speed = effective_target_speed
        self.tags.acc_status = "Active" if self.enabled else "Disabled"
        self._last_requested_drive = float(throttle_val) if not self._speed_braking else 0.
        if strict:
            self._last_observation = (frame, stamp, speed, effective_target_speed)

    def _reset_control(self):
        self.speed_pid.reset()
        self._control_target = None
        self._last_observation = None
        self._speed_braking = False
        self._last_requested_drive = 0.

    def _publish_pedals(self, truck, binding, throttle, brake, *, valid=True,
                        target=None, reason="speed controller reset"):
        if target is not None:
            self.tags.acc_speed = target
        self.tags.acc_status = reason
        self.sdk.shared_state.update_batch({"acc_throttle": throttle, "acc_brake": brake})
        publish(self.sdk.shared_state, truck, "acc", binding=binding, evidence_valid=valid,
                throttle=throttle, brake=brake, emergency=False,
                requested_speed_kmh=target, constrained_speed_kmh=target,
                speed_control_reason=reason)
