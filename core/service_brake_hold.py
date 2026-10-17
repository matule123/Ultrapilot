"""Engine-owned continuous service-brake state, not another pedal regulator.

Software continuity supports the user-observed gearbox model only. It does not
prove DLL consumption or hill hold. Release needs producer-timed same-signal or
qualified original-traffic clearance; legacy buffers cannot prove either.
"""
import time
import math
SERVICE_BRAKE_RISE_PER_S=2.5  # existing Autopilot service-pedal limit, not physical jerk


def holding_floor(hold,truck,now):
    """Rise from the actual last write; no zero edge or renewed evidence.

    Comfort never delays a current stronger request/emergency. Observed reverse
    drift bypasses this ramp; the unchanged motion/R rejection still applies.
    """
    current=float(hold['brake']);peak=max(current,float(hold.get('braking_peak',current)))
    if float(truck['speed'])<0:return peak
    elapsed=max(0.,min(.1,now-float(hold['returned_at'])))
    return min(peak,current+SERVICE_BRAKE_RISE_PER_S*elapsed)

from core.transmission_mode import simple_auto_context


def continuous_stop_phase(record, truck):
    """An approach label cannot erase a still-positive forward-started chain.

    At the first stopped observation Engine has not yet run after_write() to
    change 'approaching' into 'holding'. Admit only its already acknowledged
    positive receipt; the physical boundary still validates sequence/backend.
    A released approach, mere low speed or a new stationary brake never qualifies.
    """
    if record.get('phase') in ('braking', 'holding'):
        return True
    if record.get('phase') != 'approaching':
        return False
    try:
        return bool(record.get('brake', 0.) > 0. and record.get('chain', 0) > 0
            and record.get('write_sequence', 0) > 0
            and abs(float(truck['speed'])) < .05 and int(truck['gear']) >= 0)
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def restart_powertrain_rejection(truck):
    """Reject known engine-off evidence, never infer health from legacy defaults.

    These optional raw-presence fields belong to the already validated truck
    observation. Unknown is still unknown; gear/lease/backend/receipt checks
    remain independently mandatory. No SDK read or engine-start command here.
    """
    observed = truck.get('powertrainObservation') or {}
    if not isinstance(observed,dict):
        return 'planned restart rejected: invalid engine observation; driver takeover required'
    if observed.get('schema') != 1:
        return ''
    rpm = observed.get('engine_rpm')
    if (observed.get('engine_enabled') is False or
            (type(rpm) in (int,float) and math.isfinite(rpm) and 0. <= rpm <= 150.)):
        return 'planned restart rejected: engine is not running; driver takeover required'
    return ''


def receipt(controller):
    if (getattr(controller, 'mode', None) != 'SCS_SDK'
            or not getattr(getattr(controller, 'scs', None), 'connected', False)):
        return {}
    return dict(getattr(controller.scs, '_brake_write_receipt', {}))


