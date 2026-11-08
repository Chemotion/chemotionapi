"""Your profile: list layouts, display options, editor settings and structure templates (M7.1).

``/api/v1/profiles``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from chemotion_api.connection import Connection, request_error

#: Display switches and their meaning (``profile_api.rb``).
DISPLAY_FIELDS = ('show_external_name', 'show_sample_name', 'show_sample_short_label', 'curation')


@dataclass
class Profile:
    """Your profile. Change :attr:`data` (``layout`` — the element tabs and their order —,
    ``layout_detail_<type>``, ``default_structure_editor``, ``filters``, ``inbox_auto``, …) or the
    display fields and :meth:`save` it. The server merges ``data`` into what it has."""
    data: dict[str, Any] = field(default_factory=dict)
    show_external_name: bool | None = None
    show_sample_name: bool | None = None
    show_sample_short_label: bool | None = None
    curation: int | None = None
    structure_templates: list[dict[str, Any]] = field(default_factory=list)
    _session: Connection | None = field(default=None, repr=False, compare=False)

    @classmethod
    def from_json(cls, data: dict[str, Any], session: Connection | None = None) -> Profile:
        return cls(data=data.get('data') or {}, show_external_name=data.get('show_external_name'),
                   show_sample_name=data.get('show_sample_name'),
                   show_sample_short_label=data.get('show_sample_short_label'), curation=data.get('curation'),
                   structure_templates=data.get('user_templates') or [], _session=session)

    def _con(self) -> Connection:
        if self._session is None:
            raise ValueError('Not attached to a server connection.')
        return self._session

    def save(self) -> Profile:
        """Save the profile (``PUT /api/v1/profiles``) and reload it."""
        body: dict[str, Any] = {'data': self.data}
        body |= {k: getattr(self, k) for k in DISPLAY_FIELDS if getattr(self, k) is not None}
        res = self._con().put('/api/v1/profiles', data=body)
        if res.status_code not in (200, 201):
            raise request_error(res, 'saving your profile')
        self.__dict__.update(load_profile(self._con()).__dict__)
        return self

    def add_structure_template(self, content: str) -> dict:
        """Store a Ketcher structure template (the editor's file content) in your template list
        (``POST /api/v1/profiles``). Reload the profile to see it."""
        if not content:
            raise ValueError('The template content is empty.')
        res = self._con().post('/api/v1/profiles', data={'content': content})
        if res.status_code not in (200, 201):
            raise request_error(res, 'saving a structure template')
        return res.json()

    def delete_structure_template(self, template: dict) -> None:
        """Delete one of :attr:`structure_templates` (``DELETE /api/v1/profiles``).

        Only templates listed in this profile are accepted: the route deletes whatever file path
        it is given, so the client never sends a path the server did not hand out as a template.
        """
        path = (template.get('props') or {}).get('path')
        known = {(t.get('props') or {}).get('path') for t in self.structure_templates}
        if not path or path not in known or '/user_templates/' not in path:
            raise ValueError('Not one of this profile\'s structure templates.')
        res = self._con().delete('/api/v1/profiles', params={'path': path})
        if res.status_code not in (200, 204):
            raise request_error(res, 'deleting a structure template')
        self.structure_templates = [t for t in self.structure_templates if (t.get('props') or {}).get('path') != path]


def load_profile(session: Connection) -> Profile:
    res = session.get('/api/v1/profiles')
    if res.status_code != 200:
        raise request_error(res, 'loading your profile')
    return Profile.from_json(res.json(), session)


def ketcher_options(session: Connection) -> dict:
    """Your Ketcher 2 editor settings, ``{}`` for the defaults (``GET /profiles/editors/ketcher-options``)."""
    res = session.get('/api/v1/profiles/editors/ketcher-options')
    if res.status_code != 200:
        raise request_error(res, 'loading your Ketcher settings')
    data = res.json() or {}
    if data.get('status') is False:
        raise ConnectionError('; '.join(data.get('error_messages') or ['Ketcher settings unreadable']))
    return data.get('settings') or {}


def save_ketcher_options(session: Connection, settings: dict) -> None:
    """Replace your Ketcher 2 editor settings (``PUT /profiles/editors/ketcher-options``).

    :raises ValueError: for settings the server does not accept.
    """
    res = session.put('/api/v1/profiles/editors/ketcher-options', data={'data': settings})
    if res.status_code in (400, 422):
        raise ValueError(f'The Ketcher settings were refused: {res.text}')
    if res.status_code not in (200, 201):
        raise request_error(res, 'saving your Ketcher settings')
    data = res.json() or {}
    if isinstance(data, dict) and data.get('status') is False:
        raise ValueError('; '.join(data.get('error_messages') or ['Ketcher settings refused']))
