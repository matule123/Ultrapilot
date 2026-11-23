"""Qualification probes must not duplicate the Manager child census in-host."""
from types import SimpleNamespace


def test_supervised_daemon_explicitly_delegates_only_child_census(monkeypatch):
    import tools.qualify_oct25_traffic_capture as q
    import core.steering_replay as r
    calls=[];sent=[]
    monkeypatch.setattr(r,'configure_diagnostic_export',lambda state:None)
    monkeypatch.setattr(q,'run',lambda **kw:calls.append(kw) or {'host_rss_still_sampled':True})
    q._daemon_qualification({'mode':0},{},SimpleNamespace(send=sent.append,close=lambda:None))
    assert calls==[{'mode':0,'child_memory_external':True}]
    assert sent==[{'result':{'host_rss_still_sampled':True}}]


def test_external_census_cannot_be_selected_for_an_unsupervised_process(tmp_path):
    import pytest
    from tools.qualify_oct25_traffic_capture import run
    with pytest.raises(AssertionError,match='supervised daemon'):
        run(mode=0,enabled=False,count=40,trailers=3,ticks=1,
            directory=tmp_path/'invalid',child_memory_external=True)


def test_lock_probe_does_not_trigger_gc_inside_otherwise_empty_critical_section():
    import gc,threading
    from tools.qualify_oct25_traffic_capture import TimedLock
    raw=threading.Lock();probe=TimedLock(raw,[],[]);held_collections=[]
    def collection(phase,info):
        if phase!='start':return
        if raw.acquire(False):raw.release()
        else:held_collections.append(1)
    gc.collect();threshold=gc.get_threshold();gc.callbacks.append(collection)
    try:
        gc.set_threshold(1,100000,100000)
        for _ in range(100):
            with probe:pass
    finally:
        gc.set_threshold(*threshold);gc.callbacks.remove(collection)
    assert not held_collections,'measurement wrapper itself collected under the measured lock'
