"""Existing combined worker owns pedal expansion; control offers owned bytes."""
import threading
import time
from unittest.mock import patch
import pytest

from tests.test_activation_observation_binding import flow


@pytest.mark.parametrize('mode',[0,3])
def test_engine_does_not_expand_pedals_on_control_thread(flow,mode):
    from tests.signals.test_signal_lifecycle import lifecycle
    import core.navigation.longitudinal_diagnostics as journal_module
    from core.navigation.evidence_diagnostics import _jsonable
    state,truck,engine,ap,tick,n,clock,writes,collected=lifecycle(flow,mode)
    original=journal_module.expand_journal;caller=threading.get_ident()
    def expand(value):
        assert threading.get_ident()!=caller,'combined expanded the journal on the controller'
        return original(value)
    with patch.object(journal_module,'expand_journal',expand):tick(4,4.,color=8)
    capture=collected.samples[-1]
    result=[]
    worker=threading.Thread(target=lambda:result.append(_jsonable(capture.longitudinal)))
    worker.start();worker.join(2.)
    assert not worker.is_alive() and result
    assert result[0]['events'] and result[0]['sampled_state']['autopilot_active']
    assert all(e['call_started_at_s']<=e['call_returned_at_s'] for e in result[0]['events'])
    assert not any(ch=='parkingbrake' for _,ch,_,_ in writes)


def test_deferred_snapshot_survives_source_mutation_and_has_identical_json():
    from core.navigation.longitudinal_diagnostics import PedalJournal,expand_journal
    from core.navigation.evidence_diagnostics import capture_diagnostic_application,_jsonable
    from tests.test_pedal_decision_history import bound
    journal=PedalJournal();journal.enabled=True
    with patch('time.monotonic',return_value=100.):bound(journal,100.,.2,0.)
    packed=journal.snapshot(expanded=False)
    expected=_jsonable(expand_journal(packed))
    capture=capture_diagnostic_application({},0.,100.,1,longitudinal=packed)
    packed['events'][0]['backend']['value']=999.
    packed['events'].clear()
    actual=_jsonable(capture.longitudinal)
    sampled=actual.pop('sampled_state')
    assert actual==expected and sampled['activation'] is None
    assert actual['events'][0]['backend']['value']!=999.


def test_full_worker_does_not_advance_engine_cursor_and_retry_keeps_writes(flow):
    from tests.signals.test_signal_lifecycle import lifecycle
    state,truck,engine,ap,tick,n,clock,writes,collected=lifecycle(flow,0)
    cursor=engine._combined_pedal_cursor
    original=collected.offer
    collected.offer=lambda capture:False
    tick(4,4.,color=8)
    assert engine._combined_pedal_cursor==cursor
    collected.offer=original
    tick(4,4.,color=8)
    events=collected.samples[-1].longitudinal['events']
    assert events[0]['sequence']==cursor+1
    assert engine._combined_pedal_cursor==events[-1]['sequence']


def test_existing_bounded_worker_normalizes_in_order_and_reports_overload(tmp_path):
    from core.navigation.evidence_diagnostics import EvidenceDiagnosticCollector,_jsonable
    from dataclasses import replace
    from core.navigation.longitudinal_diagnostics import PedalJournal
    from tests.test_pedal_decision_history import bound
    from core.navigation.evidence_diagnostics import capture_diagnostic_application
    journal=PedalJournal();journal.enabled=True
    with patch('time.monotonic',return_value=100.):bound(journal,100.,0.,.3)
    capture=capture_diagnostic_application({},0.,100.,1,longitudinal=journal.snapshot(expanded=False))
    worker=EvidenceDiagnosticCollector(tmp_path/'evidence-diagnostics')
    entered=threading.Event();release=threading.Event();done=threading.Event();seen=[];threads=[]
    def ingest(value):
        entered.set();assert release.wait(3.)
        threads.append(threading.get_ident());seen.append((value.sequence,_jsonable(value.longitudinal)))
        if len(seen)==2:done.set()
    worker._ingest=ingest;worker.start()
    try:
        assert worker.offer(capture) and entered.wait(2.)
        assert worker.offer(replace(capture,sequence=2))
        start=time.perf_counter();assert worker.offer(replace(capture,sequence=3)) is False
        assert time.perf_counter()-start<.1
        assert worker._queue.maxsize==1 and worker.status()['dropped_samples']==1
        release.set();assert done.wait(3.)
        assert [v[0] for v in seen]==[1,2]
        assert seen[0][1]==seen[1][1] and all(t!=threading.get_ident() for t in threads)
    finally:release.set();worker.close(3.)
