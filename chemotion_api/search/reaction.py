from dataclasses import fields
from typing import Literal, Optional, Self

from chemotion_api.search.search_helper import SearchHelperBase
from chemotion_api.search.utils import EnumMatch, EnumConnector, new_base_field


def field_details(field_name: Literal[
    'name', 'short_label', 'temperature', 'status', 'conditions', 'rxno', 'duration', 'content']):
    unit = ''
    if field_name == 'name':
        filed_type = {
            "column": "name",
            "label": "Name",
            "type": "text",
            "advanced": True
        }
    elif field_name == 'short_label':
        filed_type = {
            "column": "short_label",
            "label": "Short Label",
            "type": "text",
            "advanced": True
        }

    elif field_name == 'status':
        filed_type = {
            "column": "status",
            "label": "Status",
            "type": "select",
            "option_layers": "statusOptions",
            "advanced": True
        }

    elif field_name == 'conditions':
        filed_type = {
            "column": "conditions",
            "label": "Conditions",
            "type": "text",
            "advanced": True
        }

    elif field_name == 'temperature':
        filed_type = {
            "column": "temperature",
            "label": "Temperature",
            "type": "system-defined",
            "option_layers": "temperature",
            "info": "Only numbers are allowed",
            "advanced": True
        }
        unit = "°C"

    elif field_name == 'duration':
        filed_type = {
            "column": "duration",
            "label": "Duration",
            "type": "system-defined",
            "option_layers": "duration",
            "info": "Only numbers are allowed",
            "advanced": True
        }
        unit = "Second(s)"

    elif field_name == 'rxno':
        filed_type = {
            "column": "rxno",
            "label": "Type",
            "type": "rxnos",
            "advanced": True
        }

    elif field_name == 'content':
        filed_type = {
            "column": "content",
            "label": "Private Note",
            "type": "text",
            "advanced": True
        }

    else:
        raise ValueError(f'Field "{field_name}" not supported.')

    return {
        'field': filed_type,
        'unit': unit
    }


class ReactionSearcher(SearchHelperBase):
    element_type_res = "reactions"
    element_type = "reaction"
    def add_search_condition(self, match: EnumMatch, connector: EnumConnector, name: Optional[str] = None,
                             short_label: Optional[str] = None, status: Optional[str] = None,
                             conditions: Optional[str] = None, reaction_type: Optional[str] = None,
                             temperature_in_c: Optional[float] = None, duration_in_sec: Optional[int] = None,
                             private_note: Optional[str] = None):
        field_values = {"name": name, "short_label": short_label, "temperature": temperature_in_c,
                        "status": status, "conditions": conditions, "rxno": reaction_type, "duration": duration_in_sec,
                        "content": private_note}
        return super().add_search_condition(match, connector, **field_values)

    def new_field(self, match: EnumMatch, connector: str, field_name: Literal[
        'name', 'short_label', 'temperature', 'status', 'conditions', 'rxno', 'duration', 'content'],
                  value: str) -> dict:
        return new_base_field(match, connector, value) | {
            "table": "reactions",
            "element_id": 0
        } | field_details(field_name)
