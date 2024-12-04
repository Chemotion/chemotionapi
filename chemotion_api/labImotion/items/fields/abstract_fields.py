from chemotion_api.labImotion.items.options import FieldUnit, get_unit
from chemotion_api.labImotion.structure import StructureRegistry

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
    def __init__(self, json_data: dict):
        self._value_system = None
        self._option_layers = None
        self.option_layers = json_data.get("option_layers", FieldUnit.ACCELERATION)
        self.value_system = json_data.get("value_system", get_unit(self.option_layers)[0])

    @property
    def value_system(self) -> str:
        available_units = get_unit(self.option_layers)
        if self._value_system not in available_units:
            self._value_system = available_units[0]
        return self._value_system

    @value_system.setter
    def value_system(self, value: str):
        available_units = get_unit(self.option_layers)
        if not isinstance(value, str):
            raise TypeError(f"value_system {type(value)} not supported")
        if value not in available_units:
            raise ValueError(f"value_system {value} must be in {available_units}")
        self._value_system = value

    @property
    def option_layers(self) -> FieldUnit:
        if self._option_layers is None:
            return FieldUnit.ACCELERATION
        return self._option_layers

    @option_layers.setter
    def option_layers(self, value: FieldUnit | str):
        if isinstance(value, str):
            value = FieldUnit(value)
        if not isinstance(value, FieldUnit):
            raise TypeError(f"option_layers {type(value)} not supported")
        self._option_layers = value
        available_units = get_unit(self._option_layers)
        if self._value_system not in available_units:
            self._value_system = available_units[0]