def approach_green_wait_allowed(record,state,truck,now=None):
    """Bounded ZERO-OUTPUT pairing, never standstill braking/launch authority.

    A forward-admitted approach may reach zero before Engine consumes its
    second green acquisition. Preserve only its original same-head commitment
    for the existing 500 ms transfer bound; Engine still validates the actual
    backend receipt and clearance before handing off to bounded launch.
    """
    from core.longitudinal import context,rejection as packet_rejection
    if not record or record.get('phase')!='approaching':return False
    # after_write also runs during the full moving approach. Reject from its
    # already consumed vehicle snapshot before making any new IPC reads.
    try:
        speed=float(truck['speed'])
        if (not math.isfinite(speed) or abs(speed)>=.05
                or int(truck['gear'])<0 or truck.get('parkBrake') is not False):
            return False
    except (KeyError,TypeError,ValueError,OverflowError):
        return False
    binding=context(state);packet=state.get('longitudinal_traffic') or {}
    signal=packet.get('signal') or {};light=signal.get('candidate') or {}
    lock=record.get('signal_lock') or {};original=lock.get('candidate') or {}
    forward_binding=simple_auto_context(state)
    final_binding=context(state)
    # IPC may advance both time and authority. Only the values actually read
    # are witnesses; caller time never predates these required reads.
    checked=max(time.monotonic(),now) if now is not None else time.monotonic()
    deadline=record.get('standstill_deadline_at',record.get('returned_at',float('-inf'))+.5)
    return bool(binding==final_binding and record.get('context')==forward_binding
        and tuple(record.get('command_context',()))==binding
        and tuple(lock.get('authority',()))==binding
        and checked<=deadline and 0<=checked-record.get('returned_at',float('-inf'))<=.5
        and truck.get('gear',-1)>=0 and abs(float(truck['speed']))<.05
        and truck.get('parkBrake') is False
        and not packet_rejection(packet,binding,checked)
        and signal.get('valid') and tuple(signal.get('authority',()))==binding
        and signal.get('lifecycle')==lock.get('lifecycle')
        and light.get('id')==original.get('id') and light.get('passage_key')==original.get('passage_key')
        and light.get('color')=='green' and light.get('stop_required') is not True
        and (light.get('phase_plan') or {}).get('status')!='green_dilemma'
        and signal.get('generation',0)>lock.get('generation',0)
        and signal.get('frame_us',0)>lock.get('frame_us',0)
        and signal.get('observed_at',0)>lock.get('observed_at',0)
        and 0<=checked-signal.get('observed_at',float('-inf'))<=.5)


def rejection(record, controller, state, truck):
    from core.longitudinal import context
    if (record['context'] != simple_auto_context(state)
            or tuple(record['command_context']) != context(state)):
        return 'continuous service brake activation or route identity changed'
    current = receipt(controller)
    approaching = record.get('phase') == 'approaching'
    if (not current or (approaching and current.get('sequence') != record['write_sequence'])
            or (not approaching and (not current.get('positive') or current.get('chain') != record['chain']))):
        return 'continuous service brake write interrupted or backend unavailable'
    now = time.monotonic()  # after identity IPC reads; no source retimestamping
    if not 0. <= now-current.get('returned_at', float('-inf')) <= .5:
        return 'continuous service brake write evidence expired'
    if truck.get('parkBrake') is not False:
        return 'parking brake changed or became unknown during service hold; driver takeover'
    # userBrake/userThrottle do not identify the owner of the input mix. A
    # positive value must not be misclassified as a proven manual intervention.
    # Explicit N/UI cancellation and observed motion/R revoke the state.
    if record.get('phase') == 'holding' and abs(float(truck['speed'])) > .05:
        return 'vehicle motion observed during continuous service brake hold'
    return ''


def planned_stop(decision):
    if not decision or decision.get('emergency') or decision.get('brake', 0) <= 0:
        return False
    if moving_speed_constraint(decision) is not None:
        return False  # Positive speed regulation is not a terminal stop receipt.
    evidence = decision.get('stopping_evidence') or {}
    traffic = evidence.get('traffic') or {}
    acc = evidence.get('acc') or {}
    policy = evidence.get('policy') or {}
    # A prospective red ahead does not turn an unrelated cruise/curve brake
    # into a stop-and-wait commitment. Bind the chain to the winning request.
    return bool((decision.get('source') == 'traffic_light' and traffic.get('light_brake', 0) > 0)
                # Traffic/obstacle braking has no signal dependency. The
                # validated decision and actual forward-started write admit
                # continuity, never clearance by disappearance of the actor.
                or traffic.get('traffic_brake', 0) > 0
                or (decision.get('source') == 'acc'
                    and (acc.get('following_status') in ('candidate', 'source_lost')
                         or acc.get('signal_brake_selected') is True
                         or evidence.get('destination_brake_selected') is True))
                or (decision.get('source') in ('toll', 'policy', 'speed_policy')
                    and (policy.get('reason') == 'toll stop/payment'
                         or decision.get('reason') == 'toll stop/payment')))


def consumed_stop_target(evidence):
    """Canonical target from this immutable input, not a later shared slot."""
    traffic = (evidence or {}).get('traffic') or {}
    signal = traffic.get('signal') or {}
    return traffic.get('light') or signal.get('candidate') or signal.get('stop_candidate') or {}


