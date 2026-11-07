"""Sample import (M2.5), offline: upload, then wait for the job's completion notification."""
import pytest

import chemotion_api.collection as collection_module
from chemotion_api.collection import Collection, ImportResult

DONE = {'id': 9, 'subject': 'Import Samples Completed',
        'content': {'data': 'Created 2 samples. \nImport successful! ', 'level': 'success',
                    'channel_subject': 'Import Samples Completed', 'collection_id': 11}}


class _Res:
    def __init__(self, status, payload=None):
        self.status_code, self._payload, self.text = status, payload, str(payload)

    def json(self):
        return self._payload


class _Session:
    def __init__(self, message_lists, post_status=201):
        self.message_lists, self.post_status, self.posts = list(message_lists), post_status, []

    def get(self, url, params=None, **kw):
        assert url == '/api/v1/messages/list' and params == {'is_ack': 9}
        msgs = self.message_lists.pop(0) if len(self.message_lists) > 1 else self.message_lists[0]
        return _Res(200, {'messages': msgs})

    def post(self, url, data=None, files=None, **kw):
        self.posts.append((url, data, sorted(files)))
        return _Res(self.post_status, {'status': 'in progress'})


def _collection(session, col_id=11):
    col = Collection.__new__(Collection)
    col._id, col.label = col_id, 'Target'
    root = type('_Root', (), {'_session': session})()
    col.get_root = lambda: root
    return col


@pytest.fixture()
def sdf(tmp_path):
    path = tmp_path / 'two.sdf'
    path.write_text('M  END\n$$$$\n')
    return str(path)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(collection_module.time, 'sleep', lambda s: None)


def test_upload_then_return_the_new_report(sdf):
    old = dict(DONE, id=3)
    other_collection = dict(DONE, id=10, content=dict(DONE['content'], collection_id=99))
    session = _Session([[old], [old, other_collection], [old, other_collection, DONE]])
    result = _collection(session).import_samples(sdf)
    assert result == ImportResult(level='success', message='Created 2 samples. \nImport successful!')
    assert result.ok
    (url, data, files), = session.posts
    assert url == '/api/v1/samples/import' and files == ['file']
    assert data == {'currentCollectionId': 11, 'import_type': 'sample'}


def test_chemicals_and_not_waiting(sdf):
    session = _Session([[]])
    assert _collection(session).import_samples(sdf, as_chemicals=True, wait=False) is None
    assert session.posts[0][1]['import_type'] == 'chemical'


def test_a_report_that_never_comes_times_out(sdf, monkeypatch):
    clock = iter(range(0, 1000, 100))
    monkeypatch.setattr(collection_module.time, 'monotonic', lambda: next(clock))
    with pytest.raises(TimeoutError, match='may still be running'):
        _collection(_Session([[]])).import_samples(sdf, timeout=250)


def test_unsupported_files_send_nothing(tmp_path):
    path = tmp_path / 'data.txt'
    path.write_text('x')
    session = _Session([[]])
    with pytest.raises(ValueError, match='.sdf, .mol, .csv, .xlsx'):
        _collection(session).import_samples(str(path))
    assert session.posts == []


def test_someone_elses_collection_is_a_permission_error(sdf):
    with pytest.raises(PermissionError):
        _collection(_Session([[]], post_status=401)).import_samples(sdf)


def test_a_report_link_is_kept():
    message = dict(DONE, content=dict(DONE['content'], level='warning', url='http://eln/api/v1/attachments/5'))
    result = ImportResult.from_message(message)
    assert (result.level, result.ok, result.report_url) == ('warning', False, 'http://eln/api/v1/attachments/5')
