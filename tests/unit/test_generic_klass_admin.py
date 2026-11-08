"""Template deletion, revisions and download (M6.1, M6.2), offline."""
import pytest

from chemotion_api.labImotion.base_generic_obj import GenericObj, KlassRevision
from chemotion_api.labImotion.items.options import ElementType


class _Res:
    def __init__(self, status, payload=None, content=b''):
        self.status_code, self._payload, self.text, self.content = status, payload, str(payload), content

    def json(self):
        return self._payload


class _Session:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def _call(self, method, url, kw):
        self.calls.append((method, url, kw.get('data', kw.get('params'))))
        return self.responses.pop(0)

    def get(self, url, **kw):
        return self._call('get', url, kw)

    def post(self, url, **kw):
        return self._call('post', url, kw)

    def delete(self, url, **kw):
        return self._call('delete', url, kw)


def _klass(session):
    obj = GenericObj.__new__(GenericObj)
    obj._connection, obj._id, obj._label = session, 15, 'Probe'
    obj.element_type = ElementType.ELEMENT
    return obj


def test_delete_needs_the_label_and_sends_the_klass_kind():
    session = _Session(_Res(201, None), _Res(401, {}))
    klass = _klass(session)
    with pytest.raises(ValueError, match="confirm='Probe'"):
        klass.delete(confirm='probe')
    assert session.calls == []
    klass.delete(confirm='Probe')
    assert session.calls == [('delete', '/api/v1/generic_elements/delete_klass/15', {'klass': 'ElementKlass'})]
    with pytest.raises(PermissionError):
        klass.delete(confirm='Probe')


def test_revisions():
    session = _Session(_Res(200, {'revisions': [{'id': 24, 'uuid': 'u', 'version': '0.2', 'released_at': 'x'}]}),
                       _Res(405, {}), _Res(201, None))
    klass = _klass(session)
    (rev,) = klass.revisions(limit=5)
    assert rev == KlassRevision(24, 'u', '0.2', 'x')
    with pytest.raises(ValueError, match='active version'):
        klass.delete_revision(rev)
    klass.delete_revision(23)
    assert session.calls[0][2] == {'id': 15, 'klass': 'ElementKlass', 'limit': 5}
    assert session.calls[2][2] == {'id': 23, 'klass_id': 15, 'klass': 'ElementKlass'}