def moving_speed_constraint(decision):
    """Consumed positive moving-actor constraint, never clearance by absence.

    Unknown/legacy inputs retain terminal protection. A fresh positive cap can
    adjust ordinary braking; it cannot clear an existing terminal stop receipt.
    """
    try:
        if (decision.get('emergency') or decision.get('refresh_pending')
                or decision.get('source') not in ('acc','traffic')):
            return None
        evidence=decision.get('stopping_evidence') or {}
        traffic=evidence.get('traffic') or {}; acc=evidence.get('acc') or {}
        policy=evidence.get('policy') or {}; basis=traffic.get('brake_basis') or {}
        scope=traffic.get('motion_constraint') or {}
        if (traffic.get('light_brake',0.) > 0. or acc.get('signal_brake_selected')
                or evidence.get('destination_brake_selected')
                or policy.get('reason') == 'toll stop/payment'
                or acc.get('following_status') == 'source_lost'
                or (traffic.get('traffic_brake',0.) > 0. and
                    basis.get('stop_contract') != 'observed_positive_motion_speed_constraint')
                or scope.get('schema') != 1 or scope.get('complete') is not True
                or scope.get('kind') != 'observed_positive_motion_speed_constraint'
                or tuple(scope['authority']) != tuple(decision['context'])
                or not 1 <= len(scope['targets']) <= 16
                or not all(isinstance(t['id'],str) and t['id'] and t['source']=='moving'
                    and type(t['slot']) is int and 0<=t['slot']<80
                    and math.isfinite(t['speed_mps']) and .1<t['speed_mps']<=70.
                    and math.isfinite(t['cap_mps']) and 1.<t['cap_mps']<=140. for t in scope['targets'])
                or len({t['id'] for t in scope['targets']}) != len(scope['targets'])
                or (acc.get('brake',0.) > 0. and
                    (not math.isfinite(acc['control_target_kmh']) or acc['control_target_kmh']<=3.6))):
            return None
        acquired=scope['source_acquisition']
        if (not all(type(acquired[k]) is int and acquired[k]>0
                    for k in ('lifecycle','generation','frame_us'))
                or not 0 <= time.monotonic()-acquired['observed_at'] <= .5):
            return None
        return scope
    except (KeyError,TypeError,ValueError,OverflowError):
        return None


