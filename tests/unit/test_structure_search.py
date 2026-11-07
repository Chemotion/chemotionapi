"""Structure search (M2.4), offline: request body and result bookkeeping."""
import pytest

from chemotion_api.elements.sample import Molecule
from chemotion_api.search.structure import StructureSearcher

MOLFILE = '\n  RDKit\n\n  1  0  0  0  0  0  0  0  0  0999 V2000\nM  END'
CLASSES = {
    'sample': {'name': 'sample', 'is_generic': False},
    'reaction': {'name': 'reaction', 'is_generic': False},
    'unmodelled': {'name': 'unmodelled', 'is_generic': False},
    'generic_element': {'name': 'generic_element', 'is_generic': True},
}


class _Res:
    def __init__(self, status, payload=None):
        self.status_code, self._payload, self.text = status, payload, str(payload)

    def json(self):
        return self._payload


class _Session:
    def __init__(self, res=None):
        self.res, self.calls = res, []

    def post(self, url, data=None, **kw):
        self.calls.append((url, data))
        return self.res


def _searcher(session=None):
    em = type('_EM', (), {'all_classes': CLASSES})()
    return StructureSearcher(session or _Session(), em, root_collection_id=3)


def _block(total):
    return {'elements': [], 'ids': list(range(total)), 'totalElements': total, 'page': 1, 'pages': 1}


def test_substructure_body_matches_the_ui():
    body = _searcher().substructure(MOLFILE).in_collection(9).find_max(40).payload()
    assert body['selection'] == {'elementType': 'structure', 'search_by_method': 'structure',
                                 'structure_search': True, 'molfile': MOLFILE, 'search_type': 'sub',
                                 'tanimoto_threshold': 0.7, 'page_size': 40}
    assert (body['collection_id'], body['per_page']) == ('9', 40)


def test_similarity_carries_its_threshold():
    body = _searcher().similar(MOLFILE, threshold=0.85).payload()
    assert (body['selection']['search_type'], body['selection']['tanimoto_threshold']) == ('similar', 0.85)


def test_a_molecule_is_searched_by_its_molfile():
    assert _searcher().substructure(Molecule({'id': 1, 'molfile': MOLFILE})).payload()['selection']['molfile'] == MOLFILE


@pytest.mark.parametrize('build, match', [
    (lambda s: s, 'substructure\\(\\) or similar\\(\\)'),
    (lambda s: s.substructure(''), 'No structure'),
    (lambda s: s.substructure(Molecule({'id': 1})), 'no molfile'),
])
def test_incomplete_searches_are_refused(build, match):
    with pytest.raises(ValueError, match=match):
        build(_searcher()).payload()


@pytest.mark.parametrize('threshold', [-0.1, 1.5])
def test_threshold_must_be_a_similarity(threshold):
    with pytest.raises(ValueError, match='between 0 and 1'):
        _searcher().similar(MOLFILE, threshold=threshold)


def test_results_count_every_type_but_only_wrap_supported_ones():
    session = _Session(_Res(201, {'samples': _block(0), 'reactions': _block(2), 'unmodelleds': _block(4),
                                  'structure_svg': 'x.svg'}))
    result = _searcher(session).substructure(MOLFILE).request()
    assert result.total('reaction') == 2 and result.total('unmodelled') == 4
    assert result.types == ['reaction', 'unmodelled']
    assert len(result.samples) == 0
    with pytest.raises(KeyError):
        result['unmodelled']


def test_a_failed_search_raises():
    with pytest.raises(ConnectionError):
        _searcher(_Session(_Res(500, 'boom'))).substructure(MOLFILE).request()
