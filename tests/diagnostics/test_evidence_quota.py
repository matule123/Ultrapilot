"""Existing bounded event exporter: saturation, recovery and fault fallback."""
import hashlib
import json
import threading

import pytest

from core.engine import UltraPilotEngine
from core.navigation.longitudinal_diagnostics import PedalJournal
from core.steering_replay import inspect_replay
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.signals.test_stop_lifecycle import directed_stop
from tests.test_pedal_decision_history import bound


def saturated(tmp_path):
    paths = []
    for i in range(8):
        path = tmp_path / f'steering-replay-{i}-significant_event.json'
        path.write_bytes(b'original evidence')
        paths.append(path)
    return paths


def test_recovery_after_explicit_archive_reuses_original_pending_event(tmp_path, monkeypatch):
    clock = [100.]
    monkeypatch.setattr('time.monotonic', lambda: clock[0])
    engine = UltraPilotEngine.__new__(UltraPilotEngine)
    engine._automatic_replay_directory = str(tmp_path)
    journal = PedalJournal(); journal.enabled = True
    journal.significant('AVOID_OBSTACLE', {'actor': {'id': 71}}, 100.)
    bound(journal, 100., 0., .3, reason='original brake')
    paths = saturated(tmp_path)
    engine._finish_significant_longitudinal_event(journal, shutdown=True)
    assert engine._automatic_replay_writer.wait(5.)['error_detail'] == 'SIGNIFICANT_EVENT_EXPORT_DISK_QUOTA'
    engine._harvest_significant_export(journal)
    failure=journal.snapshot()['event_capture_status']['export_failure']
    assert failure['reason']=='SIGNIFICANT_EVENT_EXPORT_DISK_QUOTA'
    assert failure['first_failed_at_s']==100. and failure['attempts']==1
    engine._finish_significant_longitudinal_event(journal, shutdown=True)
    assert engine._automatic_replay_writer.status['error_detail']=='SIGNIFICANT_EVENT_EXPORT_DISK_QUOTA'
    assert journal.snapshot()['event_capture_status']['export_failure']['attempts']==1
    # Only the test/user archives; runtime must never remove historical files.
    archive = tmp_path / 'archive'; archive.mkdir()
    for path in paths: path.rename(archive / path.name)
    clock[0] += 31.
    engine._finish_significant_longitudinal_event(journal, shutdown=True)
    status = engine._automatic_replay_writer.wait(5.)
    assert status['path'], status
    checked = inspect_replay(status['path'])
    assert checked['integrity_valid']
    event = checked['replay']['longitudinal']['significant_event']
    assert event['observed_at'] == 100. and event['receipt']['actor']['id'] == 71
    assert all(path.read_bytes() == b'original evidence' for path in archive.iterdir())


def test_fault_keeps_sealed_history_after_quota_failure_and_ring_aging(flow, tmp_path):
    values, step = directed_stop(flow)
    state, truck, engine, ap, tick, n, clock, writes, collected = values
    step(4, 8., color=8)
    engine._automatic_replay_directory = str(tmp_path)
    journal = engine.controller._pedal_journal
    # Control-generated event evidence, retained by the existing one-slot journal.
    journal.significant('AVOID_OBSTACLE', {'actor': {'id': 71}}, clock[0])
    paths = saturated(tmp_path)
    originals = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    engine._finish_significant_longitudinal_event(journal, shutdown=True)
    engine._automatic_replay_writer.wait(5.)
    engine._harvest_significant_export(journal)
    sealed = journal.ready_significant(clock[0], shutdown=True)
    sealed_end = sealed['before']['decision_history']['window_end_s']
    for i in range(700):
        clock[0] += .05
        bound(journal, clock[0], .2, 0.)
    step(4, 8., color=8)
    command = state.get('longitudinal_command')
    # Actual Engine failure path, original identity and final safety writes.
    command['sdk_frame_us'] += 10000000
    state.set('longitudinal_command', command)
    engine._flush_controls()
    clock[0] += .11
    engine._flush_controls()
    status = engine._automatic_replay_writer.wait(5.)
    assert status['path'], status
    checked = inspect_replay(status['path'])
    assert checked['integrity_valid'] and not checked['confirmed']
    data = checked['replay']['longitudinal']
    preceding = data['preceding_significant_event']
    assert preceding['decision_history']['window_end_s'] == sealed_end
    assert preceding['significant_event']['receipt']['actor']['id'] == 71
    assert data['event_export_status']['reason'] == 'SIGNIFICANT_EVENT_EXPORT_DISK_QUOTA'
    assert data['first_intervention'] and any(e['source'].get('phase') == 'safety_stop' for e in data['events'])
    assert {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths} == originals
    # Corruption is rejected, including structurally invalid nested evidence
    # even when a producer recomputes the outer payload hash.
    from core.steering_replay import _expand_values, _intern_values, _payload_hash
    payload=json.loads(open(status['path'],encoding='utf-8').read())
    expanded=_expand_values(payload['longitudinal_storage'])
    old=expanded['preceding_significant_event']['events']
    assert old
    old.append(dict(old[-1]))
    payload['longitudinal_storage']=_intern_values(expanded)
    payload['integrity']['payload_sha256']=_payload_hash(payload)
    damaged=tmp_path/'corrupted.json'
    damaged.write_text(json.dumps(payload),encoding='utf-8')
    assert not inspect_replay(damaged)['integrity_valid']


def test_startup_readiness_is_background_once_and_never_changes_originals(tmp_path, monkeypatch, caplog):
    import core.steering_replay as replay
    original=replay.significant_event_export_budget
    caller=threading.get_ident(); threads=[]
    def check(directory):
        threads.append(threading.get_ident())
        return original(directory)
    monkeypatch.setattr(replay,'significant_event_export_budget',check)
    paths=saturated(tmp_path)
    engine=UltraPilotEngine.__new__(UltraPilotEngine)
    engine._automatic_replay_directory=str(tmp_path)
    assert engine._start_significant_export_preflight()
    engine._automatic_replay_writer.wait(5.)
    assert threads and threads==[threads[0]] and threads[0]!=caller
    assert not engine._start_significant_export_preflight()
    assert not engine._significant_export_preflight['ready']
    assert 'Diagnostic event export NOT READY: FILE_COUNT_LIMIT' in caplog.text
    assert all(path.read_bytes()==b'original evidence' for path in paths)


@pytest.mark.parametrize('kind',['empty','files','bytes'])
def test_read_only_inventory_reports_exact_blocker_and_hashes(tmp_path,kind):
    from tools.check_event_export_readiness import inventory
    if kind=='files':saturated(tmp_path)
    if kind=='bytes':
        with (tmp_path/'steering-replay-big-significant_event.json').open('wb') as stream:
            stream.seek(16*1024*1024-1);stream.write(b'x')
    result=inventory(tmp_path)
    assert result['ready']==(kind=='empty')
    assert result['blockers']==([] if kind=='empty' else ['FILE_COUNT_LIMIT' if kind=='files' else 'BYTE_LIMIT'])
    assert not result['runtime_authorized'] and not result['fit_of_next_payload_verified']
    for row in result['files']:
        assert row['sha256']==hashlib.sha256((tmp_path/row['name']).read_bytes()).hexdigest()
