import math
import re
from pathlib import Path
import time
from datetime import datetime, timedelta

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QProgressBar, QFrame, QSizePolicy,
)
from PyQt6.QtGui import QPainter, QColor, QPen, QPolygonF, QPainterPath, QPixmap, QPainterPathStroker, QTransform, QImage
from PyQt6.QtCore import (Qt, QTimer, QPointF, QPoint, QRectF, QThread,
                          pyqtSignal)
from UI.map_projection import MapCamera
from core.navigation.navigation_intent import snapshot_matches_navigation_intent


def navigation_trip_summary(state, now=None):
    """Return truthful arrival/minutes/km values from SCS route telemetry."""
    try:
        distance_m = max(0.0, float(state.get("game_route_distance", 0.0) or 0.0))
        route_seconds = max(0.0, float(state.get("game_route_time", 0.0) or 0.0))
    except (TypeError, ValueError, OverflowError):
        return None
    if distance_m <= 0.0 and route_seconds <= 0.0:
        return None
    now = now or datetime.now()
    arrival = now + timedelta(seconds=route_seconds)
    minutes = max(0, int(math.ceil(route_seconds / 60.0)))
    distance_km = max(0, int(round(distance_m / 1000.0)))
    return arrival.strftime("%H:%M"), minutes, distance_km


def live_map_navigation_points(state, now=None):
    """Return the sole geometry that the live map may draw in this state."""
    snapshot = state.get("lane_trajectory", {}) or {}
    try:
        game_uids = tuple(int(uid) for uid in
                          (state.get("game_route_node_uids", []) or []))
        snapshot_uids = tuple(int(uid) for uid in
                              (snapshot.get("source_gps_uids", []) or []))
        route_distance = float(state.get("game_route_distance", 0.0) or 0.0)
        gps_present = bool(
            state.get("game_gps_navigation_active", False)
            or state.get("navigation_arrival_pending", False)
            or state.get("dest_city") or route_distance > 0.0
            or len(game_uids) >= 2 or len(snapshot_uids) >= 2)
    except (TypeError, ValueError, OverflowError):
        return []

    if gps_present:
        try:
            revision = int(snapshot.get("revision", -2) or -2)
            current_revision = int(state.get(
                "lane_trajectory_revision", -1) or -1)
            heartbeat = float(state.get(
                "lane_trajectory_heartbeat", 0.0) or 0.0)
            now = time.monotonic() if now is None else float(now)
            points = snapshot.get("display_points", []) or []
            if (not snapshot.get("valid", False)
                    or revision != current_revision
                    or not snapshot_matches_navigation_intent(state, snapshot)
                    or heartbeat <= 0.0 or now - heartbeat > 0.5
                    or state.get("telemetry_valid", True) is False
                    or state.get("navigation_recalculating", False)
                    or len(points) < 2):
                return []
            if any(not isinstance(point, (list, tuple)) or len(point) < 3
                   or not all(math.isfinite(float(value)) for value in point[:3])
                   for point in points):
                return []
            return points
        except (TypeError, ValueError, OverflowError):
            return []

    if (state.get("navigation_source") == "recorded_route"
            and state.get("recorded_route_active", False)):
        points = state.get("nav_path", []) or []
        try:
            if len(points) >= 2 and all(
                    isinstance(point, (list, tuple)) and len(point) >= 2
                    and all(math.isfinite(float(value)) for value in point[:3])
                    for point in points):
                return points
        except (TypeError, ValueError, OverflowError):
            pass
    return []


def rejected_navigation_command_message(state):
    """Return a persistent user-facing reason for a rejected command."""
    result = state.get("nav_command_result") or {}
    if result and not result.get("ok", False):
        return str(result.get("message") or "Navigation command was rejected.")
    return ""


class MapDownloadWorker(QThread):
    """Downloads + extracts a map dataset in the background."""
    progress = pyqtSignal(float, str)
    done = pyqtSignal(bool)

    def __init__(self, key):
        super().__init__()
        self.key = key

    def run(self):
        try:
            from core.navigation import map_data
            ok = map_data.download(self.key, progress_cb=lambda f, t: self.progress.emit(f, t))
            self.done.emit(bool(ok))
        except Exception:
            self.done.emit(False)


