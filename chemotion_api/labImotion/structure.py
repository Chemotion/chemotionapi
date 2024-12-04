from __future__ import annotations  # Enables forward references

import weakref
from _weakref import ReferenceType
from typing import TYPE_CHECKING

from chemotion_api.labImotion.items.options import FieldType

if TYPE_CHECKING:
    from chemotion_api.labImotion.items.genericproperties import GenericProperties
    from chemotion_api.labImotion import GenericObj


class StructureRegistry:
    def __init__(self, obj: GenericObj):
        self._obj: ReferenceType[GenericObj] = weakref.ref(obj)

    def get_properties(self) -> GenericProperties | None:
        return self._obj().properties

    def get_structure(self) -> dict[str, dict[str, FieldType]]:
        res = {}
        props = self.get_properties()
        if props is None:
            for _, layer in self._obj()._json_data['properties_template']['layers'].items():
                res[layer['key']] = {}
                for field in layer['fields']:
                    res[layer['key']][field['field']] = FieldType(field['type'])
        else:
            layers = props.layers
            for l in layers:
                res[l.key] = {}
                for f in l.fields:
                    res[l.key][f.field] = f.field_type
        return res

    def get_select_options_list(self) -> list[str]:
        props = self.get_properties()
        if props is None:
            select_items = self._obj()._json_data['properties_template']['select_options']
        else:
            select_items = props.select_options
        return [key for key, val in select_items.items()]


    def get_select_options(self) -> dict[str: list[str]]:
        props = self.get_properties()
        if props is None:
            select_items = self._obj()._json_data['properties_template']['select_options']
        else:
            select_items = props.select_options
        return {key: {o['key']:o['label'] for o in val['options']} for key, val in select_items.items()}
