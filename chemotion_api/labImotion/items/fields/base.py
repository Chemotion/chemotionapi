"""Base class for all LabIMotion generic-element fields.

This module defines :class:`BaseField`, the common ancestor of every concrete field type used
in user-defined generic element schemas. It provides the shared attributes (``field``, ``label``,
``position``, ``default``, ``cols`` and friends), JSON (de)serialization via :meth:`BaseField.to_dict`
and :meth:`BaseField._parse_json`, and default property accessors that concrete subclasses override
when they actually support a given feature (e.g. ``required`` or ``sub_fields``).
"""

from enum import Enum
from typing import cast

from chemotion_api.labImotion.items.condition_handler import ConditionHandler
from chemotion_api.labImotion.items.options import FieldType
from chemotion_api.labImotion.structure import StructureRegistry

from chemotion_api.labImotion.utils import all_instances_of, ChemotionSerializable


class BaseField(ChemotionSerializable, ConditionHandler):
    """Common base for every LabIMotion field type.

    A field describes a single input within a layer of a generic element schema. This base class
    holds the attributes shared by all field types and implements JSON conversion. Concrete
    subclasses set the :attr:`field_type` class attribute and extend ``required_fields`` /
    ``optional_fields`` with any type-specific keys, overriding property accessors as needed.

    :param sr: Structure registry providing access to the surrounding element schema.
    :param layer_key: Key of the layer this field belongs to.
    :param json_data: Raw JSON dictionary describing the field.
    """

    _default_required_fields = ["field_type", "field", "required", "label", "default", "position", "sub_fields",
                                "text_sub_fields"]
    _default_optional_fields = ["cols", "cond_fields", "cond_operator"]
    required_fields: list = []
    optional_fields: list = []
    field_type = FieldType.TEXT
    mapping = {"field_type": "type"}

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        """Initialize the field with default values and remember its raw JSON data.

        :param sr: Structure registry providing access to the surrounding element schema.
        :param layer_key: Key of the layer this field belongs to.
        :param json_data: Raw JSON dictionary describing the field.
        """
        ConditionHandler.__init__(self, sr)
        self._field: str | None = None
        self._label: str | None = None
        self._json_data = json_data
        self._default = ""
        self._position = 1
        self._sr = sr
        self._layer_key = layer_key
        self._cols: int | None = None

    def _parse_json(self):
        """Apply the stored JSON data onto matching (mapped) attributes via their setters."""
        for key, value in self._json_data.items():
            key = self.mapping.get(key, key)
            if hasattr(self, key):
                setattr(self, key, value)

    @property
    def layer_key(self) -> str:
        """Key of the layer this field belongs to."""
        return self._layer_key

    def to_dict(self) -> dict:
        """Serialize the field into its JSON-compatible dictionary representation.

        Required and optional keys are collected from the ``*_fields`` lists, enum values are
        unwrapped to their ``.value``, and nested serializable objects are recursively converted.

        :return: JSON dictionary representing this field.
        """
        self._json_data = {}
        for key in self._default_required_fields + self.required_fields:
            json_key = self.mapping.get(key, key)
            value = getattr(self, key)
            if isinstance(value, Enum):
                value = value.value
            if all_instances_of(value, ChemotionSerializable):
                self._json_data[json_key] = [x.to_dict() for x in value]
            else:
                self._json_data[json_key] = value

        for key in self._default_optional_fields + self.optional_fields:
            json_key = self.mapping.get(key, key)
            value = getattr(self, key, None)
            if value is not None:
                if isinstance(value, Enum):
                    value = value.value
                self._json_data[json_key] = value

        return self._json_data

    @property
    def cols(self) -> int:
        """Number of grid columns the field spans in the layer layout."""
        return cast(int, self._cols)

    @cols.setter
    def cols(self, value: int):
        """Set the column span, coercing to ``int`` and raising ``TypeError`` if not convertible."""
        if not isinstance(value, int):
            try:
                value = int(value)
            except ValueError:
                raise TypeError(f"Required {type(value)} not supported") from None
        self._cols = value

    @property
    def default(self):
        """Default value of the field (read-only at this level)."""
        return self._default

    @default.setter
    def default(self, value: str):
        """No-op setter; the base default value cannot be changed."""
        pass

    @property
    def field(self) -> str | None:
        """Unique machine name (key) of the field within its layer."""
        return self._field

    @field.setter
    def field(self, value: str):
        """Set the field key once; raise ``ValueError`` if it is already set.

        :param value: Field key string.
        :raises TypeError: If ``value`` is not a string.
        :raises ValueError: If the field key has already been assigned.
        """
        if not isinstance(value, str):
            raise TypeError(f"Required {type(value)} not supported")
        if self.field is None:
            self._field = value
        else:
            raise ValueError("Field is already set and cannot be changed")

    @property
    def label(self) -> str:
        """Human-readable label shown for the field."""
        return cast(str, self._label)

    @label.setter
    def label(self, value: str):
        """Set the display label; raise ``TypeError`` if not a string."""
        if not isinstance(value, str):
            raise TypeError(f"Required {type(value)} not supported")
        self._label = value

    @property
    def position(self) -> int:
        """Ordering position of the field within its layer."""
        return self._position

    @position.setter
    def position(self, value: int):
        """Set the ordering position; raise ``TypeError`` if not an int."""
        if not isinstance(value, int):
            raise TypeError(f"Required {type(value)} not supported")
        self._position = value

    @property
    def required(self) -> bool:
        """Whether the field is mandatory; ``False`` by default (overridden by subclasses)."""
        return False

    @required.setter
    def required(self, value: bool):
        """No-op setter; base fields do not support a required flag."""
        pass

    @property
    def sub_fields(self) -> list:
        """Nested sub-fields; empty by default (overridden by container field types)."""
        return []

    @sub_fields.setter
    def sub_fields(self, value: list):
        """No-op setter; base fields hold no sub-fields."""
        pass

    @property
    def text_sub_fields(self) -> list[dict]:
        """Text template sub-fields; empty by default (overridden by relevant field types)."""
        return []

    @text_sub_fields.setter
    def text_sub_fields(self, value: list[dict]):
        """No-op setter; base fields hold no text sub-fields."""
        pass
