"""Comments on elements and their sections (``/api/v1/comments``, M1.3)."""
from __future__ import annotations

from typing import Any

from chemotion_api.connection import Connection, request_error

#: The server's commentable types (``Comment::COMMENTABLE_TYPE``), keyed by the client's element
#: type. LabIMotion generic elements are not commentable.
COMMENTABLE_TYPES = {
    'sample': 'Sample',
    'reaction': 'Reaction',
    'wellplate': 'Wellplate',
    'screen': 'Screen',
    'research_plan': 'ResearchPlan',
}

#: Sections a comment can be attached to, per element type, as ``app/models/comment.rb`` defines
#: them: short name -> the value the server stores. ``header`` is the element as a whole (the UI's
#: comment button in the detail header).
SECTIONS: dict[str, dict[str, str]] = {
    'sample': {'header': 'sample_header', 'properties': 'sample_properties', 'analyses': 'sample_analyses',
               'qc_curation': 'sample_qc_curation', 'results': 'sample_results',
               'references': 'sample_references', 'inventory': 'sample_inventory'},
    'reaction': {'header': 'reaction_header', 'scheme': 'reaction_scheme', 'properties': 'reaction_properties',
                 'references': 'reaction_references', 'analyses': 'reaction_analyses',
                 'green_chemistry': 'reaction_green_chemistry'},
    'wellplate': {'header': 'wellplate_header', 'properties': 'wellplate_properties',
                  'analyses': 'wellplate_analyses', 'designer': 'wellplate_designer', 'list': 'wellplate_list'},
    'screen': {'header': 'screen_header', 'properties': 'screen_properties', 'analyses': 'screen_analyses'},
    'research_plan': {'header': 'research_plan_header', 'properties': 'research_plan_research_plan',
                      'analyses': 'research_plan_analyses', 'attachments': 'research_plan_attachments',
                      'references': 'research_plan_references', 'metadata': 'research_plan_metadata'},
}

PENDING = 'Pending'
RESOLVED = 'Resolved'


def commentable_type(element_type: str) -> str:
    """The server's commentable type for a client element type.

    :raises ValueError: for element types the server does not accept comments on.
    """
    try:
        return COMMENTABLE_TYPES[element_type]
    except KeyError:
        raise ValueError(f'Comments are not supported on {element_type} elements '
                         f'(only on {", ".join(COMMENTABLE_TYPES)}).') from None


def section_value(element_type: str, section: str | None) -> str:
    """Resolve a section given as a short name (``'analyses'``) or full value (``'sample_analyses'``).

    ``None`` means the element as a whole (its header section).

    :raises ValueError: for a section the element type does not have.
    """
    sections = SECTIONS[element_type]
    if section is None:
        return sections['header']
    if section in sections:
        return sections[section]
    if section in sections.values():
        return section
    raise ValueError(f'{element_type} has no comment section {section!r}; '
                     f'use one of {", ".join(sections)}')


class Comment:
    """One comment on an element. Changes are sent right away.

    Only the comment's author may edit or delete it; anyone who can read the element may
    :meth:`resolve` it. A resolved comment can no longer be edited.
    """

    def __init__(self, session: Connection, data: dict[str, Any]):
        self._session = session
        self._data = dict(data)

    def __repr__(self) -> str:
        return f'Comment(id={self.id}, section={self.section!r}, status={self.status!r})'

    @property
    def json_data(self) -> dict[str, Any]:
        """The comment as the server sent it."""
        return self._data

    id = property(lambda self: self._data.get('id'), doc='The comment id.')
    content = property(lambda self: self._data.get('content'), doc='The comment text.')
    section = property(lambda self: self._data.get('section'),
                       doc="The section's stored value, e.g. ``'sample_analyses'``.")
    status = property(lambda self: self._data.get('status'), doc="``'Pending'`` or ``'Resolved'``.")
    submitter = property(lambda self: self._data.get('submitter'), doc="The author's full name.")
    created_by = property(lambda self: self._data.get('created_by'), doc="The author's user id.")
    resolver_name = property(lambda self: self._data.get('resolver_name'),
                             doc='Who resolved it, if anyone.')
    created_at = property(lambda self: self._data.get('created_at'))
    updated_at = property(lambda self: self._data.get('updated_at'))

    @property
    def is_resolved(self) -> bool:
        return self.status == RESOLVED

    def update(self, content: str) -> Comment:
        """Replace the text. Only the author can, and only while the comment is pending."""
        return self._put({'content': content})

    def resolve(self) -> Comment:
        """Mark the comment resolved. Anyone who can read the element can do this."""
        return self._put({'content': self.content, 'status': RESOLVED})

    def delete(self) -> None:
        """Delete the comment. Only its author can."""
        res = self._session.delete(f'/api/v1/comments/{self.id}')
        if res.status_code not in (200, 204):
            raise request_error(res, f'deleting comment {self.id}')

    def _put(self, body: dict[str, Any]) -> Comment:
        res = self._session.put(f'/api/v1/comments/{self.id}', data=body)
        if res.status_code != 200:
            raise request_error(res, f'updating comment {self.id}')
        self._data = res.json()['comment']
        return self


def load_comments(session: Connection, element_type: str, element_id: int) -> list[Comment]:
    """All comments on an element, pending first, then by section, newest first (the server's order)."""
    res = session.get('/api/v1/comments', params={'commentable_id': element_id,
                                                  'commentable_type': commentable_type(element_type)})
    if res.status_code != 200:
        raise request_error(res, f'loading comments of {element_type} {element_id}')
    return [Comment(session, c) for c in res.json().get('comments') or []]


def create_comment(session: Connection, element_type: str, element_id: int, content: str,
                   section: str | None = None) -> Comment:
    """Add a comment to an element, or to one of its sections."""
    if not content:
        raise ValueError('A comment needs content.')
    body = {
        'content': content,
        'commentable_id': element_id,
        'commentable_type': commentable_type(element_type),
        'section': section_value(element_type, section),
    }
    res = session.post('/api/v1/comments', data=body)
    if res.status_code not in (200, 201):
        raise request_error(res, f'commenting on {element_type} {element_id}')
    return Comment(session, res.json()['comment'])
