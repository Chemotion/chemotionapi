from __future__ import annotations
import uuid

from chemotion_api.labImotion.items.options import ConditionOperator, FieldType
from chemotion_api.labImotion.structure import StructureRegistry

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chemotion_api.labImotion.items.fields import SelectField, TextField, CheckboxField


class ConditionHandler:
    def __init__(self, sr: StructureRegistry):
        if not hasattr(self, '_sr'):
            self._sr = sr
        self._cond_fields = None
        self._cond_operator = None

    def add_condition(self, field: SelectField | TextField | CheckboxField, value: str | bool):
        if field.field_type == FieldType.SELECT:
            options = self._sr.get_select_options()[field.option_layers]
            if value not in options:
                def find_label():
                    for key, label in options:
                        if value == label:
                            return key
                    return None

                value = find_label()
            if value is None:
                raise ValueError(f"Value must be in {', '.join(options.values())}")


        elif field.field_type == FieldType.TEXT:
            if not isinstance(value, str):
                raise ValueError('Condition value for text fields must be a string')
        elif field.field_type == FieldType.CHECKBOX:
            if isinstance(value, bool):
                value = 'true' if value else 'false'
            if value not in ['true', 'false']:
                raise ValueError('Condition value for checkboxes must be "true" or "false"')
        else:
            raise ValueError(f"Only Fields of type [{FieldType.CHECKBOX}, {FieldType.TEXT}, {FieldType.SELECT}]")

        if self.cond_fields is None:
            self.cond_fields = []
        self.cond_fields.append({
            "id": uuid.uuid4().__str__(),
            "field": field.field,
            "label": "TEST",
            "layer": field.layer_key,
            "value": value
        })

    @property
    def cond_fields(self) -> list | None:
        return self._cond_fields

    @cond_fields.setter
    def cond_fields(self, value: list | None):
        if value is None:
            self._cond_operator = None
            self._cond_fields = None
        if not isinstance(value, list):
            raise TypeError(f"cond_fields {type(value)} not supported")
        self._cond_fields = value

    @property
    def cond_operator(self) -> ConditionOperator | None:
        if self.cond_fields is not None and self._cond_operator is None:
            return ConditionOperator.MATCH_ONE
        return self._cond_operator

    @cond_operator.setter
    def cond_operator(self, value: ConditionOperator | int | None):
        if value is None:
            if self.cond_fields is None:
                self._cond_operator = None
                return
            else:
                self._cond_operator = ConditionOperator.MATCH_ONE
        if isinstance(value, int):
            value = ConditionOperator(value)
        if not isinstance(value, ConditionOperator):
            raise TypeError(f"cond_operator {type(value)} not supported")
        self._cond_operator = value
