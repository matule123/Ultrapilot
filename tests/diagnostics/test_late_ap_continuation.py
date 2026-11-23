"""A sealed continuation may arrive only after the preceding AP export.

The ordering is from Nov 2; frames/contents below are explicit small models.
No missing historical AP input is reconstructed by this test.
"""
from types import SimpleNamespace
import pytest


@pytest.mark.parametrize('background',[False,True])
def test_completed_part_keeps_original_tail_and_disabled_rendezvous(monkeypatch,tmp_path,background):
    import core.navigation.longitudinal_diagnostics as d
    import core.steering_replay as r
    old=r.SteeringReplayBuffer(2)
    old._diagnostic_inputs=d._IncidentWindow(32*1024*1024,deferred=True)
    for at in (100.,110.,120.):
        old._diagnostic_inputs.observe('ap_decision',dict(command={'computed_at':at},raw=b'\x00\xff'),at,force=True)
    state=SimpleNamespace(get=lambda key:request)
    writer=SimpleNamespace(status={'busy':False,'path':'first-part'},submit=lambda fn:False)
    plugin=SimpleNamespace(_steering_replay=old,sdk=SimpleNamespace(shared_state=state),
        _replay_export_writer=writer,_diagnostic_part_directory=str(tmp_path))
    owner=d.AutopilotIncidentParts(plugin)
    request=dict(schema=2,incident_id='a'*32+'-8703',phase='seal',start_s=90.,end_s=120.,token='first')
    owner.accept(request)
    new=r.SteeringReplayBuffer(2)
    new._diagnostic_inputs=d._IncidentWindow(32*1024*1024,deferred=True)
    new._diagnostic_inputs.observe('ap_decision',dict(command=None),121.,force=True)
    plugin._steering_replay=new
    monkeypatch.setattr(d.time,'monotonic',lambda:122.)
    # Rotate while an old export is busy. The next request does not yet exist.
    writer.status={'busy':True};owner.end();writer.status={'busy':False,'path':'first-part'}
    exports=[]
    monkeypatch.setattr(r,'export_autopilot_part_isolated',lambda directory,value:exports.append(value) or 'part')
    if background:
        owner.after_disabled_replay(old,str(tmp_path))
    else:
        owner.frozen=dict(request=request,records=old._diagnostic_inputs.rolling_snapshot(packed=True)['records'])
        owner.submitted=True
    owner.end()
    assert owner.completed_id==request['incident_id']
    assert owner.retired_ring is not None,'inactive AP must still rendezvous with the late next seal'
    assert owner.previous_tail,'background completion must retain the same original predecessor tail'
    # Advance beyond the rolling retention. Only original retained inputs may
    # fill the overlap, never the newer passive command=None packet.
    new._diagnostic_inputs.observe('ap_decision',dict(command=None),180.,force=True)
    request=dict(request,incident_id='a'*32+'-11926',start_s=100.,end_s=180.,token='second')
    owner.after_disabled_replay(SimpleNamespace(_diagnostic_inputs=owner.retired_ring),str(tmp_path))
    values=[d._IncidentWindow.expanded_row(row)['value'] for row in exports[-1]['records']]
    assert [v['command']['computed_at'] for v in values if v.get('command')]==[100.,110.,120.]
    assert all(v['raw']==b'\x00\xff' for v in values if v.get('command'))


def test_busy_ap_export_retains_forward_middle_before_next_request_exists(monkeypatch):
    import core.navigation.longitudinal_diagnostics as d
    from core.steering_replay import SteeringReplayBuffer
    replay=SteeringReplayBuffer(2)
    replay._diagnostic_inputs=ring=d._IncidentWindow(32*1024*1024,deferred=True)
    clock=[100.]
    for i in range(301):ring.observe('ap_decision',dict(original=i),70.+i*.1,force=True)
    writer=SimpleNamespace(status={'busy':True})
    owner=d.AutopilotIncidentParts(SimpleNamespace(_steering_replay=replay,_replay_export_writer=writer))
    request=dict(schema=2,incident_id='b'*32+'-1',phase='seal',start_s=70.,end_s=100.,token='first')
    owner.accept(request)
    owner.frozen=dict(request=request,records=ring.rolling_snapshot(packed=True)['records'])
    owner.submitted=True
    monkeypatch.setattr(d.time,'monotonic',lambda:clock[0])
    for i in range(1,341):
        clock[0]=100.+i*.1
        ring.observe('ap_decision',dict(original=300+i),clock[0],force=True)
        owner.end()
    # First request is still in flight; the rolling 30 s window has evicted
    # the first four seconds AFTER its seal. A frozen predecessor cannot
    # replace this original forward middle.
    owner.accept(dict(request,incident_id='b'*32+'-2',end_s=144.,token='second'))
    owner.case=owner.next_case;owner.next_case=None;owner.frozen=None;owner.submitted=False
    # The normal sealing path unions pinned, retired and current exact rows.
    writer.status={'busy':True}
    retired=owner.retired_ring.rolling_snapshot() if owner.retired_ring else {'records':[]}
    assert {round(r['at_s'],6) for r in retired['records']}.issuperset(
        {round(100.+i*.1,6) for i in range(1,41)})
    assert retired['retained_bytes']<=ring.limit and not retired['capacity_drops']


