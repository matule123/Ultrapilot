"""Phased real producers and physical writes; synthetic SDK, not ETS2 proof."""
import math
import importlib
from unittest.mock import patch

import pytest

from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_rolling_longitudinal_authority import rolling  # noqa: F401
from core.longitudinal import publish


class Mapping:
    """Copying Manager-like RPC contract shared by every real PluginSDK view."""
    def __init__(self, state, clock, cost):
        self.state, self.clock, self.cost = state, clock, cost
        self.on_write = None
    def get(self, key, default=None):
        return self.state.get(key, default)
    def __getitem__(self, key):
        return self.state.get(key)
    def __setitem__(self, key, value):
        self.clock[0] += self.cost
        self.state.set(key, value)
        if self.on_write:
            self.on_write(key, value)
    def update(self, values):
        self.clock[0] += self.cost
        self.state.update_batch(values)
        if self.on_write:
            for key, value in values.items():
                self.on_write(key, value)


def distribution(values):
    values = sorted(values)
    return dict(n=len(values), minimum=min(values) if values else None,
        median=values[len(values)//2] if values else None,
        p95=values[max(0, math.ceil(len(values)*.95)-1)] if values else None,
        p99=values[max(0, math.ceil(len(values)*.99)-1)] if values else None,
        maximum=max(values) if values else None)


def run_cadence(rolling, flow, *, seconds=75., phase=0., rpc=.00012, diagnostics=False):
    state, engine, ap, acc, policy, map_tick, observe, n, physical, writes, clock = rolling
    truck = flow[1]
    start = clock[0]
    proxy = Mapping(state, clock, rpc)
    # Hooked reads model ALL consumers, not merely one isolated IPC lookup.
    state.hook = lambda key: clock.__setitem__(0, clock[0]+rpc)
    for plugin in (ap, acc, policy, map_tick.publish_map.__self__):
        for view in (plugin.sdk, *plugin.sdk.__dict__.values()):
            if hasattr(view, '_state'):
                object.__setattr__(view, '_state', proxy)
    from core.navigation.longitudinal_diagnostics import PedalJournal
    journal = engine.controller._pedal_journal = PedalJournal()
    journal.enabled = diagnostics
    # Match the real wrapper's switches. Setting journal.enabled alone is
    # overwritten by automatic capture on every flush, so was not an off case.
    engine._automatic_longitudinal_diagnostics = diagnostics
    if not diagnostics:
        engine._maneuver_diagnostic_collector = None
    periods = dict(sdk=.033333, map=.36, traffic=.46, policy=.059, acc=.023,
                   autopilot=.026, engine=1/60.)
    due = {key: start+phase*(i+1) for i, key in enumerate(periods)}
    due['sdk'] += periods['sdk']  # The initial valid frame already exists.
    counts = dict.fromkeys(periods, 0)
    publication, reception, output, ages, pending = [], [], [], [], 0
    publication_complete, engine_reception = [], []
    engine_reads = set()
    inside_engine = [False]
    def completed_write(key, value):
        if (key in ('longitudinal_acc', 'longitudinal_command')
                and isinstance(value, dict) and 'expires_at' in value):
            publication_complete.append(value['expires_at']-clock[0])
    proxy.on_write = completed_write
    def rpc_read(key):
        clock[0] += rpc
        if inside_engine[0] and key == 'longitudinal_command':
            # Observe the same lookup copied by IPCState.get below this hook;
            # no extra RPC, clock advance, mutable alias or later reread.
            value = state.values.get(key)
            if value and 'expires_at' in value:
                token = (value.get('sdk_frame_us'), value.get('computed_at'), value['expires_at'])
                if token not in engine_reads:
                    engine_reads.add(token)
                    engine_reception.append(value['expires_at']-clock[0])
    state.hook = rpc_read
    received = set()
    faults = []
    expired_write_receipts = []
    held = dict(aforward=physical('aforward'), abackward=physical('abackward'))
    last_observed = [start]
    def sdk():
        dt = max(.000001, clock[0]-last_observed[0])
        last_observed[0] = clock[0]
        truck.update(gear=4, speed=3., sdkFrameTimeUs=truck['sdkFrameTimeUs']+max(1, int(dt*1e6)),
            x=2.25, y=10., z=15.+3.*(clock[0]-start), rotation=math.pi)
        # The actual SDK-to-control producer creates ONE new complete snapshot.
        # No fixture-generated steering packet or repaired observation time.
        state.update_batch(engine._vehicle_telemetry_payload(
            {'truck': truck, 'raw': {'sdkActive': True}}, clock[0]))
        observed = state.get('telemetry')['truck']['_control_observation']
        mode = state.get('ets2_transmission_mode')
        mode['observed_at'] = observed['observed_at']
        state.set('ets2_transmission_mode', mode)
        state.update_batch(dict(truck_world_pos=(truck['x'], truck['z']),
            truck_altitude=10., truck_heading=math.pi, truck_speed_ms=3.,
            vehicle_envelope_snapshot=dict(timestamp=observed['observed_at'],
                sdk_frame_us=truck['sdkFrameTimeUs'], tractor_position=(truck['x'],10.,truck['z']),
                tractor_heading=math.pi, tractor_speed_ms=3.,
                tractor_reference_geometry=dict(valid=True, source='synthetic_4x2',
                    wheelbase_m=3.8, reference_ahead_m=2.1))))
    def traffic():
        publish(state, state.get('telemetry')['truck'], 'traffic',
                traffic_brake=0., light_brake=0., following=None)
    def pedals():
        nonlocal pending
        current = state.get('longitudinal_command')
        if current:
            key = (current.get('sdk_frame_us'), current.get('computed_at'), current['expires_at'])
            if key not in received:
                received.add(key)
                reception.append(current['expires_at']-clock[0])
        first = len(writes)
        # Observe the historical decision as actually returned to Engine. This
        # lets an old build lacking the new applied receipt expose its write
        # margins, without attributing a later shared packet to an older write.
        module = importlib.import_module('core.longitudinal')
        decide = module.engine_decision
        consumed = []
        def record_decision(*args, **kwargs):
            result = decide(*args, **kwargs)
            if result[0] is not None and not result[1]:
                consumed.append(dict(result[0]))
            return result
        with patch.object(module, 'engine_decision', record_decision):
            inside_engine[0] = True
            try:
                engine._flush_controls()
            finally:
                inside_engine[0] = False
        for _, key, value in writes[first:]:
            held[key] = value
            assert held['aforward'] == 0 or held['abackward'] == 0
        applied = state.get('longitudinal_applied')
        if applied and applied.get('written_at', 0.) >= start:
            pending += bool(applied.get('refresh_pending'))
            if applied.get('write_started_at') is not None:
                margin = applied['expires_at']-applied['write_started_at']
                output.append(margin)
                ages.append(applied['write_started_at']-applied['source_observation_timestamp'])
                assert margin >= 0. and ages[-1] <= .5
            elif consumed and writes[first:]:
                # The in-memory test backend returns synchronously and adds no
                # delay; chronological writes therefore share their start/end.
                decision = consumed[-1]
                matched = [(at, channel, value) for at, channel, value in writes[first:]
                    if value > 0 and value == decision[
                        'throttle' if channel == 'aforward' else 'brake']]
                # A later safety-stop write is a DIFFERENT decision. Do not
                # attribute it to the earlier normal command rejected by Engine.
                if matched:
                    written_at = matched[-1][0]
                    output.append(decision['expires_at']-written_at)
                    ages.append(written_at-decision['observation_timestamp'])
                    if output[-1] < 0.:
                        expired_write_receipts.append(dict(expires_at=decision['expires_at'],
                            decision_throttle=decision['throttle'], decision_brake=decision['brake'],
                            physical_writes=matched))
        if not state.get('autopilot_active') or state.get('autopilot_control_state') == 'controlled_stop':
            faults.append(state.get('automatic_safety_stop_reason') or state.get('autopilot_disable_reason'))
        journal.drain()  # Existing bounded worker drain; no disk or new collector.
    actions = dict(sdk=sdk, map=lambda: map_tick.publish_map(.36), traffic=traffic,
        policy=lambda: policy.on_tick(.059), acc=lambda: acc.on_tick(.023),
        autopilot=lambda: ap.on_tick(.026), engine=pedals)
    try:
        while clock[0]-start < seconds:
            key = min(due, key=due.get)
            clock[0] = max(clock[0], due[key])
            actions[key]()
            counts[key] += 1
            if key in ('acc', 'autopilot'):
                value = state.get('longitudinal_acc' if key == 'acc' else 'longitudinal_command')
                if value:
                    publication.append(value['expires_at']-value['computed_at'])
            # No catch-up work queue: current non-Map worker sleeps after work.
            due[key] = clock[0] + periods[key]
            if faults:
                break
        return dict(duration_s=clock[0]-start, phase_s=phase, rpc_s=rpc,
            diagnostics=diagnostics, ticks=counts, publication_margin_s=distribution(publication),
            first_consumer_check_margin_s=distribution(reception), physical_write_margin_s=distribution(output),
            publication_complete_margin_s=distribution(publication_complete),
            first_engine_read_margin_s=distribution(engine_reception),
            observation_age_at_write_s=distribution(ages), refresh_writes=pending,
            expired_write_receipts=expired_write_receipts,
            faults=faults, active=bool(state.get('autopilot_active')))
    finally:
        state.hook = None


@pytest.mark.parametrize('phase,rpc', [(0., .00006), (.003, .00012), (.007, .0002)])
@pytest.mark.parametrize('diagnostics', [False, True])
def test_independent_production_cadences_exceed_one_minute(rolling, flow, phase, rpc, diagnostics):
    result = run_cadence(rolling, flow, phase=phase, rpc=rpc, diagnostics=diagnostics)
    assert not result['faults'], result
    assert result['duration_s'] >= 75. and result['active']
    assert result['physical_write_margin_s']['minimum'] >= 0.
