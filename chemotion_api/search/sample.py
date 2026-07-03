"""Sample search: query builder and executor."""
from typing import Literal

from chemotion_api.search.search_helper import SearchHelperBase
from chemotion_api.search.utils import EnumMatch, EnumConnector, new_base_field


def field_details(field_name: Literal['name', 'short_label', 'external_label', 'inventory_label', 'xref', 'content']):
    """Return the column/type metadata describing a searchable sample field.

    :param field_name: the sample field to describe.
    :return: a dict ``{'field': <column metadata>, 'unit': ''}``.
    :raises ValueError: if ``field_name`` is not a supported sample field.
    """
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
    """Advanced-search builder for samples."""

    element_type_res = "samples"
    element_type = "sample"

    def add_search_condition(self, match: EnumMatch, connector: EnumConnector, name: str | None = None,  # type: ignore[override]
                             short_label: str | None = None, external_label: str | None = None,
                             inventory_label: str | None = None, cas: str | None = None,
                             private_note: str | None = None):
        """Add a sample search condition for each non-``None`` field; returns ``self`` for chaining.

        :param match: the match operator applied to each added field.
        :param connector: how this condition joins to the previous one (``AND`` / ``OR``).
        :param name: sample name.
        :param short_label: short label.
        :param external_label: external label.
        :param inventory_label: inventory label.
        :param cas: CAS number (stored under the ``xref`` column).
        :param private_note: private note content.
        """
        field_values = {"name": name, "short_label": short_label, "external_label": external_label,
                        "inventory_label": inventory_label, "xref": cas, "content": private_note}
        return super().add_search_condition(match, connector, **field_values)

    def new_field(self, match: EnumMatch, connector: str,  # type: ignore[override]
                  field_name: Literal['name', 'short_label', 'external_label', 'inventory_label', 'xref', 'content'],
                  value: str) -> dict:
        """Build a sample-specific search-condition field for the payload.

        :param match: the match operator.
        :param connector: the connector token linking to the previous condition.
        :param field_name: the sample field to search.
        :param value: the value to match against.
        :return: the fully-formed condition dict.
        """
        return new_base_field(match, connector, value) | {
            "table": "samples",
            "element_id": 0,
        } | field_details(field_name)

