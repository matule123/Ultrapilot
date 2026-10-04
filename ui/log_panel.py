"""Live log panel — shows the app's own log output in real time.

A dark, console-style panel (timestamp + coloured level tag + message) that
mirrors what gets written to ``ultrapilot.log``. A custom ``logging.Handler``
feeds every record into a ring buffer (capped so a long session can't grow the
document unbounded) and renders it with colour coding:

    INFO    → grey text
    WARNING → amber
    ERROR   → red
    DEBUG   → dim
    (plugin/section prefixes like ``map:``, ``autopilot:`` keep their colour)

It is added as a top-level page („Log“) in the main window's sidebar.
"""

import logging
import os
import re
import html
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QTextCharFormat, QTextCursor, QFont, QColor
from PyQt6.QtWidgets import QVBoxLayout, QHBoxLayout, QPushButton, QLabel
from PyQt6.QtWidgets import QTextEdit

from ui.app import Page


# Pre-formatted HTML colours per level.
_LEVEL_COLOR = {
    logging.DEBUG:    "#55DDEE",
    logging.INFO:     "#00AF00",
    logging.WARNING:  "#D7AF00",
    logging.ERROR:    "#FF0033",
    logging.CRITICAL: "#FF0033",
}
_LEVEL_TAG = {
    logging.DEBUG:    "[DBG]",
    logging.INFO:     "[INF]",
    logging.WARNING:  "[WRN]",
    logging.ERROR:    "[ERR]",
    logging.CRITICAL: "[CRT]",
}


def _message_html(message):
    """Keep all log text escaped, highlighting only a startup RAM receipt."""
    prefix, marker, suffix = message.partition(" · RAM: ")
    if ((message.startswith("Plugin pripravený: ") or message.startswith("Plugin "))
            and marker):
        return (html.escape(prefix) + '<span style="color:#BAE6FD;">'
                + html.escape(marker + suffix) + '</span>')
    return html.escape(message)


def _traceback_html(lines):
    # Plain-file history has no exception object. Preserve its recorded frames;
    # do not invent local variables or read different current source revisions.
    text = "\n".join(lines[1:])
    return ('<table width="100%" border="1" bordercolor="#FF0033" cellpadding="8">'
            '<tr><td><span style="color:#FF0033;">Traceback (most recent call last)</span>'
            '<pre style="color:#CCCCCC;">' + html.escape(text) + '</pre></td></tr></table>')


def _log_line_html(timestamp, level, message, source=""):
    number = getattr(logging, level, logging.INFO)
    return (
        '<table width="100%" cellspacing="0" cellpadding="0"><tr>'
        f'<td width="50" style="color:{_LEVEL_COLOR[number]};">{_LEVEL_TAG[number]}</td>'
        f'<td width="76" style="color:#606060;">{html.escape(timestamp)}</td>'
        f'<td style="color:#CCCCCC;">{_message_html(message)}</td>'
        f'<td align="right" style="color:#606060;text-decoration:underline;">'
        f'{html.escape(source)}</td></tr></table>')


class _BufferHandler(logging.Handler):
    """A logging handler that appends formatted HTML lines to a QTextEdit.

    Created once and attached to the root logger; lives for the whole session.
    Keeps at most ``max_blocks`` lines so memory stays bounded."""

    def __init__(self, target, max_blocks=2000):
        super().__init__()
        self._target = target
        self._max = max_blocks

    def emit(self, record):
        try:
            ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
            line = _log_line_html(ts, record.levelname, record.getMessage(),
                                  f"{record.filename}:{record.lineno}")
            cursor = self._target.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertHtml(line + "<br>")
            # Trim old blocks if the document grew too large.
            doc = self._target.document()
            if doc.blockCount() > self._max:
                cursor.movePosition(QTextCursor.MoveOperation.Start)
                cursor.movePosition(QTextCursor.MoveOperation.Down,
                                    QTextCursor.MoveMode.KeepAnchor,
                                    doc.blockCount() - self._max)
                cursor.removeSelectedText()
            self._target.setTextCursor(cursor)
            self._target.ensureCursorVisible()
        except Exception:
            # A logging handler must never raise.
            pass


