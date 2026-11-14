"""ELN-to-ELN transfer through the gate (M3.9), offline."""
import pytest

import chemotion_api.notifications as notifications_module
from chemotion_api.collection import Collection

DONE = {'id': 4, 'subject': 'Gate Transfer Completed',
        'content': {'channel_subject': 'Gate Transfer Completed', 'data': '2 samples transferred', 'level': 'info'}}


class _Res:
    def __init__(self, status, payload=None):
        self.status_code, self._payload, self.text = status, payload, str(payload)

    def json(self):
        return self._payload


class _Session:
    host_url = 'http://eln.local'

    def __init__(self, *responses, messages=((),)):
        self.responses, self.calls, self.messages = list(responses), [], list(messages)

    def get_json_session_header(self):
        return {'Content-Type': 'application/json'}

    def get(self, url, params=None, headers=None, **kw):
        if url == '/api/v1/messages/list':
            msgs = self.messages.pop(0) if len(self.messages) > 1 else self.messages[0]
            return _Res(200, {'messages': list(msgs)})
        self.calls.append(('get', url, params, headers))
        return self.responses.pop(0)

    def post(self, url, data=None, params=None, headers=None, **kw):
        self.calls.append(('post', url, data if data is not None else params, headers))
        return self.responses.pop(0)


def _collection(session):
    col = Collection.__new__(Collection)
    col._id, col.label = 11, 'Out'
    col.get_root = lambda: type('_Root', (), {'_session': session})()
    return col


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(notifications_module.time, 'sleep', lambda s: None)


def test_tokens_and_registration():
    session = _Session(_Res(200, {'jwt': 'abc'}), _Res(201, None))
    col = _collection(session)
    assert col.gate_token('http://sender') == 'abc'
    col.register_gate('http://receiver/', 'abc')
    assert session.calls[0][:3] == ('get', '/api/v1/gate/jwt/new', {'collection_id': 11, 'origin': 'http://sender'})
    assert session.calls[1][:3] == ('post', '/api/v1/gate/register_gate',
                                    {'collection_id': 11, 'destination': 'http://receiver/', 'token': 'abc'})


def test_transmit_sends_our_origin_and_waits():
    session = _Session(_Res(202, None), messages=([], [DONE]))
    assert _collection(session).transmit('http://receiver/') == '2 samples transferred'
    (method, url, params, headers), = session.calls
    assert (method, url, params) == ('post', '/api/v1/gate/transmitting/11', {'target': 'http://receiver/'})
    assert headers['Referer'] == 'http://eln.local/'


def test_transmit_failures():
    failed = dict(DONE, content=dict(DONE['content'], level='error', data='boom'))
    with pytest.raises(ConnectionError, match='boom'):
        _collection(_Session(_Res(202, None), messages=([], [failed]))).transmit('http://receiver/')
    with pytest.raises(ConnectionError, match='Token missing'):
        _collection(_Session(_Res(404, {'error': 'Token missing for the target'}))).check_transmission('http://r/')
    with pytest.raises(ValueError, match='public repository'):
        _collection(_Session()).transmit('')
