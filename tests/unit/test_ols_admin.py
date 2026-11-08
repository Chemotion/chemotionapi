"""OLS term administration (M6.6), offline."""
import pytest

from chemotion_api.user import Admin


class _Res:
    def __init__(self, status, payload=None):
        self.status_code, self._payload, self.text = status, payload, str(payload)

    def json(self):
        return self._payload


class _Session:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def get(self, url, params=None, **kw):
        self.calls.append(('get', url, params))
        return self.responses.pop(0)

    def post(self, url, data=None, files=None, **kw):
        self.calls.append(('post', url, data if files is None else sorted(files)))
        return self.responses.pop(0)


def _admin(session):
    admin = Admin.__new__(Admin)
    admin._session = session
    return admin


def test_switching_needs_imported_terms():
    session = _Session(_Res(200, {'ols_terms': []}))
    with pytest.raises(ValueError, match='import the ontology first'):
        _admin(session).set_ols_terms_enabled('chmo', disable=['CHMO:1'])
    assert [c[0] for c in session.calls] == ['get']


def test_switching_and_import(tmp_path):
    owl = tmp_path / 'chmo.owl'
    owl.write_text('<rdf:RDF/>')
    session = _Session(_Res(200, {'ols_terms': [{'id': 1}]}), _Res(204), _Res(204), _Res(401))
    admin = _admin(session)
    admin.set_ols_terms_enabled('chmo', enable=['CHMO:1'], disable=['CHMO:2'])
    assert session.calls[1] == ('post', '/api/v1/admin/olsEnableDisable',
                                {'owl_name': 'chmo', 'enableIds': ['CHMO:1'], 'disableIds': ['CHMO:2']})
    admin.import_ols_terms(str(owl))
    assert session.calls[2] == ('post', '/api/v1/admin/importOlsTerms', ['file'])
    with pytest.raises(PermissionError):
        admin.import_ols_terms(str(owl))
    with pytest.raises(ValueError, match='.owl'):
        admin.import_ols_terms(str(tmp_path / 'x.txt'))
