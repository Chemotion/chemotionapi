"""Enums and helpers shared by the search query builders."""
from enum import Enum


class EnumConnector(Enum):
    """Logical connector joining consecutive search conditions (``AND`` / ``OR``)."""
    AND = 'AND'
    OR = 'OR'


class EnumMatch(Enum):
    """Match operator for a search condition, mapped to its server-side token."""
    LIKE = 'ILIKE'
    NOT_LIKE = 'NOT ILIKE'
    LESS_THAN = '<'
    BIGGER_THAN = '>'
    EXACT = '='

# Shared field metadata definitions for sample and reaction search.
# Each element type defines its searchable fields; used by field_details() in sample.py and reaction.py.
# Fields with units (e.g. temperature, duration) are stored as tuples: (definition_dict, unit_string)
FIELD_DEFINITIONS = {
    'sample': {
        'name': {"column": "name", "label": "Sample name", "type": "text", "advanced": True},
        'short_label': {"column": "short_label", "label": "Short Label", "type": "text", "advanced": True},
        'external_label': {"column": "external_label", "label": "External Label", "type": "text", "advanced": True},
        'inventory_label': {"column": "xref", "opt": "inventory_label", "label": "Inventory Label", "type": "text", "advanced": True},
        'xref': {"column": "xref", "opt": "cas", "label": "CAS", "type": "text", "advanced": True},
        'content': {"column": "content", "label": "Private Note", "type": "text", "advanced": True},
    },
    'reaction': {
        'name': {"column": "name", "label": "Name", "type": "text", "advanced": True},
        'short_label': {"column": "short_label", "label": "Short Label", "type": "text", "advanced": True},
        'status': {"column": "status", "label": "Status", "type": "select", "option_layers": "statusOptions", "advanced": True},
        'conditions': {"column": "conditions", "label": "Conditions", "type": "text", "advanced": True},
        'temperature': ({"column": "temperature", "label": "Temperature", "type": "system-defined", "option_layers": "temperature", "info": "Only numbers are allowed", "advanced": True}, "°C"),
        'rxno': {"column": "rxno", "label": "Type", "type": "rxnos", "advanced": True},
        'duration': ({"column": "duration", "label": "Duration", "type": "system-defined", "option_layers": "duration", "info": "Only numbers are allowed", "advanced": True}, "Second(s)"),
        'content': {"column": "content", "label": "Private Note", "type": "text", "advanced": True},
    }
}


def get_field_details(element_type: str, field_name: str) -> dict:
    """Return field metadata (column, type, unit) for a searchable element field.

    :param element_type: 'sample' or 'reaction'
    :param field_name: the field to describe
    :return: a dict ``{'field': <column metadata>, 'unit': <unit string>}``
    :raises ValueError: if element_type or field_name is not supported
    """
    if element_type not in FIELD_DEFINITIONS:
        raise ValueError(f'Element type "{element_type}" not supported.')

    definitions = FIELD_DEFINITIONS[element_type]
    if field_name not in definitions:
        raise ValueError(f'Field "{field_name}" not supported for {element_type}.')

    field_def = definitions[field_name]
    # Handle fields with units (stored as tuples)
    if isinstance(field_def, tuple):
        field_type, unit = field_def
        return {'field': field_type, 'unit': unit}
    else:
        return {'field': field_def, 'unit': ''}

def new_base_field(match: EnumMatch, connector: str, value: str):
    """Build the common base of an advanced-search condition field.

    :param match: the match operator (its ``.value`` token is stored).
    :param connector: the connector token linking this condition to the previous one.
    :param value: the value to match against.
    :return: a dict with the base condition keys, to be merged with field-specific keys.
    """
    return {
        "link": connector,
        "match": match.value,
        "value": value,
        "smiles": "",
        "sub_values": [],
        "unit": "",
        "validationState": None
    }