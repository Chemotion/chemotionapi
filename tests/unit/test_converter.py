from types import SimpleNamespace

from chemotion_api.converter import ProfileManager

PROFILE = {'id': 'p1', 'title': 'NMR', 'description': '', 'identifiers': [], 'tables': [], 'data': {}}


def _session(calls):
    def request(method):
        return lambda url, **kwargs: calls.append((method, url)) or SimpleNamespace(
            status_code=200, json=lambda: {'profiles': [PROFILE]}, text='')
    return SimpleNamespace(get=request('get'), put=request('put'), post=request('post'))


def test_loaded_profile_is_updated_not_duplicated():
    calls = []
    profile = ProfileManager(_session(calls)).get_profile('p1')
    profile.save()
    assert calls[-1] == ('put', '/api/v1/converter/profiles/p1')


def test_unknown_profile():
    assert ProfileManager(_session([])).get_profile('nope') is None
