import logging

from chemotion_api.labImotion.items.options import FieldUnit, get_unit
from chemotion_api.labImotion.structure import StructureRegistry

logger = logging.getLogger(__name__)

#: Unit types/keys already reported as unknown, so a klass with many such fields warns once each
#: rather than once per field.
_reported_unknown_units: set[str] = set()


def _report_unknown_unit(message: str) -> None:
    if message not in _reported_unknown_units:
        _reported_unknown_units.add(message)
        logger.warning(
            "%s — this client's unit table mirrors LabIMotion's units.rb by hand and is behind the "
            "server. The value is kept as-is; regenerate the table from the labimotion gem.",
            message,
        )


class Select:
    def __init__(self, sr: StructureRegistry, json_data):
        self._option_layers = None
        self.option_layers = json_data.get("option_layers")
        if not hasattr(self, '_sr'):
            self._sr = sr


    @property
    def option_layers(self) -> str:
        return self._option_layers

    @option_layers.setter
    def option_layers(self, value: str | None):
        options = self._sr.get_select_options_list()
        if value is None:
            value = options[0]
        if not isinstance(value, str):
            raise TypeError(f"option_layers {type(value)} not supported")
        if value != '' and value not in options:
            raise ValueError(f"option no in {self._sr.get_select_options_list()}")
        self._option_layers = value

class SystemDefined:
    """A numeric field carrying a unit type (``option_layers``) and a chosen unit (``value_system``).

    Assignment from user code is validated strictly, so a typo'd unit is caught at the call site.
    Parsing a server payload is deliberately *lenient*: LabIMotion adds units in point releases and
    the table in :mod:`chemotion_api.labImotion.items.options` is a hand-maintained mirror of the
    gem's ``units.rb``, so a klass using a unit this client has not learned yet must degrade to a
    warning rather than make the whole element unreadable.
    """

    def __init__(self, json_data: dict):
        self._value_system = None
        self._option_layers = None
        self._set_option_layers(json_data.get("option_layers", FieldUnit.ACCELERATION), strict=False)
        value_system = json_data.get("value_system")
        if value_system is None:
            available = get_unit(self.option_layers)
            value_system = available[0] if available else None
        if value_system is not None:
            self._set_value_system(value_system, strict=False)

    @property
    def value_system(self) -> str:
        if self._value_system is None:
            available_units = get_unit(self.option_layers)
            self._value_system = available_units[0] if available_units else None
        return self._value_system

    @value_system.setter
    def value_system(self, value: str):
        self._set_value_system(value, strict=True)

    def _set_value_system(self, value: str, strict: bool):
        available_units = get_unit(self.option_layers)
        if not isinstance(value, str):
            raise TypeError(f"value_system {type(value)} not supported")
        if value not in available_units:
            if strict:
                raise ValueError(f"value_system {value} must be in {available_units}")
            _report_unknown_unit(
                f"unit {value!r} is not a known unit of {self.option_layers!r}"
            )
        self._value_system = value

    @property
    def option_layers(self) -> FieldUnit | str:
        if self._option_layers is None:
            return FieldUnit.ACCELERATION
        return self._option_layers

    @option_layers.setter
    def option_layers(self, value: FieldUnit | str):
        self._set_option_layers(value, strict=True)

    def _set_option_layers(self, value: FieldUnit | str, strict: bool):
        if isinstance(value, str):
            try:
                value = FieldUnit(value)
            except ValueError:
                if strict:
                    raise
                _report_unknown_unit(f"unit type {value!r} is not known to this client")
        if not isinstance(value, FieldUnit | str):
            raise TypeError(f"option_layers {type(value)} not supported")
        self._option_layers = value
        available_units = get_unit(self._option_layers)
        if available_units and self._value_system not in available_units:
            self._value_system = available_units[0]
