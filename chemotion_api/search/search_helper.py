"""Shared base for building and running Chemotion search queries."""
from abc import ABC, abstractmethod
from typing import Self, Any, cast

from chemotion_api.element_manager import ElementManager
from chemotion_api.elements import ElementSet
from chemotion_api.connection import Connection
from chemotion_api.search.utils import EnumMatch, EnumConnector


class SearchHelperBase(ABC):
    """Base builder for an advanced search against ``/api/v1/search/advanced``.

    Subclasses set :attr:`element_type` / :attr:`element_type_res` and implement
    :meth:`new_field`. Conditions are accumulated via :meth:`add_search_condition` and the query
    is executed with :meth:`request`.

    :param connection: an authenticated :class:`~chemotion_api.connection.Connection`.
    :param element_manager: the element manager used to instantiate result elements.
    :param root_collection_id: id of the collection to search within.
    """

    element_type_res: str
    element_type: str

    def __init__(self, connection: Connection, element_manager: ElementManager, root_collection_id: int):
        self._connection = connection
        self._element_manager = element_manager
        self._collection_id = root_collection_id
        self._per_page = 15
        self._payload: dict[str, Any] = {
            "selection": {
                "elementType": "advanced",
                "advanced_params": [

                ],
                "search_by_method": "advanced",
                "page_size": self._per_page
            },
            "collection_id": self._collection_id,
            "page": 1,
            "per_page": self._per_page,
            "is_sync": False,
            "molecule_sort": True,
            "is_public": False
        }

    def in_collection(self, collection_id: int) -> Self:
        """Restrict the search to a collection; returns ``self`` for chaining.

        :param collection_id: id of the collection to search within.
        """
        self._collection_id = collection_id
        return self

    def find_max(self, per_page: int) -> Self:
        """Set the maximum number of results (page size); returns ``self`` for chaining.

        :param per_page: maximum number of results to return.
        """
        self._per_page = per_page
        return self

    def _add_search_conditions(self, match: EnumMatch, connector: EnumConnector, **field_values) -> Self:
        """Add a search condition for each non-``None`` field value; returns ``self`` for chaining.

        Subclasses expose a typed ``add_search_condition`` with named keyword parameters and
        delegate here, so the public methods are not overrides (keeps them LSP-clean).

        The connector is applied only between conditions (the first condition has no connector).

        :param match: the match operator applied to each added field.
        :param connector: how this condition joins to the previous one (``AND`` / ``OR``).
        :param field_values: ``field_name=value`` pairs; ``None`` values are skipped.
        """
        for field_name, field_value in field_values.items():
            if field_value is not None:
                _connector = connector.value if len(
                    self._payload["selection"]["advanced_params"]) > 0 else ''
                self._payload["selection"]["advanced_params"].append(
                    self.new_field(match, _connector, field_name, field_value))
        return self

    def _send_request(self) -> list[dict]:
        """POST the accumulated payload to the advanced-search endpoint and return the raw elements.

        :raises ConnectionError: if the server does not respond with HTTP 201.
        """
        self._payload['selection']['page_size'] = self._per_page
        self._payload['per_page'] = self._per_page
        self._payload['collection_id'] = self._collection_id
        res = self._connection.post('/api/v1/search/advanced', json=self._payload)
        if res.status_code != 201:
            raise ConnectionError(res.status_code)
        return res.json()[self.element_type_res]['elements']

    def request(self) -> ElementSet:
        """Execute the search and return the matching elements.

        :return: an :class:`~chemotion_api.elements.ElementSet` of the matched elements.
        :raises ConnectionError: if the server does not respond with HTTP 201.
        """
        e = ElementSet(self._connection, cast(dict, self._element_manager.all_classes.get(self.element_type)),
                       self._collection_id, False, True)

        for val in self._send_request():
            e.new_element(val)

        return e

    @abstractmethod
    def new_field(self, match: EnumMatch, connector: str,
                  field_name: str, value: Any) -> dict[str, Any]:
        """Build one element-specific search-condition field.

        :param match: the match operator.
        :param connector: the connector token linking to the previous condition.
        :param field_name: the searchable field name.
        :param value: the value to match against.
        :return: the fully-formed condition dict for the payload.
        """
        ...