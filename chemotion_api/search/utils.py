from enum import Enum


class EnumConnector(Enum):
    AND = 'AND'
    OR = 'OR'


class EnumMatch(Enum):
    LIKE = 'ILIKE'
    NOT_LIKE = 'NOT ILIKE'
    LESS_THAN = '<'
    BIGGER_THAN = '>'
    EXACT = '='

def new_base_field(match: EnumMatch, connector: str, value: str):
    return {
        "link": connector,
        "match": match.value,
        "value": value,
        "smiles": "",
        "sub_values": [],
        "unit": "",
        "validationState": None
    }