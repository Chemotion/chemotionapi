"""Literature references (M2.6), offline."""
import pytest

from chemotion_api.elements import literature
from chemotion_api.elements.literature import Reference

ROW = {'id': 1, 'literal_id': 4, 'title': 'Paper', 'doi': '10.1/x', 'litype': 'citedOwn',
       'refs': {'bibtex': '@article{x}'}, 'user_name': 'API User'}


class _Res:
    def __init__(self, status, payload=None):
        self.status_code, self._payload, self.text = status, payload, str(payload)
        self.url, self.reason = 'http://eln.test', 'x'

    def json(self):
        return self._payload


class _Session:
    def __init__(self, res=None):
        self.res, self.calls = res or _Res(200, {'literatures': [ROW]}), []

    def _call(self, method, url, **kw):
        self.calls.append((method, url, kw.get('data'), kw.get('params')))
        return self.res

    def get(self, url, **kw): return self._call('get', url, **kw)
    def post(self, url, **kw): return self._call('post', url, **kw)
    def put(self, url, **kw): return self._call('put', url, **kw)
    def delete(self, url, **kw): return self._call('delete', url, **kw)


def test_a_reference_keeps_both_ids_and_its_bibtex():
    ref = Reference.from_json(ROW)
    assert (ref.id, ref.link_id, ref.bibtex) == (1, 4, '@article{x}')


def test_adding_sends_a_new_reference_without_empty_fields():
    session = _Session()
    literature.add_reference(session, 'reaction', 7, doi='10.1/x', bibtex='@article{x}', litype='referTo')
    (_, url, data, _), = session.calls
    assert url == '/api/v1/literatures'
    assert data == {'element_type': 'reaction', 'element_id': 7,
                    'ref': {'is_new': True, 'litype': 'referTo', 'doi': '10.1/x', 'refs': {'bibtex': '@article{x}'}}}


@pytest.mark.parametrize('kwargs, match', [({}, 'DOI, URL, title or ISBN'), ({'doi': '10.1/x', 'litype': 'x'}, 'Unknown reference type')])
def test_bad_references_send_nothing(kwargs, match):
    session = _Session()
    with pytest.raises(ValueError, match=match):
        literature.add_reference(session, 'sample', 1, **kwargs)
    assert session.calls == []


def test_generic_elements_take_no_references():
    with pytest.raises(ValueError, match='not supported on my_klass'):
        literature.load_references(_Session(), 'my_klass', 1)


def test_remove_and_retype_act_on_the_link():
    session = _Session()
    ref = Reference.from_json(ROW)
    literature.remove_reference(session, 'sample', 3, ref)
    literature.set_reference_type(session, 'sample', 3, ref, 'citedRef')
    assert session.calls[0][3] == {'element_type': 'sample', 'element_id': 3, 'id': 4}
    assert session.calls[1][2] == {'element_type': 'sample', 'element_id': 3, 'id': 4, 'litype': 'citedRef'}


def test_an_unlinked_reference_cannot_be_removed():
    with pytest.raises(ValueError, match='not linked'):
        literature.remove_reference(_Session(), 'sample', 3, Reference(id=1))


def test_an_error_in_a_200_body_is_raised():
    with pytest.raises(ConnectionError, match='bad ref'):
        literature.load_references(_Session(_Res(200, {'error': 'bad ref'})), 'sample', 1)


@pytest.mark.parametrize('doi', ['nope', '', '10.1021'])
def test_an_invalid_doi_is_refused_before_sending(doi):
    session = _Session()
    with pytest.raises(ValueError, match='Not a DOI'):
        literature.doi_metadata(session, doi)
    assert session.calls == []


def test_collection_references_are_keyed_by_element_kind():
    session = _Session(_Res(200, {'collectionRefs': [], 'sampleRefs': [dict(ROW, count=2)],
                                  'reactionRefs': [], 'researchPlanRefs': []}))
    refs = literature.collection_references(session, 5)
    assert list(refs) == ['collection', 'sample', 'reaction', 'research_plan']
    assert refs['sample'][0].count == 2
