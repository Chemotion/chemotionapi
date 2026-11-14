"""Private notes (M1.4), offline: create-or-update, delete, and what is refused."""
import pytest

from chemotion_api.elements.private_notes import delete_private_note, get_private_note, set_private_note

NO_NOTE = {'note': {'id': None, 'content': None}}
NOTE = {'note': {'id': 7, 'content': 'mine', 'noteable_id': 3, 'noteable_type': 'Reaction'}}


class _Res:
    def __init__(self, status, payload=None):
        self.status_code, self._payload, self.text = status, payload, str(payload)
        self.url, self.reason = 'http://eln.test', 'x'

    def json(self):
        return self._payload


class _Session:
    def __init__(self, *responses):
        self._responses, self.calls = list(responses), []

    def _call(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs.get('data'), kwargs.get('params')))
        return self._responses.pop(0)

    def get(self, url, **kw): return self._call('get', url, **kw)
    def post(self, url, **kw): return self._call('post', url, **kw)
    def put(self, url, **kw): return self._call('put', url, **kw)
    def delete(self, url, **kw): return self._call('delete', url, **kw)


def test_no_note_is_none():
    session = _Session(_Res(200, NO_NOTE))
    assert get_private_note(session, 'reaction', 3) is None
    assert session.calls[0][3] == {'noteable_id': 3, 'noteable_type': 'Reaction'}


def test_an_existing_note_is_returned():
    assert get_private_note(_Session(_Res(200, NOTE)), 'reaction', 3) == 'mine'


def test_set_creates_when_there_is_no_note():
    session = _Session(_Res(200, NO_NOTE), _Res(201, NOTE))
    set_private_note(session, 'research_plan', 3, 'hello')
    assert session.calls[1][:3] == ('post', '/api/v1/private_notes',
                                    {'content': 'hello', 'noteable_id': 3, 'noteable_type': 'ResearchPlan'})


def test_set_updates_the_existing_note():
    session = _Session(_Res(200, NOTE), _Res(200, NOTE))
    set_private_note(session, 'reaction', 3, 'changed')
    assert session.calls[1][:3] == ('put', '/api/v1/private_notes/7', {'content': 'changed'})


def test_delete():
    session = _Session(_Res(200, NOTE), _Res(204))
    assert delete_private_note(session, 'reaction', 3) is True
    assert session.calls[1][:2] == ('delete', '/api/v1/private_notes/7')


def test_deleting_nothing_sends_no_delete():
    session = _Session(_Res(200, NO_NOTE))
    assert delete_private_note(session, 'reaction', 3) is False
    assert len(session.calls) == 1


def test_generic_elements_are_refused_before_sending():
    session = _Session()
    with pytest.raises(ValueError, match='not supported on my_klass'):
        get_private_note(session, 'my_klass', 3)
    assert session.calls == []


def test_none_is_not_a_note():
    with pytest.raises(ValueError, match='delete_private_note'):
        set_private_note(_Session(_Res(200, NO_NOTE)), 'sample', 3, None)
