"""Reuse exact immutable geometry, never cached localization or authority."""
import math
from unittest import mock

import pytest

from core.navigation.road_network import RoadNetwork


def network():
    net = RoadNetwork()
    net.loaded = True
    net.nodes.update({1: (100., 200.), 2: (110., 200.)})
    net.node_alt.update({1: 10., 2: 13.})
    net.node_rot.update({1: 0., 2: 0.})
    net._prefab_desc['fixture'] = (
        ((0., 0., 0.), (10., 0., 0.)),
        ((0., 0., 10., 0., 1., 0., 1., 0.),), ())
    net._prefab_lane_data['fixture'] = {
        'nodes': ({'y': 2.}, {'y': 2.}),
        'curves': ({'start_y': 2., 'end_y': 5.},),
    }
    return net, ('fixture', (1, 2), 0, True)


def test_repeated_localization_geometry_does_not_resample_hermite():
    net, instance = network()
    with mock.patch.object(net, '_hermite_curve', wraps=net._hermite_curve) as sample:
        first = net._prefab_curve_chain_3d(instance, (0,))
        assert net._prefab_curve_chain_3d(instance, (0,)) == first
        assert sample.call_count == 1


@pytest.mark.parametrize('change', ['position', 'altitude', 'rotation', 'curve',
                                   'curve_height', 'node_height', 'descriptor'])
def test_cache_invalidates_for_each_physical_geometry_input(change):
    net, instance = network()
    original = net._prefab_curve_chain_3d(instance, (0,))
    if change == 'position':
        net.nodes[1] = (104., 200.)
    elif change == 'altitude':
        net.node_alt[2] += 1.
    elif change == 'rotation':
        net.node_rot[1] = math.pi / 2
    elif change == 'curve':
        nodes, curves, links = net._prefab_desc['fixture']
        net._prefab_desc['fixture'] = (nodes, ((0., 0., 10., 1., 1., 0., 1., 0.),), links)
    elif change == 'curve_height':
        net._prefab_lane_data['fixture']['curves'][0]['end_y'] += 1.
    elif change == 'node_height':
        net._prefab_lane_data['fixture']['nodes'][0]['y'] += 1.
    else:
        _nodes, curves, links = net._prefab_desc['fixture']
        net._prefab_desc['fixture'] = (((1., 0., 0.), (10., 0., 0.)), curves, links)
    actual = net._prefab_curve_chain_3d(instance, (0,))
    assert actual != original
    assert actual == net._compute_prefab_curve_chain_3d(instance, (0,))


def test_geometry_cache_has_a_hard_entry_and_point_bound():
    net, instance = network()
    for index in range(600):
        net.nodes[1] = (100. + index, 200.)
        net._prefab_curve_chain_3d(instance, (0,))
    assert len(net._prefab_geometry_cache) <= 512
    assert net._prefab_geometry_cache_points <= 65536
    assert net._prefab_geometry_cache_points == sum(
        len(points) for points in net._prefab_geometry_cache.values())
