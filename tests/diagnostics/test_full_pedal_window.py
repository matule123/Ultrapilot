"""Exact full-window writes, independent of the intentionally short safety journal."""
import threading
import time
from unittest.mock import patch

from core.navigation.longitudinal_diagnostics import PedalJournal
from tests.test_pedal_decision_history import bound


def test_short_pedal_source_reuses_only_the_identical_consumed_decision(monkeypatch):
    from core.navigation import longitudinal_diagnostics as d

    journal = PedalJournal()
    journal.enabled = True
    journal._incident_window = d._IncidentWindow(32 * 1024 * 1024, deferred=True, simple_records=True)
    monkeypatch.setattr(d, 'diagnostic_build_limits', lambda: {'approved': True})
    clock = [100.]
    monkeypatch.setattr(d.time, 'monotonic', lambda: clock[0])
    original = d.freeze_primitive_record
    calls = []

    def freeze(value, **kwargs):
        record = original(value, **kwargs)
        calls.append(record)
        return record

    monkeypatch.setattr(d, 'freeze_primitive_record', freeze)
    journal.begin_decision()
    consumed = journal.observe_incident('consumer_traffic', {'packet': {'frame': 42}}, clock[0])
    value = dict(sdk_frame_us=42, selected=dict(throttle=.2, brake=0.))
    calls.clear()
    journal.bind(value)
    assert len(calls) == 2
    source = journal._local.source
    assert source is not calls[0] and source['blob'] is calls[0]['blob']
    assert 'journal_compaction_pending' not in calls[0]
    assert d.restore_exact_record(source) == value
    journal.record('throttle', .2, clock[0], clock[0], 'SCS_SDK', {'value': .2})
    rows = journal._incident_window.rolling_snapshot()['records']
    binding = next(row for row in rows if row['kind'] == 'pedal_binding')
    backend = next(row for row in rows if row['kind'] == 'backend_call')
    assert backend['value']['decision_reference'] == [binding['stream_id'], binding['sequence']]
    assert binding['value'] == dict(value, consumed_input_references={'consumer_traffic': consumed})

    clock[0] += .01  # A sampled-away full decision still gets its own short source.
    calls.clear()
    journal.bind(value)
    assert len(calls) == 2
    assert d.restore_exact_record(journal._local.source) == value

    clock[0] += .1
    calls.clear()
    journal.bind(dict(value, intervention={'reason': 'stop'}))
    assert len(calls) == 3
    assert 'intervention' in d.restore_exact_record(calls[0])
    assert d.restore_exact_record(journal._local.source) == value

    clock[0] += .1
    journal.bind(dict(value, extra=bytes(33 * 1024)))
    assert journal._local.source == {'snapshot_status': 'UNVERIFIED_SNAPSHOT_BUDGET_EXCEEDED'}


def test_full_window_retains_each_call_and_exact_binding_after_short_journal_eviction():
    # Retired Engine fixtures contain cycles; do not make this one-window
    # retention test accidentally exercise the separate 16-live-window gate.
    import gc
    gc.collect()
    journal=PedalJournal();journal.enabled=True;journal.enable_incident_window()
    expected=[]
    for i in range(1201):
        t=100+i*.05
        with patch('time.monotonic',return_value=t):
            bound(journal,t,.2 if i%3 else 0.,0. if i%3 else .3,
                identity='session' if i<1000 else 'new-session',error=i==1100)
        if i==800:
            journal._incident_window.pending=None  # New warm episode, after startup evidence.
            journal.incident_event('BRAKE',{'reason':'red'},t)
        if i>=200:expected.extend([(2*i+1,'throttle',t),(2*i+2,'brake',t)])
    window=journal.seal_incident(160.001,shutdown=True)
    calls=[r for r in window['records'] if r['kind']=='backend_call']
    assert [(r['value']['sequence'],r['value']['channel'],r['value']['call_started_at_s']) for r in calls]==expected
    sources={(r['stream_id'],r['sequence']):r for r in window['records'] if r['kind']=='pedal_binding'}
    for row in calls:
        call=row['value'];source=sources[tuple(call['decision_reference'])]['value']
        assert source['sdk_frame_us']==int(call['call_started_at_s']*1e6)
        assert source['observation_timestamp']==call['call_started_at_s']-.01
        assert call['game_consumption_verified'] is False
    assert any(r['value']['error']=='OSError' for r in calls)
    assert journal.snapshot()['dropped_events']>0
    assert window['capacity_drops']==window['capture_failures']==0
    assert journal.incident_status()['retained_bytes']<=32*1024*1024


def test_large_input_compression_never_runs_on_caller_thread():
    import core.navigation.longitudinal_diagnostics as d
    journal=PedalJournal();journal.enabled=True;journal.enable_incident_window()
    original=d.zlib.compress;calls=[];caller=threading.get_ident()
    def compress(*args,**kwargs):
        calls.append(threading.get_ident())
        return original(*args,**kwargs)
    with patch.object(d.zlib,'compress',compress):
        journal.observe_incident('traffic',{'moving':bytes(range(256))*256},100.)
        deadline=time.perf_counter()+2.
        while not calls and time.perf_counter()<deadline:time.sleep(.001)
    assert calls and caller not in calls
    assert journal._incident_window.rolling_snapshot()['records'][0]['value']['moving']==bytes(range(256))*256