class MapView(QWidget):
    """Perspective navigation map with an optional north-up 2D overview."""
    buildings_loaded = pyqtSignal(object)

    def __init__(self, state):
        super().__init__()
        self.state = state
        # Bounded display-only snapshot from the map plugin. Loading another
        # complete RoadNetwork here doubles memory and can terminate the UI.
        self.road_segments = []
        self._road_runs = []
        self.scene_polygons = []
        self.scene_features = []
        self._pal = None         # set by the page (or a default below)
        self._map_mode = "light"
        self._perspective = True
        self._active_camera = None
        self._road_ribbons = []
        self._ground_tile = None
        self._ground_generation = 0
        self._ground_build_ms = 0.0
        self._feature_logos = {}
        self._visual_buildings = []
        self._building_identity = None
        self._building_request = None
        self._building_job_pending = False
        self._building_retry_at = 0.0
        self.buildings_loaded.connect(self._accept_buildings)
        # A slightly wider initial field matches the navigation-map reference
        # and uses the broad, display-only 1.2 km scene from the map process.
        self.zoom_radius = 650.0
        self.pan_world = [0.0, 0.0]
        self._drag_at = None
        self.setMinimumHeight(300)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.live_badge = QLabel("●  LIVE", self)
        self.live_badge.setObjectName("LiveMapBadge")
        self.live_badge.setStyleSheet(
            "background:rgba(19,24,28,232);color:#35C779;"
            "border:1px solid #34383C;border-radius:9px;padding:5px 9px;"
            "font-size:11px;font-weight:750;")
        self.live_badge.adjustSize()
        self.turn_banner = QLabel("", self)
        self.turn_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.turn_banner.setStyleSheet(
            "background:#109B58;color:white;border:1px solid #20AE6C;"
            "border-radius:12px;padding:14px 25px;font-size:24px;font-weight:800;")
        self.turn_banner.setMinimumSize(270, 68)
        self.turn_banner.hide()
        self.trip_panel = QLabel("", self)
        self.trip_panel.setObjectName("LiveMapTripPanel")
        self.trip_panel.setTextFormat(Qt.TextFormat.RichText)
        self.trip_panel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.trip_panel.setFixedSize(310, 76)
        self.trip_panel.setStyleSheet(
            "background:rgba(12,16,19,238);color:#F2F4F5;"
            "border:1px solid #3B4146;border-radius:12px;padding:3px;")
        self.trip_panel.hide()
        self.map_credit = QLabel("UltraPilot Maps", self)
        self.map_credit.setStyleSheet(
            "background:transparent;color:rgba(220,223,226,115);"
            "border:none;font-size:9px;")
        self.map_credit.adjustSize()
        self.map_controls = []
        for caption, tooltip, callback in (
                ("+", "Priblížiť", self.zoom_in),
                ("−", "Oddialiť", self.zoom_out),
                ("⌖", "Vycentrovať na kamión", self.reset_view),
                ("☾", "Prepnúť dennú/nočnú mapu", self.toggle_map_mode),
                ("2D", "Prepnúť priestorový/pôdorysný pohľad", self.toggle_perspective)):
            button = QPushButton(caption, self)
            button.setToolTip(tooltip)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFixedSize(32, 30)
            button.setStyleSheet(
                "QPushButton{background:rgba(31,34,37,235);color:#E7E9EB;"
                "border:1px solid #484C50;border-radius:7px;font-size:17px;"
                "font-weight:700;padding:0;}"
                "QPushButton:hover{background:#3B4045;border-color:#6A7076;}")
            button.clicked.connect(callback)
            self.map_controls.append(button)
        self.empty_state = QLabel(
            "<div style='font-size:17px;font-weight:700;color:#F3F4F6;'>"
            "Čakám na živú mapu</div>"
            "<div style='margin-top:7px;color:#9CA3AF;'>"
            "Spusti hru a nastav GPS cieľ.<br>"
            "Potvrdená trasa sa zobrazí automaticky.</div>", self)
        self.empty_state.setObjectName("LiveMapEmptyState")
        self.empty_state.setTextFormat(Qt.TextFormat.RichText)
        self.empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state.setWordWrap(True)
        self.empty_state.setFixedSize(360, 108)
        self.empty_state.setStyleSheet(
            "background:rgba(29,32,35,235);border:1px solid #353A40;"
            "border-radius:14px;padding:12px;")
        self.apply_theme()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.live_badge.move(14, 14)
        self.live_badge.raise_()
        for index, button in enumerate(self.map_controls):
            button.move(max(8, self.width() - 44), 14 + index * 35)
            button.raise_()
        self.map_credit.move(
            max(8, self.width() - self.map_credit.width() - 12),
            max(8, self.height() - self.map_credit.height() - 8))
        self.map_credit.raise_()
        self.turn_banner.move(
            max(54, (self.width() - self.turn_banner.width()) // 2), 14)
        self.turn_banner.raise_()
        self.trip_panel.move(
            max(12, (self.width() - self.trip_panel.width()) // 2),
            max(12, self.height() - self.trip_panel.height() - 18))
        self.trip_panel.raise_()
        self.empty_state.move(max(14, (self.width() - self.empty_state.width()) // 2),
                              max(52, (self.height() - self.empty_state.height()) // 2))
        self.empty_state.raise_()

    def reset_view(self):
        self.zoom_radius = 650.0
        self.pan_world[:] = [0.0, 0.0]
        self.update()

    def zoom_in(self):
        self.zoom_radius = max(70.0, self.zoom_radius * 0.78)
        self.update()

    def zoom_out(self):
        self.zoom_radius = min(1850.0, self.zoom_radius * 1.28)
        self.update()

    def wheelEvent(self, event):
        # Wheel up zooms in, wheel down zooms out to a broad regional view.
        factor = 0.78 if event.angleDelta().y() > 0 else 1.28
        self.zoom_radius = max(70.0, min(1850.0, self.zoom_radius * factor))
        self.update()
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_at = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self._drag_at is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        delta = event.position() - self._drag_at
        if self._perspective and self._active_camera is not None:
            previous = self._active_camera.ground((self._drag_at.x(), self._drag_at.y()))
            current = self._active_camera.ground((event.position().x(), event.position().y()))
            if previous is not None and current is not None:
                self.pan_world[0] += previous[0]-current[0]
                self.pan_world[1] += previous[1]-current[1]
                self._drag_at = event.position()
                self.update()
            return
        scale = max(1e-6, (min(self.width(), self.height()) - 20) / (2 * self.zoom_radius))
        self.pan_world[0] -= delta.x() / scale
        self.pan_world[1] -= delta.y() / scale
        self._drag_at = event.position()
        self.update()

    def mouseReleaseEvent(self, event):
        self._drag_at = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseDoubleClickEvent(self, event):
        self.reset_view()

    def toggle_perspective(self):
        self._perspective = not self._perspective
        self._active_camera = None
        self.pan_world[:] = [0.0, 0.0]
        self.apply_theme()
        self.update()

    def toggle_map_mode(self):
        self._map_mode = "dark" if self._map_mode == "light" else "light"
        self.apply_theme()
        self.update()

    def _map_palette(self):
        if self._map_mode == "dark":
            return dict(land="#28372F", border="#46554B", text="#E3E9E4",
                        muted="#A3B2AA", panel="#202C27", water="#244858",
                        park="#344E39", yard="#4D4C42", building="#748078",
                        building_side="#526158", road="#BBC3BA",
                        road_edge="#5A695F", motorway="#D3C5A5",
                        route="#56A7FF", route_edge="#174E9C")
        return dict(land="#E6EDDD", border="#C3CEBA", text="#34443B",
                    muted="#69796E", panel="#FFFFFF", water="#AACFE8",
                    park="#C9DFB2", yard="#E8DFCD", building="#E4E6E8",
                    building_side="#AEB6BE", road="#FFFFFF",
                    road_edge="#CDD2C5", motorway="#FFF2D4",
                    route="#2587F4", route_edge="#1261CD")

    def apply_theme(self):
        """Keep map day/night independent of the surrounding app theme."""
        from core.theme import palette
        if self._pal is None:
            self._pal = palette(self.state.get("ui_theme", "light") or "light")
        c = self._map_palette()
        self.setStyleSheet(f"background:{c['land']};border:1px solid {c['border']};"
                          "border-radius:10px;")
        self.live_badge.setStyleSheet(
            f"background:{c['panel']};color:#1B985D;border:1px solid {c['border']};"
            "border-radius:10px;padding:5px 10px;font-size:11px;font-weight:700;")
        self.trip_panel.setStyleSheet(
            f"background:{c['panel']};color:{c['text']};border:1px solid {c['border']};"
            "border-radius:12px;padding:3px;")
        self.map_credit.setStyleSheet(
            f"background:transparent;color:{c['muted']};border:none;font-size:9px;")
        for button in self.map_controls:
            button.setStyleSheet(
                f"QPushButton{{background:{c['panel']};color:{c['text']};"
                f"border:1px solid {c['border']};border-radius:8px;"
                "font-size:17px;font-weight:700;padding:0;}"
                f"QPushButton:hover{{background:{c['yard']};}}")
        if self.map_controls:
            self.map_controls[3].setText("☀" if self._map_mode == "dark" else "☾")
            self.map_controls[4].setText("2D" if self._perspective else "3D")
        self.empty_state.setText(
            f"<b style='color:{c['text']};font-size:17px'>Čakám na živú mapu</b>"
            f"<div style='color:{c['muted']};margin-top:7px'>"
            "Spusti hru a nastav GPS cieľ.<br>Potvrdená trasa sa zobrazí automaticky.</div>")
        self.empty_state.setStyleSheet(
            f"background:{c['panel']};border:1px solid {c['border']};"
            "border-radius:14px;padding:12px;")

    def set_road_segments(self, payload):
        """Keep finite display geometry and all road-style metadata.

        These fields are display-only.  Preserving them fixes the former live
        map which reduced every motorway and prefab to the same two-pixel line.
        """
        segments = []
        for item in (payload or [])[:16000]:
            try:
                a, b = item[0], item[1]
                values = float(a[0]), float(a[1]), float(b[0]), float(b[1])
                if not all(math.isfinite(value) for value in values):
                    continue
                segments.append({
                    "a": values[:2], "b": values[2:],
                    "kind": str(item[2]) if len(item) > 2 else "road",
                    "lanes": max(1, int(item[3])) if len(item) > 3 else 2,
                    "divided": bool(item[4]) if len(item) > 4 else False,
                    "dash_on": bool(item[5]) if len(item) > 5 else True,
                    "half_width": max(1.5, float(item[8]))
                    if len(item) > 8 and item[8] is not None else 4.8,
                    "suppress_markings": bool(item[9])
                    if len(item) > 9 else False,
                    "path_key": str(item[10]) if len(item) > 10 else "",
                    "path_index": int(item[11]) if len(item) > 11 else 0,
                    "road_type": str(item[12]) if len(item) > 12 else (
                        "divided" if len(item) > 4 and bool(item[4])
                        else "local"),
                    "explored": bool(item[13]) if len(item) > 13 else False,
                })
            except (TypeError, ValueError, IndexError):
                continue
        self.road_segments = segments
        self._road_runs = self._build_road_runs(segments)
        self._ground_generation += 1
        self._road_ribbons = []
        # Build world-space road surfaces once per snapshot. Perspective then
        # projects their real widths rather than drawing fixed-width screen lines.
        for kind, half_width, explored, points, bounds in self._road_runs:
            path = QPainterPath(QPointF(*points[0]))
            for point in points[1:]:
                path.lineTo(QPointF(*point))
            stroker = QPainterPathStroker()
            stroker.setWidth(half_width*2)
            stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
            stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            self._road_ribbons.append((kind, stroker.createStroke(path).toSubpathPolygons(), bounds))

    @staticmethod
    def _build_road_runs(segments):
        """Pre-group ordered world chords once per atomic scene revision."""
        grouped = {}
        for source_index, segment in enumerate(segments):
            path_key = segment["path_key"] or f"legacy:{source_index}"
            half_width = round(float(segment["half_width"]) * 4.0) / 4.0
            key = (path_key, segment["road_type"], half_width,
                   bool(segment["explored"]))
            grouped.setdefault(key, []).append(segment)

        runs = []
        for (_path_key, road_type, half_width, explored), items in grouped.items():
            points = []
            previous_index = None
            for segment in sorted(items, key=lambda item: item["path_index"]):
                first, second = segment["a"], segment["b"]
                continuous = bool(
                    points and previous_index is not None
                    and segment["path_index"] == previous_index + 1
                    and math.dist(points[-1], first) <= 3.5)
                if not continuous and len(points) >= 2:
                    xs = [point[0] for point in points]
                    zs = [point[1] for point in points]
                    runs.append((road_type, half_width, explored, tuple(points),
                                 (min(xs), max(xs), min(zs), max(zs))))
                    points = []
                if not points:
                    points.append(first)
                points.append(second)
                previous_index = segment["path_index"]
            if len(points) >= 2:
                xs = [point[0] for point in points]
                zs = [point[1] for point in points]
                runs.append((road_type, half_width, explored, tuple(points),
                             (min(xs), max(xs), min(zs), max(zs))))
        return runs

    def set_scene_polygons(self, payload):
        polygons = []
        for item in (payload or [])[:3000]:
            try:
                points = []
                for point in item[0]:
                    x, z = float(point[0]), float(point[1])
                    if not math.isfinite(x) or not math.isfinite(z):
                        raise ValueError("non-finite polygon point")
                    points.append((x, z))
                if len(points) >= 3:
                    polygons.append({
                        "points": tuple(points),
                        "colour": max(0, min(8, int(item[1]))),
                        "z_index": int(item[2]),
                        "kind": str(item[3]).lower() if len(item) > 3 else "area",
                        "height": max(0.0, min(350.0, float(item[4])))
                        if len(item) > 4 and math.isfinite(float(item[4])) else 0.0,
                        "bounds": (min(p[0] for p in points), max(p[0] for p in points),
                                   min(p[1] for p in points), max(p[1] for p in points)),
                    })
            except (TypeError, ValueError, IndexError, OverflowError):
                continue
        self._ground_generation += 1
        self.scene_polygons = sorted(
            polygons, key=lambda polygon: polygon["z_index"])

    def set_scene_features(self, payload):
        features = []
        for item in (payload or [])[:1800]:
            try:
                x, z = float(item[0]), float(item[1])
                if not math.isfinite(x) or not math.isfinite(z):
                    continue
                features.append({
                    "pos": (x, z), "kind": str(item[2]),
                    "icon": str(item[3]), "label": str(item[4]),
                })
            except (TypeError, ValueError, IndexError, OverflowError):
                continue
        self.scene_features = features
        # Load optional local artwork once per snapshot, never per paint frame.
        # Only simple tokens are allowed, so dataset strings cannot select paths.
        keys = set(sorted({f["icon"] for f in features
                if f["kind"].lower() == "company"
                and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", f["icon"])})[:128])
        root = Path(__file__).resolve().parents[1] / "assets" / "map_logos"
        self._feature_logos = {key: value for key, value in self._feature_logos.items()
                               if key in keys}
        for key in sorted(keys)[:128]:
            if key in self._feature_logos:
                continue
            filename = root / (key + ".png")
            pixmap = QPixmap(str(filename)) if filename.is_file() else QPixmap()
            self._feature_logos[key] = pixmap.scaled(
                96, 40, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation) if not pixmap.isNull() else None

    def _bounds(self, pts):
        xs = [p[0] for p in pts]
        zs = [p[1] for p in pts]
        return min(xs), max(xs), min(zs), max(zs)

    @staticmethod
    def _truck_marker_polygon(center, heading):
        """Return a compact north-up marker aligned to ETS heading."""
        fx, fz = -math.sin(heading), -math.cos(heading)
        forward = QPointF(fx, fz)
        right_axis = QPointF(-fz, fx)

        def point(ahead, right):
            return QPointF(
                center.x() + forward.x()*ahead + right_axis.x()*right,
                center.y() + forward.y()*ahead + right_axis.y()*right)

        return QPolygonF([
            point(19.0, 0.0), point(1.0, 8.0), point(-1.5, 3.2),
            point(-13.0, 0.0), point(-1.5, -3.2), point(1.0, -8.0),
        ])

    def paintEvent(self, event):
        qp = QPainter(self)
        qp.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        qp.setPen(Qt.PenStyle.NoPen)
        qp.setBrush(QColor(self._map_palette()["land"]))
        qp.drawRoundedRect(self.rect(), 10, 10)

        truck = self.state.get("truck_world_pos")
        heading = self.state.get("truck_heading", 0.0) or 0.0

        # Truck-centered view from the engine-published local map snapshot.
        if self.road_segments and truck:
            self.empty_state.hide()
            self._paint_map(qp, w, h, truck, heading)
            return

        self.turn_banner.hide()
        self.trip_panel.hide()
        pts = [point for point in (
            self._to_xz(point)
            for point in live_map_navigation_points(self.state))
            if point is not None]
        all_pts = pts + ([truck] if truck else [])
        if not all_pts:
            self.empty_state.show()
            self.empty_state.raise_()
            return
        self.empty_state.hide()

        minx, maxx, minz, maxz = self._bounds(all_pts)
        span = max(maxx - minx, maxz - minz, 50.0)
        pad = 30
        scale = (min(w, h) - 2 * pad) / span

        def to_screen(p):
            sx = pad + (p[0] - minx) * scale
            # Flip Z so "north" (smaller z) is up on screen.
            sy = pad + (maxz - p[1]) * scale
            return QPointF(sx, sy)

        # Route polyline.
        if len(pts) >= 2:
            qp.setPen(QPen(QColor("#1597F5"), 5, Qt.PenStyle.SolidLine,
                           Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            poly = QPolygonF([to_screen(p) for p in pts])
            qp.drawPolyline(poly)
            # Start (green) and end (red) markers.
            qp.setBrush(QColor("#34C759"))
            qp.drawEllipse(to_screen(pts[0]), 5, 5)
            qp.setBrush(QColor("#FF453A"))
            qp.drawEllipse(to_screen(pts[-1]), 5, 5)

        # Truck as a heading arrow.
        if truck:
            c = to_screen(truck)
            fx, fz = -math.sin(heading), -math.cos(heading)
            tip = QPointF(c.x() + fx * 14, c.y() - fz * 14)
            left = QPointF(c.x() - fz * 7 + fx * -6, c.y() - fx * 7 - fz * -6)
            right = QPointF(c.x() + fz * 7 + fx * -6, c.y() + fx * 7 - fz * -6)
            qp.setBrush(QColor("#FFD60A"))
            qp.setPen(QPen(QColor("#FFD60A"), 1))
            qp.drawPolygon(QPolygonF([tip, left, right]))

    def _paint_map(self, qp, w, h, truck, heading):
        """Original Qt renderer using the reference map's visual hierarchy.

        It draws prefab map areas, road casing, road fill, the authoritative
        route and finally locally rendered POI symbols without a web runtime.
        """
        radius = self.zoom_radius
        scale = (min(w, h) - 20) / (2 * radius)
        cx = truck[0] + self.pan_world[0]
        cz = truck[1] + self.pan_world[1]

        camera = MapCamera(w, h, (cx, cz), heading, radius) if self._perspective else None
        self._active_camera = camera
        def to_screen(p):
            if camera:
                screen = camera.project(p)
                return QPointF(*screen) if screen is not None else QPointF(-100000, -100000)
            return QPointF(w/2+(p[0]-cx)*scale, h/2+(p[1]-cz)*scale)

        colours = self._map_palette()
        # These are actual placed prefab areas, not inferred land-use geometry.
        map_area_colours = {
            0: colours["road"], 1: colours["yard"], 2: "#D8CBB6" if self._map_mode == "light" else "#565044",
            3: colours["park"], 4: "#EDD3CE" if self._map_mode == "light" else "#573D3A",
            5: colours["park"], 6: colours["water"],
            7: "#E9E3BD" if self._map_mode == "light" else "#555337",
            8: "#DED9E9" if self._map_mode == "light" else "#484154",
        }
        for polygon in self.scene_polygons:
            if camera:
                break
            if polygon["kind"] == "building":
                continue
            min_x, max_x, min_z, max_z = polygon["bounds"]
            if (max_x < cx-radius*1.45 or min_x > cx+radius*1.45
                    or max_z < cz-radius*1.45 or min_z > cz+radius*1.45):
                continue
            qp.setBrush(QColor(map_area_colours.get(polygon["colour"], colours["yard"])))
            qp.setPen(QPen(QColor(colours["border"]), .7))
            points = (camera.polygon(polygon["points"]) if camera else
                      [(to_screen(p).x(), to_screen(p).y()) for p in polygon["points"]])
            if len(points) >= 3:
                qp.drawPolygon(QPolygonF([QPointF(*p) for p in points]))

        # Building footprints are rendered only when explicitly supplied by the
        # dataset. Company anchors alone do not prove a building's location.
        road_colours = {
            "freeway": (QColor(colours["motorway"]), QColor(colours["road_edge"])),
            "divided": (QColor(colours["motorway"]), QColor(colours["road_edge"])),
            "no_vehicles": (QColor(colours["yard"]), QColor(colours["border"])),
            "local": (QColor(colours["road"]), QColor(colours["road_edge"])),
        }
        if camera:
            self._paint_perspective_ground(qp, camera, road_colours, map_area_colours)
        else:
            # World chords are pre-grouped once when the atomic scene revision is
            # received. Paint frames now cull a few continuous runs instead of
            # sorting and drawing up to 10,000 individual segments each time.
            road_paths = []
            view_radius = radius * 1.35
            for road_type, half_width, explored, points, bounds in self._road_runs:
                min_x, max_x, min_z, max_z = bounds
                if (max_x < cx - view_radius or min_x > cx + view_radius
                        or max_z < cz - view_radius or min_z > cz + view_radius):
                    continue
                width = round(max(3.2 if road_type in ("freeway", "divided") else 2.4, min(
                    42.0, 2.0 * half_width * scale)) * 2.0) / 2.0
                path = QPainterPath(to_screen(points[0]))
                for point in points[1:]:
                    path.lineTo(to_screen(point))
                road_paths.append((road_type, width, explored, path))

            qp.setBrush(Qt.BrushStyle.NoBrush)
            for road_type, width, explored, path in road_paths:
                _surface, casing = road_colours.get(road_type, road_colours["local"])
                qp.setPen(QPen(casing, width + 2.4, Qt.PenStyle.SolidLine,
                               Qt.PenCapStyle.RoundCap,
                               Qt.PenJoinStyle.RoundJoin))
                qp.drawPath(path)
            for road_type, width, explored, path in road_paths:
                surface, _casing = road_colours.get(road_type, road_colours["local"])
                qp.setPen(QPen(surface, width, Qt.PenStyle.SolidLine,
                               Qt.PenCapStyle.RoundCap,
                               Qt.PenJoinStyle.RoundJoin))
                qp.drawPath(path)

        self._paint_buildings(qp, to_screen, cx, cz, radius, scale)
        # GPS uses only current-revision snapshot geometry. Recorded replay is
        # admitted only by live_map_navigation_points() in its exclusive mode.
        ahead = live_map_navigation_points(self.state)
        ahead = [point for point in (self._to_xz(point) for point in ahead)
                 if point is not None]
        if len(ahead) >= 2:
            if camera:
                path = QPainterPath()
                for a, b in zip(ahead, ahead[1:]):
                    pair = camera.segment(a, b)
                    if pair:
                        path.moveTo(QPointF(*pair[0])); path.lineTo(QPointF(*pair[1]))
            else:
                path = QPainterPath(to_screen(ahead[0]))
                for point in ahead[1:]: path.lineTo(to_screen(point))
            qp.setBrush(Qt.BrushStyle.NoBrush)
            for colour, width in [(colours["route_edge"], 8.0), (colours["route"], 5.0)]:
                qp.setPen(QPen(QColor(colour), width, Qt.PenStyle.SolidLine,
                               Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                qp.drawPath(path)

        self._paint_scene_features(qp, to_screen, cx, cz, radius, scale)

        snapshot = self.state.get("lane_trajectory", {}) or {}
        events = snapshot.get("turn_events", []) or []
        if events and snapshot.get("valid", False):
            event = events[0]
            try:
                distance = max(
                    0.0, float(event.get("start_s_m", 0.0) or 0.0))
            except (TypeError, ValueError, OverflowError):
                distance = 0.0
            arrow = "↱" if event.get("direction") == "right" else "↰"
            shown = (f"{distance / 1000:.1f} km" if distance >= 1000
                     else f"{int(round(distance / 10.0) * 10)} m")
            self.turn_banner.setText(f"{arrow}   {shown}")
            self.turn_banner.adjustSize()
            self.turn_banner.move(
                max(54, (self.width() - self.turn_banner.width()) // 2), 14)
            self.turn_banner.show()
            self.turn_banner.raise_()
        else:
            self.turn_banner.hide()

        trip = navigation_trip_summary(self.state)
        if trip is not None:
            arrival, minutes, kilometres = trip
            self.trip_panel.setText(
                "<table width='292' cellspacing='0' cellpadding='2'><tr>"
                f"<td align='center'><b style='font-size:18px'>{arrival}</b><br>"
                "<span style='color:#7F9086;font-size:11px'>príchod</span></td>"
                f"<td align='center'><b style='font-size:18px'>{minutes}</b><br>"
                "<span style='color:#7F9086;font-size:11px'>minút</span></td>"
                f"<td align='center'><b style='font-size:18px'>{kilometres}</b><br>"
                "<span style='color:#7F9086;font-size:11px'>km</span></td>"
                "</tr></table>")
            self.trip_panel.show()
            self.trip_panel.raise_()
        else:
            self.trip_panel.hide()

        # Crisp maps-style position marker at the exact telemetry position.
        # In this north-up projection world +Z points down on screen. The old
        # marker negated Z a second time and therefore pointed opposite to the
        # truck heading.
        c = to_screen(truck)
        marker = self._truck_marker_polygon(c, 0.0 if camera else heading)
        shadow = QPolygonF([QPointF(point.x()+1.5, point.y()+2.0)
                            for point in marker])
        qp.setPen(Qt.PenStyle.NoPen)
        qp.setBrush(QColor(0, 0, 0, 105))
        qp.drawPolygon(shadow)
        qp.setPen(QPen(QColor("#FFFFFF"), 2.4,
                       Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                       Qt.PenJoinStyle.RoundJoin))
        qp.setBrush(QColor("#168FF0"))
        qp.drawPolygon(marker)

        # Small unobtrusive interaction hint; no extra toolbar is needed.
        qp.setPen(QColor(colours["muted"]))
        qp.drawText(14, h - 12,
                    "koliesko: zoom  •  potiahnuť: posun  •  dvojklik: kamión")

    def _paint_perspective_ground(self, qp, camera, road_colours, area_colours):
        """Cache a bounded ground tile, warp it with the real camera each frame.

        Roads stay on the ground plane. Buildings, route and POI billboards
        are separately projected above it. This avoids repainting 10k world
        segments for every small camera movement and does not change routing.
        """
        corners = [camera.ground(p) for p in ((0,0),(camera.width,0),
                   (camera.width,camera.height),(0,camera.height))]
        if any(p is None for p in corners):
            return
        xs,zs = [p[0] for p in corners],[p[1] for p in corners]
        needed = (min(xs),max(xs),min(zs),max(zs))
        key = (self._ground_generation,self._map_mode)
        cached = self._ground_tile
        quality = max(needed[1]-needed[0],needed[3]-needed[2])/1700.0
        rebuild = (cached is None or cached[0] != key or
                   not (.65*quality <= cached[3] <= 1.4*quality))
        if not rebuild:
            x0,x1,z0,z1=cached[2]
            rebuild = not (x0<=needed[0] and x1>=needed[1] and
                           z0<=needed[2] and z1>=needed[3])
        if rebuild:
            start=time.perf_counter()
            dx,dz=needed[1]-needed[0],needed[3]-needed[2]
            x0,x1=needed[0]-dx*.12,needed[1]+dx*.12
            z0,z1=needed[2]-dz*.12,needed[3]+dz*.12
            pixel_scale=2048.0/max(x1-x0,z1-z0)
            width,height=max(1,math.ceil((x1-x0)*pixel_scale)),max(1,math.ceil((z1-z0)*pixel_scale))
            image=QImage(width,height,QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(QColor(self._map_palette()["land"]))
            painter=QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setTransform(QTransform(pixel_scale,0,0,pixel_scale,
                                            -x0*pixel_scale,-z0*pixel_scale))
            for polygon in self.scene_polygons:
                if polygon["kind"]=="building":
                    continue
                a,b,c,d=polygon["bounds"]
                if b<x0 or a>x1 or d<z0 or c>z1:
                    continue
                painter.setPen(QPen(QColor(self._map_palette()["border"]),.6/pixel_scale))
                painter.setBrush(QColor(area_colours.get(polygon["colour"],self._map_palette()["yard"])))
                painter.drawPolygon(QPolygonF([QPointF(*p) for p in polygon["points"]]))
            paths=[]
            for kind,contours,bounds in self._road_ribbons:
                a,b,c,d=bounds
                if b<x0 or a>x1 or d<z0 or c>z1:
                    continue
                path=QPainterPath();path.setFillRule(Qt.FillRule.OddEvenFill)
                for contour in contours:
                    path.addPolygon(contour);path.closeSubpath()
                paths.append((kind,path))
            for kind,path in paths:
                surface,edge=road_colours.get(kind,road_colours["local"])
                painter.setPen(QPen(edge,1.4/pixel_scale));painter.setBrush(edge)
                painter.drawPath(path)
            painter.setPen(Qt.PenStyle.NoPen)
            for kind,path in paths:
                painter.setBrush(road_colours.get(kind,road_colours["local"])[0])
                painter.drawPath(path)
            painter.end()
            cached=(key,image,(x0,x1,z0,z1),1/pixel_scale)
            self._ground_tile=cached
            self._ground_build_ms=(time.perf_counter()-start)*1000
        _key,image,(x0,x1,z0,z1),metres_per_pixel=cached
        to_world=QTransform(metres_per_pixel,0,0,metres_per_pixel,x0,z0)
        projection=QTransform(*camera.ground_matrix())
        qp.save()
        qp.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        qp.setTransform(to_world*projection,True)
        qp.drawImage(QPointF(0,0),image)
        qp.restore()


    def refresh_buildings(self):
        """Query separate display data in a bounded worker, never in paintEvent."""
        import threading
        identity=(self.state.get("active_map_key"),self.state.get("active_dataset_fingerprint"))
        truck=self.state.get("truck_world_pos")
        if self._building_identity != identity:
            self._visual_buildings=[]
            self._building_identity=identity
            self._building_request=None
            self._building_retry_at=0.0
        if not truck or not identity[0] or not identity[1] or identity[1]=="unavailable":
            return
        if self._building_job_pending or time.monotonic()<self._building_retry_at:
            return
        try:
            centre=(float(truck[0])+self.pan_world[0],float(truck[1])+self.pan_world[1])
            if not all(math.isfinite(v) for v in centre):return
        except (TypeError,ValueError,IndexError):
            return
        radius=min(5000.0,max(900.0,self.zoom_radius*3.0))
        previous=self._building_request
        if (previous and previous[0]==identity and previous[2]>=radius*.9
                and math.dist(previous[1],centre)<max(80.0,radius*.2)):
            return
        request=(identity,centre,radius)
        self._building_job_pending=True
        def work():
            try:
                from UI.building_layer import query_buildings
                from core.paths import app_dir
                root=Path(app_dir())/"assets"/"map_buildings"
                payload=query_buildings(root,identity[0],identity[1],centre,radius)
            except Exception:
                payload=[]
            try:
                self.buildings_loaded.emit((request,payload))
            except RuntimeError:
                pass  # Widget was closed while the read-only query finished.
        threading.Thread(target=work,name="NavigationBuildings",daemon=True).start()

    def _accept_buildings(self,result):
        self._building_job_pending=False
        request,payload=result
        current=(self.state.get("active_map_key"),self.state.get("active_dataset_fingerprint"))
        if request[0]!=current:
            self._visual_buildings=[]
            self._building_request=None
            return
        self._visual_buildings=payload
        self._building_request=request if payload else None
        self._building_retry_at=time.monotonic()+(0.0 if payload else 10.0)
        self.update()

    def _paint_buildings(self, qp, to_screen, cx, cz, radius, scale):
        """Project real footprint walls and roofs through the same map camera."""
        c = self._map_palette()
        camera = self._active_camera
        buildings = [p for p in self.scene_polygons if p["kind"] == "building"]
        identity=(self.state.get("active_map_key"),self.state.get("active_dataset_fingerprint"))
        if self._building_identity==identity:
            buildings.extend(self._visual_buildings)
        if camera:
            buildings.sort(key=lambda p: camera.local(
                ((p["bounds"][0]+p["bounds"][1])/2,
                 (p["bounds"][2]+p["bounds"][3])/2))[2], reverse=True)
        for polygon in buildings:
            min_x,max_x,min_z,max_z = polygon["bounds"]
            if (max_x < cx-radius*1.5 or min_x > cx+radius*1.5
                    or max_z < cz-radius*1.5 or min_z > cz+radius*1.5):
                continue
            points = polygon["points"]
            if camera:
                # Do not emit reflected geometry across the near plane.
                if any(camera.project(p, polygon["height"]) is None for p in points):
                    continue
                base = [QPointF(*camera.project(p)) for p in points]
                roof = [QPointF(*camera.project(p,polygon["height"])) for p in points]
            else:
                base = [to_screen(p) for p in points];roof = base
            qp.save();qp.setPen(Qt.PenStyle.NoPen)
            qp.setBrush(QColor(0,0,0,22))
            qp.drawPolygon(QPolygonF([QPointF(p.x()+2,p.y()+3) for p in base]))
            walls = sorted(range(len(base)), key=lambda i: (base[i].y()+base[(i+1)%len(base)].y())/2)
            for i in walls:
                j=(i+1)%len(base)
                shade=QColor(c["building_side"]).darker(108 if base[j].x()>base[i].x() else 100)
                qp.setBrush(shade)
                qp.drawPolygon(QPolygonF([base[i],base[j],roof[j],roof[i]]))
            qp.setPen(QPen(QColor(c["border"]),.7));qp.setBrush(QColor(c["building"]))
            qp.drawPolygon(QPolygonF(roof));qp.restore()

    def _paint_scene_features(self, qp, to_screen, cx, cz, radius, scale):
        """Readable service pins and optional local company artwork."""
        c = self._map_palette()
        icon_colours = {
            "gas": "#23986B", "fuel": "#23986B", "parking": "#478ED0",
            "service": "#D98A36", "dealer": "#D98A36", "garage": "#D98A36",
            "train": "#589BB7", "ferry": "#589BB7", "port": "#589BB7",
            "toll": "#728A9C", "weigh": "#728A9C", "viewpoint": "#9B78C7",
            "photo": "#9B78C7", "recruit": "#5D8BCA", "agency": "#5D8BCA",
            "hotel": "#9B78C7", "rest": "#478ED0", "food": "#C57453",
        }
        # Reserve full badge/label rectangles, not just icon centres. Grid
        # occupancy bounds overlap work even for the maximum 1,800 features.
        occupied = set()
        def reserve(rect):
            cells = {(x, y) for x in range(math.floor(rect.left()/24), math.floor(rect.right()/24)+1)
                     for y in range(math.floor(rect.top()/24), math.floor(rect.bottom()/24)+1)}
            if cells & occupied:
                return False
            occupied.update(cells)
            return True
        qp.save()
        features = sorted(self.scene_features,
                          key=lambda f: (f["kind"].lower() == "city",
                                         f["kind"].lower() != "company"))
        for feature in features:
            x, z = feature["pos"]
            if abs(x-cx) > radius*1.35 or abs(z-cz) > radius*1.35:
                continue
            point = to_screen((x, z))
            kind, icon = feature["kind"].lower(), feature["icon"].lower()
            label = feature["label"]
            if kind == "city":
                if not label or radius < 320:
                    continue
                font = qp.font(); font.setPointSize(11); font.setBold(True); qp.setFont(font)
                text = qp.fontMetrics().elidedText(label, Qt.TextElideMode.ElideRight, 180)
                rect = QRectF(point.x()+7, point.y()-18, qp.fontMetrics().horizontalAdvance(text)+8, 23)
                if reserve(rect):
                    path = QPainterPath(); path.addText(rect.left()+3, rect.bottom()-5, font, text)
                    qp.setBrush(QColor(c["text"])); qp.setPen(QPen(QColor(c["land"]), 3))
                    qp.drawPath(path); qp.setPen(Qt.PenStyle.NoPen); qp.drawPath(path)
                continue
            size = 23
            colour = QColor(next((value for name, value in icon_colours.items() if name in icon), "#6E91AA"))
            font = qp.font(); font.setPointSize(8); font.setBold(True); qp.setFont(font)
            text = qp.fontMetrics().elidedText(label or feature["icon"], Qt.TextElideMode.ElideRight, 100)
            logo = self._feature_logos.get(feature["icon"]) if kind == "company" else None
            company_width = max(42, min(112, (logo.width()+12) if logo else qp.fontMetrics().horizontalAdvance(text)+14))
            width = company_width if kind == "company" else size
            rect = QRectF(point.x()-width/2, point.y()-size/2, width, size)
            if not reserve(rect.adjusted(-3, -3, 3, 3)):
                continue
            qp.setPen(Qt.PenStyle.NoPen); qp.setBrush(QColor(0, 0, 0, 28))
            qp.drawRoundedRect(rect.translated(0, 2), 7, 7)
            qp.setPen(QPen(QColor(c["border"] if kind == "company" else "#FFFFFF"), 1.2))
            qp.setBrush(QColor(c["panel"]) if kind == "company" else colour)
            qp.drawRoundedRect(rect, 7, 7)
            if kind == "company":
                if logo:
                    target = QRectF(0, 0, logo.width(), logo.height())
                    target.setSize(target.size().scaled(rect.adjusted(5,4,-5,-4).size(), Qt.AspectRatioMode.KeepAspectRatio))
                    target.moveCenter(rect.center())
                    qp.drawPixmap(target, logo, QRectF(logo.rect()))
                else:
                    # A nameplate is honest when the dataset has no logo.
                    qp.setPen(QColor(c["text"])); qp.drawText(rect, Qt.AlignmentFlag.AlignCenter, text or "Firma")
            else:
                self._paint_feature_symbol(qp, rect, icon, kind)
                if label and radius <= 400:
                    label_rect = QRectF(rect.right()+5, rect.top(), qp.fontMetrics().horizontalAdvance(text)+8, 23)
                    if reserve(label_rect):
                        qp.setPen(Qt.PenStyle.NoPen); qp.setBrush(QColor(c["panel"]))
                        qp.drawRoundedRect(label_rect, 5, 5); qp.setPen(QColor(c["text"]))
                        qp.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, text)
        qp.restore()

    @staticmethod
    def _paint_feature_symbol(qp, rect, icon, kind):
        """Draw compact vector POI pictograms; never raw placeholder letters."""
        qp.save()
        qp.setBrush(Qt.BrushStyle.NoBrush)
        pen = QPen(QColor("#FFFFFF"), max(1.0, rect.width() / 11.0),
                   Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                   Qt.PenJoinStyle.RoundJoin)
        qp.setPen(pen)
        x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
        key = f"{kind} {icon}".lower()
        if any(value in key for value in ("gas", "fuel")):
            qp.drawRoundedRect(QRectF(x+w*.25, y+h*.20, w*.38, h*.60),
                               w*.04, w*.04)
            qp.drawLine(QPointF(x+w*.32, y+h*.38),
                        QPointF(x+w*.56, y+h*.38))
            hose = QPainterPath(QPointF(x+w*.63, y+h*.31))
            hose.cubicTo(x+w*.86, y+h*.32, x+w*.79, y+h*.72,
                         x+w*.72, y+h*.72)
            qp.drawPath(hose)
        elif any(value in key for value in ("service", "garage", "dealer")):
            qp.drawLine(QPointF(x+w*.27, y+h*.72),
                        QPointF(x+w*.73, y+h*.26))
            qp.drawEllipse(QPointF(x+w*.27, y+h*.72), w*.09, w*.09)
            qp.drawLine(QPointF(x+w*.64, y+h*.22),
                        QPointF(x+w*.79, y+h*.37))
        elif "train" in key:
            qp.drawRoundedRect(QRectF(x+w*.24, y+h*.18, w*.52, h*.54),
                               w*.08, w*.08)
            qp.drawLine(QPointF(x+w*.34, y+h*.36),
                        QPointF(x+w*.66, y+h*.36))
            qp.drawEllipse(QPointF(x+w*.34, y+h*.76), w*.06, w*.06)
            qp.drawEllipse(QPointF(x+w*.66, y+h*.76), w*.06, w*.06)
        elif "ferry" in key:
            boat = QPainterPath(QPointF(x+w*.18, y+h*.58))
            boat.lineTo(x+w*.82, y+h*.58)
            boat.lineTo(x+w*.69, y+h*.76)
            boat.lineTo(x+w*.31, y+h*.76)
            boat.closeSubpath()
            qp.drawPath(boat)
            qp.drawLine(QPointF(x+w*.38, y+h*.58),
                        QPointF(x+w*.38, y+h*.34))
            qp.drawLine(QPointF(x+w*.38, y+h*.34),
                        QPointF(x+w*.63, y+h*.45))
        elif any(value in key for value in ("toll", "weigh")):
            qp.drawLine(QPointF(x+w*.24, y+h*.72),
                        QPointF(x+w*.24, y+h*.27))
            qp.drawLine(QPointF(x+w*.76, y+h*.72),
                        QPointF(x+w*.76, y+h*.27))
            qp.drawLine(QPointF(x+w*.20, y+h*.29),
                        QPointF(x+w*.80, y+h*.29))
            qp.drawLine(QPointF(x+w*.36, y+h*.29),
                        QPointF(x+w*.36, y+h*.72))
        elif any(value in key for value in ("viewpoint", "photo", "sight")):
            qp.drawRoundedRect(QRectF(x+w*.20, y+h*.30, w*.60, h*.46),
                               w*.06, w*.06)
            qp.drawEllipse(QPointF(x+w*.50, y+h*.53), w*.14, w*.14)
            qp.drawLine(QPointF(x+w*.30, y+h*.30),
                        QPointF(x+w*.39, y+h*.20))
            qp.drawLine(QPointF(x+w*.39, y+h*.20),
                        QPointF(x+w*.55, y+h*.20))
        elif any(value in key for value in ("recruit", "agency")):
            qp.drawEllipse(QPointF(x+w*.50, y+h*.34), w*.13, w*.13)
            qp.drawArc(QRectF(x+w*.25, y+h*.45, w*.50, h*.38), 0, 180*16)
            qp.drawLine(QPointF(x+w*.70, y+h*.28),
                        QPointF(x+w*.82, y+h*.28))
            qp.drawLine(QPointF(x+w*.76, y+h*.22),
                        QPointF(x+w*.76, y+h*.34))
        elif kind == "company":
            roof = QPainterPath(QPointF(x+w*.18, y+h*.43))
            roof.lineTo(x+w*.50, y+h*.20)
            roof.lineTo(x+w*.82, y+h*.43)
            qp.drawPath(roof)
            qp.drawRect(QRectF(x+w*.24, y+h*.43, w*.52, h*.36))
            qp.drawRect(QRectF(x+w*.43, y+h*.58, w*.16, h*.21))
        else:
            # Parking/rest-area symbol: a car silhouette instead of a raw P.
            car = QPainterPath(QPointF(x+w*.20, y+h*.61))
            car.lineTo(x+w*.30, y+h*.40)
            car.lineTo(x+w*.68, y+h*.40)
            car.lineTo(x+w*.80, y+h*.61)
            qp.drawPath(car)
            qp.drawLine(QPointF(x+w*.20, y+h*.61),
                        QPointF(x+w*.80, y+h*.61))
            qp.drawEllipse(QPointF(x+w*.31, y+h*.69), w*.06, w*.06)
            qp.drawEllipse(QPointF(x+w*.69, y+h*.69), w*.06, w*.06)
        qp.restore()

    @staticmethod
    def _to_xz(point):
        """Accept legacy X/Z and authoritative lane X/Y/Z points."""
        if not isinstance(point, (list, tuple)):
            return None
        try:
            if len(point) >= 3:
                return float(point[0]), float(point[2])
            if len(point) >= 2:
                return float(point[0]), float(point[1])
        except (TypeError, ValueError, OverflowError):
            return None
        return None

class MapPage(QWidget):
    """Game-GPS navigation, active dataset and authoritative live map."""

    def __init__(self, state):
        super().__init__()
        self.state = state
        from core.theme import palette
        self._pal = palette(state.get("ui_theme", "light") or "light")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        head = QHBoxLayout()
        self.title = QLabel("Navigácia")
        self.title.setStyleSheet("font-size:24px;font-weight:800;color:" + self._pal['text'] + ";")
        head.addWidget(self.title)
        self.title_copy = QLabel("Herná GPS, mapové dáta a živý priebeh trasy")
        self.title_copy.setStyleSheet("color:" + self._pal['muted'] + ";font-size:12px;margin-left:8px;")
        head.addWidget(self.title_copy)
        head.addStretch()
        layout.addLayout(head)

        stats = QHBoxLayout()
        stats.setSpacing(10)
        self.nav_stats = {}
        for key, caption in (("gps", "HERNÁ GPS"), ("map", "AKTÍVNA MAPA"),
                             ("trajectory", "TRAJEKTÓRIA")):
            card = QFrame()
            card.setObjectName("NavigationStat")
            card.setStyleSheet(
                "QFrame#NavigationStat{background:" + self._pal['card']
                + ";border:1px solid " + self._pal['border']
                + ";border-radius:11px;}")
            box = QVBoxLayout(card)
            box.setContentsMargins(14, 10, 14, 10)
            box.setSpacing(2)
            cap = QLabel(caption)
            cap.setStyleSheet("font-size:9px;font-weight:750;color:"
                              + self._pal['muted'] + ";")
            value = QLabel("—")
            value.setStyleSheet("font-size:13px;font-weight:700;color:"
                                + self._pal['text'] + ";")
            box.addWidget(cap)
            box.addWidget(value)
            stats.addWidget(card, 1)
            self.nav_stats[key] = (card, cap, value)
        layout.addLayout(stats)

        content = QHBoxLayout()
        content.setSpacing(12)
        self.controls = QFrame()
        controls = self.controls
        controls.setObjectName("NavigationControls")
        controls.setFixedWidth(300)
        controls.setStyleSheet(
            "#NavigationControls{background:" + self._pal['card']
            + ";border:1px solid " + self._pal['border'] + ";border-radius:12px;}"
        )
        ctl = QVBoxLayout(controls)
        ctl.setContentsMargins(14, 14, 14, 14)
        ctl.setSpacing(9)

        self.source_cap = QLabel("AKTÍVNA NAVIGÁCIA")
        self.source_cap.setStyleSheet(
            "color:#7B818A!important;font-size:10px;font-weight:750;letter-spacing:1px;")
        ctl.addWidget(self.source_cap)
        self.status = QLabel("Čakám na hernú GPS trasu")
        self.status.setWordWrap(True)
        self.status.setStyleSheet(
            "background:#F5F6F7;color:#59616C;border-radius:7px;padding:9px;font-size:12px;")
        ctl.addWidget(self.status)

        self.gps_hint = QLabel(
            "Cieľ nastav priamo v navigácii hry. UltraPilot automaticky "
            "použije potvrdenú trasu a rovnakú revíziu zobrazí na HUD, AR aj mape.")
        self.gps_hint.setWordWrap(True)
        self.gps_hint.setStyleSheet(
            "color:#6B7280!important;font-size:11px;line-height:1.3;")
        ctl.addWidget(self.gps_hint)

        self.map_title = QLabel("MAPOVÉ DÁTA")
        self.map_title.setStyleSheet("color:#7B818A;font-size:10px;font-weight:700;margin-top:8px;")
        ctl.addWidget(self.map_title)
        self.map_combo = QComboBox()
        self.map_combo.currentIndexChanged.connect(self._on_map_selected)
        ctl.addWidget(self.map_combo)
        self.btn_dl = QPushButton("↓  Download map data")
        self.btn_dl.clicked.connect(self.download_map)
        ctl.addWidget(self.btn_dl)
        self.btn_use = QPushButton("Use & load selected map")
        self.btn_use.setStyleSheet(
            "QPushButton{background:#159957;color:white;border:none;border-radius:7px;padding:9px;font-weight:700;}"
            "QPushButton:hover{background:#118249;}"
        )
        self.btn_use.clicked.connect(self.use_selected_map)
        ctl.addWidget(self.btn_use)
        self.active_map_lbl = QLabel("Active map: —")
        self.active_map_lbl.setStyleSheet(
            "color:#FFFFFF!important;background:#159957;font-size:12px;font-weight:700;"
            "border-radius:7px;padding:9px 10px;")
        ctl.addWidget(self.active_map_lbl)
        self.dl_bar = QProgressBar()
        self.dl_bar.setRange(0, 100)
        self.dl_bar.setFormat("%p %")
        self.dl_bar.setTextVisible(True)
        self.dl_bar.setVisible(False)
        ctl.addWidget(self.dl_bar)
        self.dl_status = QLabel("")
        self.dl_status.setWordWrap(True)
        self.dl_status.setStyleSheet("color:#7B818A!important;font-size:11px;")
        ctl.addWidget(self.dl_status)
        self.btn_diag = QPushButton("Uložiť poslednú diagnostiku trasy")
        self.btn_diag.clicked.connect(self.save_route_diagnostic)
        self.btn_diag.setEnabled(False)
        ctl.addWidget(self.btn_diag)
        ctl.addStretch()
        content.addWidget(controls)

        self.view = MapView(state)
        self.view._pal = self._pal
        self.view.apply_theme()
        self.view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        content.addWidget(self.view, 1)
        layout.addLayout(content, 1)

        self._dl_worker = None
        self._last_active_map_key = None
        self._last_road_segments_revision = None
        self._last_live_map_scene_revision = None
        self._last_pose_signature = None
        self._populate_maps()
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh)
        self.timer.start(250)
        self._last_diag_export_result = None
        self._last_map_load_generation = None

    def showEvent(self, event):
        # Wide 1.2 km map geometry is presentation-only and relatively
        # expensive. Let the map plugin build it only while this page is
        # actually visible; a hidden navigation page must never compete with
        # the 100 Hz lane-authority heartbeat used by the autopilot.
        self.state.set("live_map_view_active", True)
        super().showEvent(event)

    def hideEvent(self, event):
        self.state.set("live_map_view_active", False)
        super().hideEvent(event)

    def restyle(self, theme):
        """Re-apply palette colours when the theme switches (dark ↔ light)."""
        from core.theme import palette
        self._pal = palette(theme)
        self.title.setStyleSheet("font-size:24px;font-weight:800;color:" + self._pal['text'] + ";")
        self.title_copy.setStyleSheet(
            "color:" + self._pal['muted'] + ";font-size:12px;margin-left:8px;")
        self.controls.setStyleSheet(
            "#NavigationControls{background:" + self._pal['card']
            + ";border:1px solid " + self._pal['border'] + ";border-radius:12px;}")
        self.gps_hint.setStyleSheet(
            "color:" + self._pal['muted'] + ";font-size:11px;")
        for card, cap, value in self.nav_stats.values():
            card.setStyleSheet(
                "QFrame#NavigationStat{background:" + self._pal['card']
                + ";border:1px solid " + self._pal['border']
                + ";border-radius:11px;}")
            cap.setStyleSheet("font-size:9px;font-weight:750;color:"
                              + self._pal['muted'] + ";")
            value.setStyleSheet("font-size:13px;font-weight:700;color:"
                                + self._pal['text'] + ";")
        self.status.setStyleSheet(
            "background:" + self._pal['card2'] + ";color:" + self._pal['muted']
            + ";border-radius:8px;padding:10px;font-size:12px;")
        self.map_title.setStyleSheet("color:#7B818A;font-size:10px;font-weight:700;margin-top:8px;")
        self.active_map_lbl.setStyleSheet(
            "color:#FFFFFF;background:#159957;font-size:12px;font-weight:700;"
            "border-radius:7px;padding:9px 10px;")
        self.dl_status.setStyleSheet("color:#7B818A;font-size:11px;")
        self.view._pal = self._pal
        self.view.apply_theme()

    # --- Map data -------------------------------------------------------------
    def _populate_maps(self):
        try:
            from core.navigation import map_data
            datasets = map_data.list_datasets()
        except Exception as e:
            self.dl_status.setText(f"Could not reach map index: {e}")
            return
        self.map_combo.blockSignals(True)
        self.map_combo.clear()
        # Read the user's last selection so we pre-select it (saved map).
        try:
            from core.settings.manager import SettingsManager
            wanted = (SettingsManager().get("selected_map") or "").strip()
        except Exception:
            wanted = ""
        sel_idx = 0
        for i, d in enumerate(datasets):
            mark = "✓ " if d["downloaded"] else ""
            game_version = d.get("game_version") or d["version"]
            if d.get("mod"):
                detail = f"{d['mod']} {d.get('mod_version') or d['version']} · {d['game']} {game_version}"
            else:
                detail = f"{d['game']} {game_version}"
                if d.get("content"):
                    detail += f" · {d['content']}"
            self.map_combo.addItem(f"{mark}{d['key']}  ({detail})", d["key"])
            if d["key"] == wanted:
                sel_idx = i
        if datasets:
            self.map_combo.setCurrentIndex(sel_idx)
            self.dl_status.setText("Pick your game version (or ProMods) and download once.")
        self.map_combo.blockSignals(False)
        self._update_active_map_label()
        self._update_map_actions()

    def _on_map_selected(self, _idx):
        """User picked a dataset in the combo — remember it as the active map."""
        key = self.map_combo.currentData()
        if not key:
            return
        try:
            from core.settings.manager import SettingsManager
            SettingsManager().set("selected_map", key)
        except Exception:
            pass
        # Mirror to shared state so the engine/map plugin can switch without restart.
        self.state.set("selected_map", key)
        self._update_active_map_label()
        self._update_map_actions()

    def _update_map_actions(self):
        key = self.map_combo.currentData()
        downloaded = False
        try:
            from core.navigation import map_data
            downloaded = bool(key and map_data.is_downloaded(key))
        except Exception:
            pass
        self.btn_dl.setVisible(not downloaded)
        self.btn_use.setEnabled(downloaded)
        local = False
        trucklib_required = False
        if not downloaded:
            try:
                entry = next((item for item in map_data.list_datasets()
                              if item["key"] == key), {})
                local = entry.get("source") == "local-game"
                trucklib_required = entry.get("source") == "trucklib-required"
            except Exception:
                pass
        self.btn_dl.setEnabled(not trucklib_required)
        self.btn_use.setText(
            "Použiť a načítať vybranú mapu" if downloaded else
            ("Pre ETS2 1.60 chýba TruckLib exportér" if trucklib_required
             else "Najprv vytvor mapu z nainštalovanej hry" if local
             else "Najprv stiahni mapu"))
        self.btn_dl.setText("Podpora 1.60 sa pripravuje" if trucklib_required
                            else "Vytvoriť z nainštalovanej hry" if local
                            else "Stiahnuť mapu")

    def use_selected_map(self):
        key = self.map_combo.currentData()
        if not key:
            return
        self._on_map_selected(self.map_combo.currentIndex())
        self.view.set_road_segments([])
        self.view.set_scene_polygons([])
        self.view.set_scene_features([])
        self.state.set("nav_arg", key)
        self.state.set("nav_cmd", "switch_map")
        self.dl_status.clear()
        self.dl_bar.hide()
        self.btn_use.setEnabled(False)

    def _update_active_map_label(self):
        """Show which map the autopilot is actually using."""
        name = self.state.get("active_map_name") or self.state.get("active_map_key")
        sel = self.state.get("selected_map")
        if name:
            self.active_map_lbl.setText(f"Aktívna mapa: {name}")
        elif sel:
            self.active_map_lbl.setText(f"Vybraná mapa: {sel}")
        else:
            self.active_map_lbl.setText("Aktívna mapa: —")

    def download_map(self):
        if self._dl_worker is not None:
            return
        key = self.map_combo.currentData()
        if not key:
            return
        self.btn_dl.setEnabled(False)
        self.dl_bar.setVisible(True)
        self._dl_worker = MapDownloadWorker(key)
        self._dl_worker.progress.connect(self._on_dl_progress)
        self._dl_worker.done.connect(self._on_dl_done)
        self._dl_worker.start()

    def _on_dl_progress(self, frac, text):
        self.dl_bar.setValue(int(frac * 100))
        self.dl_status.setText(text)

    def _on_dl_done(self, ok):
        self.btn_dl.setEnabled(True)
        self.dl_bar.setVisible(False)
        self._dl_worker = None
        if ok:
            self.dl_status.setText("Mapové dáta sú pripravené — načítavam cesty…")
        else:
            try:
                from core.navigation import map_data
                reason = map_data.last_error()
            except Exception:
                reason = ""
            self.dl_status.setText(
                reason or "Príprava mapy zlyhala; podrobnosti sú v logu.")
        self._populate_maps()

    def save_route_diagnostic(self):
        result = self.state.get("route_diagnostic_last_result") or {}
        build_id = result.get("route_build_id")
        if not build_id or result.get("status") == "success":
            self.status.setText("Nie je dostupný žiadny neúspešný výpočet trasy.")
            return
        self.state.set("route_diagnostic_export_result", None)
        self.state.set("route_diagnostic_export_request", build_id)
        self.status.setText("Ukladám anonymizovanú diagnostiku trasy…")

    def refresh(self):
        # The engine may auto-select a compatible dataset after comparing live
        # GPS node UIDs. Reload that same network in the UI process as well.
        active_key = self.state.get("active_map_key")
        repaint = False
        if active_key and active_key != self._last_active_map_key:
            self._last_active_map_key = active_key
            index = self.map_combo.findData(active_key)
            if index >= 0:
                self.map_combo.blockSignals(True)
                self.map_combo.setCurrentIndex(index)
                self.map_combo.blockSignals(False)
            self.view.set_road_segments([])
            self.view.set_scene_polygons([])
            self.view.set_scene_features([])
            repaint = True

        # Roads, true prefab map polygons and POIs are one atomic display
        # scene.  Older shared state falls back to the historical HUD roads.
        scene_revision = self.state.get("live_map_scene_revision")
        if scene_revision is not None:
            if scene_revision != self._last_live_map_scene_revision:
                self._last_live_map_scene_revision = scene_revision
                self.view.set_road_segments(
                    self.state.get("live_map_road_segments", []) or [])
                self.view.set_scene_polygons(
                    self.state.get("live_map_scene_polygons", []) or [])
                self.view.set_scene_features(
                    self.state.get("live_map_scene_features", []) or [])
                repaint = True
        else:
            road_revision = self.state.get("map_road_segments_revision", 0)
            if road_revision != self._last_road_segments_revision:
                self._last_road_segments_revision = road_revision
                self.view.set_road_segments(
                    self.state.get("map_road_segments", []) or [])
                repaint = True

        self.view.refresh_buildings()
        truck = self.state.get("truck_world_pos")
        heading = float(self.state.get("truck_heading", 0.0) or 0.0)
        try:
            pose_signature = (round(float(truck[0]), 1),
                              round(float(truck[1]), 1), round(heading, 3))
        except (TypeError, ValueError, IndexError):
            pose_signature = None
        if pose_signature != self._last_pose_signature:
            self._last_pose_signature = pose_signature
            repaint = True

        # Downloads keep their local progress here. Engine-side parsing is
        # shown exclusively by Dynamic Island so the navigation card cannot
        # retain a stale 2% bar after a cache load or plugin restart.
        load_progress = self.state.get("map_load_progress", {}) or {}
        if self._dl_worker is None and load_progress:
            active = bool(load_progress.get("active", False))
            generation = load_progress.get("generation")
            self.dl_bar.hide()
            self.dl_status.clear()
            if generation is not None:
                self._last_map_load_generation = generation
            self.btn_use.setEnabled(not active)

        command_error = rejected_navigation_command_message(self.state)
        if command_error:
            self.status.setText(command_error)
        elif self.state.get("nav_active"):
            dist = self.state.get("distance_to_dest")
            if dist is not None:
                self.status.setText(f"Navigating — {float(dist) / 1000:.2f} km to destination.")
            else:
                self.status.setText("GPS navigation active — following the route selected in game.")
        else:
            # Surface the map-loading status the engine publishes (loading /
            # ready / error) so the user is never left guessing why nav is off.
            ms = self.state.get("map_status")
            if ms:
                self.status.setText(str(ms))
        diagnostic = self.state.get("route_diagnostic_last_result") or {}
        self.btn_diag.setEnabled(bool(
            diagnostic.get("route_build_id")
            and diagnostic.get("status") != "success"))
        export_result = self.state.get("route_diagnostic_export_result")
        if export_result and export_result != self._last_diag_export_result:
            self._last_diag_export_result = dict(export_result)
            if export_result.get("ok"):
                self.status.setText(
                    f"Diagnostic saved: {export_result.get('path', '')}")
            else:
                self.status.setText(str(export_result.get(
                    "message", "Diagnostic could not be saved.")))
        # Keep the active-map badge in sync with whatever the map plugin
        # published (so the user sees the real running map, not just the
        # last selection from the combo).
        self._update_active_map_label()
        gps_active = bool(self.state.get("game_gps_navigation_active", False))
        self.nav_stats["gps"][2].setText("Aktívna" if gps_active else "Čakám na cieľ")
        self.nav_stats["map"][2].setText(str(
            self.state.get("active_map_name")
            or self.state.get("active_map_key") or "Nezvolená"))
        trajectory = self.state.get("lane_trajectory", {}) or {}
        if trajectory.get("valid", False):
            self.nav_stats["trajectory"][2].setText(
                f"Platná  •  rev. {trajectory.get('revision', 0)}")
        else:
            self.nav_stats["trajectory"][2].setText("Čakám na výpočet")
        if repaint or self.state.get("nav_active"):
            self.view.update()