def test_forward_retention_overload_stays_bounded_and_reports_loss():
    import random
    import core.navigation.longitudinal_diagnostics as d
    ring=d._IncidentWindow(32*1024,deferred=True,simple_records=True)
    owner=d._RetiredAutopilotInputs(ring,ring)
    raw=random.Random(92)
    for i in range(40):
        ring.observe('ap_decision',dict(raw=raw.randbytes(4096)),100.+i*.1,force=True)
        with ring.lock:entry=ring.rows[-1]
        owner.append_original(entry)
        assert owner.bytes<=owner.limit
    snapshot=owner.rolling_snapshot()
    assert snapshot['capacity_drops']>0 and len(snapshot['records'])<40


def test_new_unrelated_request_retires_old_prefix_without_false_capacity_loss():
    import core.navigation.longitudinal_diagnostics as d
    from core.steering_replay import SteeringReplayBuffer
    old=d._IncidentWindow(16*1024,deferred=True,simple_records=True)
    old.observe('ap_decision',dict(raw=bytes(range(256))*20),10.,force=True)
    retired=d._RetiredAutopilotInputs(old,old)
    replay=SteeringReplayBuffer(2);replay._diagnostic_inputs=d._IncidentWindow(16*1024,deferred=True)
    owner=d.AutopilotIncidentParts(SimpleNamespace(_steering_replay=replay))
    owner.retired_ring=retired
    owner.accept(dict(schema=2,incident_id='c'*32+'-2',phase='open',start_s=100.))
    assert not retired.rolling_snapshot()['records']
    assert not retired.drops  # intentional out-of-range retirement is not loss


def test_active_ap_never_reserves_writer_for_disabled_seal_poll(monkeypatch):
    import core.navigation.longitudinal_diagnostics as d
    from core.steering_replay import SteeringReplayBuffer
    ring=d._IncidentWindow(32*1024,deferred=True)
    replay=SteeringReplayBuffer(2);replay._diagnostic_inputs=ring
    submitted=[]
    plugin=SimpleNamespace(_steering_replay=replay,_was_active=True,
        _replay_export_writer=SimpleNamespace(status={'busy':False},submit=lambda op:submitted.append(op)))
    owner=d.AutopilotIncidentParts(plugin);owner.retired_ring=ring
    monkeypatch.setattr(d.time,'monotonic',lambda:100.)
    owner.end()
    assert not submitted,'an active AP already consumes requests; a 20 s disabled poll blocks its next export'


def test_new_seal_does_not_inherit_backoff_from_finished_disabled_poll(monkeypatch,tmp_path):
    import core.navigation.longitudinal_diagnostics as d
    from core.steering_replay import SteeringReplayBuffer
    replay=SteeringReplayBuffer(2);replay._diagnostic_inputs=d._IncidentWindow(32*1024,deferred=True)
    replay._diagnostic_inputs.observe('ap_decision',dict(command=None),100.,force=True)
    submitted=[]
    plugin=SimpleNamespace(_steering_replay=replay,_was_active=True,_diagnostic_part_directory=str(tmp_path),
        _replay_export_writer=SimpleNamespace(status={'busy':False,'path':None},submit=lambda op:submitted.append(op) or True))
    owner=d.AutopilotIncidentParts(plugin);owner.rendezvous_submitted=True;owner.retry_at=130.
    monkeypatch.setattr(d.time,'monotonic',lambda:100.)
    owner.accept(dict(schema=2,incident_id='d'*32+'-2',phase='seal',start_s=70.,end_s=100.,token='ready'))
    owner.end()
    assert submitted and owner.submitted,'a validated new seal is ready; the unrelated poll retry is not its deadline'
