"""The same pure presentation function called by the actual HUD painter."""
from unittest.mock import patch

from ui.visualization import traffic_light_presentation


def test_fresh_producer_timed_red_detection_is_visible_but_not_control():
    head = dict(id=9,color='red',detection_basis='producer_timed_unassigned',
                observation_timestamp=1000.,producer_generation=5,producer_frame_us=9)
    with patch('time.monotonic',return_value=1000.1):
        shown,color,label,only = traffic_light_presentation(None,head,{'requires_takeover':True})
    assert shown == head and color == 'red'
    assert only and 'smer nepotvrdený' in label


def test_untimed_or_expired_detection_does_not_claim_current_color():
    for stamp in (None,999.,1001.):
        head = dict(id=9,color='red',detection_basis='producer_timed_unassigned',
                    observation_timestamp=stamp,producer_generation=5,producer_frame_us=9)
        with patch('time.monotonic',return_value=1000.1):
            assert traffic_light_presentation(None,head,{})[1] == 'off'


def test_hud_uses_same_qualified_control_identity_over_detection():
    head = dict(id=3,color='red',head_observed=True)
    shown,color,label,only = traffic_light_presentation(head,dict(id=9,color='green'),{})
    assert shown == head and color == 'red' and not only