def after_write(previous, controller, forward_context, truck, decision, now,
                *, forward_history=None, green_wait=False):
    if not decision or decision.get('emergency'):
        return None
    current = receipt(controller)
    keep_approach = bool(previous and previous.get('phase') == 'approaching'
        and tuple(decision.get('context', ())) == tuple(previous['command_context'])
        and (float(truck['speed']) > .05 or green_wait))
    if not current or (not current.get('positive') and not keep_approach):
        return None
    # Engine has already validated this exact observation with the common
    # transmission rule. An engaged ratio may briefly be zero while the truck
    # is still moving forward. Do not discard the first actual planned brake
    # write in that admitted transition, then reject its stop as lost drive.
    # A raw zero ratio, launch intent or old confirmation is never sufficient.
    history = forward_history or {}
    zero_forward = bool(int(truck['gear']) == 0
        and history.get('context') == forward_context
        and history.get('phase') in ('zero_ratio_transition', 'planned_brake_transition')
        and history.get('last_frame') == truck['sdkFrameTimeUs']
        and not history.get('launch_deadline_at')
        and 0. <= now-history.get('last_observed_at', float('-inf')) <= .5
        and now <= history.get('zero_deadline_at', float('-inf')))
    if previous and (keep_approach or current['chain'] == previous['chain']):
        result = dict(previous)
        if current['chain'] != previous['chain']:
            # A permitted moving release is not a continuous terminal witness.
            # Its old peak must not be presented as written in this new chain.
            result['braking_peak'] = 0.
    elif (float(truck['speed']) > .05 and (int(truck['gear']) > 0 or zero_forward)
            and truck.get('parkBrake') is False and planned_stop(decision)):
        # Identities are those validated BEFORE this write. Never label a write
        # with a later IPC snapshot that may already belong to another route.
        result = dict(context=forward_context, chain=current['chain'],
                      command_context=tuple(decision['context']),
                      started_frame=truck['sdkFrameTimeUs'], started_at=now,
                      phase='braking', stop_evidence=decision['stopping_evidence'])
        evidence = decision['stopping_evidence']
        light = consumed_stop_target(evidence)
        result['stop_reason'] = dict(source=decision['source'], reason=decision['reason'],
            signal_id=light.get('id'), signal_color=light.get('color'),
            observation_timestamp=decision['observation_timestamp'])
        # Preserve this FIRST consumed compact cause even if a long wait exceeds
        # the rolling journal. A later zero demand cannot rewrite its origin.
        basis = (evidence.get('traffic') or {}).get('brake_basis')
        if isinstance(basis, dict):
            result['stop_reason']['brake_basis'] = dict(basis)
    else:
        return None
    if 'signal_lock' not in result:
        signal = (((decision.get('stopping_evidence') or {}).get('traffic') or {}).get('signal') or {})
        candidate = signal.get('candidate') or {}
        original = consumed_stop_target(result['stop_evidence'])
        if (signal.get('valid') and (candidate.get('color') in ('red', 'yellow') or candidate.get('stop_required') is True)
                and candidate.get('id') == original.get('id')
                and candidate.get('passage_key') == original.get('passage_key')
                and tuple(decision['context']) == tuple(result['command_context'])):
            # A transient missing head can recover on this SAME authored
            # passage. Keep the initial stop evidence immutable; bind release
            # to the new actual observed head, never an inferred green/default.
            result['signal_lock'] = dict(authority=tuple(decision['context']),
                lifecycle=signal['lifecycle'], generation=signal['generation'],
                frame_us=signal['frame_us'], observed_at=signal['observed_at'],
                candidate=dict(candidate))
    # A following/toll stop cannot be cleared by disappearance of its producer.
    evidence = decision.get('stopping_evidence') or {}
    acc = evidence.get('acc') or {}
    traffic = evidence.get('traffic') or {}
    policy = evidence.get('policy') or {}
    basis = traffic.get('brake_basis') or {}
    motion = moving_speed_constraint(decision)
    qualified_traffic_stop = bool(basis.get('stop_contract') == 'observed_conflict_stop'
            and basis.get('targets_complete') is True and basis.get('targets'))
    if traffic.get('traffic_brake', 0) > 0 and qualified_traffic_stop:
        acquisition = basis['source_acquisition']
        lock = result.get('traffic_lock')
        if lock is None:
            result['traffic_lock'] = dict(acquisition, authority=tuple(decision['context']),
                targets=list(basis['targets']), complete=True)
        elif lock['lifecycle'] == acquisition['lifecycle']:
            targets = {t['id']: t for t in lock['targets']}
            targets.update({t['id']:t for t in basis['targets']})
            result['traffic_lock'] = dict(lock, targets=list(targets.values())[:16],
                complete=lock.get('complete') is True and len(targets)<=16)
        else:
            result['traffic_lock'] = dict(lock, complete=False)
    # Separate the originally consumed reasons. Qualified clearance may remove
    # ONLY its own traffic dependency; it cannot clear toll/ACC/unknown stops.
    others = set(result.get('other_stop_sources') or ())
    if traffic.get('traffic_brake', 0) > 0 and motion is None:
        # A previous qualified owner cannot bless a newly unqualified cause.
        # Losing the complete set is sticky until this hold/authority ends.
        others.add('traffic' if qualified_traffic_stop and result.get('traffic_lock')
                   else 'unqualified_traffic')
    if acc.get('following_status') in ('candidate', 'source_lost') and motion is None:
        others.add('acc')
    if policy.get('reason') == 'toll stop/payment':
        others.add('toll')
    result['other_stop_sources'] = sorted(others)
    if evidence.get('destination_brake_selected') and evidence.get('destination'):
        result.setdefault('destination_lock', dict(context=tuple(decision['context']),
            target_kind=evidence['destination']['target_kind'],
            sdk_frame_us=decision['sdk_frame_us'],
            observation_timestamp=decision['observation_timestamp']))
        result['destination_lock'] = dict(result['destination_lock'])
        if evidence['destination']['terminal'] and current.get('positive'):
            result['destination_lock'].setdefault('terminal_receipt', dict(
                distance_m=evidence['destination']['distance_m'],
                sdk_frame_us=truck['sdkFrameTimeUs'], returned_at=current['returned_at']))
    result['other_stop_unverified'] = bool(result.get('other_stop_unverified')
        or (motion is None and (acc.get('following_status') in ('candidate', 'source_lost')
                               or traffic.get('traffic_brake', 0) > 0))
        or policy.get('reason') == 'toll stop/payment')
    result.update(brake=current['value'], returned_at=current['returned_at'],
                  write_sequence=current['sequence'], sdk_frame_us=truck['sdkFrameTimeUs'],
                  chain=current['chain'],
                  game_consumption_verified=False)
    # The deceleration requirement tends to zero with speed squared. Freezing
    # its last tiny value is not holding. Retain the strongest actual write in
    # THIS admitted stop chain, not an arbitrary new pedal constant or an
    # unexecuted request. It remains a software witness, not verified hill hold.
    result['braking_peak'] = max(result.get('braking_peak', 0.), current['value'])
    if result.get('signal_lock'):
        result.setdefault('automatic_restart_supported', True)
        result.setdefault('restart_blocker', 'locked signal is not green')
    elif result.get('traffic_lock') and result['traffic_lock'].get('complete') is True:
        supported = not bool(others-{'traffic'})
        result.update(automatic_restart_supported=supported,
            restart_blocker=('awaiting confirmed original traffic clearance' if supported
                             else 'other stop cause has no confirmed clearance'))
    else:
        result.update(automatic_restart_supported=False,
            restart_blocker='STOP_CLEARANCE_PRODUCER_TIME_AND_GENERATION_UNAVAILABLE')
    if green_wait and not current.get('positive'):
        result.setdefault('standstill_deadline_at',previous['returned_at']+.5)
        result['phase']='approaching'
        result['restart_blocker']='awaiting locked green clearance; bounded zero-output pairing'
    elif abs(float(truck['speed'])) < .05:
        result['phase'] = 'holding'
    elif result.get('signal_lock'):
        from core.longitudinal import signal_speed_control
        control = signal_speed_control((decision.get('stopping_evidence') or {}).get('traffic'), truck['speed'])
        own_profile = ((decision.get('stopping_evidence') or {}).get('acc') or {}).get('signal_stop_control') is True
        committed_write = bool(control and control.get('brake_chain_required')
                               and current.get('positive'))
        if (control and not control['terminal'] and not committed_write and own_profile
                and (previous is None or previous.get('phase') == 'approaching')
                and not result.get('other_stop_unverified')):
            result['phase'] = 'approaching'
        elif current.get('positive') and (result.get('phase') != 'approaching'
                or (control and control['terminal']) or committed_write
                or result.get('other_stop_unverified')):
            result['phase'] = 'braking'
    elif result.get('destination_lock'):
        destination = evidence.get('destination')
        if (destination and not destination['terminal']
                and (previous is None or previous.get('phase') == 'approaching')
                and not result.get('other_stop_unverified')):
            result['phase'] = 'approaching'
        elif current.get('positive'):
            result['phase'] = 'braking'
    return result


