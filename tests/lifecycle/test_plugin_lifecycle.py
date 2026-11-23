import threading
from types import SimpleNamespace
from unittest.mock import Mock
import pytest

from core.plugin_manager import PluginManager, plugin_worker, _shutdown_transport_error
from tests.test_control_safety_regressions import State


def manager(monkeypatch):
    state=State({})
    engine=SimpleNamespace(shared_state=state,settings={},running=True)
    m=PluginManager(engine)
    m.plugins['drivepolicy']=dict(process=Mock(is_alive=Mock(return_value=False),exitcode=1),
        stop_event=threading.Event(),version='1.1.3',**{'class':object})
    m._spawn=Mock()
    return m,state


def test_data_keyerror_is_not_manager_shutdown():
    assert not _shutdown_transport_error(KeyError('x'))


def test_supervision_cannot_spawn_after_ui_shutdown(monkeypatch):
    m,state=manager(monkeypatch)
    state.set('app_shutdown_requested',True)
    m.tick(.01)
    m._spawn.assert_not_called()


def test_live_disable_is_not_a_crash_restart(monkeypatch):
    m,state=manager(monkeypatch)
    state.set('plugin_enabled.drivepolicy',False)
    m.tick(.01)
    m._spawn.assert_not_called()


def test_repeated_crash_is_bounded_and_backed_off(monkeypatch):
    m,state=manager(monkeypatch)
    clock=[0.]
    monkeypatch.setattr('core.plugin_manager.time.monotonic',lambda:clock[0])
    for _ in range(400):
        m.tick(.01);clock[0]+=.01
    assert m._spawn.call_count<=3
    assert m._spawn.call_count>0
    assert state.get('plugin_health.drivepolicy')['first_failure']['exitcode']==1


def test_delayed_child_does_not_initialize_after_shutdown(monkeypatch):
    started=[]
    class Worker:
        enabled=True
        def __init__(self,sdk): pass
        def on_start(self): started.append(True)
        def on_stop(self): pass
    event=threading.Event();event.set()
    monkeypatch.setattr('core.logger.setup',lambda **kw:None)
    plugin_worker(Worker,'drivepolicy',{'app_shutdown_requested':True},event)
    assert not started


def test_worker_preserves_actual_failure_and_revokes_policy(monkeypatch):
    class Worker:
        enabled=True
        def __init__(self,sdk): self.sdk=sdk
        def on_start(self): self.sdk.set('longitudinal_policy_active',True)
        def on_tick(self,dt): raise KeyError('missing actor x')
        def on_stop(self): self.sdk.set('longitudinal_policy_active',False)
    monkeypatch.setattr('core.logger.setup',lambda **kw:None)
    monkeypatch.setattr('core.plugin_manager.time.sleep',lambda _:None)
    state={'longitudinal_policy':{'old':True}}
    with pytest.raises(SystemExit): plugin_worker(Worker,'drivepolicy',state,threading.Event())
    assert state['plugin_exit.drivepolicy']['first_failure']['type']=='KeyError'
    assert state['longitudinal_policy'] is None
    assert state['longitudinal_policy_active'] is True


def test_spawn_rechecks_shutdown_before_start(monkeypatch):
    m,state=manager(monkeypatch)
    state.raw=state.values  # real SharedState exposes its managed dictionary
    del m._spawn
    proc=Mock(pid=99)
    def make(**kwargs):
        state.set('app_shutdown_requested',True)
        return proc
    monkeypatch.setattr('core.plugin_manager.mp.Process',make)
    m._spawn('drivepolicy')
    proc.start.assert_not_called()
    assert m.plugins['drivepolicy']['stop_event'].is_set()


def test_failed_policy_stays_required_at_physical_gate():
    from core.plugin_manager import _revoke_producer
    from tests.test_longitudinal_arbitration import strict_flow
    from tests.test_activation_observation_binding import flow
    gen=flow.__wrapped__();source=next(gen)
    try:
        state,truck,engine,ap,update,n,clock,acc=strict_flow(source)
        update(4,4.);n();update(4,4.);ap.on_tick(.05)
        _revoke_producer(state.values,'drivepolicy',required=True)
        ap.on_tick(.05);engine._flush_controls()
        assert state.get('longitudinal_policy') is None
        assert state.get('ctl_throttle')==0.
    finally: gen.close()


def test_spawn_never_attributes_previous_exit_to_new_process(monkeypatch):
    m,state=manager(monkeypatch);state.raw=state.values
    del m._spawn
    state.set('plugin_exit.drivepolicy',{'reason':'disabled','first_failure':None})
    proc=Mock(pid=99,is_alive=Mock(return_value=True))
    monkeypatch.setattr('core.plugin_manager.mp.Process',lambda **kwargs:proc)
    m._spawn('drivepolicy')
    assert state.get('plugin_exit.drivepolicy') is None
    proc.start.assert_called_once()
