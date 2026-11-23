"""Counted standalone replay files must have a recoverable archive path."""
from pathlib import Path
from unittest.mock import patch
import hashlib
import pytest
import core.steering_replay as replay


def test_verified_standalone_replay_can_free_active_budget_without_deletion(tmp_path):
    buffer=replay.SteeringReplayBuffer(2)
    buffer.append({'sdk_frame_us':42,'original_bytes':b'original'})
    path=Path(buffer.export(tmp_path,reason='manual_disable',
        identity={'source_game_session_id':1,'navigation_intent_id':'old'},
        _diagnostic_child=True))
    target=path.with_name(path.stem+'-devinputs.json');path.rename(target)
    raw=target.read_bytes()
    budget=replay.incident_diagnostic_budget
    def small(directory):
        return dict(budget(directory),active_limit_bytes=len(raw)+100)
    with patch.object(replay,'incident_diagnostic_budget',side_effect=small):
        replay._archive_incidents(tmp_path,reserve_bytes=200)
    found=list((tmp_path/'archive').rglob(target.name))
    assert len(found)==1 and found[0].read_bytes()==raw
    assert replay.inspect_replay(found[0])['integrity_valid']
    assert not target.exists()


def test_unverified_standalone_is_not_silently_archived(tmp_path):
    path=tmp_path/'steering-replay-broken-manual_disable-devinputs.json'
    path.write_bytes(b'broken original')
    original=replay.incident_diagnostic_budget
    with patch.object(replay,'incident_diagnostic_budget',side_effect=lambda p:dict(original(p),active_limit_bytes=1)):
        with pytest.raises(ValueError):replay._archive_incidents(tmp_path,reserve_bytes=200)
    assert path.read_bytes()==b'broken original'
