"""Offline heuristic against rounded 24 September steering observations."""

import pytest

from plugins.autopilot.main import SteeringResponseMonitor


# Rounded, read-only extracts from the 20:44:23-29 log. gameSteer has already
# been converted from SDK left-positive to controller right-positive here.
# Interpolated rows below are synthetic; they cannot establish live timing or
# justify a production stop without binding the command to the response frame.
INCIDENT = (
    (23, 0.054, 0.041, 0.0281, 31.0, 0.017),
    (24, 0.066, 0.053, 0.0363, 34.0, -0.028),
    (25, 0.083, 0.061, 0.0424, 42.0, -0.104),
    (26, 0.090, 0.038, 0.0264, 42.0, -0.394),
    (27, 0.079, 0.031, 0.0216, 44.0, -0.639),
    (28, 0.072, 0.032, 0.0221, 45.0, -0.720),
    (29, 0.078, 0.034, 0.0237, 47.0, -0.763),
)


def test_incident_ratio_is_visible_to_offline_heuristic():
    monitor = SteeringResponseMonitor()
    reasons = []
    for left, right in zip(INCIDENT, INCIDENT[1:]):
        for step in range(20):
            fraction = step / 20
            second = left[0] + fraction
            command, game, tyre, speed, cte = (
                a + (b - a) * fraction for a, b in zip(left[1:], right[1:]))
            reason = monitor.observe(
                now=second, sdk_frame_us=round(second * 1_000_000),
                identity=(1, "intent", 9, "build", "promods-1.59", "dataset"),
                active=True, speed_kmh=speed, command=command,
                game_steer_right=game, tyre_angles_rad=(tyre, tyre),
                tyre_angle_per_input_rad=0.7)
            reasons.append((second, cte, reason))
    first = next((item for item in reasons if item[2]), None)
    assert first is not None
    assert first[0] <= 29 and abs(first[1]) < 1.0
    assert not any(reason for second, _, reason in reasons if second <= 25)
    assert monitor.observe(
        now=30.0, sdk_frame_us=30_000_000,
        identity=(1, "intent", 9, "build", "promods-1.59", "dataset"),
        active=True, speed_kmh=47.0, command=0.01,
        game_steer_right=0.01, tyre_angles_rad=(0.007, 0.007),
        tyre_angle_per_input_rad=0.7)
    assert not monitor.observe(
        now=31.0, sdk_frame_us=31_000_000,
        identity=(1, "intent", 9, "build", "promods-1.59", "dataset"),
        active=False, speed_kmh=0.0, command=0.0,
        game_steer_right=0.0, tyre_angles_rad=(),
        tyre_angle_per_input_rad=None)


@pytest.mark.parametrize("sign", (-1.0, 1.0))
@pytest.mark.parametrize("speed", (10.0, 35.0, 60.0, 90.0))
@pytest.mark.parametrize("delay_steps", (0, 1, 5))
def test_observed_steering_response_remains_authorized(sign, speed, delay_steps):
    monitor = SteeringResponseMonitor()
    identity = (1, "intent", 9, "build", "map", "dataset")
    commands = [(-sign if 35 <= index < 50 else sign) * 0.11
                for index in range(80)]
    for index in range(80):
        # Includes direction reversal at an S-bend; the monitor observes only.
        command = commands[index]
        applied = commands[max(0, index - delay_steps)] * 0.8
        assert not monitor.observe(
            now=index * 0.05, sdk_frame_us=1_000_000 + index * 50_000,
            identity=identity, active=True, speed_kmh=speed,
            command=command, game_steer_right=applied,
            tyre_angles_rad=(applied * 0.7, applied * 0.7),
            tyre_angle_per_input_rad=0.7)


def test_stale_frame_or_changed_route_cannot_accumulate_mismatch():
    monitor = SteeringResponseMonitor()
    first = (1, "intent", 9, "build", "map", "dataset")
    second = (1, "intent", 10, "build2", "map", "dataset")
    for now, frame, identity in ((0.0, 1, first), (0.5, 1, first),
                                 (1.0, 2, second), (1.5, 3, second)):
        assert not monitor.observe(
            now=now, sdk_frame_us=frame, identity=identity, active=True,
            speed_kmh=45.0, command=0.12, game_steer_right=0.03,
            tyre_angles_rad=(0.021, 0.021),
            tyre_angle_per_input_rad=0.7)
