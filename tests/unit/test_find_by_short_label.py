"""Finding samples and reactions by short label (M1.2), offline."""
import pytest

from chemotion_api import Instance


class _Res:
    def __init__(self, status, payload=None):
        self.status_code, self._payload, self.text = status, payload, str(payload)
        self.url, self.reason = 'http://eln.test', 'x'

    def json(self):
        return self._payload


class _Con:
    def __init__(self, res):
        self._res, self.urls = res, []

    def get(self, url, **kwargs):
        self.urls.append(url)
        return self._res


def _instance(res, loaded):
    instance = Instance.__new__(Instance)
    instance._con = _Con(res)
    instance.get_sample = lambda i: loaded.append(('sample', i)) or ('sample', i)
    instance.get_reaction = lambda i: loaded.append(('reaction', i)) or ('reaction', i)
    return instance


def test_a_found_sample_is_loaded():
    loaded = []
    instance = _instance(_Res(200, {'sample_id': 219, 'collection_id': 9}), loaded)
    assert instance.find_sample_by_short_label('API-173-2') == ('sample', 219)
    assert instance._con.urls == ['/api/v1/samples/findByShortLabel/API-173-2.json']


def test_a_found_reaction_is_loaded():
    loaded = []
    instance = _instance(_Res(200, {'reaction_id': 4, 'collection_id': 9}), loaded)
    assert instance.find_reaction_by_short_label('API-R4') == ('reaction', 4)
    assert instance._con.urls == ['/api/v1/reactions/findByShortLabel/API-R4.json']


@pytest.mark.parametrize('find, payload', [
    ('find_sample_by_short_label', {'sample_id': None, 'collection_id': None}),
    ('find_reaction_by_short_label', {'reaction_id': None, 'collection_id': None}),
])
def test_no_match_is_none_and_loads_nothing(find, payload):
    loaded = []
    assert getattr(_instance(_Res(200, payload), loaded), find)('NOPE-1') is None
    assert loaded == []


def test_the_label_is_url_quoted():
    instance = _instance(_Res(200, {'sample_id': None}), [])
    instance.find_sample_by_short_label('A/B 1')
    assert instance._con.urls == ['/api/v1/samples/findByShortLabel/A%2FB%201.json']


def test_an_empty_label_is_refused():
    with pytest.raises(ValueError):
        _instance(_Res(200, {}), []).find_sample_by_short_label('')


def test_a_server_error_is_raised():
    with pytest.raises(Exception, match='short label'):
        _instance(_Res(500, {'error': 'boom'}), []).find_sample_by_short_label('API-1')
