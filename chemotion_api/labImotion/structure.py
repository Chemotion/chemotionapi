"""Registry giving fields read access to their owning generic object's structure."""

from __future__ import annotations  # Enables forward references

import weakref
from _weakref import ReferenceType
from typing import TYPE_CHECKING, cast

from chemotion_api.labImotion.items.options import FieldType

if TYPE_CHECKING:
    from chemotion_api.labImotion.items.genericproperties import GenericProperties
    from chemotion_api.labImotion import GenericObj


class StructureRegistry:
    """Weak-reference handle to a :class:`GenericObj`, exposing its layers and options.

    Held by fields and layers so they can resolve sibling fields and select options without
    creating a strong reference cycle back to the owning generic object.
    """

    def __init__(self, obj: GenericObj):
        """Store a weak reference to the owning generic object.

        :param obj: The generic object whose structure this registry exposes.
        """
        self._obj: ReferenceType[GenericObj] = weakref.ref(obj)

    def get_properties(self) -> GenericProperties | None:
        """Return the owning object's properties template, or ``None`` if not generic.

        :return: The :class:`GenericProperties` of the owning object, or ``None``.
        """
        return cast("GenericObj", self._obj()).properties

    def get_structure(self) -> dict[str, dict[str, FieldType]]:
        """Return a mapping of layer key to its field keys and their field types.

        :return: Nested dict ``{layer_key: {field_key: FieldType}}`` for all layers.
        """
        res: dict = {}
        props = self.get_properties()
        if props is None:
            for _, layer in cast("GenericObj", self._obj())._json_data['properties_template']['layers'].items():
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
        """Return the keys of all select-option groups defined on the owning object.

        :return: List of select-option group keys.
        """
        props = self.get_properties()
        if props is None:
            select_items = cast("GenericObj", self._obj())._json_data['properties_template']['select_options']
        else:
            select_items = props.select_options
        return [key for key, val in select_items.items()]


    def get_select_options(self) -> dict[str, dict]:
        """Return all select-option groups as ``{group_key: {option_key: label}}``.

        :return: Nested dict of every select-option group's key-to-label mapping.
        """
        props = self.get_properties()
        if props is None:
            select_items = cast("GenericObj", self._obj())._json_data['properties_template']['select_options']
        else:
            select_items = props.select_options
        return {key: {o['key']:o['label'] for o in val['options']} for key, val in select_items.items()}
