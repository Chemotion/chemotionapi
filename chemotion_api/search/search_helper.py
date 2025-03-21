import json
from abc import ABC, abstractmethod
from typing import Self

from chemotion_api.element_manager import ElementManager
from chemotion_api.elements import ElementSet
from chemotion_api.connection import Connection
from chemotion_api.search.utils import EnumMatch, EnumConnector


class SearchHelperBase(ABC):
    element_type_res: str
    element_type: str

    def __init__(self, connection: Connection, element_manager: ElementManager, root_collection_id: int):
        self._connection = connection
        self._element_manager = element_manager
        self._collection_id = root_collection_id
        self._per_page = 15
        self._payload = {
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
        self._collection_id = collection_id
        return self

    def find_max(self, per_page: int) -> Self:
        self._per_page = per_page
        return self

    def add_search_condition(self, match: EnumMatch, connector: EnumConnector, **field_values) -> Self:
        for field_name, field_value in field_values.items():
            if field_value is not None:
                _connector = connector.value if len(
                    self._payload["selection"]["advanced_params"]) > 0 else ''
                self._payload["selection"]["advanced_params"].append(
                    self.new_field(match, _connector, field_name, field_value))
        return self

    def _send_request(self) -> list[dict]:
        self._payload['selection']['page_size'] = self._per_page
        self._payload['per_page'] = self._per_page
        self._payload['collection_id'] = self._collection_id
        with open('test.json', 'w') as file:
            file.write(json.dumps(self._payload))
        res = self._connection.post('/api/v1/search/advanced', json=self._payload)
        if res.status_code != 201:
            raise ConnectionError(res.status_code)
        return res.json()[self.element_type_res]['elements']

    def request(self) -> ElementSet:
        e = ElementSet(self._connection, self._element_manager.all_classes.get(self.element_type), self._collection_id,
                       False, True)

        for val in self._send_request():
            e.new_element(val)

        return e

    @abstractmethod
    def new_field(self, match: EnumMatch, connector: str,
                  field_name: str, value: any) -> dict[str, any]:
        ...