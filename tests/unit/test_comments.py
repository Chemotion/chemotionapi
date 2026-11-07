"""Comments (M1.3), offline: section names, request bodies, and refusals that send nothing."""
import pytest

from chemotion_api.elements.comments import (
    SECTIONS, Comment, commentable_type, create_comment, load_comments, section_value,
)

COMMENT = {'id': 5, 'content': 'Check the NMR', 'section': 'sample_analyses', 'status': 'Pending',
           'submitter': 'API User', 'created_by': 1, 'resolver_name': None,
           'commentable_id': 3, 'commentable_type': 'Sample'}


class _Res:
    def __init__(self, status, payload=None):
        self.status_code, self._payload, self.text = status, payload, str(payload)
        self.url, self.reason = 'http://eln.test', 'x'

    def json(self):
        return self._payload


class _Session:
    def __init__(self, res=None):
        self.res, self.calls = res, []

    def _call(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs.get('data'), kwargs.get('params')))
        return self.res

    def get(self, url, **kw): return self._call('get', url, **kw)
    def post(self, url, **kw): return self._call('post', url, **kw)
    def put(self, url, **kw): return self._call('put', url, **kw)
    def delete(self, url, **kw): return self._call('delete', url, **kw)


@pytest.mark.parametrize('element_type, section, expected', [
    ('sample', None, 'sample_header'),
    ('sample', 'analyses', 'sample_analyses'),
    ('sample', 'sample_analyses', 'sample_analyses'),
    ('research_plan', 'properties', 'research_plan_research_plan'),  # the server's own spelling
    ('screen', 'header', 'screen_header'),
])
def test_sections_resolve_from_short_or_full_names(element_type, section, expected):
    assert section_value(element_type, section) == expected


def test_an_unknown_section_lists_the_valid_ones():
    with pytest.raises(ValueError, match='scheme'):
        section_value('reaction', 'designer')


def test_every_commentable_type_has_a_header_section():
    assert all('header' in sections for sections in SECTIONS.values())


def test_generic_elements_are_refused():
    with pytest.raises(ValueError, match='not supported on my_klass'):
        commentable_type('my_klass')


def test_create_sends_the_server_type_and_section():
    session = _Session(_Res(201, {'comment': COMMENT}))
    comment = create_comment(session, 'research_plan', 3, 'hi', section='attachments')
    (method, url, data, _), = session.calls
    assert (method, url) == ('post', '/api/v1/comments')
    assert data == {'content': 'hi', 'commentable_id': 3, 'commentable_type': 'ResearchPlan',
                    'section': 'research_plan_attachments'}
    assert comment.id == 5


@pytest.mark.parametrize('element_type, content, section', [
    ('sample', '', None), ('my_klass', 'hi', None), ('sample', 'hi', 'nope'),
])
def test_invalid_comments_send_nothing(element_type, content, section):
    session = _Session()
    with pytest.raises(ValueError):
        create_comment(session, element_type, 3, content, section)
    assert session.calls == []


def test_load_asks_for_the_element_and_wraps_each_comment():
    session = _Session(_Res(200, {'comments': [COMMENT, dict(COMMENT, id=6)]}))
    comments = load_comments(session, 'sample', 3)
    assert [c.id for c in comments] == [5, 6]
    (_, url, _, params), = session.calls
    assert url == '/api/v1/comments' and params == {'commentable_id': 3, 'commentable_type': 'Sample'}


def test_resolve_keeps_the_content_and_takes_the_servers_answer():
    resolved = dict(COMMENT, status='Resolved', resolver_name='API User')
    session = _Session(_Res(200, {'comment': resolved}))
    comment = Comment(session, COMMENT).resolve()
    (method, url, data, _), = session.calls
    assert (method, url, data) == ('put', '/api/v1/comments/5', {'content': 'Check the NMR', 'status': 'Resolved'})
    assert comment.is_resolved and comment.resolver_name == 'API User'


def test_a_refused_update_raises_and_leaves_the_comment_unchanged():
    comment = Comment(_Session(_Res(422, {'error': '422 Unprocessable Entity'})), COMMENT)
    with pytest.raises(Exception, match='updating comment 5'):
        comment.update('new text')
    assert comment.content == 'Check the NMR'


def test_delete():
    session = _Session(_Res(200, {}))
    Comment(session, COMMENT).delete()
    assert session.calls[0][:2] == ('delete', '/api/v1/comments/5')
