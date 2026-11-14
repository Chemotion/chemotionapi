"""Bulk-created and split wellplates are found by name among the newest (M3.7), offline."""
import pytest

from chemotion_api.collection import Collection


class _Res:
    def __init__(self, status, payload=None):
        self.status_code, self._payload, self.text = status, payload, str(payload)

    def json(self):
        return self._payload


class _Session:
    def __init__(self, lists, post_status=201):
        self.lists, self.post_status, self.posts = list(lists), post_status, []

    def get(self, url, params=None, **kw):
        assert url == '/api/v1/wellplates'
        rows = self.lists.pop(0) if len(self.lists) > 1 else self.lists[0]
        return _Res(200, {'wellplates': rows if params['page'] == 1 else []})

    def post(self, url, data=None, **kw):
        self.posts.append((url, data))
        return _Res(self.post_status, {})


class _Plate:
    element_type, is_new = 'wellplate', False

    def __init__(self, wid, name):
        self.id, self.name, self.properties = wid, name, {'name': name}


def _collection(session, loaded):
    col = Collection.__new__(Collection)
    col._id, col.label = 11, 'Target'
    manager = type('_M', (), {'all_classes': {'wellplate': {}}})()
    root = type('_Root', (), {'_session': session, '_element_manager': manager})()
    col.get_root = lambda: root
    import chemotion_api.collection as module
    loaded.clear()

    class _Set:
        def __init__(self, *a):
            pass

        def load_element(self, wid):
            loaded.append(wid)
            return _Plate(wid, '?')
    module_set = module.ElementSet
    module.ElementSet = _Set
    return col, lambda: setattr(module, 'ElementSet', module_set)


def test_create_wellplates_finds_the_new_ones_in_order():
    old = [{'id': 5, 'name': 'Plate 1'}]
    after = [{'id': 8, 'name': 'Plate 2'}, {'id': 7, 'name': 'Plate 1'}] + old
    session = _Session([old, after])
    loaded = []
    col, restore = _collection(session, loaded)
    try:
        col.create_wellplates('Plate 1', 'Plate 2')
    finally:
        restore()
    assert loaded == [7, 8]  # the old "Plate 1" (id 5) is not taken
    assert session.posts == [('/api/v1/wellplates/bulk', {'wellplates': [
        {'name': 'Plate 1', 'collection_id': 11, 'wells': []}, {'name': 'Plate 2', 'collection_id': 11, 'wells': []}]})]


def test_split_wellplates_sends_the_ui_selection_and_tolerates_a_touched_source():
    old = [{'id': 5, 'name': 'P'}]
    after = [{'id': 5, 'name': 'P'}, {'id': 9, 'name': 'P-Split'}]  # the source sorted first
    session = _Session([old, after])
    loaded = []
    col, restore = _collection(session, loaded)
    try:
        col.split_wellplates(_Plate(5, 'P'))
    finally:
        restore()
    assert loaded == [9]
    assert session.posts[0] == ('/api/v1/wellplates/subwellplates', {'ui_state': {
        'wellplate': {'all': False, 'included_ids': [5], 'excluded_ids': []}, 'currentCollectionId': 11}})


def test_a_missing_result_and_refusals():
    loaded = []
    col, restore = _collection(_Session([[]]), loaded)
    try:
        with pytest.raises(ConnectionError, match='no new wellplate "X"'):
            col.create_wellplates('X')
        with pytest.raises(ValueError):
            col.create_wellplates('')
        with pytest.raises(ValueError, match='Only wellplates'):
            col.split_wellplates(type('S', (), {'element_type': 'sample', 'id': 1})())
    finally:
        restore()
    col, restore = _collection(_Session([[]], post_status=401), loaded)
    try:
        with pytest.raises(PermissionError):
            col.create_wellplates('X')
    finally:
        restore()
