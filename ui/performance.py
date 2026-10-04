from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QProgressBar
from PyQt6.QtCore import QTimer, Qt
from core.theme import palette
from core.process_memory import collect_memory

try:
    import psutil
except Exception:
    psutil = None


class PerformancePage(QWidget):
    """Performance card: total RAM, app RAM, and per-process (plugin) usage."""

    def __init__(self, state):
        super().__init__()
        self.state = state
        self._pal = palette(state.get("ui_theme", "light") or "light")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)

        title = QLabel("Výkon aplikácie")
        title.setStyleSheet("font-size:18px;font-weight:700;color:" + self._pal['text'] + ";")
        self._title = title
        lay.addWidget(title)

        summary = QHBoxLayout()
        self.ram_card = QLabel("RAM\n—")
        self.cpu_card = QLabel("CPU\n—")
        self.proc_card = QLabel("PLUGINY\n—")
        for card in (self.ram_card, self.cpu_card, self.proc_card):
            card.setMinimumHeight(62)
            card.setAlignment(Qt.AlignmentFlag.AlignCenter)
            card.setStyleSheet(
                "background:#F7F8FA;color:#1F2937;border:1px solid #E5E7EB;"
                "border-radius:9px;padding:8px;font-size:11px;font-weight:700;")
            summary.addWidget(card)
        lay.addLayout(summary)

        self.total_lbl = QLabel("Pamäť počítača")
        self.total_lbl.setStyleSheet("color:" + self._pal['muted'] + "; font-weight:bold;")
        lay.addWidget(self.total_lbl)
        self.total_bar = QProgressBar()
        lay.addWidget(self.total_bar)

        self.app_lbl = QLabel("UltraPilot RAM: —")
        self.app_lbl.setStyleSheet("font-weight:bold; margin-top:6px;")
        lay.addWidget(self.app_lbl)

        # Per-process rows container.
        self.rows_frame = QFrame()
        self.rows_frame.setStyleSheet("background:#FFFFFF;border:1px solid #E5E7EB;border-radius:10px;padding:8px;")
        self.rows = QVBoxLayout(self.rows_frame)
        lay.addWidget(self.rows_frame)
        lay.addStretch()

        if psutil is None:
            self.app_lbl.setText("Meranie výkonu nie je dostupné.")

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1500)
        self.restyle(state.get("ui_theme", "light") or "light")

    def restyle(self, theme):
        self._pal = palette(theme)
        p = self._pal
        self._title.setStyleSheet("font-size:18px;font-weight:700;color:" + p['text'] + ";")
        self.total_lbl.setStyleSheet("color:" + p['muted'] + "; font-weight:bold;")
        for card in (self.ram_card, self.cpu_card, self.proc_card):
            card.setStyleSheet("background:" + p['card2'] + ";color:" + p['text']
                              + ";border:1px solid " + p['border']
                              + ";border-radius:12px;padding:10px;font-weight:700;")
        self.app_lbl.setStyleSheet("color:" + p['text'] + ";font-weight:700;")
        self.rows_frame.setStyleSheet("background:" + p['card'] + "; border:1px solid " + p['border'] + "; border-radius:12px; padding:10px;")

    def _clear_rows(self):
        while self.rows.count():
            w = self.rows.takeAt(0).widget()
            if w:
                w.setParent(None)
                w.deleteLater()

    def refresh(self):
        if psutil is None:
            return
        vm = psutil.virtual_memory()
        self.total_bar.setValue(int(vm.percent))
        self.total_bar.setFormat(f"{vm.percent:.0f}%  ({(vm.total-vm.available)/1e9:.1f} / {vm.total/1e9:.1f} GB)")

        app_mb, _, measured = collect_memory(self.state)
        plugins = [(name, mb) for name, mb, _ in measured]
        plug_mb = sum(mb for _, mb in plugins)
        self.app_lbl.setText("Pamäť procesov (RSS) · vrátane Python runtime")
        self.ram_card.setText(f"RAM APLIKÁCIE\n{app_mb:.0f} MB" if app_mb is not None
                              else "RAM APLIKÁCIE\n—")
        try:
            cpu = psutil.cpu_percent(interval=None)
        except Exception:
            cpu = 0.0
        self.cpu_card.setText(f"CPU POČÍTAČA\n{cpu:.0f}%")
        self.proc_card.setText(f"PLUGINY\n{len(plugins)}")

        self._clear_rows()
        if not plugins:
            lbl = QLabel("Žiadne spustené pluginy.")
            lbl.setStyleSheet("color:" + self._pal['muted'] + ";")
            self.rows.addWidget(lbl)
        for label, mb in sorted(plugins, key=lambda r: -r[1]):
            pct = 100 * mb / plug_mb if plug_mb else 0
            row = QHBoxLayout()
            n = QLabel(label); n.setFixedWidth(150)
            n.setStyleSheet("color:" + self._pal['text'] + ";")
            bar = QProgressBar(); bar.setValue(int(pct))
            bar.setFormat(f"{mb:.0f} MB  ({pct:.0f}%)")
            row.addWidget(n); row.addWidget(bar)
            holder = QWidget(); holder.setLayout(row)
            self.rows.addWidget(holder)
