"""Signed measurements must not shrink the existing standstill reserves."""
import pytest
from core.acc_following import following_demand,MIN_GAP_M


@pytest.mark.parametrize('speed',[-.022485010,-.10])
def test_small_signed_speed_keeps_minimum_reference_headway(speed):
    result=following_demand(20.,0.,speed,include_brake=True)
    stationary=following_demand(20.,0.,0.,include_brake=True)
    assert result['desired_gap_m']>=MIN_GAP_M
    assert result['protective_brake']>=stationary['protective_brake']
