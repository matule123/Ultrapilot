import pytest
from core.acc_following import following_demand


@pytest.mark.parametrize('speed,lead,gap',[(15.,10.,55.),(20.,10.,90.),(10.,5.,40.)])
def test_rejected_closing_reserve_does_not_change_retained_gap_law(speed,lead,gap):
    result=following_demand(gap,lead,speed)
    old_cap=max(0.,lead+(gap-(12.+2.*speed))/2.)
    assert result['speed_cap_mps']==old_cap
    # Candidate was rejected after paired cut-in/steady-state regressions.
    candidate=max(0.,lead+(gap-(12.+2.*speed)-(speed-lead)**2/2.)/2.)
    assert candidate<old_cap


def test_opening_or_equal_speed_does_not_invent_braking():
    assert following_demand(32.,10.,10.)['speed_cap_mps']==10.
    assert following_demand(32.,15.,10.)['speed_cap_mps']==15.


def test_emergency_demand_is_not_comfort_limited():
    demand=following_demand(10.,0.,20.,include_brake=True)
    assert demand['emergency'] and demand['protective_brake']==1.
