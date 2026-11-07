"""Version history and revert (M1.5), offline, on the payload shape ELN main sends."""
import pytest

from chemotion_api.elements.versions import Version, load_versions, revert_changes

VERSION = {
    'id': 2, 'time': '2026-11-07T13:16:45.790Z', 'user': 'API User',
    'changes': [
        {'db_id': 224, 'klass_name': 'Sample', 'name': ['Sample Properties'], 'fields': {
            'name': {'label': 'Name', 'old_value': 'one', 'new_value': 'two', 'current_value': 'two',
                     'kind': 'string', 'revert': ['name'], 'revertible_value': 'one'},
            'molfile': {'label': 'Structure', 'old_value': 'a', 'new_value': 'b', 'kind': 'string',
                        'revert': ['molfile', 'molecule_id'], 'revertible_value': 'a',
                        'linked_revertible_values': {'molecule_id': 17}},
            'updated_by': {'label': 'Updated by', 'old_value': 1, 'new_value': 2, 'kind': 'string',
                           'revert': [], 'revertible_value': None},
        }},
        {'db_id': 40, 'klass_name': 'Container', 'name': ['Analysis'], 'fields': {
            'name': {'label': 'Name', 'old_value': 'x', 'new_value': 'y', 'kind': 'string',
                     'revert': ['name'], 'revertible_value': 'x'},
        }},
    ],
}


class _Res:
    def __init__(self, status, payload=None, headers=None):
        self.status_code, self._payload, self.text = status, payload, str(payload)
        self.headers, self.url, self.reason = headers or {}, 'http://eln.test', 'x'

    def json(self):
        return self._payload


class _Session:
    def __init__(self, *responses):
        self._responses, self.calls = list(responses), []

    def get(self, url, **kw):
        self.calls.append(('get', url, kw.get('params')))
        return self._responses.pop(0)

    def post(self, url, **kw):
        self.calls.append(('post', url, kw.get('data')))
        return self._responses.pop(0) if self._responses else _Res(201, [])


def test_a_version_parses_changes_and_fields():
    version = Version(_Session(), VERSION)
    assert (version.id, version.user) == (2, 'API User')
    sample_change = version.changes[0]
    assert (sample_change.klass_name, sample_change.db_id) == ('Sample', 224)
    assert sample_change.fields['name'].old_value == 'one'
    assert not sample_change.fields['updated_by'].is_revertible


def test_revert_sends_history_values_with_linked_columns_and_skips_unrevertible_fields():
    session = _Session()
    Version(session, VERSION).revert()
    (_, url, body), = session.calls
    assert url == '/api/v1/versions/revert'
    assert body == {'changes': [
        {'db_id': 224, 'klass_name': 'Sample', 'fields': [
            {'name': 'name', 'value': 'one'},
            {'name': 'molfile', 'value': 'a'}, {'name': 'molecule_id', 'value': 17}]},
        {'db_id': 40, 'klass_name': 'Container', 'fields': [{'name': 'name', 'value': 'x'}]},
    ]}


def test_reverting_selected_fields_only():
    session = _Session()
    Version(session, VERSION).changes[0].revert(fields=['name'])
    assert session.calls[0][2] == {'changes': [
        {'db_id': 224, 'klass_name': 'Sample', 'fields': [{'name': 'name', 'value': 'one'}]}]}


@pytest.mark.parametrize('fields', [['updated_by'], ['nope'], []])
def test_nothing_revertible_selected_sends_nothing(fields):
    session = _Session()
    with pytest.raises(ValueError, match='Nothing to revert'):
        revert_changes(session, Version(session, VERSION).changes, fields)
    assert session.calls == []


def test_the_whole_history_is_read_page_by_page():
    session = _Session(_Res(200, {'versions': [VERSION]}, {'X-Total-Pages': '2'}),
                       _Res(200, {'versions': [dict(VERSION, id=1)]}, {'X-Total-Pages': '2'}))
    assert [v.id for v in load_versions(session, 'research_plan', 5)] == [2, 1]
    assert [c[1:] for c in session.calls] == [
        ('/api/v1/versions/research_plans/5', {'page': 1, 'per_page': 100}),
        ('/api/v1/versions/research_plans/5', {'page': 2, 'per_page': 100})]


def test_generic_elements_have_no_history():
    with pytest.raises(ValueError, match='no version history'):
        load_versions(_Session(), 'my_klass', 1)
