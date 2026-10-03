import math
import time


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


class PID:
    """
    A generic Proportional-Integral-Derivative controller for smooth control.

    Improvements over the original:
      * no numpy dependency (was crashing on the missing ``np`` import),
      * configurable integral clamp and optional output clamp,
      * optional derivative on measurement and conditional anti-windup,
      * monotonic timing and explicit invalid-interval reset.
    """

    def __init__(self, kp: float, ki: float, kd: float, setpoint: float = 0.0,
                 integral_limit: float = 10.0, output_limits=(None, None), *,
                 derivative_on_measurement=False, anti_windup=False,
                 reset_on_setpoint=True):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.setpoint = setpoint
        self.integral_limit = integral_limit
        self.output_limits = output_limits
        self.derivative_on_measurement = derivative_on_measurement
        self.anti_windup = anti_windup
        self.reset_on_setpoint = reset_on_setpoint
        self._last_measurement = None

        self._last_error = 0.0
        self._integral = 0.0
        self._last_time = time.monotonic()

    def update(self, measured_value: float, dt: float = None, *, integrate=True) -> float:
        if dt is None:
            now = time.monotonic()
            dt = now - self._last_time
            self._last_time = now
        if not math.isfinite(dt) or dt <= 0 or not math.isfinite(measured_value):
            self.reset()
            return 0.0

        error = self.setpoint - measured_value

        p_term = self.kp * error

        if self.derivative_on_measurement:
            derivative = (0.0 if self._last_measurement is None else
                          -(measured_value - self._last_measurement) / dt)
        else:
            derivative = (error - self._last_error) / dt
        d_term = self.kd * derivative
        self._last_error = error
        self._last_measurement = measured_value

        candidate = _clamp(self._integral + (error * dt if integrate else 0.),
                           -self.integral_limit, self.integral_limit)
        lo, hi = self.output_limits
        unconstrained = p_term + self.ki * candidate + d_term
        # Conditional integration: a saturated actuator cannot realize further
        # demand in the same direction. Opposite error may unwind immediately.
        if not (self.anti_windup and ((hi is not None and unconstrained > hi and error > 0)
                or (lo is not None and unconstrained < lo and error < 0))):
            self._integral = candidate
        i_term = self.ki * self._integral

        output = p_term + i_term + d_term
        lo, hi = self.output_limits
        if lo is not None or hi is not None:
            output = _clamp(output, lo if lo is not None else -1e9,
                            hi if hi is not None else 1e9)
        return output

    def set_setpoint(self, value: float):
        # Legacy clients may reset on every change; ACC manages deliberate
        # target reductions itself and preserves load memory through small noise.
        if self.reset_on_setpoint and abs(value - self.setpoint) > 1e-6:
            self._integral = 0.0
        self.setpoint = value

    def reset(self):
        self._last_error = 0.0
        self._last_measurement = None
        self._integral = 0.0
        self._last_time = time.monotonic()
