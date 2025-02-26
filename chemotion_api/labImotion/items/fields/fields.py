import re

from chemotion_api.labImotion.items.fields import BaseField
from chemotion_api.labImotion.items.fields.abstract_fields import SystemDefined, Select
from chemotion_api.labImotion.items.fields.sub_fields import SubBaseField, NumberField, TextField as SubTextField, \
    SystemDefinedField as SubSystemDefinedField, LabelField
from chemotion_api.labImotion.items.fields.table_sub_fields import TableSubBaseField, TSDragMolecule, TSDragSample, \
    TSSelect, TSSystemDefined, TSText
from chemotion_api.labImotion.items.options import FieldType, FieldUnit, get_unit, SubFieldType, SubTableFieldType
from chemotion_api.labImotion.structure import StructureRegistry


class DummyField(BaseField):
    field_type = FieldType.DUMMY

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        super().__init__(sr, layer_key, json_data)
        self._parse_json()



class CheckboxField(BaseField):
    field_type = FieldType.CHECKBOX

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        super().__init__(sr, layer_key, json_data)
        self._parse_json()


class DatetimeField(BaseField):
    field_type = FieldType.DATETIME

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        super().__init__(sr, layer_key, json_data)
        self._readonly = False
        self._required = False
        self._parse_json()

    @property
    def required(self) -> bool:
        return self._required

    @required.setter
    def required(self, value: bool):
        if not isinstance(value, bool):
            raise TypeError(f"required {type(value)} not supported")
        self._required = value

    @property
    def readonly(self) -> bool:
        return self._readonly

    @readonly.setter
    def readonly(self, value: bool):
        if not isinstance(value, bool):
            raise TypeError(f"readonly {type(value)} not supported")
        self._readonly = value


class DatetimeRangeField(BaseField):
    field_type = FieldType.DATETIME_RANGE

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        super().__init__(sr, layer_key, json_data)
        self._parse_json()


class DragElementField(BaseField):
    field_type = FieldType.DRAG_ELEMENT

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        super().__init__(sr, layer_key, json_data)
        self._parse_json()


class DragMoleculeField(BaseField):
    field_type = FieldType.DRAG_MOLECULE

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        super().__init__(sr, layer_key, json_data)
        self._parse_json()


class DragSampleField(BaseField):
    field_type = FieldType.DRAG_SAMPLE

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        super().__init__(sr, layer_key, json_data)
        self._parse_json()


class FormulaFieldField(BaseField):
    field_type = FieldType.FORMULA_FIELD
    required_fields = ["formula", "decimal", "canAdjust"]

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        super().__init__(sr, layer_key, json_data)
        self._formula = ""
        self._decimal = 2
        self._can_adjust = True
        self._parse_json()

    @property
    def canAdjust(self) -> bool:
        return self._can_adjust

    @canAdjust.setter
    def canAdjust(self, value: bool):
        if not isinstance(value, bool):
            raise TypeError(f"canAdjust {type(value)} not supported")
        self._can_adjust = value

    @property
    def decimal(self) -> str:
        return str(self._decimal)

    @decimal.setter
    def decimal(self, value: str | int):
        if isinstance(value, int):
            value = str(value)
        if re.match(r"^[0-9]+$", value) is None:
            raise TypeError(f"decimal {type(value)} not supported. Must be a positive integer as string.")
        self._decimal = value

    @property
    def formula(self) -> str:
        return self._formula

    @formula.setter
    def formula(self, value: str):
        structure = self._sr.get_structure()[self._layer_key]
        if not isinstance(value, str):
            raise TypeError(f"formula {type(value)} not supported")
        for variable in re.split(r'[+\-*/]', value):
            variable = variable.strip('() ')
            try:
                float(variable)
            except ValueError:
                if structure.get(variable) not in [FieldType.INTEGER, FieldType.SYSTEM_DEFINED]:
                    raise ValueError(f"Only numbers (integer or floating '12.3'), field names of {FieldType.INTEGER} or {FieldType.SYSTEM_DEFINED} in the same layer or operations like addition (+), subtraction (-), multiplication (*), and division (/)")

        self._formula = value


