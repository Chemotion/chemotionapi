"""Sub-field types used inside LabIMotion input-group fields.

Input-group fields (and, via subclassing, table fields) contain a list of smaller sub-fields.
This module defines :class:`SubBaseField`, their common base, and the concrete sub-field types:
:class:`NumberField`, :class:`LabelField`, :class:`TextField` and :class:`SystemDefinedField`.
Each carries a generated ``id``, a ``field_type`` and a string ``value``.
"""

import uuid
import re
from enum import Enum

from chemotion_api.labImotion.items.fields.abstract_fields import SystemDefined
from chemotion_api.labImotion.items.options import SubFieldType, SubTableFieldType, FieldUnit, get_unit
from chemotion_api.labImotion.structure import StructureRegistry
from chemotion_api.labImotion.utils import ChemotionSerializable


class SubBaseField(ChemotionSerializable):
    """Common base for input-group sub-fields.

    Holds the shared ``id``, ``field_type`` and string ``value`` and implements JSON serialization.
    Concrete subclasses set :attr:`field_type` and may override ``value`` validation.

    :param sr: Structure registry providing access to the surrounding element schema.
    :param layer_key: Key of the layer the parent field belongs to.
    :param json_data: Raw JSON dictionary describing the sub-field.
    """

    _default_required_fields = ["id", "field_type", "value"]
    required_fields: list = []
    mapping = {"field_type": "type"}
    default = ""
    field_type: SubFieldType | SubTableFieldType | None = None

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        """Build the sub-field, assigning a generated id when none is given and reading its value.

        :param sr: Structure registry providing access to the surrounding element schema.
        :param layer_key: Key of the layer the parent field belongs to.
        :param json_data: Raw JSON dictionary describing the sub-field.
        """
        self._sr = sr
        self._layer_key = layer_key
        self._id = json_data.get("id", uuid.uuid4().__str__())
        self.value = json_data.get("value", self.default)

    def to_dict(self):
        """Serialise the sub-field to its JSON dictionary.

        :return: A dict of the required fields, with enum values unwrapped and keys remapped.
        """
        json_dict = {}
        for key in self._default_required_fields + self.required_fields:
            val = getattr(self, key)
            if isinstance(val, Enum):
                val = val.value
            key = self.mapping.get(key, key)
            json_dict[key] = val
        return json_dict

    @property
    def value(self) -> str:
        """The string value held by the sub-field."""
        return self._value

    @value.setter
    def value(self, value: str):
        """Set the sub-field value.

        :raises TypeError: If ``value`` is not a string.
        """
        if not isinstance(value, str):
            raise TypeError(f"value {type(value)} not supported")
        self._value = value

    @property
    def id(self) -> str:
        """The unique identifier of the sub-field."""
        return self._id

    @id.setter
    def id(self, value: str):
        """Set the sub-field identifier.

        :raises TypeError: If the identifier is not a string.
        """
        if not isinstance(value, str):
            raise TypeError(f"value {type(value)} not supported")
        self._id = value


class NumberField(SubBaseField):
    """A numeric sub-field whose string value must represent a number."""

    field_type = SubFieldType.NUMBER
    default = "0"

    @property
    def value(self) -> str:
        """The numeric value as a string."""
        return self._value

    @value.setter
    def value(self, value: str | float | int):
        """Set the numeric value, coercing ints/floats to strings and validating the format.

        :raises TypeError: If ``value`` is not a str, int or float.
        :raises ValueError: If the resulting string is not a valid number.
        """
        if isinstance(value, float) or isinstance(value, int):
            value = str(value)
        if not isinstance(value, str):
            raise TypeError(f"value {type(value)} not supported")
        if re.match(r"^[0-9\.]*$", value) is None:
            raise ValueError(f"value must be a number: {value}")
        self._value = value


class LabelField(SubBaseField):
    """A read-only label sub-field used to display static text."""

    field_type = SubFieldType.LABEL


class TextField(SubBaseField):
    """A free-text sub-field."""

    field_type = SubFieldType.TEXT


class SystemDefinedField(SubBaseField, SystemDefined):
    """A sub-field whose value/unit is constrained by a system-defined option set."""

    field_type = SubFieldType.SYSTEM_DEFINED
    required_fields = ['option_layers', 'value_system']

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        """Build the sub-field and initialise its system-defined support from JSON.

        :param sr: Structure registry providing access to the surrounding element schema.
        :param layer_key: Key of the layer the parent field belongs to.
        :param json_data: Raw JSON dictionary describing the sub-field.
        """
        super().__init__(sr, layer_key, json_data)
        SystemDefined.__init__(self, json_data)