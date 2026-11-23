"""Late exact AP resolution must be the predecessor of a later Engine part."""
import pytest
from tests.diagnostics.test_late_assembly import full_case


@pytest.mark.parametrize('damage',[False,True])
def test_next_part_uses_verified_immutable_resolution_without_rewriting_original(tmp_path,damage):
    from pathlib import Path
    import core.steering_replay as r
    j,window,part=full_case();first_id=window['incident_id']
    window['episode']=dict(id=first_id,part=0,continues=True,previous_incident_id=None)
    first=Path(r.export_incident(tmp_path,window,j.snapshot()));raw=first.read_bytes()
    r.export_autopilot_part(tmp_path,part)
    resolved=Path(r.complete_incident_assembly(tmp_path,first_id))
    assert r.inspect_incident(resolved)['dossier']['part_complete']
    if damage:resolved.write_bytes(resolved.read_bytes()+b'broken')
    j2,w2,p2=full_case()
    w2['episode']=dict(id=first_id,part=1,continues=False,previous_incident_id=first_id)
    r.export_autopilot_part(tmp_path,p2)
    if damage:
        with pytest.raises(ValueError):r.export_incident(tmp_path,w2,j2.snapshot())
    else:
        checked=r.inspect_incident(r.export_incident(tmp_path,w2,j2.snapshot()))
        assert checked['integrity_valid'] and checked['complete']
        assert checked['dossier']['previous_part']['name']==resolved.name
    assert first.read_bytes()==raw
