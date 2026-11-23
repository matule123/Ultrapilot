"""Explicit budget approval changes diagnostic bounds, never control authority."""
import sys
from types import SimpleNamespace
import pytest


def config(monkeypatch,approved):
    monkeypatch.setitem(sys.modules,'core.navigation.diagnostic_build_config',
        SimpleNamespace(ENABLED=True,SIMPLE_RECORDS=True,MEMORY_BUDGET_APPROVED=approved))


@pytest.mark.parametrize('approved',[False,True])
def test_exact_approved_limits_and_owner_defaults(monkeypatch,approved):
    config(monkeypatch,approved)
    from core.navigation.longitudinal_diagnostics import diagnostic_build_limits,PedalJournal,_IncidentWindow
    from core.steering_replay import SteeringReplayBuffer
    limits=diagnostic_build_limits()
    assert limits['engine_ring_bytes']==(64 if approved else 32)*1048576
    assert limits['engine_file_bytes']==(32 if approved else 16)*1048576
    assert limits['export_child_rss_bytes']==(1536 if approved else 512)*1048576
    assert limits['additional_family_rss_bytes']==(2048*1048576 if approved else None)
    journal=PedalJournal();journal.enable_incident_window()
    assert journal.incident_status()['byte_limit']==limits['engine_ring_bytes']
    ap=SteeringReplayBuffer(2)
    assert ap._diagnostic_inputs.status()['byte_limit']==32*1048576
    with pytest.raises(ValueError,match='INCIDENT_MEMORY_BUDGET'):
        _IncidentWindow(limits['engine_ring_bytes']+1)
    if not approved:
        with pytest.raises(ValueError,match='INCIDENT_MEMORY_BUDGET'):_IncidentWindow(64*1048576)


def test_approved_rss_ceiling_terminates_export_without_attesting_success(monkeypatch):
    config(monkeypatch,True)
    import multiprocessing,psutil
    import core.steering_replay as replay
    class Child:
        pid=123
        alive=True
        closed=False
        def start(self):pass
        def is_alive(self):return self.alive
        def terminate(self):self.alive=False
        def join(self,*args):pass
        def close(self):self.closed=True
    child=Child();channel=SimpleNamespace(close=lambda:None,poll=lambda timeout:False)
    monkeypatch.setattr(multiprocessing,'get_context',lambda mode:SimpleNamespace(
        Pipe=lambda **kw:(channel,channel),Process=lambda **kw:child))
    monkeypatch.setattr(psutil,'Process',lambda pid:SimpleNamespace(
        memory_info=lambda:SimpleNamespace(rss=1536*1048576+1)))
    with pytest.raises(MemoryError,match='INCIDENT_EXPORT_WORKER_RSS_BUDGET'):
        replay._run_admitted_diagnostic_export(lambda *args:None,())
    assert not child.alive and child.closed
