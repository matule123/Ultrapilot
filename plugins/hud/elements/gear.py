from plugins.hud.main import HUDElement
from core.gear_display import gear_text

class Widget(HUDElement):
    """Gear Indicator HUD Element."""
    def draw(self, offset_x, width, height):
        # Fetch telemetry
        truck = self.plugin.sdk.telemetry.get("truck", {})
        mode = self.plugin.sdk.get("ets2_transmission_mode", {}) or {}

        # Render background
        self.data.append({
            "type": "Rectangle",
            "rect": [offset_x, 100, offset_x + width, 100 + height],
            "color": (0, 0, 0, 150)
        })

        # Render text
        displayed = gear_text(truck, mode.get("mode") in (0, 3))
        self.data.append({
            "type": "Text",
            "pos": [offset_x + 20, 115],
            "text": displayed,
            "size": 24,
            "color": (255, 255, 0, 255)
        })
