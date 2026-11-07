"""Inbox search and assignment (M3.3), offline."""
import pytest

from chemotion_api.elements.attachments import Attachment
from chemotion_api.inbox import Inbox


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


class _El:
    def __init__(self, element_type, eid):
        self.element_type, self.id = element_type, eid


DATASET = {'container': {'id': 50, 'name': 'nmr', 'container_type': 'dataset'}}


def test_assign_to_a_sample_and_drop_the_cached_listing():
    session = _Session(_Res(201, DATASET))
    inbox = Inbox(session)
    inbox._content = inbox._unsorted_content = {'stale': True}
    att = Attachment(session, {'id': 7, 'filename': 'nmr.txt'})
    assert inbox.assign(att, _El('sample', 3)) == DATASET['container']
    assert session.calls == [('post', '/api/v1/inbox/samples/3', {'attachment_id': 7})]
    assert inbox._content is None and inbox._unsorted_content is None


def test_assign_to_a_reaction_variation():
    session = _Session(_Res(201, DATASET))
    Inbox(session).assign(7, _El('reaction', 4), variation=2)
    assert session.calls == [('post', '/api/v1/inbox/reactions/4', {'attachment_id': 7, 'variation': 2})]


@pytest.mark.parametrize('element, kwargs, error', [
    (_El('wellplate', 1), {}, ValueError),
    (_El('sample', None), {}, ValueError),
    (_El('sample', 1), {'variation': 1}, ValueError),
])
def test_assign_rejects_locally(element, kwargs, error):
    session = _Session()
    with pytest.raises(error):
        Inbox(session).assign(7, element, **kwargs)
    assert session.calls == []


def test_assign_refused():
    with pytest.raises(PermissionError):
        Inbox(_Session(_Res(401, {}))).assign(7, _El('sample', 1))
    with pytest.raises(ValueError, match='No such'):
        Inbox(_Session(_Res(404, {}))).assign(7, _El('sample', 1))


def test_search_and_unlinked():
    rows = [{'id': 3, 'name': 'a', 'short_label': 'API-1', 'type': None}]
    session = _Session(_Res(200, {'samples': rows}), _Res(200, {'reactions': []}),
                       _Res(200, {'inbox': {'unlinked_attachments': [{'id': 9, 'filename': 'x.txt'}]}}))
    inbox = Inbox(session)
    assert inbox.search_samples('API-1') == rows
    assert inbox.search_reactions('API-R1') == []
    assert inbox.search_samples('') == []
    (att,) = inbox.unlinked_attachments(sort_by='created_at')
    assert att.filename == 'x.txt'
    assert session.calls[0] == ('get', '/api/v1/inbox/samples', {'search_string': 'API-1'})
    assert session.calls[2] == ('get', '/api/v1/inbox/unlinked_attachments', {'sort_column': 'created_at'})
    with pytest.raises(ValueError):
        inbox.unlinked_attachments(sort_by='size')