class InputGroupField(BaseField):
    field_type = FieldType.INPUT_GROUP

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        super().__init__(sr, layer_key, json_data)
        self._sub_fields = []
        self._parse_json()

    @property
    def sub_fields(self) -> list:
        return self._sub_fields

    @sub_fields.setter
    def sub_fields(self, value: list):
        new_val = []
        for entry in value:
            if isinstance(entry, SubBaseField):
                new_val.append(entry)
            elif isinstance(entry, dict) and entry.get('type') in SubFieldType.list():
                sf_type = SubFieldType(entry['type'])
                new_val.append(self._factory_subfield(sf_type, entry))
            else:
                raise TypeError("Value entries must be of type SubBaseField or dict")

        self._sub_fields = new_val



    def add_subfield(self, sf_type: SubFieldType) -> NumberField | SubTextField | SubSystemDefinedField | LabelField:
        self.sub_fields.append(self._factory_subfield(sf_type))
        return self.sub_fields[-1]

    def _factory_subfield(self, sf_type: SubFieldType,
                          data=None) -> NumberField | SubTextField | SubSystemDefinedField | LabelField:
        if data is None:
            data = {}
        if sf_type == SubFieldType.TEXT:
            return SubTextField(self._sr, self._layer_key, data)
        elif sf_type == SubFieldType.LABEL:
            return LabelField(self._sr, self._layer_key, data)
        elif sf_type == SubFieldType.NUMBER:
            return NumberField(self._sr, self._layer_key, data)
        elif sf_type == SubFieldType.SYSTEM_DEFINED:
            return SubSystemDefinedField(self._sr, self._layer_key, data)


class IntegerField(BaseField):
    field_type = FieldType.INTEGER

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        super().__init__(sr, layer_key, json_data)
        self._required = False
        self._parse_json()

    @property
    def required(self) -> bool:
        return self._required

    @required.setter
    def required(self, value: bool):
        if not isinstance(value, bool):
            raise TypeError(f"required {type(value)} not supported")
        self._required = value


class SelectField(BaseField, Select):
    field_type = FieldType.SELECT
    required_fields = ['option_layers']

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        super().__init__(sr, layer_key, json_data)
        Select.__init__(self, sr, json_data)
        self._parse_json()


class SystemDefinedField(BaseField, SystemDefined):
    field_type = FieldType.SYSTEM_DEFINED
    required_fields = ['option_layers', 'value_system']

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        super().__init__(sr, layer_key, json_data)
        SystemDefined.__init__(self, json_data)
        self._parse_json()


class TableField(BaseField):
    field_type = FieldType.TABLE

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        super().__init__(sr, layer_key, json_data)
        self._sub_fields = []
        self._parse_json()

    @property
    def sub_fields(self) -> list:
        return self._sub_fields

    @sub_fields.setter
    def sub_fields(self, value: list):
        new_val = []
        for entry in value:
            if isinstance(entry, TableSubBaseField):
                new_val.append(entry)
            elif isinstance(entry, dict) and entry.get('type') in SubTableFieldType.list():
                sf_type = SubTableFieldType(entry['type'])
                new_val.append(self._factory_subfield(sf_type, entry))
            else:
                raise TypeError("Value entries must be of type SubBaseField or dict")

        self._sub_fields = new_val



    def add_subfield(self, sf_type: SubTableFieldType, col_name: str) -> TableSubBaseField:
        self.sub_fields.append(self._factory_subfield(sf_type, {'col_name': col_name}))
        return self.sub_fields[-1]

    def _factory_subfield(self, sf_type: SubTableFieldType,
                          data=None) -> TableSubBaseField:
        if data is None:
            data = {}
        if sf_type == SubTableFieldType.DRAG_MOLECULE:
            return TSDragMolecule(self._sr, self._layer_key, data)
        elif sf_type == SubTableFieldType.DRAG_SAMPLE:
            return TSDragSample(self._sr, self._layer_key, data)
        elif sf_type == SubTableFieldType.SELECT:
            return TSSelect(self._sr, self._layer_key, data)
        elif sf_type == SubTableFieldType.SYSTEM_DEFINED:
            return TSSystemDefined(self._sr, self._layer_key, data)
        elif sf_type == SubTableFieldType.TEXT:
            return TSText(self._sr, self._layer_key, data)


class TextFormulaField(BaseField):
    field_type = FieldType.TEXT_FORMULA

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        super().__init__(sr, layer_key, json_data)
        self._parse_json()


class TextField(BaseField):
    field_type = FieldType.TEXT

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        super().__init__(sr, layer_key, json_data)
        self._required = False
        self._parse_json()

    @property
    def required(self) -> bool:
        return self._required

    @required.setter
    def required(self, value: bool):
        if not isinstance(value, bool):
            raise TypeError(f"required {type(value)} not supported")
        self._required = value


class TextareaField(BaseField):
    field_type = FieldType.TEXTAREA

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        super().__init__(sr, layer_key, json_data)
        self._parse_json()


class UploadField(BaseField):
    field_type = FieldType.UPLOAD

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        super().__init__(sr, layer_key, json_data)
        self._parse_json()
