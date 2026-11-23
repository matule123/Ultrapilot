"""Capacity regression at the exact previous production benchmark load."""
import pytest
from tests.diagnostics.test_incident_assembly import CANDIDATE_ENABLED


@pytest.mark.parametrize('mode',[0,3])
@pytest.mark.skipif(not CANDIDATE_ENABLED,reason='Capacity qualification runs against the isolated instrumented installed-base candidate')
def test_original_900_tick_load_retains_thirty_before_and_ten_after(mode):
    from tools.benchmark_oct25_diagnostic_window import assembly
    result=assembly(mode,True)
    assert result['active'] and result['fault'] is None
    assert result['assembled']>=1
    from core.navigation.longitudinal_diagnostics import diagnostic_build_limits
    limit=diagnostic_build_limits()['engine_ring_bytes']
    assert result['engine_ring']['byte_limit']==limit
    assert result['engine_ring']['retained_bytes']<=limit
    assert result['engine_ring']['capacity_drops']==0,result['engine_ring']
    assert result['engine_ring']['capture_failures']==0
    # After 45 s the ordinary rolling streams must retain the whole requested
    # 30+10 s, not merely report a permanently incomplete short tail.
    for kind in ('ego','traffic','signal_native','consumer_command_pair',
                 'consumed_decision','output_summary'):
        stream=result['retained_streams'][kind]
        assert stream['span_s']>=39.9,(kind,stream)


def test_exact_compressed_rows_keep_original_bytes_and_clocks():
    from core.navigation.longitudinal_diagnostics import _IncidentWindow
    from copy import deepcopy
    ring=_IncidentWindow(32*1024*1024)
    value=dict(moving=bytes(range(256))*256,packet=dict(sdk_frame_us=42,
        observation_timestamp=100.,computed_at=100.02,context=[7,'original']))
    original=deepcopy(value)
    ring.observe('traffic',value,100.03)
    value['packet']['sdk_frame_us']=99
    internal=ring.rolling_snapshot(packed=True)['records'][0]['value']
    assert internal['encoding']=='internal-owned-window-v1'
    assert ring.status()['retained_bytes']<8192
    assert ring.rolling_snapshot()['records'][0]['value']==original
    ring.event('BRAKE',dict(reason='red'),100.03)
    sealed=ring.seal(110.03)
    assert sealed['records'][0]['value']==original


def test_corrupt_internal_compressed_row_is_rejected():
    from core.navigation.longitudinal_diagnostics import _IncidentWindow
    ring=_IncidentWindow(32*1024*1024)
    ring.observe('traffic',dict(moving=bytes(65536)),100.)
    value=ring.rows[0][0]['value']
    value['raw_sha256']='0'*64
    with pytest.raises(ValueError,match='INCIDENT_PACKED_HASH'):ring.rolling_snapshot()
