import pytest

from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.signals.test_stop_lifecycle import directed_stop
from tests.test_roundabout_intervention_reporting import pedal


@pytest.mark.parametrize('mode',[0,3])
def test_final_hold_floor_respects_existing_pedal_rise_at_60hz(flow,mode):
    values,step=directed_stop(flow,mode)
    state,truck,engine,ap,tick,n,clock,writes,collected=values
    for speed in (2.,.7,.2,.06):step(4,speed)
    before=pedal(engine,'abackward')
    step(0 if mode==0 else 4,.04,dt=1/60)
    after=pedal(engine,'abackward')
    assert after>0 and after-before <= 2.5/60+1e-7
    for _ in range(10):step(0 if mode==0 else 4,0.,dt=1/60)
    assert state.get('autopilot_active')
    assert pedal(engine,'aforward')==0
    assert pedal(engine,'abackward')>=state.get('simple_auto_service_hold')['braking_peak']-1e-7
