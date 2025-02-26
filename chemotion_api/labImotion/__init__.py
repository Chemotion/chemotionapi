import json
import os
import re
import string
from typing import Self, Callable

from chemotion_api.labImotion.icons import all_icons
from chemotion_api.labImotion.items.options import ElementType
from chemotion_api.labImotion.items.validation import validate_generic_element, validate_generic_dataset, \
    validate_generic_segment, SchemaRegistry
from chemotion_api.labImotion.base_generic_obj import GenericObj
from chemotion_api.connection import Connection
from urllib.parse import urlparse, unquote


class GenericElement(GenericObj):
    url = "/api/v1/generic_elements/klasses_all.json"
    url_create = "/api/v1/generic_elements/create_element_klass"
    url_upload = '/api/v1/generic_elements/upload_klass'
    url_activate = "/api/v1/generic_elements/de_activate_klass"
    url_save = "/api/v1/generic_elements/update_element_klass"
    url_save_template = "/api/v1/generic_elements/update_template"

    element_type = ElementType.ELEMENT

    @staticmethod
    def preprocess_icon_name(icon_name: str) -> str:
        fa_prefix = 'fa fa-'
        if not isinstance(icon_name, str):
            raise TypeError(f"icon_name {type(icon_name)} not supported")
        if icon_name.startswith(fa_prefix):
            icon_name = icon_name[len(fa_prefix):]
        if icon_name not in all_icons:
            raise TypeError(f"icon_name is no valid icon name check https://fontawesome.com/v4/icons/")
        return fa_prefix + icon_name

    def __init__(self, json_data: dict, connection: Connection):
        super().__init__(json_data, connection)
        self._icon_name = json_data["icon_name"]

    def to_dict(self) -> dict:
        super().to_dict()
        self._json_data |= {
            'icon_name': self._icon_name,
            'name': self.name
        }
        return self._json_data

    @property
    def icon_name(self) -> str:
        return self._icon_name

    @icon_name.setter
    def icon_name(self, value: str):
        self._icon_name = self.preprocess_icon_name(value)

    @property
    def name(self) -> str:
        return self._json_data.get("name", '')

    @name.setter
    def name(self, value: str):
        if self.name != '':
            raise ValueError(f"name {self.name} already set")
        if not isinstance(value, str):
            raise TypeError(f"name {type(value)} not supported")
        self._json_data['name'] = value

    @classmethod
    def validator(cls) -> Callable[[dict], None]:
        return validate_generic_element


class GenericSegment(GenericObj):
    url = "/api/v1/segments/list_segment_klass.json"
    url_create = "/api/v1/segments/create_segment_klass"
    url_upload = '/api/v1/segments/upload_klass'
    url_activate = "/api/v1/generic_elements/de_activate_klass"
    url_save = "/api/v1/segments/update_segment_klass"
    url_save_template = "/api/v1/generic_elements/update_template"

    element_type = ElementType.SEGMENT

    def __init__(self, json_data: dict, connection: Connection):
        super().__init__(json_data, connection)
        self._element_klass = GenericElement(json_data["element_klass"], connection)
        pass

    @property
    def element_klass(self):
        return self._element_klass

    def to_dict(self) -> dict:
        dict_val = super().to_dict()
        dict_val |= {
            'element_klass': self._element_klass.to_dict()
        }
        return dict_val

    @classmethod
    def validator(cls) -> Callable[[dict], None]:
        return validate_generic_segment


class GenericDataset(GenericObj):
    url = "/api/v1/generic_dataset/list_dataset_klass.json"
    url_activate = "/api/v1/generic_elements/de_activate_klass"
    url_save_template = "/api/v1/generic_elements/update_template"
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
    def validator(cls) -> Callable[[dict], None]:
        return validate_generic_dataset


class GenericManager():
    def __init__(self, connection: Connection):
        self._connection = connection

    def load_all_elements(self) -> list[GenericElement]:
        return GenericElement.load_all(self._connection)

    def load_all_segments(self) -> list[GenericSegment]:
        return GenericSegment.load_all(self._connection)

    def load_all_datasets(self) -> list[GenericDataset]:
        return GenericDataset.load_all(self._connection)

    def get_element(self, **fiter_args) -> GenericElement:
        return self._get_single_generic_entry(GenericElement.load_all(self._connection), **fiter_args)

    def get_segment(self, **fiter_args) -> GenericSegment:
        return self._get_single_generic_entry(GenericSegment.load_all(self._connection), **fiter_args)

    def get_dataset(self, **fiter_args) -> GenericDataset:
        return self._get_single_generic_entry(GenericDataset.load_all(self._connection), **fiter_args)

    def _get_single_generic_entry(self, generic_element: list[GenericDataset | GenericSegment | GenericElement],
                                  **fiter_args) -> GenericDataset | GenericSegment | GenericElement:
        def filter(element):
            for key, item in fiter_args.items():
                if not hasattr(element, key) or getattr(element, key) != item:
                    return False
            return True

        filtered = [x for x in generic_element if filter(x)]
        if len(filtered) >= 2:
            raise KeyError("Multiple results!")
        if len(filtered) == 0:
            raise KeyError("No element found!")
        return filtered[0]


    def upload_elements_json(self, file_path: str) -> list[GenericElement]:
        return GenericElement.upload(self._connection, file_path)

    def upload_segment_json(self, file_path: str) -> list[GenericSegment]:
        return GenericSegment.upload(self._connection, file_path)

    def create_new_element(self, label: str, icon_name: str, description: str = '', prefix: str = '', name: str = '') -> \
            list[GenericElement]:
        all_elements = self.load_all_elements()
        all_names = [x.name for x in all_elements]
        if name == '':
            name = t_name = re.sub(r'[^a-z]', '', label.lower())[:4]
            i = 0
            while name in all_names:
                name = t_name + string.ascii_lowercase[i]
                i += 1
        if prefix == '':
            prefix = re.sub(r'[^A-Z]', '', label.upper())[:4]
        icon_name = GenericElement.preprocess_icon_name(icon_name)
        return GenericElement.create_new(self._connection, klass_prefix=prefix, label=label, icon_name=icon_name,
                                         name=name,
                                         desc=description)

    def create_new_segment(self, label: str, description: str, element: GenericElement) -> list[GenericSegment]:
        all_elements = self.load_all_elements()
        all_names = [(x.id, x.identifier) for x in all_elements if x.is_active]
        if (element.id, element.identifier) not in all_names:
            raise ValueError("Element is not active or not available")
        return GenericSegment.create_new(self._connection, element_klass=element.id, label=label,
                                         desc=description)

    def write_all_validation_schemas(self):
        cwd = os.getcwd()

        for (schema_key, schema_entry) in SchemaRegistry.instance().registry:
            parsed_url = urlparse(schema_key)
            file_path = unquote(parsed_url.path)
            if file_path.startswith('/'):
                file_path = file_path[1:]  # Remove leading slash
            file_path = os.path.join(cwd, 'schemas', file_path)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path + '.json', 'w', encoding='utf-8') as f:
                f.write(json.dumps(schema_entry.contents, indent=4))
