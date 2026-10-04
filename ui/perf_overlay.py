"""Reference-style, read-only memory popover with exact published plugin PIDs.

RSS is the process working set, not exclusive physical memory allocation.
"""

from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QFont, QFontMetrics
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea,
)
from core.process_memory import collect_memory


def _collect(state=None):
    return collect_memory(state)


def _memory(value):
    if value is None:
        return "—"
    return f"{value / 1000:.2f} GB" if value >= 1000 else f"{value:.2f} MB"


class PerfOverlay(QWidget):
    """Frameless, always-on-top, draggable mini performance panel."""

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(310, 348)
        self._rows = {}
        self._drag = None
        # Resolve the palette BEFORE _build() so the labels can read _pal.
        from core.theme import palette
        self._pal = palette(state.get("ui_theme", "light") or "light")
        self._build()
        self._apply_window_style()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.setInterval(500)
        self.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
        self.timer.start()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def restyle(self, theme):
        from core.theme import palette
        self._pal = palette(theme)
        self._apply_window_style()

    def _apply_window_style(self):
        # This reference console stays dark even in the application's light theme.
        self.setStyleSheet(
            # Override the inherited application-wide QWidget background for
            # row wrappers and the scroll viewport as well as their labels.
            "QWidget{background:transparent;border:none;}"
            "PerfOverlay{background:transparent;}"
            "QFrame#PerfSurface{background:#202020;border:1px solid #d6d6d8;border-radius:5px;}"
            "QWidget#PerfRows,QScrollArea{background:transparent;border:none;}"
            "QLabel{background:transparent;border:none;font-family:Consolas;"
            "font-size:12px;color:#cccccc;}"
            "QLabel#PerfBranch{color:#8be9fd;}"
            "QLabel#PerfValue{color:#b9f6ff;}"
            "QLabel#PerfTitle{color:#eeeeee;}"
            "QScrollBar:vertical{background:transparent;width:5px;margin:0;}"
            "QScrollBar::handle:vertical{background:#606060;min-height:25px;}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
            "QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:transparent;}")

    def show_above(self, anchor):
        """Open as a compact popover directly above the performance button."""
        point = anchor.mapToGlobal(QPoint(0, 0))
        screen = anchor.screen().availableGeometry() if anchor.screen() else None
        x = point.x()
        y = point.y() - self.height() - 10
        if screen is not None:
            x = max(screen.left() + 8, min(x, screen.right() - self.width() - 8))
            y = max(screen.top() + 8, min(y, screen.bottom() - self.height() - 8))
        self.move(x, y)
        self.show()
        self.raise_()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(0)
        self.surface = QFrame()
        self.surface.setObjectName("PerfSurface")
        root.addWidget(self.surface)
        body = QVBoxLayout(self.surface)
        body.setContentsMargins(18, 18, 18, 18)
        body.setSpacing(0)
        title = QLabel("┌ Plugins")
        title.setObjectName("PerfTitle")
        title.setFixedHeight(19)
        body.addWidget(title)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.rows_widget = QWidget()
        self.rows_widget.setObjectName("PerfRows")
        self.rows_box = QVBoxLayout(self.rows_widget)
        self.rows_box.setContentsMargins(0, 0, 0, 0)
        self.rows_box.setSpacing(0)
        self.rows_box.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.rows_widget)
        body.addWidget(self.scroll, 1)
        self.empty = QLabel("│  žiadne spustené pluginy")
        self.empty.setFixedHeight(19)
        body.addWidget(self.empty)
        tail = QLabel("│")
        tail.setObjectName("PerfBranch")
        tail.setFixedHeight(19)
        body.addWidget(tail)
        self.total_lbl = QLabel("└ Total:   —")
        self.total_lbl.setObjectName("PerfTitle")
        self.total_lbl.setFixedHeight(19)
        body.addWidget(self.total_lbl)
        self.setToolTip("Pamäť procesov (RSS) vrátane Pythonu a zdieľaných stránok. "
                        "1 MB = 1 000 000 bajtov. Obnova každých 0,5 s.")

    def refresh(self):
        from core.logger import PLUGIN_LABELS
        app_mb, _app_cpu, plugins = _collect(self.state)
        self.total_lbl.setText(f"└ Total:   {_memory(app_mb)}")
        self.empty.setVisible(not plugins)
        self.empty.setText("│  meranie nie je dostupné" if app_mb is None
                           else "│  žiadne spustené pluginy")
        self.scroll.setVisible(bool(plugins))
        ordered = sorted(plugins, key=lambda row: (-row[1], row[0]))
        names = {row[0] for row in ordered}
        for name in list(self._rows):
            if name not in names:
                widget, *_ = self._rows.pop(name)
                self.rows_box.removeWidget(widget)
                widget.deleteLater()
        for index, (name, mb, _cpu) in enumerate(ordered):
            if name not in self._rows:
                wrap = QWidget()
                wrap.setFixedHeight(19)
                layout = QHBoxLayout(wrap)
                layout.setContentsMargins(0, 0, 0, 0)
                layout.setSpacing(4)
                branch = QLabel("│")
                branch.setObjectName("PerfBranch")
                branch.setFixedWidth(13)
                value = QLabel()
                value.setObjectName("PerfValue")
                value.setFixedWidth(73)
                value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                label = QLabel()
                layout.addWidget(branch)
                layout.addWidget(value)
                layout.addWidget(label, 1)
                self._rows[name] = wrap, value, label
            wrap, value, label = self._rows[name]
            value.setText(_memory(mb))
            display_name = PLUGIN_LABELS.get(name.lower().replace(" ", "_"), name)
            full_name = "- " + display_name
            label.setText(full_name)
            label.setToolTip(display_name)
            self.rows_box.insertWidget(index, wrap)
        # Preserve every plugin; long lists scroll rather than clipping rows.
        font = QFont("Consolas")
        font.setPixelSize(12)
        metrics = QFontMetrics(font)
        max_label = max((metrics.horizontalAdvance(row[2].text())
                         for row in self._rows.values()), default=170)
        desired_width = max(310, min(430, max_label + 155))
        screen = self.screen().availableGeometry() if self.screen() else None
        if screen is not None:
            desired_width = min(desired_width, screen.width() - 16)
        self.setFixedWidth(desired_width)
        desired = min(540, 110 + max(1, len(plugins)) * 19)
        if screen is not None:
            desired = min(desired, screen.height() - 16)
        if self.height() != desired:
            old_bottom = self.y() + self.height()
            self.setFixedHeight(desired)
            y = old_bottom - desired
            if screen is not None:
                y = max(screen.top() + 8, min(y, screen.bottom() - desired - 8))
            self.move(self.x(), y)

    # --- drag by the title area ---
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and e.position().y() <= 52:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e):
        if self._drag is not None and (e.buttons() & Qt.MouseButton.LeftButton):
            self.move(e.globalPosition().toPoint() - self._drag)
            e.accept()

    def mouseReleaseEvent(self, e):
        self._drag = None
