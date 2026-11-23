"""Narrow diagnostic-only attribution, exactness and critical-section checks."""
import threading


def test_ring_entry_allocation_is_outside_the_shared_lock(monkeypatch):
    import core.navigation.longitudinal_diagnostics as d
    ring=d._IncidentWindow(1024*1024,deferred=True,simple_records=True)
    original=d._WindowEntry.__init__
    def allocate(self,value):
        assert ring.lock.acquire(False),'GC-capable record allocation inside the diagnostic ring lock'
        ring.lock.release()
        return original(self,value)
    monkeypatch.setattr(d._WindowEntry,'__init__',allocate)
    ring.observe('ego',dict(frame=42,raw=b'original'),100.,force=True)
    saved=ring.rolling_snapshot()
    assert saved['records'][0]['value']==dict(frame=42,raw=b'original')


def test_legacy_shared_fields_are_charged_and_released_only_once():
    import core.navigation.longitudinal_diagnostics as d
    ring=d._IncidentWindow(1024*1024,deferred=True,simple_records=False)
    ring.exact_consumers=True
    same=dict(raw=bytes(range(256))*8)
    ring.observe('consumer_traffic',dict(packet=same,other=same),100.,force=True)
    inputs=ring.row_inputs(ring.rows[0][0]);assert len(inputs)==1
    with ring.lock:ring.drop_entry(ring.rows.popleft())
    assert ring.bytes==0
    assert all(shared.uses==0 for shared in inputs)


def test_json_normalization_does_not_reflect_on_primitive_scalars(monkeypatch):
    import core.navigation.evidence_diagnostics as d
    original=d.is_dataclass
    def reflect(value):
        assert not isinstance(value,(str,bool,int,float)) and value is not None
        return original(value)
    monkeypatch.setattr(d,'is_dataclass',reflect)
    assert d._jsonable({'x':[None,True,1,1.,'value']})=={'x':[None,True,1,1.,'value']}


def test_repeated_owned_pedal_source_expands_once_but_outputs_stay_detached(monkeypatch):
    import core.navigation.longitudinal_diagnostics as d
    original=dict(context=['original'],sdk_frame_us=42,observation_timestamp=100.,
        actual_speed_mps=3.,requested=dict(throttle=.2,brake=0.))
    packed=d.pack_source(d.pack_journal_inputs(d.compact_decision(original)))
    journal=dict(events=[dict(sequence=i,source=packed,intervention=None,
        call_started_at_s=100.+i*.01,call_returned_at_s=100.001+i*.01) for i in (1,2)])
    expand=d.expand_decision;calls=[]
    def decoded(value,*a,**kw):calls.append(value);return expand(value,*a,**kw)
    monkeypatch.setattr(d,'expand_decision',decoded)
    restored=d.expand_journal(journal)
    assert len(calls)==1
    assert restored['events'][0]['source']==restored['events'][1]['source']
    restored['events'][0]['source']['context'][0]='changed'
    assert restored['events'][1]['source']['context']==['original']
    assert restored['events'][1]['call_started_at_s']==100.02


def test_temporary_journal_bind_does_not_prepare_json_or_compress(monkeypatch):
    import core.navigation.longitudinal_diagnostics as d
    from unittest.mock import patch
    import pytest
    if not d.diagnostic_build_limits()['approved']:pytest.skip('Approved exact candidate required')
    value=dict(context=['original'],sdk_frame_us=42,observation_timestamp=100.,
        actual_speed_mps=3.,requested=dict(throttle=.2,brake=0.))
    expected=d.expand_decision(d.unpack_source(d.pack_source(d.pack_journal_inputs(d.compact_decision(value)))))
    journal=d.PedalJournal();journal.enabled=True
    def forbidden(*a,**kw):raise AssertionError('legacy JSON/compression on control caller')
    with patch.object(d.json,'dumps',forbidden),patch.object(d.zlib,'compressobj',forbidden),patch.object(d,'compact_decision',forbidden):
        journal.bind(value)
    assert journal.source()==expected
    assert journal._local.source.get('record_codec')=='pickle5-primitives-v1'
    assert journal._local.size<=32768+16384
