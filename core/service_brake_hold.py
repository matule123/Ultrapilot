"""Engine-owned continuous service-brake state, not another pedal regulator.

Software continuity supports the user-observed gearbox model only. It does not
prove DLL consumption or hill hold. Only the versioned producer-timed signal
sidecar can authorize release; legacy semaphore/actor buffers cannot do so.
"""
import time

from core.transmission_mode import simple_auto_context


def receipt(controller):
    if (getattr(controller, 'mode', None) != 'SCS_SDK'
            or not getattr(getattr(controller, 'scs', None), 'connected', False)):
        return {}
    return dict(getattr(controller.scs, '_brake_write_receipt', {}))


def rejection(record, controller, state, truck):
    from core.longitudinal import context
    if (record['context'] != simple_auto_context(state)
            or tuple(record['command_context']) != context(state)):
        return 'continuous service brake activation or route identity changed'
    current = receipt(controller)
    if not current.get('positive') or current.get('chain') != record['chain']:
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
    evidence = decision.get('stopping_evidence') or {}
    traffic = evidence.get('traffic') or {}
    acc = evidence.get('acc') or {}
    policy = evidence.get('policy') or {}
    return bool(traffic.get('light_brake', 0) > 0
                or acc.get('following_status') in ('candidate', 'source_lost')
                or policy.get('reason') == 'toll stop/payment')


def after_write(previous, controller, forward_context, truck, decision, now):
    if not decision or decision.get('emergency'):
        return None
    current = receipt(controller)
    if not current.get('positive'):
        return None
    if previous and current['chain'] == previous['chain']:
        result = dict(previous)
    elif (float(truck['speed']) > .05 and int(truck['gear']) > 0
            and truck.get('parkBrake') is False and planned_stop(decision)):
        # Identities are those validated BEFORE this write. Never label a write
        # with a later IPC snapshot that may already belong to another route.
        result = dict(context=forward_context, chain=current['chain'],
                      command_context=tuple(decision['context']),
                      started_frame=truck['sdkFrameTimeUs'], started_at=now,
                      phase='braking', stop_evidence=decision['stopping_evidence'])
        evidence = decision['stopping_evidence']
        light = (evidence.get('traffic') or {}).get('light') or {}
        result['stop_reason'] = dict(source=decision['source'], reason=decision['reason'],
            signal_id=light.get('id'), signal_color=light.get('color'),
            observation_timestamp=decision['observation_timestamp'])
    else:
        return None
    if 'signal_lock' not in result:
        signal = ((result['stop_evidence'].get('traffic') or {}).get('signal') or {})
        if signal.get('valid') and (signal.get('candidate') or {}).get('color') == 'red':
            result['signal_lock'] = dict(authority=tuple(decision['context']),
                lifecycle=signal['lifecycle'], generation=signal['generation'],
                frame_us=signal['frame_us'], observed_at=signal['observed_at'],
                candidate=dict(signal['candidate']))
    # A following/toll stop cannot be cleared by disappearance of its producer.
    evidence = decision.get('stopping_evidence') or {}
    acc = evidence.get('acc') or {}
    traffic = evidence.get('traffic') or {}
    policy = evidence.get('policy') or {}
    result['other_stop_unverified'] = bool(result.get('other_stop_unverified')
        or acc.get('following_status') in ('candidate', 'source_lost')
        or traffic.get('traffic_brake', 0) > 0
        or policy.get('reason') == 'toll stop/payment')
    result.update(brake=current['value'], returned_at=current['returned_at'],
                  write_sequence=current['sequence'], sdk_frame_us=truck['sdkFrameTimeUs'],
                  game_consumption_verified=False)
    if result.get('signal_lock'):
        result.setdefault('automatic_restart_supported', True)
        result.setdefault('restart_blocker', 'locked signal is not green')
    else:
        result.update(automatic_restart_supported=False,
            restart_blocker='STOP_CLEARANCE_PRODUCER_TIME_AND_GENERATION_UNAVAILABLE')
    if abs(float(truck['speed'])) < .05:
        result['phase'] = 'holding'
    return result


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
    if not reason and not lock:
        reason = 'STOP_CLEARANCE_PRODUCER_TIME_AND_GENERATION_UNAVAILABLE'
    if not reason:
        if (not signal.get('valid') or tuple(signal.get('authority', ())) != binding
                or tuple(lock['authority']) != binding
                or signal.get('lifecycle') != lock['lifecycle']
                or candidate.get('id') != lock['candidate']['id']):
            reason = signal.get('reason') or 'locked signal authority, lifecycle or ID is not valid'
        elif not 0 <= now-signal.get('observed_at', float('-inf')) <= .5:
            reason = 'locked signal observation expired'
        elif signal.get('generation', 0) <= lock['generation'] or signal.get('frame_us', 0) <= lock['frame_us']:
            reason = 'green is not a new producer frame/generation'
        elif signal['observed_at'] <= lock['observed_at']:
            reason = 'green observation does not follow the locked red acquisition'
        elif candidate.get('color') != 'green':
            reason = 'locked signal is not green'
        elif record.get('other_stop_unverified'):
            reason = 'another latched stop reason lacks confirmed clearance'
        else:
            reason = launch_rejection(state)
    if reason:
        record.pop('green_candidate', None)
        record.update(automatic_restart_supported=bool(lock), restart_blocker=reason)
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
    try:
        if (not signal.get('valid') or tuple(signal['authority']) != binding
                or tuple(witness['authority']) != binding
                or signal['lifecycle'] != witness['lifecycle']
                or signal['candidate']['id'] != witness['candidate']['id']
                or signal['candidate']['color'] != 'green'
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
    return bool((hold.get('context') == simple_auto_context(state)
        and tuple(hold.get('command_context', ())) == binding
        and hold.get('phase') in ('braking','holding') and hold.get('brake', 0) > 0
        and 0 <= now-hold.get('returned_at', float('-inf')) <= .5)
        or (resume.get('mode') == 3 and tuple(resume.get('context', ())) == binding
            and now <= resume.get('deadline_at', 0.)))
