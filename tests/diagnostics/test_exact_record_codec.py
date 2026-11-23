"""Independent losslessness proof before any candidate integration.

No Engine, Controller, collector, worker or live mapping is instantiated here.
"""
import hashlib
import random
import struct
import zlib
from copy import deepcopy

import pytest

from core.navigation.longitudinal_diagnostics import freeze_exact_record,restore_exact_record


def exact(actual,expected):
    assert type(actual) is type(expected)
    if type(expected) is float:
        assert struct.pack('!d',actual)==struct.pack('!d',expected)
    elif type(expected) is dict:
        assert len(actual)==len(expected)
        for (ak,av),(ek,ev) in zip(actual.items(),expected.items()):exact(ak,ek);exact(av,ev)
    elif type(expected) in (list,tuple):
        assert len(actual)==len(expected)
        for a,e in zip(actual,expected):exact(a,e)
    else:assert actual==expected


@pytest.mark.parametrize('compressed',[False,True])
def test_original_types_float_bits_clocks_and_native_bytes_roundtrip(compressed):
    nan=struct.unpack('!d',bytes.fromhex('7ff8000000000042'))[0]
    source=dict(activation=2**100,session='session-73',identity=('intent',7,'build'),
        frame=307371038,observation_timestamp=19958.1560448,
        checked_at=19958.1594125,gear=0,speed=-0.,valid=True,missing=None,
        values=[1,1.,False,True,-0.,float('inf'),float('-inf'),nan,'žltá 🟡'],
        native=bytes(range(256))*34,empty=[{},[],(),b'',''],
        reserved=dict(encoding='internal-owned-window-v1',blob=b'ordinary original data',
            raw_bytes=99,raw_sha256='not a runtime wrapper'),
        pedals=[('throttle',0.,100.,100.001,True),('brake',.34,100.002,100.003,False)])
    expected=deepcopy(source);record=freeze_exact_record(source)
    source['frame']=0;source['pedals'].clear()
    if compressed:record=dict(record,encoding='internal-owned-window-v1',blob=zlib.compress(record['blob'],1))
    exact(restore_exact_record(record),expected)


def test_seeded_nested_primitive_trees_and_arbitrary_ieee_float_bits():
    rng=random.Random(20261025)
    def tree(depth):
        leaf=[None,True,False,rng.randrange(-2**150,2**150),
            struct.unpack('!d',rng.getrandbits(64).to_bytes(8,'big'))[0],
            bytes(rng.randrange(256) for _ in range(13)),'test žltá']
        if depth==0:return rng.choice(leaf)
        return rng.choice([leaf,tuple(leaf),{'frame':rng.randrange(2**64),'child':tree(depth-1)}])
    for _ in range(300):
        original=tree(4);exact(restore_exact_record(freeze_exact_record(original)),original)


@pytest.mark.parametrize('bad',[bytearray(b'data'),memoryview(b'data'),object(),{1,2}])
def test_no_silent_type_coercion(bad):
    with pytest.raises(ValueError,match='UNSUPPORTED_TYPE'):freeze_exact_record({'nested':[bad]})


def test_cycle_and_byte_overflow_are_explicit():
    cycle=[];cycle.append(cycle)
    with pytest.raises(ValueError,match='NODE_BUDGET'):freeze_exact_record(cycle)
    with pytest.raises(ValueError,match='BYTE_BUDGET'):freeze_exact_record(bytes(512*1024))


@pytest.mark.parametrize('fault',['hash','size','trailing','compressed-trailing','short'])
def test_corrupt_or_incomplete_record_never_restores(fault):
    record=freeze_exact_record({'frame':42,'bytes':bytes(range(256))})
    if fault=='hash':record['raw_sha256']='0'*64
    elif fault=='size':record['raw_bytes']=512*1024+1
    elif fault=='trailing':
        raw=record['blob']+b'x';record.update(blob=raw,raw_bytes=len(raw),raw_sha256=hashlib.sha256(raw).hexdigest())
    elif fault=='compressed-trailing':record.update(encoding='internal-owned-window-v1',blob=zlib.compress(record['blob'])+b'x')
    else:record['blob']=record['blob'][:-1]
    with pytest.raises((ValueError,EOFError)):restore_exact_record(record)


