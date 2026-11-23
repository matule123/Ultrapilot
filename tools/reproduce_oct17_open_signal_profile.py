"""Original Oct17 target-rebound reproducer, also collected by completion tests.

Two failures on the entry runtime are retained in the audit logs. Keep this
assertion unchanged while fixing the production distance reference; no xfail.
"""
import pytest
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.signals.test_signal_timing import timing_flow


@pytest.mark.parametrize('mode',[0,3])
def test_same_red_stop_target_cannot_rebound_as_vehicle_slows(flow,tmp_path,mode):
    values,step=timing_flow(flow,tmp_path,mode)
    state,truck,engine,ap,tick,n,clock,writes,collected=values
    targets=[]
    for gen,(distance,speed) in enumerate(((40.,9.),(38.,7.42),(32.4,4.9),(27.3,5.71)),start=50):
        step(gen,'red',speed=speed,progress=42.-distance)
        targets.append(state.get('longitudinal_acc')['constrained_speed_kmh'])
        assert state.get('autopilot_active'),state.get('autopilot_disable_reason')
    assert all(b<=a+1e-9 for a,b in zip(targets,targets[1:])), targets
