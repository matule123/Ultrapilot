"""Offline incident correlation must not invent evidence or double-count twins."""
from tools.package_oct24_driving_incidents import case_for,unique


def test_same_engine_and_autopilot_fault_belongs_to_one_incident():
    assert case_for(43409.8352861)==case_for(43409.8372004)=='02-201351-acc42'


def test_separate_activation_faults_remain_separate():
    assert case_for(43454.0447587)=='03-201435-hold'
    assert case_for(43501.2854872)=='04-201522-acc39'


def test_unwitnessed_time_not_forced_into_nearest_known_fault():
    assert case_for(None) is None
    assert case_for(43363.0) is None


def test_deduplicate_identical_data_not_conflicting_same_sequence():
    before={'sequence':1,'brake':.2,'unknown':None}
    after={'sequence':1,'brake':.4,'unknown':None}
    rows=unique([before,dict(reversed(list(before.items()))),after])
    assert rows==[before,after]
    assert rows[0]['unknown'] is None
