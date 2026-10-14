"""Nominal acceleration-space actuator mapping for the existing speed PID.

These gains describe the explicit offline plant, NOT measured ETS2 load or
physical jerk. No second regulator, additional observation or lease is created.
Safety/stop-profile paths bypass this ordinary comfort state.
"""
DRIVE_GAIN_MS2 = 2.2
BRAKE_GAIN_MS2 = 4.0


def pedal_acceleration(throttle, brake):
    """Explicit single signed nominal demand, preserving validated mapping.

    Extra recovery slew was rejected by the fixed load/delay/target matrix:
    smaller drive steps alone did not improve modeled physical jerk. The
    existing Autopilot ramp remains the only authoritative comfort stage.
    """
    demand = DRIVE_GAIN_MS2*throttle-BRAKE_GAIN_MS2*brake
    return max(0., demand)/DRIVE_GAIN_MS2, max(0., -demand)/BRAKE_GAIN_MS2, demand
