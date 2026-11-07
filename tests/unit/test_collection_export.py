"""Collection export and import (M3.1), offline: start the job, wait for its notification."""
import pytest

import chemotion_api.notifications as notifications_module
from chemotion_api.collection import Collection, RootCollection, export_collections

ZIP = 'Collection Import and Export'
FAIL = 'Collection Import and Export Failure'


def _msg(mid, subject, data, url=None):
    return {'id': mid, 'subject': subject,
            'content': {'channel_subject': subject, 'data': data, 'url': url, 'level': 'success'}}


OLD_IMPORT = _msg(1, ZIP, 'Collection import: A processed successfully. ', 'http://0.0.0.0:3000/import_logs/a.log')
EXPORTED = _msg(2, ZIP, 'Collection Export: ["A"] processed successfully. 2026-01-01', 'http://0.0.0.0:3000/zip/j.zip')


class _Res:
    def __init__(self, status, payload=None, content=b''):
        self.status_code, self._payload, self.text, self.content = status, payload, str(payload), content

    def json(self):
        return self._payload


class _Session:
    def __init__(self, message_lists, post_status=201):
        self.message_lists, self.post_status, self.posts, self.downloads = list(message_lists), post_status, [], []

    def get(self, url, params=None, **kw):
        if url == '/api/v1/messages/list':
            msgs = self.message_lists.pop(0) if len(self.message_lists) > 1 else self.message_lists[0]
            return _Res(200, {'messages': msgs})
        self.downloads.append(url)
        return _Res(200, content=b'PK zip')

    def post(self, url, data=None, files=None, **kw):
        self.posts.append((url, data, sorted(files or {})))
        return _Res(self.post_status, {'status': 204})


class _Col:
    def __init__(self, cid, label='A'):
        self.id, self.label = cid, label


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(notifications_module.time, 'sleep', lambda s: None)


def test_export_waits_for_the_new_export_and_downloads_by_path(tmp_path):
    session = _Session([[OLD_IMPORT], [OLD_IMPORT], [OLD_IMPORT, EXPORTED]])
    out = export_collections(session, [_Col(5), _Col(6, 'B')], str(tmp_path / 'e.zip'))
    assert session.posts == [('/api/v1/collections/export', {'collection_ids': [5, 6]}, [])]
    assert session.downloads == ['/zip/j.zip']  # the server's root URL is not reachable
    assert open(out, 'rb').read() == b'PK zip'


def test_an_import_notification_is_not_taken_for_the_export(tmp_path, monkeypatch):
    clock = iter(range(0, 1000, 100))
    monkeypatch.setattr(notifications_module.time, 'monotonic', lambda: next(clock))
    newer_import = dict(OLD_IMPORT, id=7)
    with pytest.raises(TimeoutError):
        export_collections(_Session([[], [newer_import]]), [_Col(5)], str(tmp_path / 'e.zip'), timeout=250)


def test_a_failed_export_raises(tmp_path):
    failed = _msg(3, FAIL, 'Collection Export: There was an issue while processing ["A"].')
    with pytest.raises(ConnectionError, match='issue while processing'):
        export_collections(_Session([[], [failed]]), [_Col(5)], str(tmp_path / 'e.zip'))


def test_export_refusals(tmp_path):
    with pytest.raises(PermissionError):
        export_collections(_Session([[]], post_status=401), [_Col(5)], str(tmp_path / 'e.zip'))
    with pytest.raises(ValueError, match='not saved'):
        export_collections(_Session([[]]), [_Col(None)], str(tmp_path / 'e.zip'))
    with pytest.raises(ValueError, match='Select'):
        export_collections(_Session([[]]), [], str(tmp_path / 'e.zip'))


def _root(session, tree_after):
    root = RootCollection.__new__(RootCollection)
    root._session, root._children, root._parent = session, [], None

    def child(cid, label, parent):
        col = Collection.__new__(Collection)
        col._id, col._parent, col._children = cid, parent, []
        col.label = label
        parent._children.append(col)
        return col

    child(1, 'Mine', root)

    def load():
        root._children = []
        for cid, label, parent_id in tree_after:
            parent = root if parent_id is None else next(c for c in root.walk() if c.id == parent_id)
            child(cid, label, parent)
    root.load_collection = load
    return root


def test_import_returns_the_new_top_level_collections(tmp_path):
    archive = tmp_path / 'a.zip'
    archive.write_bytes(b'PK')
    done = _msg(4, ZIP, 'Collection import: A, A-sub processed successfully. ', 'http://x/import_logs/l.log')
    session = _Session([[OLD_IMPORT], [OLD_IMPORT, done]])
    root = _root(session, [(1, 'Mine', None), (8, 'A', None), (9, 'A-sub', 8)])
    new = root.import_collections(str(archive))
    assert [(c.id, c.label) for c in new] == [(8, 'A')]
    assert session.posts == [('/api/v1/collections/import', None, ['file'])]


def test_a_failed_import_raises(tmp_path):
    archive = tmp_path / 'a.zip'
    archive.write_bytes(b'PK')
    failed = _msg(4, FAIL, 'Collection import: There was an issue while processing .')
    root = _root(_Session([[], [failed]]), [])
    with pytest.raises(ConnectionError, match='failed'):
        root.import_collections(str(archive))
