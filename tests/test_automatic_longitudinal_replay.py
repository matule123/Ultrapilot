"""No game mapping, no installed files, no manual diagnostic arm."""
import json

import pytest

from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.signals.test_signal_lifecycle import lifecycle
from core.navigation.longitudinal_diagnostics import PedalJournal
from core.steering_replay import SteeringReplayBuffer


def test_normal_unarmed_start_keeps_actual_pedal_writes(flow):
    state, truck, engine, ap, tick, n, clock, writes, collected = lifecycle(flow)
    engine._maneuver_diagnostic_collector = None
    tick(4, .4)
    journal = engine.controller._pedal_journal
    assert journal.enabled
    saved = journal.snapshot()
    assert saved['events']
    assert saved['events'][-1]['source']['requested']['producer_trace']
    assert saved['events'][-1]['source']['observed_gear'] == 4
    assert saved['events'][-1]['source']['actual_speed_mps'] == .4


def test_existing_replay_accepts_integrity_checked_pedal_incident(tmp_path):
    from core.steering_replay import inspect_replay
    journal = PedalJournal()
    journal.enabled = True
    journal.bind(dict(context=[1,2,3,4,5,6,7,8], sdk_frame_us=10,
                      observation_timestamp=1., selected=dict(throttle=.2,brake=0.)))
    journal.record('throttle', .2, 1.1, 1.11, 'SCS_SDK',
                   dict(status='MAPPING_WRITE_RETURNED',value=.2))
    path = SteeringReplayBuffer(2).export(tmp_path, reason='automatic_disable',
        longitudinal=journal.snapshot(), sample_kind='longitudinal_boundary_incident')
    checked = inspect_replay(path)
    assert checked['integrity_valid']
    assert checked['confirmed'] is checked['runtime_authorized'] is False
    value = checked['replay']
    assert value['longitudinal']['events'][0]['backend']['value'] == .2
    assert value['longitudinal']['events'][0]['game_consumption_verified'] is False


def test_immutable_ring_snapshot_does_not_destroy_combined_or_overwrite_prior_binding():
    journal = PedalJournal(); journal.enabled = True
    journal.bind(dict(context=[1]*8, sdk_frame_us=1, observation_timestamp=1.))
    journal.record('throttle',.2,1.,1.1,'SCS_SDK',dict(status='MAPPING_WRITE_RETURNED',value=.2))
    a = journal.snapshot()
    journal.bind(dict(context=[2]*8,sdk_frame_us=2,observation_timestamp=2.))
    journal.record('brake',.3,2.,2.1,'SCS_SDK',dict(status='MAPPING_WRITE_RETURNED',value=.3))
    b = journal.snapshot(after_sequence=a['last_sequence'])
    assert a['events'][0]['source']['sdk_frame_us'] == 1
    assert b['events'][0]['source']['sdk_frame_us'] == 2
    assert len(journal.snapshot()['events']) == 2
    a['events'][0]['source']['sdk_frame_us'] = 999
    assert journal.snapshot()['events'][0]['source']['sdk_frame_us'] == 1


@pytest.mark.parametrize('mode',[0,3])
def test_unarmed_fault_export_contains_prior_decision_and_release(flow,tmp_path,mode):
    from core.steering_replay import inspect_replay
    state, truck, engine, ap, tick, n, clock, writes, collected = lifecycle(flow,mode)
    engine._maneuver_diagnostic_collector = None
    engine._automatic_replay_directory = str(tmp_path)
    tick(4,.4)
    original=state.get('longitudinal_command')
    # Genuine future command remains refused. Disable effects are unchanged.
    faulty=dict(original,sdk_frame_us=truck['sdkFrameTimeUs']+10000000)
    state.set('longitudinal_command',faulty)
    engine._flush_controls()
    ap.on_tick(.05)
    engine._flush_controls()  # Actual post-disable release writes
    # A moving technical fault retains the existing controlled-stop authority
    # until standstill; the diagnostic tail clock is not a control timeout.
    ap._publish_automatic_disable('later cleanup reason')
    engine._flush_controls()
    writer=engine._automatic_replay_writer
    status=writer.wait(5.)
    assert not status['error'] and status['path']
    checked=inspect_replay(status['path'])
    assert checked['integrity_valid']
    block=checked['replay']['longitudinal']
    assert 'ahead of vehicle observation' in block['first_intervention']['reason']
    assert block['first_intervention']['details']['sdk_frame_us'] == faulty['sdk_frame_us']
    assert any(e['source'].get('phase') == 'release' for e in block['events'])
    assert any(e['source'].get('phase') == 'safety_stop' for e in block['events'])
    assert any((e['source'].get('requested') or {}).get('computed_at') == original['computed_at'] for e in block['events'])
    assert all(not e['game_consumption_verified'] for e in block['events'])


