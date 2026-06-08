"""Reaction search: query builder and executor."""
from dataclasses import fields
from typing import Literal, Optional, Self

from chemotion_api.search.search_helper import SearchHelperBase
from chemotion_api.search.utils import EnumMatch, EnumConnector, new_base_field


def field_details(field_name: Literal[
    'name', 'short_label', 'temperature', 'status', 'conditions', 'rxno', 'duration', 'content']):
    """Return the column/type metadata (and unit) describing a searchable reaction field.

    :param field_name: the reaction field to describe.
    :return: a dict ``{'field': <column metadata>, 'unit': <unit string>}``.
    :raises ValueError: if ``field_name`` is not a supported reaction field.
    """
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
    """Advanced-search builder for reactions."""

    element_type_res = "reactions"
    element_type = "reaction"
    def add_search_condition(self, match: EnumMatch, connector: EnumConnector, name: str | None = None,  # type: ignore[override]
                             short_label: str | None = None, status: str | None = None,
                             conditions: str | None = None, reaction_type: str | None = None,
                             temperature_in_c: float | None = None, duration_in_sec: int | None = None,
                             private_note: str | None = None):
        """Add a reaction search condition for each non-``None`` field; returns ``self`` for chaining.

        :param match: the match operator applied to each added field.
        :param connector: how this condition joins to the previous one (``AND`` / ``OR``).
        :param name: reaction name.
        :param short_label: short label.
        :param status: reaction status.
        :param conditions: reaction conditions.
        :param reaction_type: reaction type (RXNO).
        :param temperature_in_c: temperature in degrees Celsius.
        :param duration_in_sec: duration in seconds.
        :param private_note: private note content.
        """
        field_values = {"name": name, "short_label": short_label, "temperature": temperature_in_c,
                        "status": status, "conditions": conditions, "rxno": reaction_type, "duration": duration_in_sec,
                        "content": private_note}
        return super().add_search_condition(match, connector, **field_values)

    def new_field(self, match: EnumMatch, connector: str, field_name: Literal[  # type: ignore[override]
        'name', 'short_label', 'temperature', 'status', 'conditions', 'rxno', 'duration', 'content'],
                  value: str) -> dict:
        """Build a reaction-specific search-condition field for the payload.

        :param match: the match operator.
        :param connector: the connector token linking to the previous condition.
        :param field_name: the reaction field to search.
        :param value: the value to match against.
        :return: the fully-formed condition dict.
        """
        return new_base_field(match, connector, value) | {
            "table": "reactions",
            "element_id": 0
        } | field_details(field_name)
