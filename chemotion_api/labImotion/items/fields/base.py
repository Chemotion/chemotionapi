import copy
from enum import Enum

from chemotion_api.labImotion.items.condition_handler import ConditionHandler
from chemotion_api.labImotion.items.options import FieldType
from chemotion_api.labImotion.structure import StructureRegistry

from chemotion_api.labImotion.utils import all_instances_of, ChemotionSerializable


class BaseField(ChemotionSerializable, ConditionHandler):
    _default_required_fields = ["field_type", "field", "required", "label", "default", "position", "sub_fields",
                                "text_sub_fields"]
    _default_optional_fields = ["cols", "cond_fields", "cond_operator"]
    required_fields = []
    optional_fields = []
    field_type = FieldType.TEXT
    mapping = {"field_type": "type"}

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        ConditionHandler.__init__(self, sr)
        self._field = None
        self._label = None
        self._json_data = json_data
        self._default = ""
        self._position = 1
        self._sr = sr
        self._layer_key = layer_key
        self._cols = None

    def _parse_json(self):
        for key, value in self._json_data.items():
            key = self.mapping.get(key, key)
            if hasattr(self, key):
                setattr(self, key, value)

    @property
    def layer_key(self) -> str:
        return self._layer_key

    def to_dict(self) -> dict:
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
        return self._cols

    @cols.setter
    def cols(self, value: int):
        if not isinstance(value, int):
            try:
                value = int(value)
            except ValueError:
                raise TypeError(f"Required {type(value)} not supported")
        self._cols = value

    @property
    def default(self):
        return self._default

    @default.setter
    def default(self, value: str):
        pass

    @property
    def field(self) -> str | None:
        return self._field

    @field.setter
    def field(self, value: str):
        if not isinstance(value, str):
            raise TypeError(f"Required {type(value)} not supported")
        if self.field is None:
            self._field = value
        else:
            raise ValueError("Field is already set and cannot be changed")

    @property
    def label(self) -> str:
        return self._label

    @label.setter
    def label(self, value: str):
        if not isinstance(value, str):
            raise TypeError(f"Required {type(value)} not supported")
        self._label = value

    @property
    def position(self) -> int:
        return self._position

    @position.setter
    def position(self, value: int):
        if not isinstance(value, int):
            raise TypeError(f"Required {type(value)} not supported")
        self._position = value

    @property
    def required(self) -> bool:
        return False

    @required.setter
    def required(self, value: bool):
        pass

    @property
    def sub_fields(self) -> list:
        return []

    @sub_fields.setter
    def sub_fields(self, value: list):
        pass

    @property
    def text_sub_fields(self) -> list[dict]:
        return []

    @text_sub_fields.setter
    def text_sub_fields(self, value: list[dict]):
        pass
