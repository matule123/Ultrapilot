"""Export-only regressions; no control behavior or record codec is changed."""
import hashlib
import json
import threading
import time
from unittest.mock import patch

import pytest

from core.steering_replay import _payload_hash


@pytest.mark.parametrize('payload',[
    {'unicode':'žltá 🟡','n':-0.,'flags':[True,False,None,1,1.]},
    {'records':[{'sequence':i,'at_s':100.+i*.05,'bytes':'00ff'*50} for i in range(400)],
     'integrity':{'ignored':'old'}},
    {'nested':{'keys':{'a':'\u0000\n','b':'quote"slash\\','z':2**100}},'empty':[]},
])
def test_hash_is_identical_to_original_streaming_canonical_json(payload):
    original=hashlib.sha256()
    value={k:v for k,v in payload.items() if k!='integrity'}
    for piece in json.JSONEncoder(ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).iterencode(value):
        original.update(piece.encode('utf-8'))
    assert _payload_hash(payload)==original.hexdigest()


def test_export_hash_does_not_walk_json_in_python_for_every_scalar():
    calls=[];original=json.JSONEncoder.iterencode
    def observed(self,value,_one_shot=False):
        calls.append(_one_shot)
        return original(self,value,_one_shot=_one_shot)
    with patch.object(json.JSONEncoder,'iterencode',observed):
        _payload_hash({'records':[{'sequence':i,'value':.2} for i in range(1000)]})
    assert calls==[True], 'canonical hash must use the same JSON bytes through the C encoder'


def test_parent_admission_serializes_export_jobs_without_running_child_work(tmp_path):
    import core.steering_replay as replay
    entered=[];release=threading.Event();attempting=threading.Event()
    def first():
        with replay._diagnostic_disk_lock(tmp_path,name='.diagnostic-export-admission.lock'):
            entered.append('AP');release.wait(2.)
    def second():
        attempting.set()
        with replay._diagnostic_disk_lock(tmp_path,name='.diagnostic-export-admission.lock'):
            entered.append('Engine')
    a=threading.Thread(target=first);a.start()
    deadline=time.perf_counter()+2.
    while not entered and time.perf_counter()<deadline:time.sleep(.001)
    b=threading.Thread(target=second);b.start();assert attempting.wait(1.)
    time.sleep(.04);assert entered==['AP']
    release.set();a.join(2.);b.join(2.)
    assert not a.is_alive() and not b.is_alive() and entered==['AP','Engine']


def test_missing_ap_part_uses_bounded_parent_wait_and_explicit_incomplete_export(tmp_path,monkeypatch):
    import core.steering_replay as replay
    request=dict(incident_id='a'*32+'-7')
    window=dict(required_autopilot_part=request,first_reason='original')
    passed=[];clock=iter([0.,21.])
    monkeypatch.setattr(replay.time,'perf_counter',lambda:next(clock))
    monkeypatch.setattr(replay,'_run_diagnostic_export',lambda target,args:passed.append(args) or 'partial')
    assert replay.export_incident_isolated(tmp_path,window,{})=='partial'
    assert passed[0][1]['ap_parent_wait_expired'] is True
    assert passed[0][1]['first_reason']=='original'
    assert 'ap_parent_wait_expired' not in window


def test_part_available_after_admission_wait_is_fully_validated_not_declared_missing(tmp_path,monkeypatch):
    from types import SimpleNamespace
    import core.steering_replay as replay
    import core.navigation.longitudinal_diagnostics as diagnostics
    incident_id='a'*32+'-9';(tmp_path/('ap-inputs-'+incident_id+'.json')).write_text('{}')
    window=dict(required_autopilot_part=dict(incident_id=incident_id),
        ap_parent_wait_expired=True,first_reason='original')
    checked=[];sent=[]
    monkeypatch.setattr(diagnostics,'expand_incident_window',lambda value:value)
    def validate(directory,value,*,wait_s):
        assert wait_s==0.,'an admitted child must not wait for its AP prerequisite'
        checked.append(value);return dict(verified=True,complete=True)
    monkeypatch.setattr(replay,'_await_autopilot_part',validate)
    def export(directory,value,journal):
        assert value['autopilot_part_result']['verified']
        result=tmp_path/'verified.json';result.write_text('{}');return str(result)
    monkeypatch.setattr(replay,'export_incident',export)
    replay._incident_export_child(str(tmp_path),window,{},SimpleNamespace(send=sent.append,close=lambda:None))
    assert len(checked)==1 and sent[0].get('integrity_valid') is True,sent


def test_packed_seal_defers_metadata_and_restores_identical_window():
    import gc
    from core.navigation.longitudinal_diagnostics import _IncidentWindow,expand_incident_window
    def filled():
        # Earlier Engine fixtures contain cycles. Reclaim retired windows
        # before exercising metadata, not the separate 16-window overload gate.
        gc.collect()
        ring=_IncidentWindow(32*1024*1024,deferred=True,simple_records=True)
        ring.session='same-test-session'
        for i in range(601):
            ring.observe('ego',dict(frame=i,observed_at=100+i*.1,raw=b'\x00\xff'*8),100+i*.1,force=True)
            if i==400:ring.event('BRAKE',dict(reason='original red',epoch=7),140.)
        assert ring.failures==0
        return ring
    expected=filled().seal(160.,packed=False)
    ring=filled()
    with patch('builtins.sorted',side_effect=AssertionError('history sort on control thread')):
        packed=ring.seal(160.,packed=True)
    assert packed['incomplete'] and packed['_metadata_pending']
    assert expand_incident_window(packed)==expected


def test_passive_compression_coalesces_notifications_between_bounded_batches(monkeypatch):
    import core.navigation.longitudinal_diagnostics as diagnostics
    class Finished(Exception):pass
    class Wake:
        calls=0
        def wait(self):
            self.calls+=1
            if self.calls>1:raise Finished
        def clear(self):pass
    class Probe(diagnostics._WindowCompression):
        windows=[]
        wake=Wake()
    sleeps=[];caller=threading.get_ident();original_sleep=diagnostics.time.sleep
    def sleep(seconds):
        if threading.get_ident()==caller:sleeps.append(seconds)
        else:original_sleep(seconds)
    monkeypatch.setattr(diagnostics.time,'sleep',sleep)
    with pytest.raises(Finished):Probe.run()
    assert sleeps==[1/60], 'passive bookkeeping must yield between batches, not compete on every notification'
