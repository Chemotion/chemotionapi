"""Profile (M7.1), offline: saving, and the guard on template deletion."""
import pytest

from chemotion_api.profile import Profile, save_ketcher_options

TEMPLATE = {'struct': '', 'props': {'path': '/app/uploads/production/user_templates/7/abc.txt'}}


class _Res:
    def __init__(self, status, payload=None):
        self.status_code, self._payload, self.text = status, payload, str(payload)

    def json(self):
        return self._payload


class _Session:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def _call(self, method, url, kw):
        self.calls.append((method, url, kw.get('data', kw.get('params'))))
        return self.responses.pop(0)

    def get(self, url, **kw):
        return self._call('get', url, kw)

    def put(self, url, **kw):
        return self._call('put', url, kw)

    def delete(self, url, **kw):
        return self._call('delete', url, kw)


def test_save_sends_data_and_display_fields():
    profile_json = {'data': {'layout': {'sample': 1}}, 'show_external_name': True, 'curation': 2, 'user_templates': []}
    session = _Session(_Res(200, {}), _Res(200, profile_json))
    profile = Profile(data={'layout': {'sample': 1}}, show_external_name=True, _session=session)
    profile.save()
    assert session.calls[0] == ('put', '/api/v1/profiles', {'data': {'layout': {'sample': 1}}, 'show_external_name': True})
    assert profile.curation == 2


def test_template_deletion_only_for_listed_templates():
    session = _Session(_Res(200, {'status': True}))
    profile = Profile(structure_templates=[TEMPLATE], _session=session)
    for bad in ({'props': {'path': '/etc/passwd'}}, {'props': {}}, {}):
        with pytest.raises(ValueError, match='Not one of'):
            profile.delete_structure_template(bad)
    assert session.calls == []
    profile.delete_structure_template(TEMPLATE)
    assert session.calls == [('delete', '/api/v1/profiles', {'path': TEMPLATE['props']['path']})]
    assert profile.structure_templates == []


def test_refused_ketcher_settings():
    with pytest.raises(ValueError, match='refused'):
        save_ketcher_options(_Session(_Res(422, {})), {'nope': 1})
