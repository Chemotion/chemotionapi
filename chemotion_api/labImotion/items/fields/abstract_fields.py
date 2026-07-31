"""Mixin classes shared by select-style and unit-aware LabIMotion fields.

This module defines two reusable mixins:

* :class:`Select` adds an ``option_layers`` attribute pointing at a named set of select options
  registered in the structure.
* :class:`SystemDefined` adds an ``option_layers`` / ``value_system`` pair describing a physical
  unit (:class:`~chemotion_api.labImotion.items.options.FieldUnit`) and a chosen unit symbol.

They are combined with :class:`~chemotion_api.labImotion.items.fields.base.BaseField` (and the
sub-field bases) to build concrete select and system-defined field types.
"""

from typing import cast

from chemotion_api.labImotion.items.options import FieldUnit, get_unit
from chemotion_api.labImotion.structure import StructureRegistry

class Select:
    """Mixin providing a validated ``option_layers`` reference to a named select-options set.

    :param sr: Structure registry used to resolve the available select-option lists.
    :param json_data: Raw JSON dictionary; its ``option_layers`` key seeds the initial value.
    """

    def __init__(self, sr: StructureRegistry, json_data):
        """Initialize the option-layers reference, defaulting from the structure if absent."""
        self._option_layers: str | None = None
        self.option_layers = json_data.get("option_layers")
        if not hasattr(self, '_sr'):
            self._sr = sr


    @property
    def option_layers(self) -> str:
        """Name of the registered select-options set backing this field."""
        return cast(str, self._option_layers)

    @option_layers.setter
    def option_layers(self, value: str | None):
        """Set the select-options set name, validating it against the registered options.

        :param value: Options-set name, or ``None`` to default to the first registered set.
        :raises TypeError: If ``value`` is not a string.
        :raises ValueError: If ``value`` is not among the registered options sets.
        """
        options = self._sr.get_select_options_list()
        if value is None:
            value = options[0]
        if not isinstance(value, str):
            raise TypeError(f"option_layers {type(value)} not supported")
        if value != '' and value not in options:
            raise ValueError(f"option no in {self._sr.get_select_options_list()}")
        self._option_layers = value

class SystemDefined:
    """Mixin providing a physical-unit (``option_layers``) and unit-symbol (``value_system``) pair.

    ``option_layers`` selects a :class:`~chemotion_api.labImotion.items.options.FieldUnit` (a unit
    family such as acceleration), and ``value_system`` picks one of the concrete unit symbols
    available for that family.

    :param json_data: Raw JSON dictionary; its ``option_layers`` and ``value_system`` keys seed
        the initial values, defaulting to acceleration and its first unit.
    """

    def __init__(self, json_data: dict):
        """Initialize the unit family and unit symbol from JSON, applying sensible defaults."""
        self._value_system: str | None = None
        self._option_layers: FieldUnit | None = None
        self.option_layers = json_data.get("option_layers", FieldUnit.ACCELERATION)
        self.value_system = json_data.get("value_system", get_unit(self.option_layers)[0])

    @property
    def value_system(self) -> str:
        """Currently selected unit symbol, falling back to the first available for the family."""
        available_units = get_unit(self.option_layers)
        if self._value_system not in available_units:
            self._value_system = available_units[0]
        return cast(str, self._value_system)

    @value_system.setter
    def value_system(self, value: str):
        """Set the unit symbol, validating it against the units of the current family.

        :param value: Unit symbol string.
        :raises TypeError: If ``value`` is not a string.
        :raises ValueError: If ``value`` is not a valid unit for the selected family.
        """
        available_units = get_unit(self.option_layers)
        if not isinstance(value, str):
            raise TypeError(f"value_system {type(value)} not supported")
        if value not in available_units:
            raise ValueError(f"value_system {value} must be in {available_units}")
        self._value_system = value

    @property
    def option_layers(self) -> FieldUnit:
        """Selected unit family, defaulting to ``FieldUnit.ACCELERATION`` when unset."""
        if self._option_layers is None:
            return FieldUnit.ACCELERATION
        return self._option_layers

    @option_layers.setter
    def option_layers(self, value: FieldUnit | str):
        """Set the unit family and reset the unit symbol if it no longer fits.

        :param value: A :class:`FieldUnit` or its string value.
        :raises TypeError: If ``value`` is neither a string nor a :class:`FieldUnit`.
        """
        if isinstance(value, str):
            value = FieldUnit(value)
        if not isinstance(value, FieldUnit):
            raise TypeError(f"option_layers {type(value)} not supported")
        self._option_layers = value
        available_units = get_unit(self._option_layers)
        if self._value_system not in available_units:
            self._value_system = available_units[0]