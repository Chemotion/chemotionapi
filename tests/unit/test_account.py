"""API tokens, two-factor login and counters (M7.2, M7.3), offline."""
import json

import pytest

from chemotion_api.account import (OtpRequired, api_tokens, create_api_token, revoke_api_token, set_counter,
                                   set_reaction_label)


class _Res:
    def __init__(self, status, payload=None):
        self.status_code, self._payload = status, payload
        self.text = json.dumps(payload) if not isinstance(payload, str) else payload

    def json(self):
        return self._payload


class _Session:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def _call(self, method, url, kw):
        self.calls.append((method, url, kw.get('data')))
        return self.responses.pop(0)

    def get(self, url, **kw):
        return self._call('get', url, kw)

    def post(self, url, **kw):
        return self._call('post', url, kw)

    def put(self, url, **kw):
        return self._call('put', url, kw)


def test_create_list_revoke():
    session = _Session(_Res(201, {'token': 'chemtoken_abc'}),
                       _Res(200, {'user': {'tokens': [{'id': 3, 'name': 'ci', 'expires_at': 'x', 'revoked': False}]}}),
                       _Res(201, True))
    assert create_api_token(session, '123456', 'ci', 90) == 'chemtoken_abc'
    (token,) = api_tokens(session)
    revoke_api_token(session, token, '654321')
    assert session.calls[0][2] == {'otp_attempt': '123456', 'expires_in_days': 90, 'name': 'ci'}
    assert session.calls[2][2] == {'id': 3, 'otp_attempt': '654321'}


def test_otp_errors():
    with pytest.raises(PermissionError, match='two-factor login enabled'):
        create_api_token(_Session(_Res(401, '2FA is needed')), '1')
    with pytest.raises(OtpRequired, match='wrong'):
        create_api_token(_Session(_Res(422, {'error': 'OTP Missing', 'otp_required': True, 'otp_wrong': True})), '1')
    with pytest.raises(OtpRequired, match='give the current'):
        create_api_token(_Session(_Res(422, {'error': 'OTP Missing', 'otp_wrong': False})), '')
    with pytest.raises(LookupError):
        revoke_api_token(_Session(_Res(409, 'Token already revoked')), 3, '1')
    with pytest.raises(ValueError):
        create_api_token(_Session(), '1', expires_in_days=0)


def test_counters():
    session = _Session(_Res(200, {'counters': {'samples': '10'}}), _Res(200, None))
    assert set_counter(session, 'samples', 10) == {'counters': {'samples': '10'}}
    set_reaction_label(session, 'R', 4)
    assert session.calls == [('put', '/api/v1/users/update_counter', {'type': 'samples', 'counter': 10}),
                             ('put', '/api/v1/users/reaction_short_label', {'reactions_count': 4, 'reaction_name_prefix': 'R'})]
    with pytest.raises(ValueError):
        set_counter(session, 'samples', -1)