def profile_approach_allowed(record, decision, truck):
    """Only a current same-head red distance target permits approach recovery.

    This never clears the signal commitment or grants standstill brake authority.
    Missing head, green confirmation, other stops and handoff preserve zero drive.
    """
    from core.longitudinal import signal_speed_control
    traffic = (decision.get('stopping_evidence') or {}).get('traffic') or {}
    signal = traffic.get('signal') or {}
    light = signal.get('candidate') or {}
    lock = record.get('signal_lock') or {}
    acc = (decision.get('stopping_evidence') or {}).get('acc') or {}
    control = signal_speed_control(traffic, truck['speed'])
    destination = (decision.get('stopping_evidence') or {}).get('destination')
    if record.get('destination_lock') and not record.get('signal_lock'):
        return bool(record.get('phase') == 'approaching' and destination
            and not destination['terminal'] and float(truck['speed']) > .05
            and not record.get('other_stop_unverified')
            and not decision.get('refresh_pending') and not decision.get('emergency')
            and tuple(decision.get('context', ())) == tuple(record['command_context']))
    return bool(record.get('phase') == 'approaching' and control and not control['terminal']
        # A preceding positive write must cross the terminal response zone
        # without a zero edge, even if this tick's underspeed PID asks to coast.
        and not (control.get('brake_chain_required') and record.get('brake',0.)>0.)
        and float(truck['speed']) > .05 and not record.get('other_stop_unverified')
        and not decision.get('refresh_pending') and not decision.get('emergency')
        and tuple(decision.get('context', ())) == tuple(record['command_context'])
        and signal.get('lifecycle') == lock.get('lifecycle')
        and light.get('id') == (lock.get('candidate') or {}).get('id')
        and light.get('passage_key') == (lock.get('candidate') or {}).get('passage_key')
        and (light.get('color') in ('red', 'yellow') or light.get('stop_required') is True)
        and acc.get('signal_stop_control') is True
        and 0. <= time.monotonic()-signal.get('observed_at', float('-inf')) <= .5)


