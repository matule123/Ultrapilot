"""Explicit offline quota preparation never modifies installation evidence."""
import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from core.navigation.longitudinal_diagnostics import PedalJournal
from core.steering_replay import SteeringReplayBuffer, inspect_replay
import tools.prepare_event_archive as archive


def event(source):
    journal=PedalJournal();journal.enabled=True
    journal.significant('AVOID_OBSTACLE',{'actor':{'id':71}},100.)
    snapshot=journal.expand_significant(journal.ready_significant(100.2))
    return Path(SteeringReplayBuffer(2).export(source,reason='significant_event',longitudinal=snapshot))


def test_preparation_hashes_roundtrip_without_moving_originals(tmp_path,monkeypatch):
    source=tmp_path/'installation';source.mkdir()
    monkeypatch.setattr(archive,'__file__',str(tmp_path/'tools/prepare_event_archive.py'))
    first=event(source);raw=first.read_bytes()
    for i in range(7):(source/f'steering-replay-copy{i}-significant_event.json').write_bytes(raw)
    before={p.name:p.read_bytes() for p in source.iterdir()}
    output=tmp_path/'docs/steering-audit/prepared'
    result=archive.prepare(source,output)
    assert result['files']==8 and not result['applied'] and not result['original_quota_ready']
    assert {p.name:p.read_bytes() for p in source.iterdir()}==before
    receipt=json.loads((output/'archive-receipt.json').read_text())
    assert receipt['action']=='PREPARED_NOT_APPLIED' and not receipt['runtime_authorized']
    with zipfile.ZipFile(output/'significant-events.zip') as zipped:
        assert {n:zipped.read(n) for n in zipped.namelist()}==before
    assert result['archive_sha256']==hashlib.sha256((output/'significant-events.zip').read_bytes()).hexdigest()
    with pytest.raises(ValueError,match='NEW workspace'):
        archive.prepare(source,output)


def test_corrupt_original_refuses_preparation_without_partial_archive(tmp_path,monkeypatch):
    source=tmp_path/'installation';source.mkdir()
    monkeypatch.setattr(archive,'__file__',str(tmp_path/'tools/prepare_event_archive.py'))
    original=event(source)
    data=json.loads(original.read_text());data['identity']['tampered']=True
    original.write_text(json.dumps(data));raw=original.read_bytes()
    assert not inspect_replay(original)['integrity_valid']
    output=tmp_path/'docs/steering-audit/corrupt'
    with pytest.raises(ValueError,match='Invalid original'):
        archive.prepare(source,output)
    assert not output.exists() and original.read_bytes()==raw
