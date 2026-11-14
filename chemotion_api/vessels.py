"""Vessels: reusable vessel templates and the physical vessel instances made from them (M4.2).

A **template** (``VesselTemplate``) describes a kind of vessel — name, vessel and material type,
volume — and is shared by everyone on the ELN. A **vessel** (``Vessel``) is one physical item of a
template, owned by you and kept in collections, with its own name, short label, weight and codes.
Both have UUID ids. ``/api/v1/vessels``.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any

from chemotion_api.connection import Connection, request_error

_URL = '/api/v1/vessels'

TEMPLATE_FIELDS = ('name', 'details', 'material_details', 'material_type', 'vessel_type', 'volume_amount',
                   'volume_unit')
VESSEL_FIELDS = ('name', 'description', 'bar_code', 'qr_code', 'weight_amount', 'weight_unit')


@dataclass
class VesselTemplate:
    """A vessel template. Change its fields and :meth:`save` it."""
    id: str | None = None
    name: str = ''
    vessel_type: str | None = None
    material_type: str | None = None
    material_details: str | None = None
    volume_amount: float | None = None
    volume_unit: str | None = None
    details: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)
    _session: Connection | None = field(default=None, repr=False, compare=False)

    @classmethod
    def from_json(cls, data: dict[str, Any], session: Connection | None = None) -> VesselTemplate:
        names = {f.name for f in fields(cls)} - {'raw', '_session'}
        values: dict[str, Any] = {k: data.get(k) for k in names if k in data}
        values['name'] = values.get('name') or ''
        return cls(**values, raw=data, _session=session)

    def _payload(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in TEMPLATE_FIELDS if getattr(self, k) is not None}

    def save(self) -> VesselTemplate:
        """Create the template, or update it (``POST /vessels/templates/create``, ``PUT /vessels/templates/:id``).

        :raises ValueError: if another template already has this name (on create).
        """
        session = _con(self._session)
        if not self.name:
            raise ValueError('A vessel template needs a name.')
        if self.id is None:
            res = session.post(f'{_URL}/templates/create', data=self._payload())
            if res.status_code == 409:
                raise ValueError(f'A vessel template named "{self.name}" already exists.')
        else:
            res = session.put(f'{_URL}/templates/{self.id}', data=self._payload())
        if res.status_code not in (200, 201):
            raise request_error(res, f'saving vessel template "{self.name}"')
        self.__dict__.update(VesselTemplate.from_json(res.json(), session).__dict__)
        return self

    def delete(self) -> None:
        """Delete the template (``DELETE /vessels/vessel_template/:id``).

        :raises ValueError: while any vessel is still made from it.
        """
        res = _con(self._session).delete(f'{_URL}/vessel_template/{self.id}')
        if res.status_code == 400:
            raise ValueError(f'Vessel template "{self.name}" still has vessels; delete them first.')
        if res.status_code not in (200, 204):
            raise request_error(res, f'deleting vessel template "{self.name}"')

    def vessels(self, collection=None) -> list[Vessel]:
        """Your vessels of this template, optionally only those in ``collection``
        (``GET /vessels/templates/:id``)."""
        params = {'collection_id': collection.id} if collection is not None else {}
        res = _con(self._session).get(f'{_URL}/templates/{self.id}', params=params)
        if res.status_code != 200:
            raise request_error(res, f'loading the vessels of template "{self.name}"')
        return [Vessel.from_json(v, self._session) for v in res.json().get('vessels') or []]


@dataclass
class Vessel:
    """One vessel. Change :data:`VESSEL_FIELDS` and :meth:`save` it."""
    id: str
    name: str | None = None
    short_label: str | None = None
    description: str | None = None
    bar_code: str | None = None
    qr_code: str | None = None
    weight_amount: float | None = None
    weight_unit: str | None = None
    template: VesselTemplate | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)
    _session: Connection | None = field(default=None, repr=False, compare=False)

    element_type = 'vessel'

    @classmethod
    def from_json(cls, data: dict[str, Any], session: Connection | None = None) -> Vessel:
        template = data.get('vessel_template')
        return cls(id=data['id'], **{k: data.get(k) for k in VESSEL_FIELDS + ('short_label',)},
                   template=VesselTemplate.from_json(template, session) if template else None,
                   raw=data, _session=session)

    def save(self) -> Vessel:
        """Save the changed fields (``PUT /vessels/:id``). The template is changed on the template."""
        body = {k: getattr(self, k) for k in VESSEL_FIELDS if getattr(self, k) is not None}
        res = _con(self._session).put(f'{_URL}/{self.id}', data=body)
        if res.status_code not in (200, 201):
            raise request_error(res, f'saving vessel {self.id}')
        self.__dict__.update(Vessel.from_json(res.json(), self._session).__dict__)
        return self

    def delete(self) -> None:
        """Delete this vessel (``DELETE /vessels/:id``)."""
        res = _con(self._session).delete(f'{_URL}/{self.id}')
        if res.status_code == 401:
            raise PermissionError(f'You may not delete vessel {self.short_label or self.id}.')
        if res.status_code not in (200, 204):
            raise request_error(res, f'deleting vessel {self.id}')


def _con(session: Connection | None) -> Connection:
    if session is None:
        raise ValueError('Not attached to a server connection.')
    return session


def _template_id(template: VesselTemplate | str) -> str:
    template_id = template if isinstance(template, str) else template.id
    if not template_id:
        raise ValueError('Save the vessel template first.')
    return template_id


def templates(session: Connection) -> list[VesselTemplate]:
    """All vessel templates (``GET /vessels/names/all``)."""
    res = session.get(f'{_URL}/names/all')
    if res.status_code != 200:
        raise request_error(res, 'loading the vessel templates')
    return [VesselTemplate.from_json(t, session) for t in res.json() or []]


def load_template(session: Connection, template_id: str) -> VesselTemplate:
    res = session.get(f'{_URL}/material/{template_id}')
    if res.status_code != 200:
        raise request_error(res, f'loading vessel template {template_id}')
    return VesselTemplate.from_json(res.json(), session)


def load_vessel(session: Connection, vessel_id: str) -> Vessel:
    res = session.get(f'{_URL}/{vessel_id}')
    if res.status_code != 200:
        raise request_error(res, f'loading vessel {vessel_id}')
    return Vessel.from_json(res.json(), session)


def list_vessels(session: Connection, collection_id: int, per_page: int = 50) -> list[Vessel]:
    """Every vessel in a collection, newest first (``GET /vessels``, paged by 50)."""
    out, page = [], 1
    while True:
        res = session.get(_URL, params={'collection_id': collection_id, 'page': page, 'per_page': per_page})
        if res.status_code != 200:
            raise request_error(res, f'listing the vessels of collection {collection_id}')
        rows = res.json().get('vessels') or []
        out += [Vessel.from_json(v, session) for v in rows]
        if len(rows) < per_page or page >= int(res.headers.get('X-Total-Pages', page)):
            return out
        page += 1


def create_vessel(session: Connection, collection_id: int, template: VesselTemplate | str, **fields_) -> Vessel:
    unknown = set(fields_) - {'name', 'description', 'short_label', 'weight_amount', 'weight_unit'}
    if unknown:
        raise ValueError(f'Unknown vessel fields: {", ".join(sorted(unknown))}')
    body = {'vessel_template_id': _template_id(template), 'collection_id': collection_id} | fields_
    res = session.post(f'{_URL}/instances/create', data=body)
    if res.status_code == 403:
        raise PermissionError(f'You may not add vessels to collection {collection_id}.')
    if res.status_code not in (200, 201):
        raise request_error(res, 'creating a vessel')
    return Vessel.from_json(res.json(), session)


def bulk_create_vessels(session: Connection, collection_id: int, template: VesselTemplate | str, count: int,
                        base_name: str | None = None, short_labels: list[str] | None = None) -> list[Vessel]:
    if not 1 <= count <= 100:
        raise ValueError('count is 1 to 100.')
    body: dict[str, Any] = {'vessel_template_id': _template_id(template), 'collection_id': collection_id,
                            'count': count}
    if base_name is not None:
        body['base_name'] = base_name
    if short_labels is not None:
        body['short_labels'] = short_labels
    res = session.post(f'{_URL}/bulk_create', data=body)
    if res.status_code == 403:
        raise PermissionError(f'You may not add vessels to collection {collection_id}.')
    if res.status_code not in (200, 201):
        raise request_error(res, 'creating vessels')
    return [Vessel.from_json(v, session) for v in res.json() or []]
