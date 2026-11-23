"""One assembly must not decode the same content again at final readback."""
from pathlib import Path
from unittest.mock import patch
import core.steering_replay as replay
import pytest
from tests.diagnostics.test_late_assembly import full_case


def test_exact_assembly_decodes_each_immutable_replay_only_once(tmp_path):
    j,window,part=full_case()
    original=Path(replay.export_incident(tmp_path,window,j.snapshot()))
    ap=Path(replay.export_autopilot_part(tmp_path,part))
    # Count the actual full JSON decoder, not public inspector invocations:
    # final verification still rechecks current bytes/hash and all contracts.
    decoder=replay.json.JSONDecoder.raw_decode
    decoded=[]
    def count(self,text,idx=0):
        value=decoder(self,text,idx)
        if isinstance(value[0],dict) and value[0].get('schema_version')==replay.SCHEMA_VERSION:
            decoded.append(value[0].get('sample_kind'))
        return value
    with patch.object(replay.json.JSONDecoder,'raw_decode',count):
        path=replay.complete_incident_assembly(tmp_path,window['incident_id'])
    assert len(decoded)==2,decoded
    assert replay.inspect_incident(path)['complete']
    assert original.exists() and ap.exists()


def test_cached_decode_never_accepts_changed_file_or_foreign_request(tmp_path):
    _,window,part=full_case()
    path=Path(replay.export_autopilot_part(tmp_path,part))
    cache=replay._ReplayVerificationCache()
    assert replay.inspect_autopilot_part(path,part['request'],_verified_replays=cache)['verified']
    foreign=dict(part['request'],token='different original request')
    assert not replay.inspect_autopilot_part(path,foreign,_verified_replays=cache)['verified']
    raw=path.read_bytes();path.write_bytes(raw[:-1]+b'!')
    assert not replay.inspect_replay(path,_cache=cache)['integrity_valid']
    assert len(cache.rows)==1


def test_corruption_between_attachment_and_final_readback_still_fails(tmp_path):
    j,window,part=full_case()
    replay.export_incident(tmp_path,window,j.snapshot())
    path=Path(replay.export_autopilot_part(tmp_path,part))
    original=replay._payload_hash;changed=[]
    def corrupt(value):
        digest=original(value)
        if value.get('assembly_of') and not changed:
            changed.append(True);path.write_bytes(path.read_bytes()+b'corruption')
        return digest
    with patch.object(replay,'_payload_hash',side_effect=corrupt):
        with pytest.raises(ValueError,match='LATE_ASSEMBLY_READBACK'):
            replay.complete_incident_assembly(tmp_path,window['incident_id'])
    assert changed


def test_read_reuse_has_fixed_file_and_source_byte_bounds(tmp_path):
    cache=replay._ReplayVerificationCache()
    for i in range(8):
        cache.put((str(tmp_path/str(i)),str(i)),20*1024*1024,dict(integrity_valid=True))
        assert len(cache.rows)<=2 and cache.source_bytes<=64*1024*1024
    cache.put(('oversized','digest'),65*1024*1024,dict(integrity_valid=True))
    assert ('oversized','digest') not in cache.rows
