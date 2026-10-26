from types import SimpleNamespace

import pytest

from chemotion_api.collection import RootCollection


def _tree():
    root = RootCollection(SimpleNamespace())
    root._set_children([
        {'id': 1, 'label': 'Projects', 'children': [
            {'id': 2, 'label': 'CO2 reduction'},
        ]},
        {'id': 3, 'label': 'Other'},
    ])
    return root


@pytest.mark.parametrize('path', ['/Projects/CO2 reduction', '/projects/co2 reduction', 'PROJECTS/Co2 Reduction',
                                  ['Projects', 'CO2 reduction'], ['projects', 'co2 REDUCTION']])
def test_get_collection_case_insensitive(path):
    assert _tree().get_collection(path, case_insensitive=True).id == 2


def test_get_collection_relative_case_insensitive():
    root = _tree()
    assert root.get_collection('/Projects').get_collection('CO2 reduction', case_insensitive=True).id == 2


def test_get_collection_case_sensitive_by_default():
    with pytest.raises(ModuleNotFoundError):
        _tree().get_collection('/projects/co2 reduction')


def test_move_and_delete_case_insensitive():
    root = _tree()
    root.move('/Projects/CO2 reduction', '/Other', case_insensitive=True)
    assert root.get_collection('/Other/CO2 reduction').id == 2
    root.delete('/other/co2 REDUCTION', case_insensitive=True)
    assert [c.label for c in root.get_collection('/Other').children] == []
