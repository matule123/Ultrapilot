"""Theme-aware, read-only memory popover with exact published plugin PIDs.

RSS is the process working set, not exclusive physical memory allocation.
"""

from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QGraphicsDropShadowEffect, QPushButton, QProgressBar, QScrollArea,
)
from core.process_memory import collect_memory


def _collect(state=None):
    return collect_memory(state)


def _memory(value):
    if value is None:
        return "—"
    return f"{value / 1000:.2f} GB" if value >= 1000 else f"{value:.1f} MB"


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
        self.setFixedSize(360, 360)
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
        p = self._pal
        self.setStyleSheet(
            "PerfOverlay{background:transparent;}"
            "QFrame#PerfSurface{background:" + p['card'] + ";border:1px solid "
            + p['border'] + ";border-radius:16px;}"
            "QLabel,QWidget#PerfRows{background:transparent;border:none;color:" + p['text'] + ";}"
            "QLabel#PerfTitle{font-size:16px;font-weight:750;}"
            "QLabel#PerfTotal{font-size:27px;font-weight:800;}"
            "QLabel#PerfMuted{font-size:11px;color:" + p['muted'] + ";}"
            "QLabel#PerfValue{font-size:12px;font-weight:650;}"
            "QLabel#PerfBadge{background:" + p['card2'] + ";color:" + p['title']
            + ";border-radius:8px;padding:5px 9px;font-size:11px;}"
            "QPushButton#PerfClose{background:transparent;border:none;border-radius:8px;"
            "font-size:20px;color:" + p['muted'] + ";}"
            "QPushButton#PerfClose:hover{background:" + p['card2'] + ";}"
            "QScrollArea{background:transparent;border:none;}"
            "QScrollBar:vertical{background:transparent;width:7px;margin:0;}"
            "QScrollBar::handle:vertical{background:" + p['border']
            + ";min-height:25px;border-radius:3px;}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
            "QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:transparent;}"
            "QProgressBar{background:" + p['card2'] + ";border:none;border-radius:3px;}"
            "QProgressBar::chunk{background:" + p['accent2'] + ";border-radius:3px;}")

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
        shadow = QGraphicsDropShadowEffect(self.surface)
        shadow.setBlurRadius(22)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 105))
        self.surface.setGraphicsEffect(shadow)
        root.addWidget(self.surface)
        body = QVBoxLayout(self.surface)
        body.setContentsMargins(13, 12, 13, 13)
        body.setSpacing(4)
        body.setSpacing(12)
        heading = QHBoxLayout()
        title = QLabel("Výkon aplikácie")
        title.setObjectName("PerfTitle")
        heading.addWidget(title, 1)
        close = QPushButton("×")
        close.setObjectName("PerfClose")
        close.setFixedSize(28, 28)
        close.setToolTip("Zavrieť kartu výkonu")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self.hide)
        heading.addWidget(close)
        body.addLayout(heading)
        caption = QLabel("Pamäť UltraPilotu")
        caption.setObjectName("PerfMuted")
        body.addWidget(caption)
        summary = QHBoxLayout()
        self.total_lbl = QLabel("—")
        self.total_lbl.setObjectName("PerfTotal")
        summary.addWidget(self.total_lbl, 1)
        self.count_lbl = QLabel("0 pluginov")
        self.count_lbl.setObjectName("PerfBadge")
        summary.addWidget(self.count_lbl)
        body.addLayout(summary)
        plugins_title = QLabel("PLUGINY  ·  PODĽA PAMÄTE")
        plugins_title.setObjectName("PerfMuted")
        body.addWidget(plugins_title)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.rows_widget = QWidget()
        self.rows_widget.setObjectName("PerfRows")
        self.rows_box = QVBoxLayout(self.rows_widget)
        self.rows_box.setContentsMargins(0, 0, 4, 0)
        self.rows_box.setSpacing(10)
        self.rows_box.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.rows_widget)
        body.addWidget(self.scroll, 1)
        self.empty = QLabel("Čakám na procesy pluginov…")
        self.empty.setObjectName("PerfMuted")
        self.empty.setWordWrap(True)
        body.addWidget(self.empty)
        footer = QLabel("Pamäť procesov (RSS) · obnova každých 0,5 s")
        footer.setObjectName("PerfMuted")
        footer.setWordWrap(True)
        footer.setToolTip("1 MB = 1 000 000 bajtov. RSS zahŕňa Python a zdieľané stránky; "
                          "súčet nie je výlučne pridelená fyzická RAM.")
        body.addWidget(footer)

    def refresh(self):
        app_mb, _app_cpu, plugins = _collect(self.state)
        self.total_lbl.setText(_memory(app_mb))
        count = len(plugins)
        suffix = "plugin" if count == 1 else "pluginy" if 2 <= count <= 4 else "pluginov"
        self.count_lbl.setText(f"{count} {suffix}")
        self.empty.setVisible(not plugins)
        self.empty.setText("Meranie pamäte nie je dostupné." if app_mb is None
                           else "Žiadne spustené pluginy.")
        self.scroll.setVisible(bool(plugins))
        ordered = sorted(plugins, key=lambda row: (-row[1], row[0]))
        names = {row[0] for row in ordered}
        for name in list(self._rows):
            if name not in names:
                widget, *_ = self._rows.pop(name)
                self.rows_box.removeWidget(widget)
                widget.deleteLater()
        plugin_total = sum(row[1] for row in plugins)
        for index, (name, mb, _cpu) in enumerate(ordered):
            if name not in self._rows:
                wrap = QWidget()
                wrap.setFixedHeight(39)
                layout = QVBoxLayout(wrap)
                layout.setContentsMargins(0, 0, 0, 0)
                layout.setSpacing(6)
                line = QHBoxLayout()
                label = QLabel(name)
                label.setObjectName("PerfValue")
                value = QLabel()
                value.setObjectName("PerfValue")
                value.setAlignment(Qt.AlignmentFlag.AlignRight)
                line.addWidget(label, 1)
                line.addWidget(value)
                layout.addLayout(line)
                bar = QProgressBar()
                bar.setRange(0, 1000)
                bar.setFixedHeight(5)
                bar.setTextVisible(False)
                layout.addWidget(bar)
                self._rows[name] = wrap, value, bar
            wrap, value, bar = self._rows[name]
            value.setText(_memory(mb))
            bar.setValue(round(1000 * mb / plugin_total) if plugin_total else 0)
            bar.setToolTip("Podiel na súčte RSS pluginov")
            self.rows_box.insertWidget(index, wrap)
        desired = min(540, 226 + min(6, max(1, len(plugins))) * 49)
        if self.height() != desired:
            old_bottom = self.y() + self.height()
            self.setFixedHeight(desired)
            screen = self.screen().availableGeometry() if self.screen() else None
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
