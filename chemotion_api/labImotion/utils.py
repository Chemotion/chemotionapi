import json
from typing import Self, Callable

from chemotion_api.connection import Connection
from chemotion_api.labImotion.items.genericproperties import GenericProperties
from chemotion_api.utils import FixedDict


class GenericObj:
    url = None
    url_create = None
    element_type = None

    def __init__(self, json_data: dict, connection: Connection):
        self._json_data = json_data
        self._connection = connection
        self._id = json_data['id']
        self._version = json_data['version']
        self._identifier = json_data['identifier']
        self._is_active = json_data['is_active']
        self._is_generic = json_data.get('is_generic', True)
        if self.is_generic:
            self._properties = FixedDict({
                'template': GenericProperties(json_data['properties_template'], self.element_type),
                'release': GenericProperties(json_data['properties_release'], self.element_type)
            })
        else:
            self._properties = FixedDict({})

    @property
    def is_active(self) -> bool:
        return self._is_active

    @is_active.setter
    def is_active(self, value: bool):
        if not isinstance(value, bool):
            raise TypeError(f"is_active {type(value)} not supported")
        self._is_active = value

    @property
    def identifier(self) -> str:
        return self._identifiet

    @identifier.setter
    def identifier(self, value: str):
        if value is None:
            return
        if not isinstance(value, str):
            raise TypeError(f"identifier {type(value)} not supported")
        self._identifiet = value

    @property
    def properties(self) -> FixedDict:
        return self._properties

    @property
    def id(self) -> int:
        return self._id

    @property
    def is_generic(self) -> bool:
        return self._is_generic

    def validate(self, json_data: dict = None):
        if json_data is None:
            json_data = self._json_data

        self.validator()(json_data)

    @classmethod
    def validator(cls) -> Callable[[dict], None]:
        raise NotImplementedError()

    @classmethod
    def load_all(cls, con: Connection) -> list[Self]:
        if cls.url is None:
            return []
        res = con.get(cls.url)
        if res.status_code != 200:
            raise ConnectionError(f"{res.status_code} -> {res.text}")
        return_val = list()
        klass_list = res.json()['klass']
        for obj in klass_list:
            return_val.append(cls(obj, con))
        return return_val

    @classmethod
    def _create_new(cls, con: Connection, pkg: dict, label: str, desc: str, **kwargs) -> list[Self]:
        if cls.url_create is None:
            return []
        res = con.post(cls.url_create, data={
            label: label,
            desc: desc,
            pkg: pkg,
            **kwargs
        })
        if res.status_code != 200:
            raise ConnectionError(f"{res.status_code} -> {res.text}")

        return cls.load_all(con)
