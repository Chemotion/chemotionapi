from chemotion_api.labImotion.items.options import FieldType, ConditionOperator, FieldUnit, get_unit



class BaseField:
    def __init__(self, json_data: dict):
        self._field = None
        self._label = ""
        self._json_data = json_data
        self._cols = 1
        self._default = ""
        self._position = 1
        self._required = False
        self._sub_fields = []
        self._text_sub_fields = []
        self._field_type = FieldType.TEXT
        self._cond_fields = []
        self._cond_operator = ConditionOperator.MATCH_ONE
        self._option_layers = None
        self._value_system = None
        self.field_type = json_data.get("type", FieldType.TEXT)

        for key, value in json_data.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def set_system_unit(self, field_unit: FieldUnit | None = None):
        is_default = field_unit is None
        if is_default:
            field_unit = FieldUnit.ACCELERATION
        if self.field_type == FieldType.SYSTEM_DEFINED:
            self._option_layers = field_unit.value
            self._value_system = get_unit(field_unit)
        else:
            self._option_layers = None
            self._value_system = None
            if not is_default:
                raise ValueError("system_unit is only supported for field type SYSTEM_DEFINED")

    def set_select_options(self, value: str = ''):
        is_default = value == ''
        if self.field_type == FieldType.SELECT:
            self._option_layers = None
            self._value_system = value
        else:
            self._option_layers = None
            self._value_system = None
            if not is_default:
                raise ValueError("select_options is only supported for field type SELECT")

    @property
    def value_system(self) -> str | None:
        return self._value_system

    @property
    def option_layers(self) -> str | None:
        return self._value_system

    @property
    def cols(self) -> int:
        return self._cols

    @cols.setter
    def cols(self, value: int):
        if not isinstance(value, int):
            raise TypeError(f"Required {type(value)} not supported")
        self._cols = value

    @property
    def default(self):
        return self._default

    @default.setter
    def default(self, value: str):
        if not isinstance(value, str):
            raise TypeError(f"Required {type(value)} not supported")
        self._default = value

    @property
    def field(self) -> str | None:
        return self._field

    @field.setter
    def field(self, value: str):
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
        return self._required

    @required.setter
    def required(self, value: bool):
        if not isinstance(value, bool):
            raise TypeError(f"Required {type(value)} not supported")
        self._required = value

    @property
    def sub_fields(self) -> list[dict]:
        return self._sub_fields

    @sub_fields.setter
    def sub_fields(self, value: list[dict]):
        if not isinstance(value, list):
            raise TypeError(f"Sub_fields {type(value)} not supported")
        self._sub_fields = value

    @property
    def text_sub_fields(self) -> list[dict]:
        return self._text_sub_fields

    @text_sub_fields.setter
    def text_sub_fields(self, value: list[dict]):
        if not isinstance(value, list):
            raise TypeError(f"Text_sub_fields {type(value)} not supported")
        self._text_sub_fields = value

    @property
    def field_type(self) -> FieldType:
        return self._field_type

    @field_type.setter
    def field_type(self, value: FieldType | str):
        if isinstance(value, str):
            value = FieldType(value)
        if not isinstance(value, FieldType):
            raise TypeError(f"Field type {type(value)} not supported")
        if self._field_type == value:
            return
        self.set_system_unit()
        self.set_select_options()
        self._sub_fields = []
        self._text_sub_fields = []
        self._field_type = value


def field_factory(json_data) -> BaseField:
    return BaseField(json_data)


def create_field(field_type: FieldType):
    return BaseField({'type': field_type})
