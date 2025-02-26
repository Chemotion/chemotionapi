from chemotion_api.labImotion.items.fields.base import BaseField
from chemotion_api.labImotion.items.fields.fields import TextField, CheckboxField, DatetimeField, DatetimeRangeField, \
    DragSampleField, DragMoleculeField, DragElementField, FormulaFieldField, InputGroupField, IntegerField, SelectField, \
    SystemDefinedField, TableField, TextFormulaField, TextareaField, UploadField, DummyField
from chemotion_api.labImotion.items.options import FieldType
from chemotion_api.labImotion.structure import StructureRegistry


def field_factory(sr: StructureRegistry, layer_key: str, json_data) -> BaseField:

    ft = FieldType(json_data.get('type'))
    return _field_factory(sr, layer_key, ft, json_data)


def create_field(sr: StructureRegistry, layer_key: str, field_type: FieldType, label: str, position: int, field: str) -> BaseField:
    return _field_factory(sr, layer_key, field_type, {'type': field_type.value, 'label': label, 'field': field, 'position': position})


def _field_factory(sr: StructureRegistry, layer_key: str, field_type: FieldType, json_data) -> BaseField:
    match field_type:
        case FieldType.DUMMY:
            return DummyField(sr, layer_key, json_data)
        case FieldType.CHECKBOX:
            return CheckboxField(sr, layer_key, json_data)
        case FieldType.DATETIME:
            return DatetimeField(sr, layer_key, json_data)
        case FieldType.DATETIME_RANGE:
            return DatetimeRangeField(sr, layer_key, json_data)
        case FieldType.DRAG_ELEMENT:
            return DragElementField(sr, layer_key, json_data)
        case FieldType.DRAG_MOLECULE:
            return DragMoleculeField(sr, layer_key, json_data)
        case FieldType.DRAG_SAMPLE:
            return DragSampleField(sr, layer_key, json_data)
        case FieldType.FORMULA_FIELD:
            return FormulaFieldField(sr, layer_key, json_data)
        case FieldType.INPUT_GROUP:
            return InputGroupField(sr, layer_key, json_data)
        case FieldType.INTEGER:
            return IntegerField(sr, layer_key, json_data)
        case FieldType.SELECT:
            return SelectField(sr, layer_key, json_data)
        case FieldType.SYSTEM_DEFINED:
            return SystemDefinedField(sr, layer_key, json_data)
        case FieldType.TABLE:
            return TableField(sr, layer_key, json_data)
        case FieldType.TEXT_FORMULA:
            return TextFormulaField(sr, layer_key, json_data)
        case FieldType.TEXT:
            return TextField(sr, layer_key, json_data)
        case FieldType.TEXTAREA:
            return TextareaField(sr, layer_key, json_data)
        case FieldType.UPLOAD:
            return UploadField(sr, layer_key, json_data)

    raise ValueError(f"Field type {FieldType} is not supported")
