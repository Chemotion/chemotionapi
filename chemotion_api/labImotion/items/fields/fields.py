"""Concrete LabIMotion field types (text, integer, select, datetime, …)."""
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
    """Placeholder field carrying no input, used as a structural spacer."""

    field_type = FieldType.DUMMY

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        """Build the field and populate it from its raw JSON data.

        :param sr: Structure registry providing access to the surrounding element schema.
        :param layer_key: Key of the layer the field belongs to.
        :param json_data: Raw JSON dictionary describing the field.
        """
        super().__init__(sr, layer_key, json_data)
        self._parse_json()



class CheckboxField(BaseField):
    """A boolean checkbox field."""

    field_type = FieldType.CHECKBOX

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        """Build the field and populate it from its raw JSON data.

        :param sr: Structure registry providing access to the surrounding element schema.
        :param layer_key: Key of the layer the field belongs to.
        :param json_data: Raw JSON dictionary describing the field.
        """
        super().__init__(sr, layer_key, json_data)
        self._parse_json()


class DatetimeField(BaseField):
    """A single date-and-time field that may be marked required and/or read-only."""

    field_type = FieldType.DATETIME

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        """Build the field, defaulting it to optional and writable, then populate it from JSON.

        :param sr: Structure registry providing access to the surrounding element schema.
        :param layer_key: Key of the layer the field belongs to.
        :param json_data: Raw JSON dictionary describing the field.
        """
        super().__init__(sr, layer_key, json_data)
        self._readonly = False
        self._required = False
        self._parse_json()

    @property
    def required(self) -> bool:
        """Whether the field must be filled in."""
        return self._required

    @required.setter
    def required(self, value: bool):
        """Set whether the field is required.

        :raises TypeError: If ``value`` is not a bool.
        """
        if not isinstance(value, bool):
            raise TypeError(f"required {type(value)} not supported")
        self._required = value

    @property
    def readonly(self) -> bool:
        """Whether the field is read-only."""
        return self._readonly

    @readonly.setter
    def readonly(self, value: bool):
        """Set whether the field is read-only.

        :raises TypeError: If ``value`` is not a bool.
        """
        if not isinstance(value, bool):
            raise TypeError(f"readonly {type(value)} not supported")
        self._readonly = value


class DatetimeRangeField(BaseField):
    """A field capturing a start/end date-and-time range."""

    field_type = FieldType.DATETIME_RANGE

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        """Build the field and populate it from its raw JSON data.

        :param sr: Structure registry providing access to the surrounding element schema.
        :param layer_key: Key of the layer the field belongs to.
        :param json_data: Raw JSON dictionary describing the field.
        """
        super().__init__(sr, layer_key, json_data)
        self._parse_json()


class DragElementField(BaseField):
    """A field that references another generic element via drag-and-drop."""

    field_type = FieldType.DRAG_ELEMENT

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        """Build the field and populate it from its raw JSON data.

        :param sr: Structure registry providing access to the surrounding element schema.
        :param layer_key: Key of the layer the field belongs to.
        :param json_data: Raw JSON dictionary describing the field.
        """
        super().__init__(sr, layer_key, json_data)
        self._parse_json()


class DragMoleculeField(BaseField):
    """A field that references a molecule via drag-and-drop."""

    field_type = FieldType.DRAG_MOLECULE

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        """Build the field and populate it from its raw JSON data.

        :param sr: Structure registry providing access to the surrounding element schema.
        :param layer_key: Key of the layer the field belongs to.
        :param json_data: Raw JSON dictionary describing the field.
        """
        super().__init__(sr, layer_key, json_data)
        self._parse_json()


class DragSampleField(BaseField):
    """A field that references a sample via drag-and-drop."""

    field_type = FieldType.DRAG_SAMPLE

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        """Build the field and populate it from its raw JSON data.

        :param sr: Structure registry providing access to the surrounding element schema.
        :param layer_key: Key of the layer the field belongs to.
        :param json_data: Raw JSON dictionary describing the field.
        """
        super().__init__(sr, layer_key, json_data)
        self._parse_json()


