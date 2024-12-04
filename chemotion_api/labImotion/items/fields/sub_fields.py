import uuid
import re
from enum import Enum

from chemotion_api.labImotion.items.fields.abstract_fields import SystemDefined
from chemotion_api.labImotion.items.options import SubFieldType, FieldUnit, get_unit
from chemotion_api.labImotion.structure import StructureRegistry
from chemotion_api.labImotion.utils import ChemotionSerializable


class SubBaseField(ChemotionSerializable):
    _default_required_fields = ["id", "field_type", "value"]
    required_fields = []
    mapping = {"field_type": "type"}
    default = ""
    field_type = None

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        self._sr = sr
        self._layer_key = layer_key
        self._id = json_data.get("id", uuid.uuid4().__str__())
        self.value = json_data.get("value", self.default)

    def to_dict(self):
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
        return self._value

    @value.setter
    def value(self, value: str):
        if not isinstance(value, str):
            raise TypeError(f"value {type(value)} not supported")
        self._value = value

    @property
    def id(self) -> str:
        return self._id

    @id.setter
    def id(self, value: str):
        if not isinstance(id, str):
            raise TypeError(f"value {type(id)} not supported")
        self._id = id


class NumberField(SubBaseField):
    field_type = SubFieldType.NUMBER
    default = "0"

    @property
    def value(self) -> str:
        return self._value

    @value.setter
    def value(self, value: str | float | int):
        if isinstance(value, float) or isinstance(value, int):
            value = str(value)
        if not isinstance(value, str):
            raise TypeError(f"value {type(value)} not supported")
        if re.match(r"^[0-9\.]*$", value) is None:
            raise ValueError(f"value must be a number: {value}")
        self._value = value


class LabelField(SubBaseField):
    field_type = SubFieldType.LABEL


class TextField(SubBaseField):
    field_type = SubFieldType.TEXT


class SystemDefinedField(SubBaseField, SystemDefined):
    field_type = SubFieldType.SYSTEM_DEFINED
    required_fields = ['option_layers', 'value_system']

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        super().__init__(sr, layer_key, json_data)
        SystemDefined.__init__(self, json_data)