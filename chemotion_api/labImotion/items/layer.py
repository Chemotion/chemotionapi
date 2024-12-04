import re
import string
from enum import Enum

from chemotion_api.labImotion.items.condition_handler import ConditionHandler
from chemotion_api.labImotion.items.fields import BaseField, field_factory, FieldType, create_field
from chemotion_api.labImotion.items.options import LayerColor
from chemotion_api.labImotion.items.validation import validate_generic_layer
from chemotion_api.labImotion.structure import StructureRegistry
from chemotion_api.labImotion.utils import ChemotionSerializable, all_instances_of


class Layer(ChemotionSerializable, ConditionHandler):
    @classmethod
    def generate_new_layer(cls, sr: StructureRegistry, key: str, label: str):
        return cls(sr, {
            "key": key,
            "label": label,
            "color": "none",
            "style": "panel_generic_heading",
            "cols": 1,
            "position": 10,
            "wf": False,
            "timeRecord": "",
            "wf_position": 0,
            "fields": []
        })

    def __init__(self, sr: StructureRegistry, json_data: dict):
        ConditionHandler.__init__(self, sr)
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
        self._fields = []
        self._sr = sr

        for key, value in json_data.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def add_field(self, field_type: FieldType, label: str, field: str = "", idx: int = -1):
        all_keys = [l.field for l in self.fields]
        if field == '':
            field = re.sub(r'[^a-z]', '_', label.lower())
            t_field = field
            i = 0
            while field in all_keys or field.endswith('_'):
                field = t_field + string.ascii_lowercase[i]
                i += 1

        new_field = create_field(self._sr, self.key, field_type, field, idx, field)
        if idx < 0 :
            self.fields.append(new_field)
        else:
            self.fields.insert(idx, new_field)
        self.update_fields_position()
        return new_field

    def update_fields_position(self):
        i = 1
        for f in self.fields:
            f.position = i
            i += 1


    def validate(self, json_data: dict = None):
        if json_data is None:
            json_data = self._json_data
        validate_generic_layer(json_data)

    def to_dict(self) -> dict:
        for key, _ in self._json_data.items():
            if hasattr(self, key):
                value = getattr(self, key)
                if isinstance(value, Enum):
                    value = value.value
                if all_instances_of(value, ChemotionSerializable):
                    self._json_data[key] = [x.to_dict() for x in value]
                else:
                    self._json_data[key] = value
        return self._json_data

    @property
    def fields(self) -> list[BaseField]:
        return self._fields

    @fields.setter
    def fields(self, value: list[dict | BaseField]):
        self._fields = []
        for field in value:
            if isinstance(field, BaseField):
                self._fields.append(value)
            elif isinstance(field, dict):
                self._fields.append(field_factory(self._sr, self.key, field))

    @property
    def timeRecord(self) -> str:
        return self._timeRecord

    @timeRecord.setter
    def timeRecord(self, time_rec):
        pass

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
        if re.match(r'^panel_generic_heading$|^panel_generic_heading_([bui])(?!.*\1)([bui])?(?!.*\1|.*\2)([bui])?$',
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
