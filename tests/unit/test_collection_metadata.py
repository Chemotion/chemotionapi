"""Collection metadata and taking ownership (M3.6), offline."""
import pytest

from chemotion_api.collection import Collection


class _Res:
    def __init__(self, status, payload=None):
        self.status_code, self._payload, self.text = status, payload, str(payload)

    def json(self):
        return self._payload


class _Session:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def get(self, url, **kw):
        self.calls.append(('get', url, kw.get('params')))
        return self.responses.pop(0)

    def post(self, url, data=None, **kw):
        self.calls.append(('post', url, data))
        return self.responses.pop(0)


def _collection(session):
    col = Collection.__new__(Collection)
    col._id, col.label = 11, 'Target'
    col.get_root = lambda: type('_Root', (), {'_session': session})()
    return col


def test_metadata_round_trip():
    session = _Session(_Res(404, {}), _Res(201, {'id': 1, 'metadata': {'title': 'T'}}),
                       _Res(200, {'id': 1, 'metadata': {'title': 'T'}}))
    col = _collection(session)
    assert col.metadata() is None
    assert col.save_metadata({'title': 'T'}) == {'title': 'T'}
    assert col.metadata() == {'title': 'T'}
    assert session.calls[1] == ('post', '/api/v1/collections/metadata', {'collection_id': 11, 'metadata': {'title': 'T'}})


def test_metadata_of_someone_elses_collection():
    with pytest.raises(ValueError, match='own collections'):
        _collection(_Session(_Res(404, {}))).save_metadata({'title': 'T'})
    with pytest.raises(ValueError, match='dict'):
        _collection(_Session()).save_metadata(['title'])


def test_take_ownership():
    session = _Session(_Res(201, {'collection': {'id': 11, 'label': 'Target'}}))
    assert _collection(session).take_ownership()['label'] == 'Target'
    assert session.calls == [('post', '/api/v1/collection_shares/take_ownership/11', None)]
    with pytest.raises(PermissionError, match='Cannot take ownership'):
        _collection(_Session(_Res(403, {'error': 'You have not been offered ownership'}))).take_ownership()
