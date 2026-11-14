"""Text templates: the reusable snippets of the UI's rich-text editors (M3.8).

The ELN keeps three kinds (``/api/v1/text_templates``):

* **Predefined** templates, shared by everyone and named (``'h-nmr'``, ``'esi'``, …). Admins and
  users with the global text template editor right maintain them.
* **Personal** templates, your own named snippets.
* Per element type, **your editor toolbar**: which predefined templates the editor of e.g. a sample
  offers, grouped (``{'_toolbar': [...], 'MS': [...]}``).

A template's :attr:`TextTemplate.ops` is a Quill delta, the format of the ELN's rich-text fields
(``description``, an analysis's ``content``, …), so it can be appended to one directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from chemotion_api.connection import Connection, request_error

#: Element types with their own toolbar (``TextTemplate::TYPES``); a generic element's toolbar is
#: kept under its klass name.
TOOLBAR_TYPES = ('sample', 'reaction', 'wellplate', 'screen', 'research_plan', 'reaction_description',
                 'device_description')

_URL = '/api/v1/text_templates'


@dataclass
class TextTemplate:
    """One predefined or personal template."""
    id: int | None
    name: str
    type: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def ops(self) -> list[dict[str, Any]]:
        """The template text as Quill delta operations."""
        return list((self.data or {}).get('ops') or [])

    @property
    def text(self) -> str:
        """The template as plain text, without formatting."""
        return ''.join(op['insert'] for op in self.ops if isinstance(op.get('insert'), str))

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> TextTemplate:
        return cls(id=data.get('id'), name=data.get('name') or '', type=data.get('type'), data=data.get('data') or {})


def _ops_data(ops: list[dict] | str | dict) -> dict:
    if isinstance(ops, str):
        return {'ops': [{'insert': ops}]}
    if isinstance(ops, dict):
        return ops
    return {'ops': list(ops)}


class TextTemplates:
    """Reads and edits text templates. Get one from ``instance.text_templates()``.

    Usage::

    >>> tt = instance.text_templates()
    >>> esi = tt.predefined('esi')
    >>> sample.properties['description']['ops'] += esi.ops
    >>> mine = tt.create_personal('yield note', 'Yield after column: ')
    """

    def __init__(self, session: Connection):
        self._session = session

    def predefined_names(self) -> list[str]:
        """The names of all predefined templates, newest first."""
        res = self._session.get(f'{_URL}/predefinedNames')
        if res.status_code != 200:
            raise request_error(res, 'loading the predefined text template names')
        return list(res.json().get('text_templates') or [])

    def predefined(self, name: str) -> TextTemplate | None:
        """The predefined template ``name``, or ``None``."""
        res = self._session.get(f'{_URL}/by_name', params={'name': name})
        if res.status_code != 200:
            raise request_error(res, f'loading text template "{name}"')
        found = res.json().get('text_templates') or []
        return TextTemplate.from_json(found[0]) if found else None

    def create_predefined(self, name: str, ops: list[dict] | str | dict) -> TextTemplate:
        """Create a predefined template for everyone. Admins and global template editors only."""
        return self._send_predefined('post', {'name': name, 'data': _ops_data(ops)}, f'creating text template "{name}"')

    def update_predefined(self, template: TextTemplate) -> TextTemplate:
        """Save a changed predefined template (name and data). Admins and global template editors only."""
        return self._send_predefined('put', {'id': template.id, 'name': template.name, 'data': template.data},
                                     f'updating text template "{template.name}"')

    def delete_predefined(self, name: str) -> None:
        """Delete a predefined template. Admins and global template editors only."""
        res = self._session.delete(f'{_URL}/by_name', params={'name': name})
        if res.status_code == 401:
            raise PermissionError('Only admins and global text template editors can delete predefined templates.')
        if res.status_code not in (200, 204):
            raise request_error(res, f'deleting text template "{name}"')

    def _send_predefined(self, method: str, body: dict, what: str) -> TextTemplate:
        res = getattr(self._session, method)(f'{_URL}/predefined_text_template', data=body)
        if res.status_code == 401:
            raise PermissionError('Only admins and global text template editors can change predefined templates.')
        if res.status_code == 422:
            raise ValueError(f'{what}: {res.text}')
        if res.status_code not in (200, 201):
            raise request_error(res, what)
        return TextTemplate.from_json(res.json())

    def personal(self) -> list[TextTemplate]:
        """Your personal templates, newest first."""
        res = self._session.get(f'{_URL}/personal')
        if res.status_code != 200:
            raise request_error(res, 'loading your personal text templates')
        return [TextTemplate.from_json(t) for t in res.json().get('text_templates') or []]

    def create_personal(self, name: str, ops: list[dict] | str | dict) -> TextTemplate:
        """Create a personal template.

        :param ops: Quill delta operations, a ``{'ops': [...]}`` delta, or plain text.
        :raises ValueError: if you already have a template of that name.
        """
        res = self._session.post(f'{_URL}/personal', data={'name': name, 'data': _ops_data(ops)})
        if res.status_code == 422:
            raise ValueError(f'Cannot create text template "{name}": {res.text}')
        if res.status_code not in (200, 201):
            raise request_error(res, f'creating text template "{name}"')
        return TextTemplate.from_json(res.json())

    def update_personal(self, template: TextTemplate) -> TextTemplate:
        """Save a changed personal template (its name and data)."""
        if template.id is None:
            raise ValueError('Create the template before updating it.')
        res = self._session.put(f'{_URL}/personal/{template.id}',
                                data={'id': template.id, 'name': template.name, 'data': template.data})
        if res.status_code == 422:
            raise ValueError(f'Cannot rename text template to "{template.name}": {res.text}')
        if res.status_code not in (200, 201):
            raise request_error(res, f'updating text template {template.id}')
        return TextTemplate.from_json(res.json())

    def delete_personal(self, template: TextTemplate | int) -> None:
        """Delete one of your personal templates."""
        template_id = template if isinstance(template, int) else template.id
        res = self._session.delete(f'{_URL}/personal/{template_id}')
        if res.status_code not in (200, 204):
            raise request_error(res, f'deleting text template {template_id}')

    def toolbar(self, element_type: str) -> dict[str, list[str]]:
        """Which predefined templates your editor offers for ``element_type`` (one of
        :data:`TOOLBAR_TYPES`, or a generic element's klass name), by group:
        ``{'_toolbar': [names], 'MS': [names]}``."""
        res = self._session.get(f'{_URL}/by_type', params={'type': element_type})
        if res.status_code != 200:
            raise request_error(res, f'loading your {element_type} text templates')
        return dict(res.json().get(element_type) or {})

    def set_toolbar(self, element_type: str, groups: dict[str, list[str]]) -> dict[str, list[str]]:
        """Replace your editor's template selection for ``element_type`` (see :meth:`toolbar`)."""
        res = self._session.put(f'{_URL}/update', data={'type': element_type, 'data': groups})
        if res.status_code not in (200, 201):
            raise request_error(res, f'saving your {element_type} text templates')
        return dict(res.json().get('data') or {})
