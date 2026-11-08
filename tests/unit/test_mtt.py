"""MTT assay requests (M6.5), offline."""
import json

import pytest

from chemotion_api.mtt import MttRequest, create_request, delete_requests, list_requests

REQ = {'id': 1, 'request_id': 'r', 'element_id': 13, 'state': 0, 'state_name': 'initial', 'active': True,
       'revoked': False, 'expired': False, 'outputs': [{'id': 5, 'output_data': {'result': []}, 'notes': None}]}


class _Res:
    def __init__(self, status, payload=None):
        self.status_code, self._payload, self.text = status, payload, str(payload)

    def json(self):
        return self._payload


class _Session:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def get_json_session_header(self):
        return {}

    def _call(self, method, url, kw):
        self.calls.append((method, url, kw.get('data', kw.get('params'))))
        return self.responses.pop(0)

    def get(self, url, **kw):
        return self._call('get', url, kw)

    def post(self, url, **kw):
        return self._call('post', url, kw)

    def patch(self, url, **kw):
        return self._call('patch', url, kw)

    def delete(self, url, **kw):
        return self._call('delete', url, kw)


EL = type('E', (), {'id': 13})()


def test_create_list_update_delete():
    session = _Session(_Res(201, 'http://mtt?url=x'), _Res(200, [REQ]),
                       _Res(200, {'request': {'state': 2, 'state_name': 'completed', 'revoked': False}}),
                       _Res(200, {'deleted_count': 1}))
    assert create_request(session, EL, [type('W', (), {'id': 7})()]) == 'http://mtt?url=x'
    (req,) = list_requests(session, EL)
    assert req.outputs[0].id == 5
    assert req.update(state=2).state_name == 'completed'
    assert delete_requests(session, [req]) == 1
    assert session.calls[0][2] == {'id': 13, 'wellplate_ids': [7]}
    assert session.calls[2] == ('patch', '/api/v1/mtt/requests/1', {'state': 2})
    assert json.loads(session.calls[3][2]) == {'ids': [1]}


def test_refusals():
    with pytest.raises(ValueError, match='state'):
        MttRequest.from_json(REQ, _Session()).update(state=7)
    with pytest.raises(PermissionError):
        create_request(_Session(_Res(403, {})), EL, [1])
    with pytest.raises(LookupError):
        delete_requests(_Session(_Res(404, {})), [1])
    with pytest.raises(ValueError, match='wellplates'):
        create_request(_Session(), EL, [])
