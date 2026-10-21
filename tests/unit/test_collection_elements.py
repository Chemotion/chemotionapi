from types import SimpleNamespace

import pytest

from chemotion_api.collection import RootCollection
from chemotion_api.elements.abstract_element import AbstractElement


class _Session:
    def __init__(self):
        self.calls = []

    def get_json_session_header(self):
        return {'Content-Type': 'application/json'}

    def _send(self, method, url, data, headers):
        assert headers['Content-Type'] == 'application/json'
        self.calls.append((method, url, data))
        return SimpleNamespace(status_code=204, text='')

    def put(self, url, data, headers):
        return self._send('put', url, data, headers)

    def post(self, url, data, headers):
        return self._send('post', url, data, headers)

    def delete(self, url, data, headers):
        return self._send('delete', url, data, headers)


def _setup():
    session = _Session()
    root = RootCollection(session)
    root._id = 1
    root._set_children([{'id': 2, 'label': 'A'}, {'id': 3, 'label': 'B'}])
    return session, root, root.get_collection('/A'), root.get_collection('/B')


def _element(element_type, id):
    return AbstractElement(SimpleNamespace(), SimpleNamespace(_host_url=''), id=id, element_type=element_type,
                           avoid_load=True)


def test_move_groups_ids_by_type():
    session, root, a, b = _setup()
    a.move_elements(b, _element('sample', 5), _element('sample', 6), _element('reaction', 7))
    assert session.calls == [('put', '/api/v1/collections/elements', {
        'ui_state': {'currentCollection': {'id': 2, 'is_sync_to_me': False},
                     'sample': {'checkedAll': False, 'checkedIds': [5, 6]},
                     'reaction': {'checkedAll': False, 'checkedIds': [7]}},
        'collection_id': 3, 'is_sync_to_me': False})]


def test_element_shortcuts():
    session, root, a, b = _setup()
    sample = _element('sample', 5)
    sample.assign_to(b)
    sample.remove_from(a)
    assert [(m, d['ui_state']['currentCollection']['id'], d.get('collection_id')) for m, _, d in session.calls] == \
           [('post', 1, 3), ('delete', 2, None)]


def test_unsaved_element_and_error():
    session, root, a, b = _setup()
    with pytest.raises(ValueError):
        a.move_elements(b, _element('sample', None))
    session._send = lambda *args: SimpleNamespace(status_code=401, text='Unauthorized')
    with pytest.raises(ConnectionError):
        a.remove_elements(_element('sample', 5))
