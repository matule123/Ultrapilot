"""Exercise the whole card's Qt callbacks, not just the DEV scene renderer."""
import os
import subprocess
import sys

import pytest

from ui.visualization import _map_point_xz


@pytest.mark.parametrize('point,expected', [
    ([12., 9., 34.], (12., 34.)),
    ([12., 34.], (12., 34.)),
    ([12., float('nan'), 34.], (12., 34.)),
    (None, None), ([1.], None), ([float('inf'), 2.], None),
    (['bad', 2., 3.], None),
])
def test_map_point_formats(point, expected):
    assert _map_point_xz(point) == expected


@pytest.mark.parametrize('dev', [False, True])
def test_complete_visualization_opens_with_production_xyz_path(dev):
    code = '''
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from ui.visualization import VisualizationPage
class State:
    def __init__(self):
        self.d = dict(truck_world_pos=(34800., 45200.), truck_heading=0.,
            nav_path=[[34800.,8.,45200.],[34800.,8.,45180.]],
            traffic=[], dev_hud_enabled=DEV)
    def get(self,k,d=None): return self.d.get(k,d)
    def set(self,k,v): self.d[k]=v
app=QApplication([])
errors=[]
sys.excepthook=lambda t,v,tb: errors.append(str(v))
p=VisualizationPage(State());p.resize(1100,800);p.show()
QTimer.singleShot(250,app.quit)
app.exec()
assert not errors, errors
assert not getattr(p.top_down,'_paint_failed',False)
p.timer.stop();p.hud_preview.timer.stop();p.close()
'''.replace('DEV', repr(dev))
    result = subprocess.run([sys.executable, '-c', code],
        env=dict(os.environ, QT_QPA_PLATFORM='offscreen', PYTHONCASEOK='1'),
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_top_down_callback_contains_and_logs_failure(monkeypatch, caplog):
    from PyQt6.QtWidgets import QApplication
    from ui.visualization import _TopDown
    app = QApplication.instance() or QApplication([])
    widget = _TopDown(None)
    def fail(event):
        raise ValueError('broken presentation input')
    monkeypatch.setattr(widget, '_paint', fail)
    widget.paintEvent(None)
    widget.paintEvent(None)
    assert widget._paint_failed
    assert caplog.text.count('Visualization map paint failed') == 1
    monkeypatch.setattr(widget, '_paint', lambda event: None)
    widget.paintEvent(None)
    assert not widget._paint_failed
    widget.close()