def test_verified_codec_in_existing_ring_keeps_reserved_fields_and_original_bytes():
    from core.navigation.longitudinal_diagnostics import _IncidentWindow
    ring=_IncidentWindow(32*1024*1024,deferred=True,simple_records=True)
    source=dict(frame=42,observation_timestamp=100.,native=bytes(range(256))*30,
        source_value=dict(encoding='internal-owned-window-v1',blob=b'original data',raw_bytes=12))
    original=deepcopy(source)
    ring.observe('consumer_traffic',source,100.,force=True)
    source['source_value']['raw_bytes']=0
    exact(ring.rolling_snapshot()['records'][0]['value'],original)


def test_exact_native_maximum_capture_without_a_live_mapping():
    from tools.qualify_oct25_traffic_capture import raw_capture
    capture=raw_capture(40,3,100.,42000000,19,'test-session',10.)
    original=dict(session=capture.session,observed_at=capture.observed_at,
        moving=capture.moving,parked=capture.parked,stable=capture.stable,source=capture.source)
    exact(restore_exact_record(freeze_exact_record(original)),original)


def test_worker_wire_format_restores_types_and_bytes_after_real_json_roundtrip():
    import json
    from core.navigation.longitudinal_diagnostics import pack_exact_window,unpack_exact_window
    source=dict(records=[dict(sequence=1,at_s=100.001,value=dict(
        sdk_frame_us=42,context=(7,'session'),bytes=bytes(range(256)),
        original=dict(encoding='internal-owned-window-v1',blob=b'not a wrapper'),
        pair=[False,None,0,0.,-0.]))],
        subevents=[dict(kind='STOP',receipt=dict(reason='first',identity=(1,'a')))],
        first_intervention=dict(kind='STOP',receipt=dict(reason='first',bytes=b'\x00\xff')))
    stored=json.loads(json.dumps(pack_exact_window(source)))
    exact(unpack_exact_window(stored),source)
    stored['records'][0]['value']['blob']['data']='broken'
    with pytest.raises(ValueError):unpack_exact_window(stored)


def test_existing_incident_and_ap_files_restore_original_tuple_bytes_and_float_bits(tmp_path):
    from core.steering_replay import export_incident,export_autopilot_part,inspect_incident,inspect_replay
    from tests.diagnostics.test_incident_assembly import sealed_case
    journal,window,part=sealed_case()
    original=dict(native=bytes(range(256)),route=(7,'session'),values=[True,None,0,-0.,(1,2)])
    window['record_format']='simple-exact-record'
    window['records'][0]['value']['original_evidence']=original
    part['records'][0]['value']['original_evidence']=original
    part['records'][0]['value']=freeze_exact_record(part['records'][0]['value'])
    ap=export_autopilot_part(tmp_path,part)
    main=export_incident(tmp_path,window,journal.snapshot())
    checked=inspect_incident(main)
    assert checked['integrity_valid'] and checked['assembly_complete'],checked.get('reason')
    exact(checked['replay']['longitudinal']['diagnostic_incident']['records'][0]['value']['original_evidence'],original)
    ap_checked=inspect_replay(ap)
    exact(ap_checked['replay']['diagnostic_consumed_inputs']['records'][0]['value']['original_evidence'],original)


def test_c_ownership_copy_is_exact_without_executing_custom_reducers():
    from core.navigation.longitudinal_diagnostics import freeze_primitive_record
    original=dict(frame=42,at=100.001,context=(7,'session'),native=bytes(range(256))*34,
        values=[None,False,True,-0.,2**100,('tuple',[1,2])])
    owned=freeze_primitive_record(original);expected=deepcopy(original)
    original['values'].clear()
    exact(restore_exact_record(owned),expected)
    called=[]
    class Forbidden:
        def __reduce__(self):called.append(True);return (str,('bad',))
    with pytest.raises(ValueError,match='UNSUPPORTED_TYPE'):freeze_primitive_record({'data':Forbidden()})
    assert called==[]
    raw=b'cos\nsystem\n.'
    bad=dict(owned,blob=raw,raw_bytes=len(raw),raw_sha256=hashlib.sha256(raw).hexdigest())
    with pytest.raises(ValueError,match='CLASS_FORBIDDEN'):restore_exact_record(bad)
