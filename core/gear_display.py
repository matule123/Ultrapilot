"""Presentation-only dashboard gear; never a selector/control confirmation."""
import math


def gear_text(truck, automatic=False):
    """Prefer the game's displayed gear, including an explicit dashboard zero."""
    value = truck.get("gearDashboard")
    if value is None:
        value = truck.get("gear")
    try:
        number = float(value)
        if not math.isfinite(number) or not number.is_integer():
            return "—"
        number = int(number)
    except (TypeError, ValueError, OverflowError):
        return "—"
    if number < 0:
        return "R"
    if number == 0:
        return "N"
    return "D" if automatic else str(number)
