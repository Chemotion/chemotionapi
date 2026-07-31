"""Factory helpers for LabIMotion generic-element fields.

This package groups all concrete field types together with the factory functions used to build
them from JSON or from explicit parameters. :func:`field_factory` reconstructs a field from raw
JSON data, while :func:`create_field` builds a new field from individual arguments. Both dispatch
on :class:`~chemotion_api.labImotion.items.options.FieldType` via :func:`_field_factory`.
"""

from chemotion_api.labImotion.items.fields.base import BaseField
from chemotion_api.labImotion.items.fields.fields import TextField, CheckboxField, DatetimeField, DatetimeRangeField, \
    DragSampleField, DragMoleculeField, DragElementField, FormulaFieldField, InputGroupField, IntegerField, SelectField, \
    SystemDefinedField, TableField, TextFormulaField, TextareaField, UploadField, DummyField
from chemotion_api.labImotion.items.options import FieldType
from chemotion_api.labImotion.structure import StructureRegistry


def field_factory(sr: StructureRegistry, layer_key: str, json_data) -> BaseField:
    """Build a field instance from its raw JSON data.

    The concrete field type is determined from the ``type`` entry of ``json_data``.

    :param sr: Structure registry providing access to the surrounding element schema.
    :param layer_key: Key of the layer the field belongs to.
    :param json_data: Raw JSON dictionary describing the field; must contain a ``type`` key.
    :return: The constructed concrete :class:`BaseField` subclass instance.
    :raises ValueError: If the field type is not supported.
    """
    ft = FieldType(json_data.get('type'))
    return _field_factory(sr, layer_key, ft, json_data)


def create_field(sr: StructureRegistry, layer_key: str, field_type: FieldType, label: str, position: int, field: str) -> BaseField:
    """Create a new field from explicit parameters.

    :param sr: Structure registry providing access to the surrounding element schema.
    :param layer_key: Key of the layer the field belongs to.
    :param field_type: Type of field to create.
    :param label: Human-readable label for the field.
    :param position: Ordering position of the field within its layer.
    :param field: Unique machine name (key) of the field.
    :return: The constructed concrete :class:`BaseField` subclass instance.
    :raises ValueError: If the field type is not supported.
    """
    return _field_factory(sr, layer_key, field_type, {'type': field_type.value, 'label': label, 'field': field, 'position': position})


def _field_factory(sr: StructureRegistry, layer_key: str, field_type: FieldType, json_data) -> BaseField:
    """Dispatch on ``field_type`` and instantiate the matching concrete field class.

    :param sr: Structure registry providing access to the surrounding element schema.
    :param layer_key: Key of the layer the field belongs to.
    :param field_type: Type of field to create.
    :param json_data: Raw JSON dictionary passed to the field constructor.
    :return: The constructed concrete :class:`BaseField` subclass instance.
    :raises ValueError: If the field type is not supported.
    """
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
