"""Text templates (M3.8), offline."""
import pytest

from chemotion_api.text_templates import TextTemplate, TextTemplates

ESI = {'id': 3, 'name': 'esi', 'type': 'PredefinedTextTemplate',
       'data': {'ops': [{'insert': 'MS (ESI): '}, {'insert': 'MASS', 'attributes': {'bold': True}}]}}


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

    def post(self, url, **kw):
        return self._call('post', url, kw)

    def put(self, url, **kw):
        return self._call('put', url, kw)

    def delete(self, url, **kw):
        return self._call('delete', url, kw)


def test_predefined():
    session = _Session(_Res(200, {'text_templates': ['esi', 'ei']}), _Res(200, {'text_templates': [ESI]}),
                       _Res(200, {'text_templates': []}))
    tt = TextTemplates(session)
    assert tt.predefined_names() == ['esi', 'ei']
    esi = tt.predefined('esi')
    assert (esi.id, esi.text, esi.ops[1]['attributes']) == (3, 'MS (ESI): MASS', {'bold': True})
    assert tt.predefined('nope') is None


def test_personal_crud_and_plain_text():
    created = {'id': 9, 'name': 'note', 'type': 'PersonalTextTemplate', 'data': {'ops': [{'insert': 'Yield: '}]}}
    session = _Session(_Res(201, created), _Res(200, dict(created, name='note 2')), _Res(200, created),
                       _Res(200, {'text_templates': [created]}))
    tt = TextTemplates(session)
    note = tt.create_personal('note', 'Yield: ')
    note.name = 'note 2'
    assert tt.update_personal(note).name == 'note 2'
    tt.delete_personal(note)
    assert [t.id for t in tt.personal()] == [9]
    assert session.calls[:3] == [
        ('post', '/api/v1/text_templates/personal', {'name': 'note', 'data': {'ops': [{'insert': 'Yield: '}]}}),
        ('put', '/api/v1/text_templates/personal/9', {'id': 9, 'name': 'note 2', 'data': created['data']}),
        ('delete', '/api/v1/text_templates/personal/9', None)]


def test_duplicate_names_and_permissions():
    with pytest.raises(ValueError, match='Cannot create'):
        TextTemplates(_Session(_Res(422, {'error': 'Name has already been taken'}))).create_personal('x', 'y')
    with pytest.raises(PermissionError):
        TextTemplates(_Session(_Res(401, {}))).create_predefined('x', 'y')
    with pytest.raises(PermissionError):
        TextTemplates(_Session(_Res(401, {}))).delete_predefined('x')
    with pytest.raises(ValueError, match='Create the template'):
        TextTemplates(_Session()).update_personal(TextTemplate(None, 'x'))


def test_toolbar_round_trip():
    groups = {'_toolbar': ['h-nmr'], 'MS': ['esi']}
    session = _Session(_Res(200, {'sample': groups}), _Res(200, {'id': 1, 'data': groups}))
    tt = TextTemplates(session)
    assert tt.toolbar('sample') == groups
    assert tt.set_toolbar('sample', groups) == groups
    assert session.calls[1] == ('put', '/api/v1/text_templates/update', {'type': 'sample', 'data': groups})
