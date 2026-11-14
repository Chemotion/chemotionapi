"""Sample inventory/safety records (`/api/v1/chemicals`) — routing and data handling, offline."""
import pytest

from chemotion_api.elements.sample import Chemical


class _Res:
    def __init__(self, status, body=None):
        self.status_code, self._body = status, body
        self.text, self.content, self.headers = str(body), b'x', {}
        self.request = None

    def json(self):
        return self._body


class _Server:
    """Records calls; GET answers whatever `record` currently is."""

    def __init__(self, record):
        self.record, self.calls = record, []

    def get(self, path, **kw):
        self.calls.append(('GET', path, None))
        return _Res(200, self.record)

    def put(self, path, data=None, **kw):
        self.calls.append(('PUT', path, data))
        self.record = self.record | {'cas': data.get('cas', self.record.get('cas')),
                                     'chemical_data': data['chemical_data']}
        return _Res(200, True)

    def post(self, path, data=None, **kw):
        self.calls.append(('POST', path, data))
        self.record = {'id': 9, 'sample_id': data['sample_id'], 'cas': data['cas'],
                       'chemical_data': data['chemical_data']}
        return _Res(201, self.record)


def test_a_missing_record_is_created_on_save():
    server = _Server({'id': None, 'cas': None, 'chemical_data': None})
    chem = Chemical(server, 5, server.record)
    assert not chem.exists and chem.data == {}
    chem.data['vendor'] = 'Acme'
    chem.save()
    method, path, body = server.calls[0]
    assert (method, path) == ('POST', '/api/v1/chemicals/create')
    assert body == {'sample_id': 5, 'chemical_data': [{'vendor': 'Acme'}], 'cas': ''}
    assert chem.exists and chem.id == 9 and chem.data == {'vendor': 'Acme'}


def test_an_existing_record_is_updated_and_reread():
    record = {'id': 3, 'cas': '64-17-5', 'chemical_data': [{'vendor': 'Old'}, {'kept': True}]}
    server = _Server(record)
    chem = Chemical(server, 5, record)
    chem.data['vendor'] = 'New'
    chem.save()
    method, path, body = server.calls[0]
    assert (method, path) == ('PUT', '/api/v1/chemicals')
    assert body['chemical_data'] == [{'vendor': 'New'}, {'kept': True}]   # further entries kept
    assert body['cas'] == '64-17-5'
    assert server.calls[-1][0] == 'GET'                                   # PUT answers `true`
    assert chem.data == {'vendor': 'New'}


def test_a_refused_write_is_a_permission_error():
    class _Denied(_Server):
        def put(self, path, data=None, **kw):
            return _Res(401, {'error': '401 Unauthorized'})
    server = _Denied({'id': 3, 'cas': None, 'chemical_data': [{}]})
    with pytest.raises(PermissionError):
        Chemical(server, 5, server.record).save()
