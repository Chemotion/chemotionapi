"""Cell-line samples, and the cell-line *material* they share.

A cell-line sample (amount, passage, contamination…) belongs to a **material**: the cell line as a
concept — name, source, organism, tissue, growth medium and so on — shared by every sample of it.
This client keeps the two apart (owner, 2026-11-13): ``properties`` holds the sample's own fields,
:attr:`CellLine.material` the shared ones.

How the server treats the material on a save, and what this client does about it:

* It looks the material up by ``name`` and ``source``. Changing either links the sample to another
  material (created if none matches). Every save sends the full material, so a save that only
  touched the sample never re-links it by accident.
* It applies changes to the material's other fields **only if you created it** (or nobody did) and
  otherwise ignores them while still answering success. This client checks first and raises
  ``PermissionError`` instead of letting the change vanish.
* A change to the material shows on **every** sample of that cell line.
"""
import copy
from typing import Any, cast

from chemotion_api.elements.abstract_element import AbstractElement
from chemotion_api.models import CellLineMaterialModel, CellLinePropertiesModel, validate_field
from chemotion_api.utils import PropertyDict

SAMPLE_FIELDS = ('name', 'description', 'amount', 'unit', 'passage', 'contamination')
MATERIAL_FIELDS = tuple(CellLineMaterialModel.model_fields)
#: Request names of material fields whose API parameter differs from the stored column.
_MATERIAL_PARAM = {'name': 'material_names', 'description': 'material_description'}
_REQUIRED = ('amount', 'unit', 'passage')


class CellLine(AbstractElement):
    """A cell-line sample. See the module documentation for how the shared material behaves.

    Usage::

        >>> line = collection.new_cell_line('HeLa', source='ATCC')
        >>> line.properties['amount'] = 1_000_000
        >>> line.properties['unit'] = 'cells'
        >>> line.properties['passage'] = 3
        >>> line.material['organism'] = 'Homo sapiens'
        >>> line.save()
    """

    _properties_model = CellLinePropertiesModel
    _attachable_type = 'CelllineSample'

    def _set_json_data(self, json_data):
        super()._set_json_data(json_data)
        material = cast(dict, self.json_data).get('cellline_material') or {}
        self._material = {key: material.get(key) for key in MATERIAL_FIELDS}
        self._material_loaded = copy.deepcopy(self._material)
        self._material_owner = material.get('created_by')

    def _parse_properties(self) -> dict:
        data = cast(dict, self.json_data)
        return self._validated_properties({key: data.get(key) for key in SAMPLE_FIELDS})

    @property
    def material(self) -> PropertyDict:
        """The cell line's shared material. Changes reach every sample of it; see the module notes."""
        self._ensure_loaded()
        return PropertyDict(self._on_material_change, self._material)

    def _on_material_change(self, dict_obj, name, value):
        if len(name) > 1:
            raise ValueError('Material fields are single values; assign the whole field.')
        dict_obj[-1][name[-1]] = validate_field(CellLineMaterialModel, name[0], value[-1])
        return False

    # Routes: the cell-line API takes both create and update on /cell_lines, with the id in the
    # body, and answers with the bare record (no root key).
    def save_url(self) -> str:
        return '/api/v1/cell_lines'

    def _record_from_detail(self, res_json: dict) -> dict:
        return res_json

    def _record_from_create(self, res_json: dict) -> dict | None:
        return res_json

    def save(self, load_after_save: bool = False):
        missing = [k for k in _REQUIRED if self.properties.get(k) is None]
        missing += [f'material {k}' for k in ('name', 'source') if not self._material.get(k)]
        if missing:
            raise ValueError(f'A cell line needs {", ".join(missing)} before it can be saved.')
        self._refuse_ignored_material_change()
        super().save(load_after_save)
        self._material_loaded = copy.deepcopy(self._material)

    def _refuse_ignored_material_change(self) -> None:
        if self.is_new:
            return
        same_material = all(self._material.get(k) == self._material_loaded.get(k) for k in ('name', 'source'))
        changed = [k for k in MATERIAL_FIELDS if self._material.get(k) != self._material_loaded.get(k)]
        if not same_material or not changed or self._material_owner is None:
            return
        if self._session.current_user_id() != self._material_owner:
            raise PermissionError(
                f'The material {self._material.get("name")!r} was created by another user, so the '
                f'server would ignore changes to {", ".join(changed)} (while reporting success). '
                f'Ask its creator, or link this sample to another material by changing its name or '
                f'source.')

    def _clean_properties_data(self, serialize_data: dict | None = None) -> dict:
        props = self.properties
        out: dict[str, Any] = {key: props.get(key) for key in SAMPLE_FIELDS}
        for key in MATERIAL_FIELDS:
            out[_MATERIAL_PARAM.get(key, key)] = self._material.get(key)
        if not self.is_new:
            out['cell_line_sample_id'] = str(self.id)
        return out | (serialize_data or {})