class FormulaFieldField(BaseField):
    """A numeric field whose value is computed from a formula over other integer/system fields."""

    field_type = FieldType.FORMULA_FIELD
    required_fields = ["formula", "decimal", "canAdjust"]

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        """Build the field with default formula settings, then populate it from JSON.

        :param sr: Structure registry providing access to the surrounding element schema.
        :param layer_key: Key of the layer the field belongs to.
        :param json_data: Raw JSON dictionary describing the field.
        """
        super().__init__(sr, layer_key, json_data)
        self._formula = ""
        self._decimal: int | str = 2
        self._can_adjust = True
        self._parse_json()

    @property
    def canAdjust(self) -> bool:
        """Whether the computed value may be manually adjusted."""
        return self._can_adjust

    @canAdjust.setter
    def canAdjust(self, value: bool):
        """Set whether the computed value may be manually adjusted.

        :raises TypeError: If ``value`` is not a bool.
        """
        if not isinstance(value, bool):
            raise TypeError(f"canAdjust {type(value)} not supported")
        self._can_adjust = value

    @property
    def decimal(self) -> str:
        """The number of decimal places to display, as a string."""
        return str(self._decimal)

    @decimal.setter
    def decimal(self, value: str | int):
        """Set the number of decimal places from an int or a positive-integer string.

        :raises TypeError: If ``value`` is not a non-negative integer (or its string form).
        """
        if isinstance(value, int):
            value = str(value)
        if re.match(r"^[0-9]+$", value) is None:
            raise TypeError(f"decimal {type(value)} not supported. Must be a positive integer as string.")
        self._decimal = value

    @property
    def formula(self) -> str:
        """The arithmetic formula expression used to compute the field value."""
        return self._formula

    @formula.setter
    def formula(self, value: str):
        """Set and validate the formula expression.

        The expression may only reference numbers, integer or system-defined field names of the
        same layer, and the operators ``+``, ``-``, ``*`` and ``/``.

        :raises TypeError: If ``value`` is not a string.
        :raises ValueError: If the expression references an unsupported token.
        """
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
    """A composite field grouping several typed sub-fields (number, text, label, system-defined)."""

    field_type = FieldType.INPUT_GROUP

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        """Build the field with an empty sub-field list, then populate it from JSON.

        :param sr: Structure registry providing access to the surrounding element schema.
        :param layer_key: Key of the layer the field belongs to.
        :param json_data: Raw JSON dictionary describing the field.
        """
        super().__init__(sr, layer_key, json_data)
        self._sub_fields: list = []
        self._parse_json()

    @property
    def sub_fields(self) -> list:
        """The list of :class:`SubBaseField` sub-fields contained in this group."""
        return self._sub_fields

    @sub_fields.setter
    def sub_fields(self, value: list):
        """Set the sub-fields, building them from dicts or accepting ready instances.

        :param value: A list of :class:`SubBaseField` instances or sub-field dicts.
        :raises TypeError: If an entry is neither a :class:`SubBaseField` nor a valid sub-field dict.
        """
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
        """Append a new sub-field of the given type and return it.

        :param sf_type: The type of sub-field to create and append.
        :return: The newly created sub-field instance.
        """
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
    """An integer-valued field that may be marked required."""

    field_type = FieldType.INTEGER

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        """Build the field, defaulting it to optional, then populate it from JSON.

        :param sr: Structure registry providing access to the surrounding element schema.
        :param layer_key: Key of the layer the field belongs to.
        :param json_data: Raw JSON dictionary describing the field.
        """
        super().__init__(sr, layer_key, json_data)
        self._required = False
        self._parse_json()

    @property
    def required(self) -> bool:
        """Whether the field must be filled in."""
        return self._required

    @required.setter
    def required(self, value: bool):
        """Set whether the field is required.

        :raises TypeError: If ``value`` is not a bool.
        """
        if not isinstance(value, bool):
            raise TypeError(f"required {type(value)} not supported")
        self._required = value