def test_backend_failure_retains_last_successful_pair_and_error(tmp_path):
    from tests.test_longitudinal_evidence_diagnostics import memory_controller
    from core.steering_replay import inspect_replay
    ctl=memory_controller(); journal=ctl._pedal_journal=PedalJournal();journal.enabled=True
    journal.bind(dict(context=[1]*8,sdk_frame_us=1,observation_timestamp=1.))
    ctl.set_throttle(.2); ctl.set_brake(0.)
    ctl.scs._buf.close()
    ctl.set_throttle(.3)
    path=SteeringReplayBuffer(2).export(tmp_path,reason='automatic_disable',longitudinal=journal.snapshot(expanded=False))
    events=inspect_replay(path)['replay']['longitudinal']['events']
    assert events[-1]['backend']['status'] == 'MAPPING_WRITE_FAILED'
    assert events[-1]['pair_after']['throttle'] is None
    assert events[-1]['last_successful_pair_after']['throttle'] == pytest.approx(.2)


def test_sealed_export_is_atomic_and_corruption_is_not_verified(tmp_path):
    from core.steering_replay import inspect_replay
    journal=PedalJournal();journal.enabled=True
    for i in range(150):
        journal.record('throttle',0.,i,i+.01,'SCS_SDK',dict(status='MAPPING_WRITE_RETURNED',value=0.))
    snapshot=journal.snapshot(expanded=False)
    assert snapshot['retained_bytes'] <= 65536 and snapshot['dropped_events'] > 0
    path=SteeringReplayBuffer(2).export(tmp_path,reason='automatic_disable',longitudinal=snapshot)
    checked=inspect_replay(path)
    assert checked['integrity_valid'] and checked['incomplete']
    assert checked['confirmed'] is checked['runtime_authorized'] is False
    from pathlib import Path
    target=Path(path); payload=json.loads(target.read_text(encoding='utf-8'))
    payload['longitudinal_storage']['values'].pop()
    target.write_text(json.dumps(payload),encoding='utf-8')
    assert not inspect_replay(path)['integrity_valid']


def test_one_background_export_never_blocks_or_builds_a_queue():
    import threading
    from core.steering_replay import AsyncReplayExporter
    gate=threading.Event(); entered=threading.Event(); writer=AsyncReplayExporter()
    def slow():entered.set();gate.wait(3.);return 'file'
    assert writer.submit(slow)
    assert entered.wait(1.)
    assert not writer.submit(lambda:'second-file')
    assert writer.status['dropped_requests'] == 1
    gate.set(); assert writer.wait(3.)['path'] == 'file'


def test_older_producer_trace_and_new_engine_input_are_not_relabelled(flow):
    from core.longitudinal import publish
    state,truck,engine,ap,tick,n,clock,writes,collected=lifecycle(flow)
    old=state.get('longitudinal_command')
    tick(4,.5,flush=False)
    current_truck=state.get('telemetry')['truck']
    state.set('longitudinal_command',old)
    publish(state,current_truck,'traffic',traffic_brake=1.,light_brake=0.)
    engine._flush_controls()
    event=collected.samples[-1].longitudinal['events'][-1]
    source=event['source']
    prior=source['requested']['producer_trace']['inputs']['traffic']
    current=source['inputs']['traffic']
    assert prior['sdk_frame_us'] < current['sdk_frame_us']
    assert prior['traffic_brake'] == 0. and current['traffic_brake'] == 1.
    assert source['selected']['emergency'] and event['backend']['value'] == 1.


def test_export_analyzer_uses_original_observations_and_keeps_channels_order(flow,tmp_path):
    from core.steering_replay import inspect_replay
    from tools.analyze_longitudinal_evidence import load_rows,analyze_rows
    state,truck,engine,ap,tick,n,clock,writes,collected=lifecycle(flow)
    engine._maneuver_diagnostic_collector=None
    for i in range(3):tick(4,.4+i*.1)
    tick(4,.6,color=2)
    events=engine.controller._pedal_journal.snapshot()['events']
    path=SteeringReplayBuffer(2).export(tmp_path,reason='automatic_disable',
        longitudinal=engine.controller._pedal_journal.snapshot(expanded=False))
    from pathlib import Path
    rows,checked=load_rows(Path(path)); result=analyze_rows(rows)
    assert checked['integrity_valid']
    assert result['simultaneous_positive_pair_observations'] == 0
    assert [w['sequence'] for w in result['write_series']] == [e['sequence'] for e in events]
    # Startup release calls precede a bound decision; their time remains None,
    # never copied from the later active SDK sample.
    assert [w['observation_timestamp'] for w in result['write_series']] == [(e['source'] or {}).get('observation_timestamp') for e in events]
    assert any(w['requested_speed_kmh'] is not None for w in result['write_series'])


