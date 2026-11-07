"""Attachment management (M3.4), offline: delete, unlink, images, thumbnails, bulk calls."""
import base64
import json

import pytest

from chemotion_api.elements.attachments import Attachment, delete_attachments, load_files, load_thumbnails


class _Res:
    def __init__(self, status, payload=None, content=b''):
        self.status_code, self._payload, self.content, self.text = status, payload, content, str(payload)

    def json(self):
        return self._payload


class _Session:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def get_json_session_header(self):
        return {'Content-Type': 'application/json'}

    def _call(self, method, url, kw):
        self.calls.append((method, url, kw.get('data')))
        return self.responses.pop(0)

    def get(self, url, **kw):
        return self._call('get', url, kw)

    def post(self, url, **kw):
        return self._call('post', url, kw)

    def delete(self, url, **kw):
        return self._call('delete', url, kw)


def _b64(data: bytes) -> str:
    return base64.encodebytes(data).decode()  # the server's Base64.encode64 wraps lines


def test_single_attachment_calls():
    session = _Session(_Res(200, content=b'PNG'), _Res(200, _b64(b'thumb')), _Res(200, None),
                       _Res(200, {'attachment': {'id': 5, 'attachable_id': None}}), _Res(200, {}))
    att = Attachment(session, {'id': 5, 'filename': 'a.tif', 'attachable_id': 9})
    assert att.load_image() == b'PNG'
    assert att.load_thumbnail() == b'thumb'
    assert att.load_thumbnail() is None
    att.unlink()
    assert att['attachable_id'] is None
    att.delete()
    assert [c[:2] for c in session.calls] == [
        ('get', '/api/v1/attachments/image/5'), ('get', '/api/v1/attachments/thumbnail/5'),
        ('get', '/api/v1/attachments/thumbnail/5'), ('delete', '/api/v1/attachments/link/5'),
        ('delete', '/api/v1/attachments/5')]


def test_an_unservable_image_is_a_value_error():
    with pytest.raises(ValueError, match='cannot be shown'):
        Attachment(_Session(_Res(422, {'error': 'not an image'})), {'id': 5, 'filename': 'a.txt'}).load_image()


def test_bulk_delete_sends_a_json_body():
    session = _Session(_Res(200, {'deleted_attachments': [{'id': 1}, {'id': 2}]}))
    assert delete_attachments(session, [Attachment(session, {'id': 1}), 2]) == [1, 2]
    assert json.loads(session.calls[0][2]) == {'ids': [1, 2]}
    with pytest.raises(PermissionError, match='none was deleted'):
        delete_attachments(_Session(_Res(401, {})), [1])
    with pytest.raises(ValueError):
        delete_attachments(_Session(), [])


def test_bulk_thumbnails_and_files_keep_the_order_and_the_gaps():
    session = _Session(_Res(201, {'thumbnails': [{'id': 1, 'thumbnail': _b64(b't1')}, None, {'id': 3, 'thumbnail': None}]}),
                       _Res(201, {'files': [{'id': 1, 'file': _b64(b'f1')}, None]}))
    assert load_thumbnails(session, [1, 2, 3]) == {1: b't1', 2: None, 3: None}
    assert load_files(session, [1, 2]) == {1: b'f1', 2: None}
    assert session.calls[0] == ('post', '/api/v1/attachments/thumbnails', {'ids': [1, 2, 3]})
    with pytest.raises(PermissionError):
        load_files(_Session(_Res(401, {})), [1])