def fresh_moving_stop_request(hold, decision, truck):
    """Allow positive pedal adjustment without breaking the acknowledged chain."""
    signal=(((decision.get('stopping_evidence') or {}).get('traffic') or {}).get('signal') or {})
    candidate=signal.get('candidate') or signal.get('stop_candidate') or {}
    lock=hold.get('signal_lock') or {}
    original = consumed_stop_target(hold.get('stop_evidence'))
    same_authority = tuple(decision.get('context',())) == tuple(hold.get('command_context',()))
    # Static authored geometry is not a fresh color observation. It can adjust
    # a still-positive approach brake using the validated command/SDK pair,
    # but never clear a stop or authorize propulsion.
    static_target = (not signal.get('valid') and signal.get('prefab_required') is True
        and candidate.get('head_observed') is False
        and candidate.get('passage_key') == original.get('passage_key')
        and bool(original.get('passage_key')))
    return bool(float(truck.get('speed',0.))>.05 and decision.get('brake',0.)>0
        and same_authority and candidate.get('stop_target_kind')=='derived_directed_curve_entry'
        and (static_target or (signal.get('valid') and (candidate.get('color') in ('red','yellow') or candidate.get('stop_required') is True)
            and candidate.get('passage_key') == (lock.get('candidate') or {}).get('passage_key')
            and signal.get('lifecycle') == lock.get('lifecycle')
            and 0 <= time.monotonic()-signal.get('observed_at',float('-inf')) <= .5)))


