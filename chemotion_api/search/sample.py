from typing import Literal, Optional

from chemotion_api.elements import ElementSet
from chemotion_api.search.search_helper import SearchHelperBase
from chemotion_api.search.utils import EnumMatch, EnumConnector, new_base_field


def field_details(field_name: Literal['name', 'short_label', 'external_label', 'inventory_label', 'xref', 'content']):
    if field_name == 'name':
        filed_type = {
            "column": "name",
            "label": "Sample name",
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

    elif field_name == 'external_label':
        filed_type = {
            "column": "external_label",
            "label": "External Label",
            "type": "text",
            "advanced": True
        }

    elif field_name == 'inventory_label':
        filed_type = {
            "column": "xref",
            "opt": "inventory_label",
            "label": "Inventory Label",
            "type": "text",
            "advanced": True
        }

    elif field_name == 'xref':
        filed_type = {
            "column": "xref",
            "opt": "cas",
            "label": "CAS",
            "type": "text",
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
        'unit': ''
    }


class SampleSearcher(SearchHelperBase):
    element_type_res = "samples"
    element_type = "sample"

    def add_search_condition(self, match: EnumMatch, connector: EnumConnector, name: Optional[str] = None,
                             short_label: Optional[str] = None, external_label: Optional[str] = None,
                             inventory_label: Optional[str] = None, cas: Optional[str] = None,
                             private_note: Optional[str] = None):
        field_values = {"name": name, "short_label": short_label, "external_label": external_label,
                        "inventory_label": inventory_label, "xref": cas, "content": private_note}
        return super().add_search_condition(match, connector, **field_values)

    def new_field(self, match: EnumMatch, connector: str,
                  field_name: Literal['name', 'short_label', 'external_label', 'inventory_label', 'xref', 'content'],
                  value: str) -> dict:
        return new_base_field(match, connector, value) | {
            "table": "samples",
            "element_id": 0,
        } | field_details(field_name)

