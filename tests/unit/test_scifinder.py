"""SciFinder-n (M7.7), offline."""
import pytest

from chemotion_api.scifinder import load_credential, search


class _Res:
    def __init__(self, status, payload=None):
        self.status_code, self._payload, self.text = status, payload, str(payload)

    def json(self):
        return self._payload


class _Session:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def get(self, url, **kw):
        self.calls.append(('get', url, None))
        return self.responses.pop(0)

    def post(self, url, data=None, **kw):
        self.calls.append(('post', url, data))
        return self.responses.pop(0)


def test_credential_hides_its_tokens():
    cred = load_credential(_Session(_Res(200, {'id': 1, 'access_token': 'secret-a', 'refresh_token': 'secret-r',
                                               'expires_at': 'later', 'updated_at': 'now'})))
    assert cred.present and 'secret' not in repr(cred)
    assert load_credential(_Session(_Res(200, {}))) is None


def test_search():
    session = _Session(_Res(201, {'results': [1]}), _Res(201, {'errors': ['SciFinder-n token missing or expired.']}),
                       _Res(201, {'errors': ['Timeout. Go to Account & Profile']}))
    assert search(session, 'M  END', 'reactions', 'rxnfile') == {'results': [1]}
    assert session.calls[0][2] == {'str': 'M  END', 'search': 'reactions', 'ctype': 'x-mdl-rxnfile'}
    with pytest.raises(PermissionError):
        search(session, 'M  END')
    with pytest.raises(ConnectionError, match='Timeout'):
        search(session, 'M  END')
    with pytest.raises(ValueError):
        search(session, 'x', structure_type='smiles')