class SelectField(BaseField, Select):
    """A field offering a choice from a predefined set of select options."""

    field_type = FieldType.SELECT
    required_fields = ['option_layers']

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        """Build the field, initialise its select-option support, then populate it from JSON.

        :param sr: Structure registry providing access to the surrounding element schema.
        :param layer_key: Key of the layer the field belongs to.
        :param json_data: Raw JSON dictionary describing the field.
        """
        super().__init__(sr, layer_key, json_data)
        Select.__init__(self, sr, json_data)
        self._parse_json()


class SystemDefinedField(BaseField, SystemDefined):
    """A field whose value/unit is constrained by a system-defined option set."""

    field_type = FieldType.SYSTEM_DEFINED
    required_fields = ['option_layers', 'value_system']

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        """Build the field, initialise its system-defined support, then populate it from JSON.

        :param sr: Structure registry providing access to the surrounding element schema.
        :param layer_key: Key of the layer the field belongs to.
        :param json_data: Raw JSON dictionary describing the field.
        """
        super().__init__(sr, layer_key, json_data)
        SystemDefined.__init__(self, json_data)
        self._parse_json()


class TableField(BaseField):
    """A tabular field whose columns are typed table sub-fields."""

    field_type = FieldType.TABLE

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        """Build the field with an empty column list, then populate it from JSON.

        :param sr: Structure registry providing access to the surrounding element schema.
        :param layer_key: Key of the layer the field belongs to.
        :param json_data: Raw JSON dictionary describing the field.
        """
        super().__init__(sr, layer_key, json_data)
        self._sub_fields: list = []
        self._parse_json()

    @property
    def sub_fields(self) -> list:
        """The list of :class:`TableSubBaseField` columns of the table."""
        return self._sub_fields

    @sub_fields.setter
    def sub_fields(self, value: list):
        """Set the table columns, building them from dicts or accepting ready instances.

        :param value: A list of :class:`TableSubBaseField` instances or column dicts.
        :raises TypeError: If an entry is neither a :class:`TableSubBaseField` nor a valid dict.
        """
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
        """Append a new table column of the given type and name, and return it.

        :param sf_type: The type of table sub-field (column) to create.
        :param col_name: The column name of the new sub-field.
        :return: The newly created table sub-field instance.
        """
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
    """A text field whose value is produced by a text/template formula."""

    field_type = FieldType.TEXT_FORMULA

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        """Build the field and populate it from its raw JSON data.

        :param sr: Structure registry providing access to the surrounding element schema.
        :param layer_key: Key of the layer the field belongs to.
        :param json_data: Raw JSON dictionary describing the field.
        """
        super().__init__(sr, layer_key, json_data)
        self._parse_json()


class TextField(BaseField):
    """A single-line text field that may be marked required."""

    field_type = FieldType.TEXT

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        """Build the field, defaulting it to optional, then populate it from JSON.

        :param sr: Structure registry providing access to the surrounding element schema.
        :param layer_key: Key of the layer the field belongs to.
        :param json_data: Raw JSON dictionary describing the field.
        """
        super().__init__(sr, layer_key, json_data)
        self._required = False
        self._parse_json()

    @property
    def required(self) -> bool:
        """Whether the field must be filled in."""
        return self._required

    @required.setter
    def required(self, value: bool):
        """Set whether the field is required.

        :raises TypeError: If ``value`` is not a bool.
        """
        if not isinstance(value, bool):
            raise TypeError(f"required {type(value)} not supported")
        self._required = value


class TextareaField(BaseField):
    """A multi-line text (textarea) field."""

    field_type = FieldType.TEXTAREA

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        """Build the field and populate it from its raw JSON data.

        :param sr: Structure registry providing access to the surrounding element schema.
        :param layer_key: Key of the layer the field belongs to.
        :param json_data: Raw JSON dictionary describing the field.
        """
        super().__init__(sr, layer_key, json_data)
        self._parse_json()


class UploadField(BaseField):
    """A field for attaching uploaded files."""

    field_type = FieldType.UPLOAD

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        """Build the field and populate it from its raw JSON data.

        :param sr: Structure registry providing access to the surrounding element schema.
        :param layer_key: Key of the layer the field belongs to.
        :param json_data: Raw JSON dictionary describing the field.
        """
        super().__init__(sr, layer_key, json_data)
        self._parse_json()
