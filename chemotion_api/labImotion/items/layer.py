"""A LabIMotion layer — a named, ordered group of fields within a generic element."""
import re
import string
from enum import Enum
from typing import cast

from chemotion_api.labImotion.items.condition_handler import ConditionHandler
from chemotion_api.labImotion.items.fields import BaseField, field_factory, FieldType, create_field
from chemotion_api.labImotion.items.options import LayerColor
from chemotion_api.labImotion.items.validation import validate_generic_layer
from chemotion_api.labImotion.structure import StructureRegistry
from chemotion_api.labImotion.utils import ChemotionSerializable, all_instances_of


class Layer(ChemotionSerializable, ConditionHandler):
    """A named, positioned panel grouping fields within a generic element's properties."""

    @classmethod
    def generate_new_layer(cls, sr: StructureRegistry, key: str, label: str):
        """Create an empty layer with default styling for the given key and label.

        :param sr: Structure registry shared with the owning generic object.
        :param key: The unique key of the new layer.
        :param label: The display label of the new layer.
        :return: A new :class:`Layer` with no fields.
        """
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
        """Build a layer from its raw JSON representation after validating it.

        :param sr: Structure registry shared with the owning generic object.
        :param json_data: The raw layer dict.
        :raises jsonschema.ValidationError: If ``json_data`` does not match the layer schema.
        """
        ConditionHandler.__init__(self, sr)
        self._json_data = json_data
        self.validate()
        self._wf = False
        self._key = ''
        self._style = 'panel_generic_heading'
        self._label = ''
        self._cols = 1
        self._color: str | LayerColor = ''
        self._position = 1
        self._wf_position = 1
        self._timeRecord = ''
        self._fields: list = []
        self._sr = sr

        for key, value in json_data.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def add_field(self, field_type: FieldType, label: str, field: str = "", idx: int = -1):
        """Create and insert a new field, generating a unique key if none is given.

        :param field_type: The :class:`FieldType` of the new field.
        :param label: Display label of the new field.
        :param field: Optional field key; auto-derived from ``label`` when empty.
        :param idx: Insert position; appended at the end when negative.
        :return: The newly created field.
        """
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
        """Renumber the ``position`` of every field in the layer consecutively from one."""
        i = 1
        for f in self.fields:
            f.position = i
            i += 1


    def validate(self, json_data: dict | None = None):
        """Validate the layer against the generic-layer JSON schema.

        :param json_data: Layer dict to validate; defaults to this layer's own data.
        :raises jsonschema.ValidationError: If the data does not match the schema.
        """
        if json_data is None:
            json_data = self._json_data
        validate_generic_layer(json_data)

    def to_dict(self) -> dict:
        """Serialise the layer back into its JSON dictionary representation.

        :return: The updated layer dict with fields serialised.
        """
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
        """The fields contained in this layer."""
        return self._fields

    @fields.setter
    def fields(self, value: list[dict | BaseField]):
        """Set the fields from a list of field objects or raw field dicts."""
        self._fields = []
        for field in value:
            if isinstance(field, BaseField):
                self._fields.append(value)
            elif isinstance(field, dict):
                self._fields.append(field_factory(self._sr, self.key, field))

    @property
    def timeRecord(self) -> str:
        """The time-record marker of the layer (read-only in practice)."""
        return self._timeRecord

    @timeRecord.setter
    def timeRecord(self, time_rec):
        """No-op setter; the time record cannot be changed through this property."""
        pass

    @property
    def wf(self) -> bool:
        """Whether this layer is a workflow layer."""
        return self._wf

    @wf.setter
    def wf(self, wf: bool):
        """Set the workflow flag.

        :raises TypeError: If ``wf`` is not a boolean.
        """
        if isinstance(wf, bool):
            self._wf = wf
        else:
            raise TypeError('wf must be a boolean')

    @property
    def key(self) -> str:
        """The unique key of the layer."""
        return self._key

    @key.setter
    def key(self, key: str):
        """Set the layer key.

        :raises TypeError: If ``key`` is not a string.
        """
        if isinstance(key, str):
            self._key = key
        else:
            raise TypeError('key must be a string')

    @property
    def style(self) -> str:
        """The heading style/formatting of the layer panel."""
        return self._style

    @style.setter
    def style(self, style: str):
        """Set the layer heading style.

        :raises TypeError: If ``style`` does not match the allowed heading-style pattern.
        """
        if re.match(r'^panel_generic_heading$|^panel_generic_heading_([bui])(?!.*\1)([bui])?(?!.*\1|.*\2)([bui])?$',
                    style) is not None:
            self._style = style
        else:
            raise TypeError('style must be a string')

    @property
    def label(self) -> str:
        """The display label of the layer."""
        return self._label

    @label.setter
    def label(self, label: str):
        """Set the layer label.

        :raises TypeError: If ``label`` is not a string.
        """
        if isinstance(label, str):
            self._label = label
        else:
            raise TypeError('label must be a string')

    @property
    def color(self) -> str:
        """The colour theme of the layer panel."""
        return cast(str, self._color)

    @color.setter
    def color(self, color: str | LayerColor):
        """Set the layer colour from a :class:`LayerColor` or its string value.

        :raises ValueError: If a string ``color`` is not a valid :class:`LayerColor`.
        :raises TypeError: If ``color`` cannot be interpreted as a :class:`LayerColor`.
        """
        if isinstance(color, str):
            color = LayerColor(color)
        if isinstance(color, LayerColor):
            self._color = color
        else:
            raise TypeError(f'color must be a string and in [{", ".join(LayerColor.list())}]')

    @property
    def cols(self) -> int:
        """The number of columns the layer's fields are laid out in."""
        return self._cols

    @cols.setter
    def cols(self, cols: int):
        """Set the column count.

        :raises TypeError: If ``cols`` is not a positive integer.
        """
        if isinstance(cols, int) and cols > 0:
            self._cols = cols
        else:
            raise TypeError('cols must be a integer and cols > 0')

    @property
    def wf_position(self) -> int:
        """The position of this layer within the workflow."""
        return self._wf_position

    @wf_position.setter
    def wf_position(self, wf_position: int):
        """Set the workflow position.

        :raises TypeError: If ``wf_position`` is not a non-negative integer.
        """
        if isinstance(wf_position, int) and wf_position >= 0:
            self._wf_position = wf_position
        else:
            raise TypeError('wf_position must be a integer and cols >= 0')

    @property
    def position(self) -> int:
        """The display position of the layer among its siblings."""
        return self._position

    @position.setter
    def position(self, position: int):
        """Set the layer position.

        :raises TypeError: If ``position`` is not a non-negative integer.
        """
        if isinstance(position, int) and position >= 0:
            self._position = position
        else:
            raise TypeError('position must be a integer and position >= 0')