def clearance(record, state):
    """Green must be two new acquisitions >=100 ms apart, same locked head.

    This rejects a one-frame color flicker without a long arbitrary delay. The
    producer's clock/generation, not polling frequency, controls confirmation.
    Return an immutable witness; Engine rechecks immediately before release.
    """
    from core.longitudinal import context, launch_rejection, rejection as packet_rejection
    binding = context(state)
    packet = state.get('longitudinal_traffic') or {}
    lock = record.get('signal_lock')
    signal = packet.get('signal') or {}
    candidate = signal.get('candidate') or {}
    now = time.monotonic()
    reason = packet_rejection(packet, binding, now)
    traffic_lock = record.get('traffic_lock')
    traffic_witness = packet.get('stop_clearance')
    if traffic_lock and not reason:
        traffic_reason = traffic_clearance_rejection(traffic_witness, traffic_lock, packet, binding, now)
        if not traffic_reason:
            first = record.get('traffic_clear_candidate')
            if first is None:
                record['traffic_clear_candidate'] = dict(traffic_witness)
            elif (traffic_witness['generation'] > first['generation']
                    and traffic_witness['frame_us'] > first['frame_us']
                    and traffic_witness['observed_at']-first['observed_at'] >= .1):
                others = set(record.get('other_stop_sources') or ())
                others.discard('traffic')
                record['other_stop_sources'] = sorted(others)
                record['other_stop_unverified'] = bool(others)
                if not lock and not others and not launch_rejection(state):
                    record.update(automatic_restart_supported=True, restart_blocker='')
                    return dict(traffic_witness)
        else:
            record.pop('traffic_clear_candidate', None)
        if not lock:
            record.update(automatic_restart_supported=traffic_lock.get('complete') is True,
                restart_blocker=traffic_reason or 'confirming original traffic body clearance acquisitions')
            return None
    if not reason and not lock:
        reason = 'STOP_CLEARANCE_PRODUCER_TIME_AND_GENERATION_UNAVAILABLE'
    if not reason:
        if (not signal.get('valid') or tuple(signal.get('authority', ())) != binding
                or tuple(lock['authority']) != binding
                or signal.get('lifecycle') != lock['lifecycle']
                or candidate.get('id') != lock['candidate']['id']):
            reason = signal.get('reason') or 'locked signal authority, lifecycle or ID is not valid'
        elif candidate.get('passage_key') != lock['candidate'].get('passage_key'):
            reason = 'locked directed prefab passage changed'
        elif (record.get('entry_overrun') or (candidate.get('stop_target_kind')=='derived_directed_curve_entry'
                and candidate.get('distance',0.)+candidate.get('front_allowance_m',0.)
                    +candidate.get('junction_standoff_m',0.)<0.)):
            record['entry_overrun']=True
            reason='directed junction entry passed before stop; driver takeover required'
        elif not 0 <= now-signal.get('observed_at', float('-inf')) <= .5:
            reason = 'locked signal observation expired'
        elif signal.get('generation', 0) <= lock['generation'] or signal.get('frame_us', 0) <= lock['frame_us']:
            reason = 'green is not a new producer frame/generation'
        elif signal['observed_at'] <= lock['observed_at']:
            reason = 'green observation does not follow the locked red acquisition'
        elif candidate.get('color') != 'green':
            reason = 'locked signal is not green'
        elif (candidate.get('stop_required') is True
                or (candidate.get('phase_plan') or {}).get('status') == 'green_dilemma'):
            reason = 'locked green lacks current phase clearance reserve'
        elif record.get('other_stop_unverified'):
            reason = 'another latched stop reason lacks confirmed clearance'
        else:
            reason = launch_rejection(state)
    if reason:
        record.pop('green_candidate', None)
        record.update(automatic_restart_supported=bool(lock) and not record.get('entry_overrun'), restart_blocker=reason)
        return None
    first = record.get('green_candidate')
    if (first is None or signal['generation'] < first['generation']
            or signal['frame_us'] < first['frame_us'] or signal['observed_at'] < first['observed_at']):
        record['green_candidate'] = {k: signal[k] for k in ('generation','frame_us','observed_at')}
        record.update(automatic_restart_supported=True, restart_blocker='confirming stable green acquisitions')
        return None
    if (signal['generation'] <= first['generation'] or signal['frame_us'] <= first['frame_us']
            or signal['observed_at']-first['observed_at'] < .1):
        record.update(automatic_restart_supported=True, restart_blocker='confirming stable green acquisitions')
        return None
    record.update(automatic_restart_supported=True, restart_blocker='')
    return dict(signal)