def test_fault_export_is_background_even_with_slow_disk(flow,tmp_path,monkeypatch):
    import threading
    state,truck,engine,ap,tick,n,clock,writes,collected=lifecycle(flow)
    engine._maneuver_diagnostic_collector=None
    engine._automatic_replay_directory=str(tmp_path)
    gate=threading.Event();entered=threading.Event()
    original=SteeringReplayBuffer.export
    def slow(self,*args,**kwargs):
        entered.set();gate.wait(3.);return original(self,*args,**kwargs)
    monkeypatch.setattr(SteeringReplayBuffer,'export',slow)
    p=state.get('longitudinal_command');p['sdk_frame_us']+=10000000
    state.set('longitudinal_command',p)
    engine._flush_controls()
    ap._publish_automatic_disable('secondary cleanup')
    engine._flush_controls()
    assert entered.wait(1.)
    assert engine._automatic_replay_writer.status['busy']
    assert not state.get('autopilot_active')
    assert all(v==0. for _,channel,v,_ in writes[-2:] if channel in ('aforward','abackward'))
    gate.set(); assert engine._automatic_replay_writer.wait(3.)['path']


def test_full_signal_stop_trace_preserves_actual_reader_contract(flow,tmp_path):
    from core.steering_replay import inspect_replay
    state,truck,engine,ap,tick,n,clock,writes,collected=lifecycle(flow,full_identity=True)
    engine._maneuver_diagnostic_collector=None
    tick(4,.4,color=2)
    packet=state.get('longitudinal_command')
    tick(0,0.,color=2)
    saved=engine.controller._pedal_journal.snapshot()
    event=saved['events'][-1];source=event['source']
    assert 'snapshot_status' not in source
    assert source['service_hold']['chain']
    assert source['service_hold']['game_consumption_verified'] is False
    assert source['observed_gear'] == 0 and source['actual_speed_mps'] == 0.
    assert source['sdk_response']['gameBrake'] is None  # Model did not supply it.
    trace=source['requested']['producer_trace']
    signal=trace['inputs']['traffic']['signal']
    assert signal['candidate']['id'] == source['service_hold']['signal_lock']['id']
    assert signal['candidate']['color'] == 'red'  # Reader-normalized SDK enum 2.
    assert signal['generation'] and signal['observed_at']
    from core.sdk.signal_snapshot import compact
    assert signal == compact(state.get('longitudinal_traffic')['signal'])
    # Control fixtures now supply the authored passage required in production;
    # geometric-only heads are explicitly tested as detection-only evidence.
    assert signal['candidate']['passage_key'] == 'fixture-directed-control'
    assert trace['brake_requests']
    path=SteeringReplayBuffer(2).export(tmp_path,reason='automatic_disable',longitudinal=saved)
    events=inspect_replay(path)['replay']['longitudinal']['events']
    assert events[-1]['source']['requested']['producer_trace'] == trace
    assert packet['computed_at'] < source['requested']['computed_at']


def test_export_capture_failure_cannot_change_physical_outputs(flow,monkeypatch):
    state,truck,engine,ap,tick,n,clock,writes,collected=lifecycle(flow)
    engine._maneuver_diagnostic_collector=None
    def fail(*args,**kwargs):raise OSError('diagnostic only')
    monkeypatch.setattr(engine,'_finish_automatic_longitudinal_incident',fail)
    tick(4,.4)
    assert state.get('autopilot_active')
    assert engine._automatic_longitudinal_export_error == 'OSError'
    assert any(ch=='aforward' and v>0 for _,ch,v,_ in writes[-2:])


def test_consumed_eco_preference_keeps_original_time_and_parameter(flow):
    from plugins.ecodrive.main import Plugin as EcoDrive
    from sdk.plugin_sdk import PluginSDK
    state,truck,engine,ap,tick,n,clock,writes,collected=lifecycle(flow)
    engine._maneuver_diagnostic_collector=None
    eco=EcoDrive(PluginSDK(state.values,'ecodrive'));eco.sdk.shared_state=state
    eco.on_start()
    tick(4,.4,flush=False);eco.on_tick(.05);ap.on_tick(.05);engine._flush_controls()
    actual=state.get('longitudinal_eco')
    trace=engine.controller._pedal_journal.snapshot()['events'][-1]['source']['requested']['producer_trace']
    assert trace['eco']['smoothing'] == actual['smoothing'] == .15
    assert trace['eco']['observation_timestamp'] == actual['observation_timestamp']
    assert trace['eco']['sdk_frame_us'] == actual['sdk_frame_us']
