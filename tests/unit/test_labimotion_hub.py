"""LabIMotion Hub (M6.3), offline."""
import pytest

from chemotion_api.labImotion import GenericManager
from chemotion_api.labImotion.items.options import ElementType


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

    def post(self, url, data=None, **kw):
        self.calls.append(('post', url, data))
        return self.responses.pop(0)


def test_routes_per_kind():
    session = _Session(_Res(200, [{'identifier': 'a'}]), _Res(200, []), _Res(200, {'error': 'Cannot connect to Chemotion Repository'}))
    gm = GenericManager(session)
    assert gm.hub_templates() == [{'identifier': 'a'}]
    assert gm.hub_templates(ElementType.DATASET) == []
    with pytest.raises(ConnectionError, match='Cannot connect'):
        gm.hub_templates(ElementType.SEGMENT)
    assert [c[1] for c in session.calls] == ['/api/v1/generic_elements/fetch_repo', '/api/v1/generic_dataset/fetch_repo',
                                             '/api/v1/segments/fetch_repo']


def test_import_and_submit(monkeypatch):
    session = _Session(_Res(201, {'status': 'success', 'klass': []}), _Res(201, {'error': 'nope'}),
                       _Res(201, {'status': 'ok'}))
    gm = GenericManager(session)
    monkeypatch.setattr(gm, 'load_all_segments', lambda: ['loaded'])
    assert gm.import_hub_template('id-1', ElementType.SEGMENT) == ['loaded']
    assert session.calls[0] == ('post', '/api/v1/segments/create_repo_klass', {'identifier': 'id-1'})
    with pytest.raises(ConnectionError, match='nope'):
        gm.import_hub_template('id-2', ElementType.SEGMENT)
    gm.submit_to_hub(24, ElementType.ELEMENT, 'a@b.example', 'NMR workflow', 'please review')
    assert session.calls[2][2] == {'klass': 'ElementKlass', 'id': 24, 'contact_email': 'a@b.example',
                                   'application': 'NMR workflow', 'message': 'please review'}