class LogPage(Page):
    """Sidebar page: a live, colour-coded console of the app's log output."""

    # Class-level so we attach the handler exactly once even if the page is
    # rebuilt on theme switch.
    _handler = None

    def __init__(self, state):
        super().__init__(state)
        title = QLabel("📋 Žurnál (Log)")
        title.setStyleSheet("font-size: 22px; font-weight: 800; color: #34D399; margin-bottom: 8px;")
        self.layout.addWidget(title)

        sub = QLabel("Živý výpis logov aplikácie — rovnaké ako v ultrapilot.log.")
        sub.setStyleSheet("color: #9AA4B2; font-size: 13px; margin-bottom: 12px;")
        sub.setWordWrap(True)
        self.layout.addWidget(sub)

        # Toolbar: clear + auto-scroll toggle + level filter (cosmetic).
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.clear_btn = QPushButton("🗑 Vyčistiť")
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.clicked.connect(self._clear)
        bar.addWidget(self.clear_btn)
        self.scroll_btn = QPushButton("⬇ Auto-scroll: ZAP")
        self.scroll_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.scroll_btn.setCheckable(True)
        self.scroll_btn.setChecked(True)
        self.scroll_btn.clicked.connect(self._toggle_scroll)
        bar.addWidget(self.scroll_btn)
        bar.addStretch()
        wrap = self._row_wrap(bar)
        self.layout.addWidget(wrap)

        # The console itself — always dark for readability regardless of theme.
        self.view = QTextEdit()
        self.view.setReadOnly(True)
        self.view.setFont(QFont("Consolas", 10))
        self.view.document().setMaximumBlockCount(2000)
        self.view.setStyleSheet(
            "QTextEdit{background:#0C0C0C; color:#CCCCCC; border:1px solid #30363D;"
            " border-radius:10px; padding:8px;}")
        self.layout.addWidget(self.view, stretch=1)

        self._auto_scroll = True
        self._traceback_lines = []
        # All plugins run in separate processes. A logging.Handler attached to
        # this UI process cannot see their records, so tail the shared file that
        # every process writes instead.
        from core.paths import app_dir
        self._log_file = os.path.join(app_dir(), "ultrapilot.log")
        self._log_pos = 0
        self._discard_partial = False
        try:
            size = os.path.getsize(self._log_file)
            self._log_pos = max(0, size - 96_000)
            self._discard_partial = self._log_pos > 0
        except OSError:
            pass
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_file)
        self._poll_timer.start(250)
        self._poll_file()

    def _poll_file(self):
        try:
            size = os.path.getsize(self._log_file)
            if size < self._log_pos:
                self._log_pos = 0
                self._discard_partial = False
            if size == self._log_pos:
                return
            with open(self._log_file, "r", encoding="utf-8", errors="replace") as stream:
                stream.seek(self._log_pos)
                if self._discard_partial:
                    stream.readline()  # discard a possibly partial first line
                    self._discard_partial = False
                lines = stream.readlines()
                self._log_pos = stream.tell()
        except (OSError, ValueError):
            return
        pattern = re.compile(
            r"^(?:\d{4}-\d{2}-\d{2} )?(?P<time>\d{2}:\d{2}:\d{2}),\d+\s+"
            r"(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL)\s+(?P<src>\S+)\s+(?P<msg>.*)$")
        cursor = self.view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        metadata = re.compile(r"^\[source:(?P<source>[^\]\r\n]+)\]\s*")
        for raw in lines:
            line = raw.rstrip("\r\n")
            match = pattern.match(line)
            if match and self._traceback_lines:
                cursor.insertHtml(_traceback_html(self._traceback_lines))
                self._traceback_lines.clear()
            if line.startswith("Traceback (most recent call last)"):
                self._traceback_lines = [line]
                continue
            if self._traceback_lines:
                self._traceback_lines.append(line)
                if ((line and not line.startswith(" ") and not line.startswith("During "))
                        or len(self._traceback_lines) >= 200):
                    cursor.insertHtml(_traceback_html(self._traceback_lines))
                    self._traceback_lines.clear()
                continue
            if match:
                item = match.groupdict()
                location = metadata.search(item["msg"])
                message = item["msg"][location.end():] if location else item["msg"]
                source = location.group("source") if location else ""
                if message.startswith("Please wait for map to load"):
                    rendered = '<span style="color:#D7AF00;">' + html.escape(message) + '</span><br>'
                else:
                    rendered = _log_line_html(item["time"], item["level"], message, source)
            else:
                rendered = f'<span style="color:#7B8491;">{html.escape(line)}</span><br>'
            cursor.insertHtml(rendered)
        self.view.setTextCursor(cursor)
        if self._auto_scroll:
            self.view.ensureCursorVisible()

    def _row_wrap(self, layout):
        from PyQt6.QtWidgets import QWidget
        w = QWidget()
        w.setObjectName("Panel")
        w.setStyleSheet("background: transparent;")
        w.setLayout(layout)
        return w

    def _clear(self):
        self.view.clear()

    def _toggle_scroll(self):
        self._auto_scroll = self.scroll_btn.isChecked()
        self.scroll_btn.setText("⬇ Auto-scroll: ZAP" if self._auto_scroll
                                else "⬇ Auto-scroll: VYP")
