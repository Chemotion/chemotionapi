import re

from chemotion_api.labImotion.items.conditions import Condition
from chemotion_api.labImotion.items.fields import BaseField, field_factory, FieldType, create_field
from chemotion_api.labImotion.items.options import ConditionOperator, LayerColor
from chemotion_api.labImotion.items.validation import validate_generic_layer


class Layer():
    def __init__(self, json_data: dict):
        self._json_data = json_data
        self.validate()
        self._wf = False
        self._key = ''
        self._style = 'panel_generic_heading'
        self._label = ''
        self._cols = 1
        self._color = ''
        self._position = 1
        self._wf_position = 1
        self._timeRecord = ''
        self._cond_operator = ConditionOperator.MATCH_ONE
        self._cond_fields = []
        self._field = []

        for key, value in json_data.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def add_field(self, field_type: FieldType):
        self.field.append(create_field(field_type))

    def validate(self, json_data: dict = None):
        if json_data is None:
            json_data = self._json_data
        validate_generic_layer(json_data)

    @property
    def cond_fields(self) -> list[Condition]:
        return self._cond_fields

    @cond_fields.setter
    def cond_fields(self, value: list[dict | Condition]):
        self._cond_fields = []
        for field in value:
            if isinstance(field, Condition):
                self._cond_fields.append(value)
            elif isinstance(field, dict):
                self._cond_fields.append(Condition(**field))

    @property
    def field(self) -> list[BaseField]:
        return self._field

    @field.setter
    def field(self, value: list[dict | BaseField]):
        self._field = []
        for field in value:
            if isinstance(field, BaseField):
                self._field.append(value)
            elif isinstance(field, dict):
                self._field.append(field_factory(field))

    @property
    def timeRecord(self) -> str:
        return self._timeRecord

    @timeRecord.setter
    def timeRecord(self, time_rec):
        pass

    @property
    def cond_operator(self) -> ConditionOperator:
        return self._cond_operator

    @cond_operator.setter
    def cond_operator(self, cond_operator: int | ConditionOperator):
        if isinstance(cond_operator, int):
            cond_operator = ConditionOperator(cond_operator)
        if isinstance(cond_operator, ConditionOperator):
            self._cond_operator = cond_operator
        else:
            raise TypeError('cond_operator must be a ConditionOperator')

    @property
    def wf(self) -> bool:
        return self._wf

    @wf.setter
    def wf(self, wf: bool):
        if isinstance(wf, bool):
            self._wf = wf
        else:
            raise TypeError('wf must be a boolean')

    @property
    def key(self) -> str:
        return self._key

    @key.setter
    def key(self, key: str):
        if isinstance(key, str):
            self._key = key
        else:
            raise TypeError('key must be a string')

    @property
    def style(self) -> str:
        return self._style

    @style.setter
    def style(self, style: str):
        if re.match(r'^panel_generic_heading$|^panel_generic_head0,ing_([bui])(?!.*\1)([bui])?(?!.*\1|.*\2)([bui])?$',
                    style) is not None:
            self._style = style
        else:
            raise TypeError('style must be a string')

    @property
    def label(self) -> str:
        return self._label

    @label.setter
    def label(self, label: str):
        if isinstance(label, str):
            self._label = label
        else:
            raise TypeError('label must be a string')

    @property
    def color(self) -> str:
        return self._color

    @color.setter
    def color(self, color: str | LayerColor):
        if isinstance(color, str):
            color = LayerColor(color)
        if isinstance(color, LayerColor):
            self._color = color
        else:
            raise TypeError(f'color must be a string and in [{", ".join(LayerColor.list())}]')

    @property
    def cols(self) -> int:
        return self._cols

    @cols.setter
    def cols(self, cols: int):
        if isinstance(cols, int) and cols > 0:
            self._cols = cols
        else:
            raise TypeError('cols must be a integer and cols > 0')

    @property
    def wf_position(self) -> int:
        return self._wf_position

    @wf_position.setter
    def wf_position(self, wf_position: int):
        if isinstance(wf_position, int) and wf_position >= 0:
            self._wf_position = wf_position
        else:
            raise TypeError('wf_position must be a integer and cols >= 0')

    @property
    def position(self) -> int:
        return self._position

    @position.setter
    def position(self, position: int):
        if isinstance(position, int) and position >= 0:
            self._position = position
        else:
            raise TypeError('position must be a integer and position >= 0')
