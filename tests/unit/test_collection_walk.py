from types import SimpleNamespace

from chemotion_api.collection import RootCollection


def _tree():
    root = RootCollection(SimpleNamespace())
    root._set_children([
        {'id': 1, 'label': 'A', 'children': [
            {'id': 2, 'label': 'A1', 'children': [{'id': 3, 'label': 'A1a'}]},
            {'id': 4, 'label': 'A2'},
        ]},
        {'id': 5, 'label': 'B'},
    ])
    return root


def test_walk_all_pre_order():
    assert [c.get_path() for c in _tree().walk()] == ['/A', '/A/A1', '/A/A1/A1a', '/A/A2', '/B']


def test_walk_include_self_and_max_depth():
    root = _tree()
    assert [c.label for c in root.walk(max_depth=1)] == ['A', 'B']
    assert [c.label for c in root.walk(include_self=True, max_depth=0)] == ['root']
    assert [c.label for c in root.get_collection('/A').walk(include_self=True)] == ['A', 'A1', 'A1a', 'A2']
