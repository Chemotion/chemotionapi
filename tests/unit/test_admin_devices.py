"""Device administration (M7.5), offline."""
import pytest

from chemotion_api.user import Admin

DEVICE = {'id': 8, 'name': 'NMR', 'name_abbreviation': 'NMR1', 'initials': 'NMR1'}


class _Res:
    def __init__(self, status, payload=None):
        self.status_code, self._payload, self.text = status, payload, str(payload)

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

    def put(self, url, **kw):
        return self._call('put', url, kw)

    def delete(self, url, **kw):
        return self._call('delete', url, kw)


def _admin(session):
    admin = Admin.__new__(Admin)
    admin._session = session
    return admin


def test_update_keeps_the_required_names_and_flags_collector_fields():
    session = _Session(_Res(200, {'device': DEVICE}), _Res(200, {'device': DEVICE}))
    _admin(session).update_device(8, datacollector_host='h')
    assert session.calls[1][2] == {'id': 8, 'name': 'NMR', 'name_abbreviation': 'NMR1', 'datacollector_host': 'h',
                                   'datacollector_fields': True}


def test_errors_and_guards():
    with pytest.raises(ValueError, match='add_device takes'):
        _admin(_Session()).add_device('n', 'a', phone='1')
    with pytest.raises(ValueError, match='Unknown device fields'):
        _admin(_Session()).update_device(8, phone='1')
    with pytest.raises(ValueError, match='taken'):
        _admin(_Session(_Res(201, {'errors': {'name_abbreviation': ['taken']}}))).add_device('n', 'a')
    with pytest.raises(ValueError, match="confirm='NMR1'"):
        _admin(_Session(_Res(200, {'device': DEVICE}))).delete_device(8, confirm='x')
    with pytest.raises(PermissionError):
        _admin(_Session(_Res(401, {}))).list_devices()