def test_gear_transition_event_silence_is_not_a_missing_periodic_frame():
    from core.navigation.longitudinal_diagnostics import _IncidentWindow
    ring=_IncidentWindow(32*1024*1024)
    for i in range(402):ring.observe('ego',{'frame':i},100+i*.1)
    ring.observe('drive_boundary',{'gear':4},100.)
    ring.observe('drive_boundary',{'gear':0},135.)
    ring.event('WAIT',{'reason':'red'},130.)
    saved=ring.seal(140.1)
    assert not saved['incomplete']
    assert 'drive_boundary' not in saved['sampling']['gaps']


def test_pedal_detail_missing_binding_cannot_be_complete():
    from core.steering_replay import _window_pedal_detail
    result=_window_pedal_detail({'records':[{'kind':'backend_call','value':dict(
        sequence=1,channel='brake',call_started_at_s=1.,call_returned_at_s=1.001,
        decision_reference=['missing',1])}]})
    assert result['incomplete'] and result['missing_decision_references']==1


def test_each_actually_consumed_packet_is_retained_between_periodic_samples():
    j=PedalJournal();j.enabled=True;j.enable_incident_window();j.begin_decision()
    for i in range(3):
        j.observe_incident('consumer_traffic',dict(packet=dict(valid=True,
            sdk_frame_us=i+1,traffic_brake=.1+i*.01)),100+i*.01)
    rows=j._incident_window.rolling_snapshot()['records']
    assert [r['value']['packet']['sdk_frame_us'] for r in rows]==[1,2,3]
    assert j._local.input_references['consumer_traffic']==[rows[-1]['stream_id'],rows[-1]['sequence']]


def test_exact_repeated_packet_is_shared_but_each_read_keeps_original_time():
    j=PedalJournal();j.enabled=True;j.enable_incident_window()
    j._incident_window.simple_records=False  # Exercise the legacy shared-envelope codec.
    packet=dict(frame=42,observed_at=100.,moving=bytes(range(256))*128)
    for i in range(801):
        j.observe_incident('consumer_traffic',dict(packet=packet,
            read_started_at=100+i*.05),100+i*.05)
    rows=j._incident_window.rolling_snapshot(packed=True)['records']
    assert len(rows)==801
    bodies=[r['value']['inputs']['packet'] for r in rows]
    assert len({id(body) for body in bodies})==1
    saved=j._incident_window.rolling_snapshot()['records']
    assert [r['value']['read_started_at'] for r in saved]==[100+i*.05 for i in range(801)]
    assert all(r['value']['packet']==packet for r in saved)
    assert j.incident_status()['retained_bytes']<2*1024*1024
    packet['frame']=43
    j.observe_incident('consumer_traffic',dict(packet=packet),140.01)
    after=j._incident_window.rolling_snapshot()['records']
    assert after[-2]['value']['packet']['frame']==42 and after[-1]['value']['packet']['frame']==43


def test_equal_ipc_copies_share_storage_despite_different_python_reference_counts():
    import copy
    j=PedalJournal();j.enabled=True;j.enable_incident_window()
    j._incident_window.simple_records=False
    packet=dict(context=[7,'session','map'],sdk_frame_us=42,
        following=dict(target_id='a'),values=[[1,2]]*120,raw=bytes(range(256))*8)
    j.observe_incident('consumer_traffic',dict(packet=packet),100.)
    for i in range(1,4):
        # IPC deepcopy changes Python reference counts/intern flags, not the
        # actual fields. Those implementation details are not new evidence.
        duplicate=copy.deepcopy(packet)
        j.observe_incident('consumer_traffic',dict(packet=duplicate),100+i*.01)
    rows=j._incident_window.rolling_snapshot(packed=True)['records']
    assert len({id(r['value']['inputs']['packet']) for r in rows})==1
    assert all(r['value']['packet']==packet for r in j._incident_window.rolling_snapshot()['records'])


def test_nested_consumed_input_retains_independent_exact_records_without_rewriting_rows():
    import copy
    j=PedalJournal();j.enabled=True;j.enable_incident_window()
    # The approved bounded standalone-record design deliberately does not
    # intern arbitrary nested subtrees (see the simple-record proposal).
    j._incident_window.simple_records=True
    following=dict(target_id='a',witnesses=[dict(id=i,position=[i,2.,3.],
        bodies=[dict(dimensions=[2.,3.,8.],xyz=[i,2.,3.])]*4) for i in range(40)])
    traffic=dict(frame=42,following=following,signal=dict(id=3,color='red'))
    j.observe_incident('consumer_traffic',dict(packet=traffic),100.)
    binding=dict(inputs=dict(traffic=copy.deepcopy(traffic)),sdk_frame_us=42)
    j.observe_incident('pedal_binding',binding,100.01)
    rows=j._incident_window.rolling_snapshot(packed=True)['records']
    assert len(rows)==2
    assert all(r['value'].get('record_codec') for r in rows)
    saved=j._incident_window.rolling_snapshot()['records']
    assert saved[0]['value']==dict(packet=traffic) and saved[1]['value']==binding
    traffic['following']['witnesses'][0]['position'][0]=-999
    binding['inputs']['traffic']['signal']['color']='green'
    again=j._incident_window.rolling_snapshot()['records']
    assert again==saved
    assert j.incident_status()['retained_bytes']<=j._incident_window.limit
