"""Cell line samples (``/api/v1/cell_lines``, M4.1).

A cell line *sample* is a physical batch of cells (amount, passage, contamination). It belongs to a
cell line *material*, the shared description of the line (organism, tissue, growth medium, …),
which the server finds or creates by name and source when a sample is saved.
"""
from __future__ import annotations

from typing import Any, cast

from chemotion_api.connection import request_error
from chemotion_api.elements.abstract_element import AbstractElement
from chemotion_api.elements.registry import register_element_type

#: The sample's own fields.
SAMPLE_FIELDS = ('name', 'short_label', 'description', 'amount', 'unit', 'passage', 'contamination')
#: The material's fields, as the server's create/update params name them (``material_names`` is
#: the material's ``name``, ``material_description`` its ``description``).
MATERIAL_FIELDS = ('material_names', 'source', 'cell_type', 'organism', 'tissue', 'mutation', 'disease',
                   'growth_medium', 'biosafety_level', 'variant', 'optimal_growth_temp', 'cryo_pres_medium',
                   'gender', 'material_description')
_MATERIAL_KEYS = {'material_names': 'name', 'material_description': 'description'}
#: Units the UI offers for the cell amount.
AMOUNT_UNITS = ('g', 'units/ml', 'cell count', 'cells/ml')


@register_element_type('cell_line', url='/api/v1/cell_lines', response_key='cell_line')
class CellLine(AbstractElement):
    """
    A cell line sample. It extends :class:`chemotion_api.elements.abstract_element.AbstractElement`.

    ``properties`` holds the sample fields (:data:`SAMPLE_FIELDS`) and the material fields
    (:data:`MATERIAL_FIELDS`) side by side. ``material_names`` and ``source`` identify the material:
    saving with a name and source the server already knows links the sample to that material,
    otherwise a new material is created. ``amount`` and ``passage`` are integers.

    Usage::

    >>> cells = collection.new_cell_line()
    >>> cells.properties.update(material_names='HeLa', source='ATCC', amount=1000000,
    ...                         unit='cell count', passage=12)
    >>> cells.save()
    >>> part = cells.split(collection)
    """

    def _parse_properties(self) -> dict:
        data = cast(dict, self.json_data)
        material = data.get('cellline_material') or {}
        props: dict[str, Any] = {key: data.get(key) for key in SAMPLE_FIELDS}
        for key in MATERIAL_FIELDS:
            props[key] = material.get(_MATERIAL_KEYS.get(key, key))
        return props

    @property
    def attachments(self):  # type: ignore[override]
        """Cell lines have no element attachments (their files live in analyses): always ``None``."""
        return None

    @property
    def material_id(self) -> int | None:
        """The id of the cell line material this sample belongs to."""
        return (cast(dict, self.json_data).get('cellline_material') or {}).get('id')

    def _clean_properties_data(self, serialize_data: dict | None = None) -> dict:
        props = self.properties
        out: dict[str, Any] = {key: props.get(key) for key in SAMPLE_FIELDS + MATERIAL_FIELDS
                               if props.get(key) is not None}
        for key in ('amount', 'passage'):
            if key in out:
                out[key] = int(out[key])
        if not self.is_new:
            out['cell_line_sample_id'] = str(self.id)
        return out

    def clean_data(self) -> dict:
        for key in ('material_names', 'source', 'unit') if self.is_new else ('unit',):
            if not self.properties.get(key):
                raise ValueError(f'A cell line needs {key!r}.')
        for key in ('amount', 'passage') if self.is_new else ('amount',):
            if self.properties.get(key) is None:
                raise ValueError(f'A cell line needs {key!r} (an integer >= 0).')
        data = super().clean_data()
        # Not part of the cell line params; the server rejects nothing, but keep the body lean.
        for key in ('type', 'is_new', 'segments', 'attachments', 'cellline_material'):
            data.pop(key, None)
        if not self.is_new:
            data.pop('id', None)
        return data

    def save_url(self) -> str:
        # Both create (POST) and update (PUT) use the collection URL; the id travels in the body.
        return '/api/v1/cell_lines'

    def _unwrap_response(self, res_json: dict) -> dict:
        return res_json if 'cell_line' not in res_json else res_json['cell_line']

    def copy(self, collection) -> CellLine:
        """A copy of this cell line sample in ``collection``, created right away
        (``POST /api/v1/cell_lines/copy``)."""
        return self._copy_or_split('copy', collection)

    def split(self, collection) -> CellLine:  # type: ignore[override]
        """A split of this cell line sample into ``collection``, created right away and labelled as
        a child of this one (``POST /api/v1/cell_lines/split``)."""
        return self._copy_or_split('split', collection)

    def _copy_or_split(self, action: str, collection) -> CellLine:
        body = {'id': self._saved_id_for(action), 'collection_id': collection.id,
                'container': self._fresh_container()}
        res = self._session.post(f'/api/v1/cell_lines/{action}', data=body)
        if res.status_code == 403:
            raise PermissionError(f'You may not add cell lines to collection "{collection.label}".')
        if res.status_code not in (200, 201):
            raise request_error(res, f'{action} of cell line {self.id}')
        return CellLine(self._generic_segments, self._session, json_data=res.json())

    @staticmethod
    def _fresh_container() -> dict:
        from chemotion_api.elements.empty_elements import init_container
        return init_container()


def material_names(session) -> list[dict]:
    """All cell line materials: ``{'id', 'name', 'source'}`` dicts (``GET /api/v1/cell_lines/names/all``)."""
    res = session.get('/api/v1/cell_lines/names/all')
    if res.status_code != 200:
        raise request_error(res, 'loading the cell line names')
    return res.json() or []


def load_material(session, material_id: int) -> dict:
    """One cell line material (``GET /api/v1/cell_lines/material/:id``)."""
    res = session.get(f'/api/v1/cell_lines/material/{material_id}')
    if res.status_code != 200:
        raise request_error(res, f'loading cell line material {material_id}')
    return res.json()
