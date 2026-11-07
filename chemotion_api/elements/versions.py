"""Version history of elements, and reverting changes (``/api/v1/versions``, M1.5).

The ELN logs every change to an element and to the records that belong to it (its analyses
containers, a reaction's samples, a wellplate's wells, …). The history lists those changes newest
first; each one can be reverted field by field.

Reverting is deliberately narrow on the server: a change may only set a field the history offers a
revert for, and only to the value the history offers (its ``revertible_value``). The client therefore
builds reverts from the history entries themselves and never from caller-supplied values.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from chemotion_api.connection import Connection, request_error

#: The element types with a history route, and that route's name.
VERSIONED_TYPES = {
    'sample': 'samples',
    'reaction': 'reactions',
    'research_plan': 'research_plans',
    'screen': 'screens',
    'wellplate': 'wellplates',
}

#: The server caps a history page at this many versions.
MAX_PER_PAGE = 100


def versions_route(element_type: str) -> str:
    """The history route of an element type.

    :raises ValueError: for element types without a history (LabIMotion generic elements).
    """
    try:
        return VERSIONED_TYPES[element_type]
    except KeyError:
        raise ValueError(f'{element_type} elements have no version history '
                         f'(only {", ".join(VERSIONED_TYPES)} do).') from None


class VersionField:
    """One changed field within a :class:`VersionChange`."""

    def __init__(self, name: str, data: dict[str, Any]):
        self.name = name
        self._data = dict(data)

    def __repr__(self) -> str:
        return f'VersionField({self.name!r}: {self.old_value!r} -> {self.new_value!r})'

    label = property(lambda self: self._data.get('label'), doc='The label the UI shows.')
    kind = property(lambda self: self._data.get('kind'), doc="How the value is rendered, e.g. ``'string'``.")
    old_value = property(lambda self: self._data.get('old_value'), doc='The value before this change.')
    new_value = property(lambda self: self._data.get('new_value'), doc='The value this change set.')
    current_value = property(lambda self: self._data.get('current_value'), doc='The value now.')
    revertible_value = property(lambda self: self._data.get('revertible_value'),
                                doc='What reverting this field writes back.')

    @property
    def is_revertible(self) -> bool:
        """Whether the server offers a revert for this field (the UI's revert checkbox)."""
        return bool(self._data.get('revert'))

    def revert_payload(self) -> list[dict[str, Any]]:
        """This field's entries in a revert request: itself plus the columns restored with it."""
        linked = self._data.get('linked_revertible_values') or {}
        return [{'name': self.name, 'value': self.revertible_value},
                *({'name': name, 'value': value} for name, value in linked.items())]


class VersionChange:
    """The changes one version made to one record (the element itself, or a record belonging to it)."""

    def __init__(self, session: Connection, data: dict[str, Any]):
        self._session = session
        self._data = dict(data)
        self.fields: dict[str, VersionField] = {
            name: VersionField(name, field) for name, field in (data.get('fields') or {}).items()}

    def __repr__(self) -> str:
        return f'VersionChange({self.klass_name} {self.db_id}: {", ".join(self.fields)})'

    db_id = property(lambda self: self._data.get('db_id'), doc='The id of the changed record.')
    klass_name = property(lambda self: self._data.get('klass_name'),
                          doc="The changed record's type, e.g. ``'Sample'`` or ``'Container'``.")
    name = property(lambda self: self._data.get('name') or [],
                    doc="Where the UI shows it, e.g. ``['Sample Properties']``.")

    def revert_payload(self, fields: Iterable[str] | None = None) -> dict[str, Any] | None:
        """The revert request entry for this record, or ``None`` if nothing selected is revertible.

        :param fields: field names to revert; ``None`` for every revertible field.
        """
        wanted = None if fields is None else set(fields)
        chosen = [f for f in self.fields.values()
                  if f.is_revertible and (wanted is None or f.name in wanted)]
        if not chosen:
            return None
        return {'db_id': self.db_id, 'klass_name': self.klass_name,
                'fields': [entry for f in chosen for entry in f.revert_payload()]}

    def revert(self, fields: Iterable[str] | None = None) -> None:
        """Revert this record's fields to what they were before this change. Sent right away.

        :param fields: field names to revert; ``None`` for every revertible field.
        :raises ValueError: if none of them can be reverted.
        """
        revert_changes(self._session, [self], fields)


class Version:
    """One entry of an element's history: who changed what, when."""

    def __init__(self, session: Connection, data: dict[str, Any]):
        self._session = session
        self._data = dict(data)
        self.changes = [VersionChange(session, c) for c in data.get('changes') or []]

    def __repr__(self) -> str:
        return f'Version(id={self.id}, time={self.time!r}, user={self.user!r}, changes={len(self.changes)})'

    id = property(lambda self: self._data.get('id'),
                  doc='Position in the history, counted from the oldest (1).')
    time = property(lambda self: self._data.get('time'), doc='When it happened (ISO 8601).')
    user = property(lambda self: self._data.get('user'), doc="Who made it, by full name.")

    def revert(self, fields: Iterable[str] | None = None) -> None:
        """Revert what this version changed, across all records it touched. Sent right away.

        Reload the element afterwards to see the result.

        :param fields: field names to revert (in any of the changed records); ``None`` for every
            revertible field.
        :raises ValueError: if none of them can be reverted.
        """
        revert_changes(self._session, self.changes, fields)


def load_versions(session: Connection, element_type: str, element_id: int) -> list[Version]:
    """The element's whole history, newest first."""
    route = versions_route(element_type)
    versions: list[Version] = []
    page = 1
    while True:
        res = session.get(f'/api/v1/versions/{route}/{element_id}',
                          params={'page': page, 'per_page': MAX_PER_PAGE})
        if res.status_code != 200:
            raise request_error(res, f'loading the history of {element_type} {element_id}')
        versions.extend(Version(session, v) for v in res.json().get('versions') or [])
        try:
            pages = int(res.headers.get('X-Total-Pages') or 1)
        except ValueError:
            pages = 1
        if page >= pages:
            return versions
        page += 1


def revert_changes(session: Connection, changes: Iterable[VersionChange],
                   fields: Iterable[str] | None = None) -> None:
    """Send one revert request for the given changes. It is applied completely or not at all."""
    wanted = None if fields is None else list(fields)
    payload = [p for c in changes if (p := c.revert_payload(wanted)) is not None]
    if not payload:
        raise ValueError('Nothing to revert: none of the selected fields can be reverted.')
    res = session.post('/api/v1/versions/revert', data={'changes': payload})
    if res.status_code not in (200, 201):
        raise request_error(res, 'reverting changes')
