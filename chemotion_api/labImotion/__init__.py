from typing import Self, Callable

from chemotion_api.labImotion.items.options import ElementType
from chemotion_api.labImotion.items.validation import validate_generic_element, validate_generic_dataset, \
    validate_generic_segment
from chemotion_api.labImotion.utils import GenericObj
from chemotion_api.connection import Connection


class GenericManager():
    def __init__(self, connection: Connection):
        self._connection = connection

    def load_all_elements(self):
        return GenericElement.load_all(self._connection)

    def load_all_segments(self):
        return GenericSegment.load_all(self._connection)

    def load_all_datasets(self):
        return GenericDataset.load_all(self._connection)


class GenericElement(GenericObj):
    url = "/api/v1/generic_elements/klasses_all.json"
    url_create = "/api/v1/generic_elements/klasses_all.json"
    element_type = ElementType.ELEMENT

    @classmethod
    def validator(cls) -> Callable[[dict],None]:
        return validate_generic_element

    @classmethod
    def create_new(cls, con: Connection, pkg: dict, klass_prefix: str, label: str, name: str, desc: str,
                   icon_name: str) -> list[Self]:
        return super()._create_new(con, pkg, klass_prefix=klass_prefix, label=label, name=name, desc=desc,
                                   icon_name=icon_name, is_generic=True)


class GenericSegment(GenericObj):
    url = "/api/v1/segments/list_segment_klass.json"
    url_create = "/api/v1/generic_elements/create_element_klass"
    element_type = ElementType.SEGMENT

    @classmethod
    def validator(cls) -> Callable[[dict],None]:
        return validate_generic_segment

    @classmethod
    def create_new(cls, con: Connection, pkg: dict, label: str, desc: str, element_class: GenericElement) -> list[Self]:
        return super()._create_new(con, pkg, label=label, desc=desc, element_class = element_class.id)


class GenericDataset(GenericObj):
    url = "/api/v1/generic_dataset/list_dataset_klass.json"
    element_type = ElementType.DATASET

    def __init__(self, json_data: dict, connection: Connection):
        super().__init__(json_data, connection)
        self._ols_term_id = json_data["ols_term_id"]

    @property
    def ols_term_id(self) -> str:
        return self._ols_term_id

    @ols_term_id.setter
    def ols_term_id(self, value: str):
        self._ols_term_id = value

    @classmethod
    def validator(cls) -> Callable[[dict],None]:
        return validate_generic_dataset

    @classmethod
    def create_new(cls, con: Connection, pkg: dict, label: str, desc: str, element_class: GenericElement) -> list[Self]:
        return super()._create_new(con, pkg, label=label, desc=desc, element_class = element_class.id)
