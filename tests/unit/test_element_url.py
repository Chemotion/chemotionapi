from types import SimpleNamespace

import pytest

from chemotion_api.elements.abstract_element import AbstractElement
from chemotion_api.elements.generic_element import GenericElement

SESSION = SimpleNamespace(_host_url='http://localhost:3000', host_url='http://localhost:3000')


def _element(cls=AbstractElement, element_type='sample', id=5, json_data=None):
    element = cls(SimpleNamespace(), SESSION, id=id, element_type=element_type, avoid_load=True)
    element.json_data = json_data or {}
    return element


def _labels(*labels):
    return {'tag': {'taggable_data': {'collection_labels': list(labels)}}}


def test_url_uses_owned_collection():
    element = _element(json_data=_labels({'id': 3, 'is_shared': True, 'is_synchronized': False},
                                         {'id': 4, 'is_shared': False, 'is_synchronized': False}))
    assert element.url() == 'http://localhost:3000/mydb/collection/4/sample/5'


def test_url_falls_back_to_all_collection():
    assert _element(element_type='reaction', json_data={'tag': None}).url() == \
           'http://localhost:3000/mydb/collection/all/reaction/5'


def test_url_with_collection_id_and_generic_type():
    element = _element(GenericElement, element_type='plan', json_data={'collection_id': 7})
    assert element.url() == 'http://localhost:3000/mydb/collection/7/plan/5'
    assert element.url(9) == 'http://localhost:3000/mydb/collection/9/plan/5'


def test_open_new_tab(monkeypatch):
    opened = []
    monkeypatch.setattr('webbrowser.open_new_tab', opened.append)
    url = _element(element_type='research_plan').open()
    assert opened == [url] == ['http://localhost:3000/mydb/collection/all/research_plan/5']


def test_unsaved_element_cannot_be_opened():
    with pytest.raises(ValueError):
        _element(id=None).open()
