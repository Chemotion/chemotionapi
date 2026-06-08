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