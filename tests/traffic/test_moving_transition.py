"""Pinned October 29 packets plus production native/ACC/Engine output cases."""
import copy
import json
from pathlib import Path
from unittest.mock import patch
import pytest

from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.lifecycle.test_joint_regressions import joint  # noqa: F401
from tests.traffic.test_crossing_dev_hud import step, crossing


def historical():
    return json.loads((Path(__file__).parent.parent/'fixtures/oct29-motion-transition.json').read_text(encoding='utf-8'))


def test_exact_consumed_oct29_pair_discards_drive_without_technical_disable():
    from core.longitudinal import signal_drive_write_guard, write_rejection
    f=historical();values={'longitudinal_traffic':f['new_traffic']}
    class State:
        def get(self,key,default=None):return copy.deepcopy(values.get(key,default))
    selected=copy.deepcopy(f['selected'])
    # New arbitration carries this exact already-consumed owner as control
    # provenance. The original replay stores it in ACC 16994, not guessed ID.
    selected['required_acc_owner']=f['acc']['following_owner']
    truck=dict(speed=f['source']['actual_speed_mps'])
    with patch('time.monotonic',return_value=f['checked_at']):
        result,reason=signal_drive_write_guard(State(),truck,selected,tuple(selected['context']))
    assert reason=='',reason
    assert result['throttle']==0. and result['brake']==selected['brake']
    assert result['computed_at']==selected['computed_at']
    assert result['observation_timestamp']==selected['observation_timestamp']
    assert result['expires_at']<=selected['expires_at']
    assert not write_rejection(result,tuple(selected['context']),f['checked_at'])


@pytest.mark.parametrize('fault',['no_completion','wrong_owner','old','future','foreign','missing','emergency'])
def test_exact_pair_cannot_infer_clearance_from_empty_list_or_continuity(fault):
    from core.longitudinal import signal_drive_write_guard
    f=historical();traffic=f['new_traffic'];value=f['selected']
    value['required_acc_owner']=f['acc']['following_owner']
    if fault=='no_completion':
        traffic['following']['constraint_completions']=[];traffic['following']['constraint_completion']=None
    elif fault=='wrong_owner':value['required_acc_owner']['acquired_generation']+=1
    elif fault=='old':traffic['observation_timestamp']-=1.
    elif fault=='future':traffic['computed_at']=f['checked_at']+.01
    elif fault=='foreign':traffic['context'][0]='other'
    elif fault=='emergency':traffic['traffic_brake']=1.
    class State:
        def get(self,key,default=None):return copy.deepcopy(traffic) if key=='longitudinal_traffic' and fault!='missing' else default
    with patch('time.monotonic',return_value=f['checked_at']):
        result,reason=signal_drive_write_guard(State(),{'speed':.1},value,tuple(value['context']))
    if fault=='emergency':
        assert not reason
        assert result['throttle']==0. and result['brake']==1. and result['emergency']
    else:assert reason


def test_original_crossing_completion_between_arbitration_and_write(joint,monkeypatch):
    """Real native producer/selector/Policy/ACC/AP/Engine/Controller backend.

    Spatial fixture is modeled; exact historical pair is tested separately.
    Publish a qualified completion in the last-read race, without changing
    the original required owner or granting clearance from an empty list.
    """
    from core import longitudinal
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    actor=crossing(at=32.,arrival=4.1,aid=66)
    step(joint,[actor],1)
    for gen in range(2,5):step(joint,[actor],gen,speed=1.5)
    assert acc._followed_target and acc._following_kind=='crossing'
    assert physical('aforward')>0.
    original=longitudinal.signal_drive_write_guard
    def publication(*args,**kwargs):
        packet=state.get('longitudinal_traffic')
        # Exact producer-shaped receipt, with the same retained owner and
        # original acquisition clock. Not a missing-actor/clear-road assertion.
        follow=packet['following'];proof=dict(follow['retained_target_continuity'],
            status='observed_original_crossing_model_ended',kind='crossing')
        follow.update(constraint_completion=proof,constraint_completions=[proof],
            motion_constraint=None,crossing=dict(status='no_conflict_unproven_coverage',conflicts=[],brake=0.))
        packet['motion_constraint']=None;state.set('longitudinal_traffic',packet)
        return original(*args,**kwargs)
    start=len(writes)
    monkeypatch.setattr(longitudinal,'signal_drive_write_guard',publication)
    engine._flush_controls()
    assert state.get('autopilot_active'),state.get('autopilot_intervention')
    assert not state.get('autopilot_intervention')
    assert physical('aforward')==0.
    assert not any(c=='aforward' and v>0 for _,c,v in writes[start:])
    monkeypatch.setattr(longitudinal,'signal_drive_write_guard',original)
    # ACC consumes the same new evidence on its next independent tick.
    acc.on_tick(.033);policy.on_tick(.033);ap.on_tick(.033);engine._flush_controls()
    assert not acc._followed_target
    assert state.get('autopilot_active') and not state.get('safety_hazard_active')
    assert not (physical('aforward')>0 and physical('abackward')>0)
