"""Small lookups (M2.7), offline: CAS lookup, search suggestions, reaction scheme request."""
import pytest

from chemotion_api import Instance
from chemotion_api.elements.reaction import Reaction
from chemotion_api.elements.sample import MoleculeManager


class _Res:
    def __init__(self, status, payload=None):
        self.status_code, self._payload, self.text = status, payload, str(payload)
        self.url, self.reason = 'http://eln.test', 'x'

    def json(self):
        return self._payload


class _Session:
    def __init__(self, res):
        self.res, self.calls = res, []

    def get(self, url, **kw):
        self.calls.append(('get', url, kw.get('params')))
        return self.res

    def post(self, url, **kw):
        self.calls.append(('post', url, kw.get('data')))
        return self.res


def test_cas_lookup():
    session = _Session(_Res(201, {'smiles': 'CCO', 'cas': '64-17-5', 'source': 'pubchem'}))
    assert MoleculeManager(session).lookup_cas(' 64-17-5 ')['smiles'] == 'CCO'
    assert session.calls == [('post', '/api/v1/cas_lookup/lookup', {'cas_number': '64-17-5'})]


def test_an_empty_cas_number_sends_nothing():
    session = _Session(None)
    with pytest.raises(ValueError):
        MoleculeManager(session).lookup_cas('  ')
    assert session.calls == []


def test_suggestions():
    instance = Instance.__new__(Instance)
    instance._con = _Session(_Res(200, {'suggestions': [{'name': 'API-1', 'search_by_method': 'sample_short_label'}]}))
    assert instance.suggestions('API', 'samples', collection_id=4) == [
        {'name': 'API-1', 'search_by_method': 'sample_short_label'}]
    assert instance._con.calls == [('get', '/api/v1/suggestions/samples', {'query': 'API', 'collection_id': '4'})]
    assert instance.suggestions('') == []


class _Mat:
    def __init__(self, path, name=None, equivalent=None):
        self.svg_path, self.name, self.properties = path, name, {'equivalent': equivalent}


def test_the_scheme_request_mirrors_the_ui():
    props_holder = {}
    _R = type('_R', (Reaction,), {'properties': property(lambda self: props_holder)})
    reaction = _R.__new__(_R)
    reaction._session = _Session(_Res(201, {'reaction_svg': '<svg/>'}))
    reaction._id = 3
    props = {'starting_materials': [_Mat('/images/molecules/a.svg')], 'reactants': [],
             'products': [_Mat('/images/samples/p.svg', equivalent=0.8)],
             'solvents': [_Mat(None, 'water'), _Mat(None, None)],
             'temperature': {'userText': '25', 'valueUnit': '°C'}, 'duration': '2 h', 'conditions': None}
    props_holder.update(props)
    assert reaction.render_scheme_svg() == '<svg/>'
    (_, url, body), = reaction._session.calls
    assert url == '/api/v1/reaction_svg'
    assert body == {'materials_svg_paths': {'starting_materials': ['/images/molecules/a.svg'], 'reactants': [],
                                            'products': [['/images/samples/p.svg', 0.8]]},
                    'temperature': '25 °C', 'solvents': ['water'], 'duration': '2 h', 'conditions': '',
                    'products_only': False, 'show_yield': True}
