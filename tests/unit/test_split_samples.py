"""Server-side sample splits (M2.2), offline.

`POST /api/v1/samples/subsamples` answers `{}`, so the client finds the new subsamples among the
collection's newest samples: ids above the newest one before the split, labelled `<parent>-<n>`.
"""
import pytest

import chemotion_api.collection as collection_module
from chemotion_api.collection import Collection


class _Res:
    def __init__(self, status, payload=None):
        self.status_code, self._payload, self.text = status, payload, str(payload)

    def json(self):
        return self._payload


class _Session:
    def __init__(self, before, after, post_status=201):
        self.lists, self.post_status, self.calls = [before, after], post_status, []

    def get(self, url, params=None, **kw):
        self.calls.append(('get', url, params))
        return _Res(200, {'samples': self.lists.pop(0) if self.lists else []})

    def post(self, url, data=None, **kw):
        self.calls.append(('post', url, data))
        return _Res(self.post_status, {})


class _Sample:
    element_type, is_new = 'sample', False

    def __init__(self, sample_id, label):
        self.id, self.short_label = sample_id, label


@pytest.fixture()
def loaded(monkeypatch):
    ids = []

    class _Loader:
        def __init__(self, *args, **kwargs):
            pass

        def load_element(self, element_id):
            ids.append(element_id)
            return ('loaded', element_id)

    monkeypatch.setattr(collection_module, 'ElementSet', _Loader)
    return ids


def _collection(session, col_id=11):
    col = Collection.__new__(Collection)
    col._id, col.label = col_id, 'Source'
    root = type('_Root', (), {'_session': session,
                              '_element_manager': type('_EM', (), {'all_classes': {'sample': {}}})()})()
    col.get_root = lambda: root
    return col


def test_new_subsamples_are_found_by_label_above_the_previous_newest_id(loaded):
    before = [{'id': 50, 'short_label': 'API-5'}, {'id': 20, 'short_label': 'API-2'}]
    after = [{'id': 53, 'short_label': 'API-2-1'}, {'id': 52, 'short_label': 'API-5-3'},
             {'id': 51, 'short_label': 'API-9'}, {'id': 50, 'short_label': 'API-5'},
             {'id': 40, 'short_label': 'API-5-2'}]  # an older split of API-5: must not be picked
    session = _Session(before, after)
    result = _collection(session).split_samples(_Sample(5, 'API-5'), _Sample(2, 'API-2'))
    assert result == [('loaded', 52), ('loaded', 53)]
    post = next(c for c in session.calls if c[0] == 'post')
    assert post[1] == '/api/v1/samples/subsamples'
    assert post[2] == {'ui_state': {'sample': {'all': False, 'included_ids': [5, 2], 'excluded_ids': []},
                                    'currentCollectionId': 11}}


def test_a_label_prefix_is_not_a_match(loaded):
    """API-1 must not claim API-10-1 (another parent's subsample)."""
    session = _Session([{'id': 9, 'short_label': 'x'}], [{'id': 10, 'short_label': 'API-10-1'}])
    with pytest.raises(ConnectionError, match='no new subsample of API-1'):
        _collection(session).split_samples(_Sample(1, 'API-1'))


def test_a_subsample_that_never_shows_up_is_an_error_saying_the_split_happened(loaded):
    with pytest.raises(ConnectionError, match='split request was accepted'):
        _collection(_Session([], [])).split_samples(_Sample(1, 'API-1'))


@pytest.mark.parametrize('samples, match', [
    ((), 'No samples'),
    ((type('_R', (), {'element_type': 'reaction', 'id': 1, 'is_new': False})(),), 'Only samples'),
    ((_Sample(None, 'API-1'),), 'not been saved'),
])
def test_bad_input_sends_nothing(samples, match, loaded):
    session = _Session([], [])
    with pytest.raises(ValueError, match=match):
        _collection(session).split_samples(*samples)
    assert session.calls == []


def test_a_read_only_collection_is_a_permission_error(loaded):
    with pytest.raises(PermissionError):
        _collection(_Session([], [], post_status=401)).split_samples(_Sample(1, 'API-1'))
