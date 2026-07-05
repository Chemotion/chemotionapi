"""Reaction search: query builder and executor."""

from chemotion_api.search.search_helper import SearchHelperBase
from chemotion_api.search.utils import EnumMatch, EnumConnector, new_base_field, get_field_details


def field_details(field_name: str):
    """Return the column/type metadata (and unit) describing a searchable reaction field.

    :param field_name: the reaction field to describe (one of ``name``, ``short_label``,
        ``temperature``, ``status``, ``conditions``, ``rxno``, ``duration``, ``content``).
    :return: a dict ``{'field': <column metadata>, 'unit': <unit string>}``.
    :raises ValueError: if ``field_name`` is not a supported reaction field.
    """
    return get_field_details('reaction', field_name)


class ReactionSearcher(SearchHelperBase):
    """Advanced-search builder for reactions."""

    element_type_res = "reactions"
    element_type = "reaction"
    def add_search_condition(self, match: EnumMatch, connector: EnumConnector, name: str | None = None,
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
        return self._add_search_conditions(match, connector, **field_values)

    def new_field(self, match: EnumMatch, connector: str, field_name: str,
                  value: str) -> dict:
        """Build a reaction-specific search-condition field for the payload.

        :param match: the match operator.
        :param connector: the connector token linking to the previous condition.
        :param field_name: the reaction field to search (one of ``name``, ``short_label``,
            ``temperature``, ``status``, ``conditions``, ``rxno``, ``duration``, ``content``).
        :param value: the value to match against.
        :return: the fully-formed condition dict.
        :raises ValueError: if ``field_name`` is not a supported reaction field.
        """
        return new_base_field(match, connector, value) | {
            "table": "reactions",
            "element_id": 0
        } | field_details(field_name)
