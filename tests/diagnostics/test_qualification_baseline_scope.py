"""Only the explicitly approved off-baseline completeness condition changes."""
import pytest
from tools.assess_oct25_traffic_qualification import worker_contract_valid


@pytest.mark.parametrize('enabled,approved,missing,errors,capacity,expected',[
    (False,False,2,[],1,False),
    (False,True,2,[],1,True),
    (True,True,2,[],1,False),
    (True,False,0,[],1,True),
    (True,True,0,[],1,True),
    (False,True,0,['error'],1,False),
    (False,True,2,[],2,False),
    (True,True,0,[],2,False),
])
def test_worker_contract_keeps_enabled_loss_errors_and_queue_gates(enabled,approved,missing,errors,capacity,expected):
    worker=dict(queue_capacity=capacity,reported_missing_pedal_events=missing,errors=errors)
    assert worker_contract_valid(worker,enabled=enabled,baseline_scope_approved=approved) is expected
