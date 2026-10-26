import json
import warnings
from typing import Self
from collections.abc import Callable

import logging

from chemotion_api.connection import Connection
from chemotion_api.labImotion.items.genericproperties import GenericProperties
from chemotion_api.labImotion.items.options import SaveActionType
from chemotion_api.labImotion.structure import StructureRegistry
from chemotion_api.labImotion.utils import ChemotionSerializable, generate_pkg_info


logger = logging.getLogger(__name__)

class GenericObj(ChemotionSerializable):
    url = None
    url_create = None
    url_upload = None
    url_activate = None
    url_save = None
    url_save_template = None
    element_type = None

    def __init__(self, json_data: dict, connection: Connection):
        self._json_data = json_data
        self._connection = connection
        self._id = json_data['id']
        self._version = json_data['version']
        self._identifier = json_data['identifier']
        self._uuid = json_data['uuid']
        self._is_active = json_data['is_active']
        self._label = json_data['label']
        self._desc = json_data['desc']
        self._is_generic = json_data.get('is_generic', True)
        self._sr = StructureRegistry(self)
        self._properties = None
        self._release: GenericProperties | None = None
        if self.is_generic:
            self._properties = GenericProperties(json_data['properties_template'], self.element_type, self._sr)

    def to_dict(self):
        if self.is_generic:
            self._json_data |= {
                'uuid': self._identifier,
                'label': self.label,
                'desc': self.desc,
                'properties_template': self._properties.to_dict()
            }
        return self._json_data

    def save(self, save_type_action: SaveActionType = SaveActionType.DRAFT):
        if self.url_save_template is not None:
            self.save_template(save_type_action)
        if self.url_save is not None:
            self.save_generale_properties()

    def save_template(self, save_type_action: SaveActionType = SaveActionType.DRAFT):
        if self.url_save_template is None:
            raise TypeError('Save template is not supported')
        res = self._connection.post(self.url_save_template, data=self.to_dict() | {
            "release": save_type_action.value,
            "klass": self.element_type.value,
            "version": None
        })
        if res.status_code != 201:
            raise ConnectionError(f"{res.status_code} -> {res.text}")

    def save_generale_properties(self):
        if self.url_save is None:
            raise TypeError('Save template is not supported')
        res = self._connection.post(self.url_save, data=self.to_dict())
        if res.status_code != 201:
            raise ConnectionError(f"{res.status_code} -> {res.text}")

    def activate(self):
        self.is_active = True

    def deactivate(self):
        self.is_active = False

    @property
    def label(self) -> str:
        return self._label

    @label.setter
    def label(self, value: str):
        if not isinstance(value, str):
            raise TypeError(f"label {type(value)} not supported")
        self._label = value
        
    @property
    def desc(self) -> str:
        return self._desc
    
    @desc.setter
    def desc(self, value: str):
        if not isinstance(value, str):
            raise TypeError(f"desc {type(value)} not supported")
        self._desc = value

    @property
    def version(self) -> str:
        return self._version

    @property
    def is_active(self) -> bool:
        return self._is_active

    @is_active.setter
    def is_active(self, value: bool):
        if not isinstance(value, bool):
            raise TypeError(f"is_active {type(value)} not supported")
        res = self._connection.post(self.url_activate, data={
            'klass': self.element_type.value,
            'id': self.id,
            'is_active': value
        })
        if res.status_code != 201:
            raise ConnectionError(f"{res.status_code} -> {res.text}")
        self._is_active = value

    @property
    def identifier(self) -> str:
        return self._identifier

    @identifier.setter
    def identifier(self, value: str):
        if value is None:
            return
        if not isinstance(value, str):
            raise TypeError(f"identifier {type(value)} not supported")
        self._identifier = value

    @property
    def uuid(self) -> str:
        return self._uuid

    @property
    def properties(self) -> GenericProperties | None:
        return self._properties

    @property
    def release(self) -> GenericProperties | None:
        """
        The released version of the template (read only). It is parsed on first access, so a template
        with an invalid release copy can still be loaded and repaired by releasing it again.
        """
        if self._release is None and self.is_generic and self._json_data.get('properties_release'):
            self._release = GenericProperties(self._json_data['properties_release'], self.element_type, self._sr)
        return self._release

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
    def load_all(cls, con: Connection, strict: bool = False) -> list[Self]:
        """
        Loads all templates of this kind.

        :param con: the connection
        :param strict: if True, an invalid template raises an error. Otherwise, it is skipped with a warning
        :return: all (valid) templates
        """
        if cls.url is None:
            return []
        res = con.get(cls.url)
        if res.status_code != 200:
            raise ConnectionError(f"{res.status_code} -> {res.text}")
        return_val = list()
        klass_list = res.json()['klass']
        for obj in klass_list:
            try:
                return_val.append(cls(obj, con))
            except Exception as e:
                # One klass this client cannot parse must not take the rest down with it. Real
                # instances carry klasses authored years ago by older chem-generic-ui versions;
                # before this, a single such klass made get_element/get_segment/get_dataset — and
                # therefore the whole generic API — raise, including for klasses that parse fine.
                if strict:
                    raise
                name = obj.get('name') or obj.get('label') or obj.get('id')
                logger.warning(
                    "skipping LabIMotion klass %r: it could not be parsed (%s: %s). Elements using "
                    "this klass will not be available; every other klass is unaffected.",
                    name, type(e).__name__, e)
        return return_val

    @classmethod
    def upload(cls, con: Connection, file_path: str) -> list[Self]:
        if cls.url_create is None:
            return []
        with open(file_path) as f:
            json_data = json.loads(f.read())
        res = con.post(cls.url_upload, data=json_data)
        if res.status_code != 201:
            raise ConnectionError(f"{res.status_code} -> {res.text}")
        return cls.load_all(con)

    @classmethod
    def create_new(cls, con: Connection, **kwargs) -> list[Self]:
        if cls.url_create is None:
            return []
        res = con.post(cls.url_create, data={
            **kwargs
        } | generate_pkg_info())
        if res.status_code != 201:
            raise ConnectionError(f"{res.status_code} -> {res.text}")

        return cls.load_all(con)