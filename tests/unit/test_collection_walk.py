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


def test_label_aliases():
    col = _tree().get_collection('/A/A1')
    assert col.name == col.get_label() == col.get_name() == col.label == 'A1'


def test_an_account_without_an_all_collection_says_so():
    """A 3.1.2 server answers `{"collection": null}` for an account that owns nothing.

    Subscripting that raised `TypeError: 'NoneType' object is not subscriptable` from inside
    `get_root_collection()`, which says nothing about the cause.
    """
    import json

    import pytest

    class _Session:
        def get(self, url, **_):
            body = {'collection': None} if url.endswith('/all') else []
            return SimpleNamespace(status_code=200, content=json.dumps(body).encode(),
                                   json=lambda: body)

    root = RootCollection(_Session())
    with pytest.raises(ValueError, match="no 'All' collection"):
        root.load_collection()
