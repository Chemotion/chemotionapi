"""Private notes on elements (``/api/v1/private_notes``, M1.4).

A private note is one free-text note per user per element, visible only to its author — unlike a
comment, which every reader of the element sees.
"""
from __future__ import annotations

from typing import Any

from chemotion_api.connection import Connection, request_error
from chemotion_api.elements.comments import COMMENTABLE_TYPES

#: Element types that take private notes: the same five as comments (``private_note_api.rb``).
NOTEABLE_TYPES = COMMENTABLE_TYPES


def noteable_type(element_type: str) -> str:
    """The server's noteable type for a client element type.

    :raises ValueError: for element types the server does not take private notes on.
    """
    try:
        return NOTEABLE_TYPES[element_type]
    except KeyError:
        raise ValueError(f'Private notes are not supported on {element_type} elements '
                         f'(only on {", ".join(NOTEABLE_TYPES)}).') from None


def _load(session: Connection, element_type: str, element_id: int) -> dict[str, Any]:
    """The current user's note on the element; the server answers an empty note (id null) if none."""
    res = session.get('/api/v1/private_notes', params={'noteable_id': element_id,
                                                       'noteable_type': noteable_type(element_type)})
    if res.status_code != 200:
        raise request_error(res, f'loading the private note of {element_type} {element_id}')
    return res.json().get('note') or {}


def get_private_note(session: Connection, element_type: str, element_id: int) -> str | None:
    """Your private note on the element, or ``None`` if you have none."""
    note = _load(session, element_type, element_id)
    return note.get('content') if note.get('id') is not None else None


def set_private_note(session: Connection, element_type: str, element_id: int, content: str) -> None:
    """Create your private note on the element, or replace its text if you already have one."""
    if not isinstance(content, str):
        raise ValueError('A private note is text; use delete_private_note() to remove it.')
    note = _load(session, element_type, element_id)
    if note.get('id') is None:
        res = session.post('/api/v1/private_notes', data={
            'content': content, 'noteable_id': element_id, 'noteable_type': noteable_type(element_type)})
    else:
        res = session.put(f'/api/v1/private_notes/{note["id"]}', data={'content': content})
    if res.status_code not in (200, 201):
        raise request_error(res, f'saving the private note of {element_type} {element_id}')


def delete_private_note(session: Connection, element_type: str, element_id: int) -> bool:
    """Delete your private note on the element. Returns ``False`` if there was none."""
    note = _load(session, element_type, element_id)
    if note.get('id') is None:
        return False
    res = session.delete(f'/api/v1/private_notes/{note["id"]}')
    if res.status_code not in (200, 204):
        raise request_error(res, f'deleting the private note of {element_type} {element_id}')
    return True