def resume_rejection(witness, state):
    from core.longitudinal import context, rejection as packet_rejection, launch_rejection
    binding = context(state)
    packet = state.get('longitudinal_traffic') or {}
    signal = packet.get('signal') or {}
    now = time.monotonic()
    reason = packet_rejection(packet, binding, now)
    if reason:
        return reason
    if witness.get('kind') == 'traffic':
        current = packet.get('stop_clearance')
        reason = traffic_clearance_rejection(current,
            witness.get('stop_lock') or {}, packet, binding, now)
        if reason:
            return reason
        if current['generation'] < witness['generation'] or current['observed_at'] < witness['observed_at']:
            return 'traffic clearance regressed during bounded restart'
        reason = launch_rejection(state)
        checked = time.monotonic()
        latest_binding=context(state)
        if latest_binding != binding:
            return 'traffic restart identity changed during clearance reads'
        return reason or packet_rejection(packet, latest_binding, checked) or (
            'traffic clearance expired during restart' if not 0 <= checked-current['observed_at'] <= .5 else '')
    try:
        if (not signal.get('valid') or tuple(signal['authority']) != binding
                or tuple(witness['authority']) != binding
                or signal['lifecycle'] != witness['lifecycle']
                or signal['candidate']['id'] != witness['candidate']['id']
                or signal['candidate'].get('passage_key') != witness['candidate'].get('passage_key')
                or signal['candidate']['color'] != 'green'
                or signal['candidate'].get('stop_required') is True
                or (signal['candidate'].get('phase_plan') or {}).get('status') == 'green_dilemma'
                or signal['generation'] < witness['generation']
                or signal['frame_us'] < witness['frame_us']
                or not 0 <= now-signal['observed_at'] <= .5):
            return 'signal clearance lost during bounded restart'
    except (KeyError, TypeError, ValueError):
        return 'signal clearance incomplete during bounded restart'
    reason = launch_rejection(state)
    if reason:
        return reason
    # All IPC reads precede this clock. Slow reads cannot extend either the
    # signal's lease or the vehicle-based traffic packet lease.
    current_binding = context(state)
    checked_at = time.monotonic()
    if current_binding != binding:
        return 'signal restart identity changed during clearance reads'
    reason = packet_rejection(packet, binding, checked_at)
    if reason:
        return reason
    if not 0 <= checked_at-signal['observed_at'] <= .5:
        return 'signal clearance expired during restart validation'
    return ''


def traffic_clearance_rejection(witness, lock, packet, binding, now):
    try:
        if (not lock.get('complete') or not witness
                or witness.get('status') != 'observed_original_bodies_receding'
                or tuple(witness['authority']) != binding or tuple(lock['authority']) != binding
                or witness['lifecycle'] != lock['lifecycle']
                or witness['generation'] <= lock['generation'] or witness['frame_us'] <= lock['frame_us']
                or {t['id'] for t in witness['targets']} != {t['id'] for t in lock['targets']}
                or not all(t.get('record') and t.get('previous_record') and t['record'] != t['previous_record']
                           and t['minimum_reference_clearance_m'] > 2.6 for t in witness['targets'])
                or not 0 <= now-witness['observed_at'] <= .5
                or witness['observed_at'] <= lock['observed_at']
                or packet.get('traffic_brake', 0) > 0 or packet.get('emergency')):
            return 'original traffic stop lacks new observed-body clearance'
    except (KeyError, TypeError, ValueError):
        return 'original traffic stop clearance is incomplete'
    return ''


def real_auto_wait_allowed(state, truck):
    """Zero ratio while continuously holding or bounded D confirmation only."""
    from core.longitudinal import context
    from core.transmission_mode import selected_mode, vehicle_control_observation_rejection
    if selected_mode(state.get('ets2_transmission_mode') or {},
                     state.get('transmission_mode_preference', 'auto')) != 3:
        return False
    if vehicle_control_observation_rejection(state, truck):
        return False
    if truck.get('gear', -1) != 0 or abs(truck.get('speed', float('inf'))) >= .05 or truck.get('parkBrake') is not False:
        return False
    binding = context(state)
    hold = state.get('simple_auto_service_hold') or {}
    resume = state.get('service_brake_resume') or {}
    now = time.monotonic()
    return bool(approach_green_wait_allowed(hold,state,truck,now) or (hold.get('context') == simple_auto_context(state)
        and tuple(hold.get('command_context', ())) == binding
        and continuous_stop_phase(hold,truck) and hold.get('brake', 0) > 0
        and 0 <= now-hold.get('returned_at', float('-inf')) <= .5)
        or (resume.get('mode') == 3 and tuple(resume.get('context', ())) == binding
            and now <= resume.get('deadline_at', 0.)))
