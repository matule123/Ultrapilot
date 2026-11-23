"""Real ABI metadata/export edge cases, no live mapping or driving changes."""
import base64
import zlib
import pytest


def test_native_binary_event_metadata_survives_dossier_manifest(tmp_path):
    from core.navigation.longitudinal_diagnostics import PedalJournal
    from core.steering_replay import export_incident,inspect_incident
    j=PedalJournal();j.enabled=True;j.enable_incident_window()
    original=bytes(range(160))
    j.observe_incident('ego',dict(speed=5.,sdk_frame_us=42),100.)
    j.incident_event('TRAFFIC_TRANSITION',dict(reason='native lead',source=dict(
        generation=8,frame_us=42,observed_at=100.,ego_body_payload=original)),100.)
    result=inspect_incident(export_incident(tmp_path,j.seal_incident(110.),j.snapshot()))
    assert result['integrity_valid']
    encoded=result['dossier']['subevents'][0]['receipt']['source']['ego_body_payload']
    assert zlib.decompress(base64.b64decode(encoded['data']))==original
    assert result['dossier']['subevents'][0]['receipt']['source']['observed_at']==100.
    assert result['incomplete'] and not result['complete']


@pytest.mark.parametrize('count',[8,40])
@pytest.mark.parametrize('trailers',[0,1,3])
def test_full_abi_population_has_distinct_bodies_and_original_clocks(count,trailers):
    from tools.qualify_oct25_traffic_capture import raw_capture
    from core.navigation.traffic_producer import LegacyTrafficProducer
    source=raw_capture(count,trailers,100.,12345,12,'session',5.)
    snapshot=LegacyTrafficProducer().produce(source,100.)
    assert len(snapshot.actors)==count*2
    assert len({a.actor_id for a in snapshot.actors})==count*2
    assert sum(len(a.bodies) for a in snapshot.actors)==count*(2+trailers)
    assert source.source['frame_us']==12345 and source.source['observed_at']==100.
    assert len(source.moving)==6960 and len(source.parked)==1720


def test_dense_owner_event_fits_same_receipt_budget_without_losing_fields():
    from core.navigation.longitudinal_diagnostics import PedalJournal
    j=PedalJournal();j.enabled=True;j.enable_incident_window()
    owner=dict(reason='original red and native conflict',epoch=7,observed_at=100.,
        witnesses=[dict(id=i,frame=42,x=float(i),bodies=[dict(x=i+j,dimensions=[2.,3.,8.])
            for j in range(4)]) for i in range(40)])
    j.incident_event('TRAFFIC_TRANSITION',owner,100.)
    result=j.seal_incident(110.)
    assert result['capture_failures']==0
    assert result['subevents'][0]['receipt']==owner
    assert result['first_reason']==owner['reason']


def test_dense_incident_storage_is_lossless_under_original_file_quota(tmp_path):
    from core.navigation.longitudinal_diagnostics import PedalJournal
    from core.steering_replay import export_incident,inspect_incident,_expand_values,_payload_hash,inspect_replay
    import json,hashlib
    from pathlib import Path
    j=PedalJournal();j.enabled=True;j.enable_incident_window()
    for i in range(410):
        at=100.+i*.1
        j.observe_incident('decision',dict(sdk_frame_us=i+1,observation_timestamp=at,
            actors=[dict(id=a,x=i*.013+a,y=10.,z=a*.31) for a in range(80)]),at)
        if i==300:j.incident_event('BRAKE',dict(reason='original'),at)
    window=j.seal_incident(141.)
    main=Path(export_incident(tmp_path,window,j.snapshot()))
    checked=inspect_incident(main)
    assert checked['integrity_valid']
    replay=main.parent/checked['dossier']['replay']
    stored=json.loads(replay.read_text())
    block=_expand_values(stored['longitudinal_storage'])['diagnostic_incident']
    assert block['encoding']=='zlib-immutable-json-v1'
    assert replay.stat().st_size<16*1024*1024
    assert checked['replay']['longitudinal']['diagnostic_incident']['records']==window['records']
    # A valid outer hash must not bless a damaged compressed inner payload.
    outer=_expand_values(stored.pop('longitudinal_storage'))
    outer['diagnostic_incident']['raw_sha256']='0'*64
    from core.steering_replay import _intern_values
    stored['longitudinal_storage']=_intern_values(outer)
    stored['integrity']['payload_sha256']=_payload_hash(stored)
    replay.write_text(json.dumps(stored))
    assert not inspect_replay(replay)['integrity_valid']
