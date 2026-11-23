"""Recorded summary overflow and bounded AP rotations, no control changes."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest


def test_recorded_summary_values_fit_existing_retained_budget_losslessly():
    from core.navigation.longitudinal_diagnostics import _DecisionHistory, expand_history
    rows=json.loads((Path(__file__).parent.parent/'fixtures/oct29-history-overflow.json').read_text(encoding='utf-8'))
    h=_DecisionHistory()
    for saved in rows:
        h._append(saved['kind'],saved['at_s'],saved['row'],dict(context=None,route_identity=None))
    assert h.failures==0
    restored=expand_history(h.snapshot())['regular_samples']
    assert len(restored)==len(rows)
    for original,actual in zip(rows,restored):
        for field,value in original['row'].items():
            if field in actual:assert actual[field]==value
    assert h.snapshot()['retained_bytes']<=h.MAX_BYTES


def test_second_disable_rotation_retains_both_original_ap_streams(monkeypatch):
    import core.navigation.longitudinal_diagnostics as d
    from core.steering_replay import SteeringReplayBuffer
    def ring(at,frame):
        r=d._IncidentWindow(32*1024*1024)
        r.observe('ap_decision',dict(frame=frame),at,force=True)
        return r
    first=ring(100.,1);second=ring(101.,2);third=ring(102.,3)
    replay=SteeringReplayBuffer(2);replay._diagnostic_inputs=first
    plugin=SimpleNamespace(_steering_replay=replay,_replay_export_writer=SimpleNamespace(status={'busy':True}))
    owner=d.AutopilotIncidentParts(plugin)
    monkeypatch.setattr(d.time,'monotonic',lambda:102.)
    replay._diagnostic_inputs=second;owner.end()
    replay._diagnostic_inputs=third;owner.end()
    kept=owner.retired_ring.rolling_snapshot(packed=False)
    assert {r['value']['frame'] for r in kept['records']}=={1,2}
    assert not kept['capture_failures']
    assert kept['retained_bytes']<=32*1024*1024


def test_capture_failure_keeps_bounded_operation_cause():
    from core.navigation.longitudinal_diagnostics import _DecisionHistory
    h=_DecisionHistory()
    for _ in range(20):h._append('regular',100.,{'reason':'x'*40000},{})
    saved=h.snapshot()
    assert saved['capture_failures']==20 and saved['incomplete']
    assert len(saved['failure_reasons'])<=8
    assert saved['failure_reasons'][0]['operation']=='summary_encode'
