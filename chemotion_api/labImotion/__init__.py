import json
import os
from pathlib import Path
import re
import string
from collections.abc import Callable

from chemotion_api.labImotion import ontology
from chemotion_api.labImotion.icons import all_icons
from chemotion_api.labImotion.items.options import ElementType, SaveActionType
from chemotion_api.labImotion.items.validation import validate_generic_element, validate_generic_dataset, \
    validate_generic_segment, SchemaRegistry
from chemotion_api.labImotion.base_generic_obj import GenericObj
from chemotion_api.connection import Connection
from chemotion_api.element_manager import ElementManager
from urllib.parse import urlparse, unquote


class GenericElementKlass(GenericObj):
    """
    The template (klass) of a generic element type, e.g. 'Workflow'. The elements created from it are
    :class:`chemotion_api.elements.GenericElement` objects.
    """
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
            'name': self.name,
            'klass_prefix': self.klass_prefix
        }
        return self._json_data

    @property
    def klass_prefix(self) -> str:
        """
        The prefix of the elements' short labels (``<initials>-<prefix><counter>``)
        """
        return self._json_data.get('klass_prefix', '')

    @klass_prefix.setter
    def klass_prefix(self, value: str):
        if not isinstance(value, str) or value == '':
            raise TypeError("klass_prefix must be a non-empty string")
        self._json_data['klass_prefix'] = value

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


# Former name, kept for compatibility. Not to be confused with the element class
# chemotion_api.elements.GenericElement (an element of such a template)
GenericElement = GenericElementKlass


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
        self._element_klass = GenericElementKlass(json_data["element_klass"], connection)
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


class GenericManager:
    def __init__(self, connection: Connection, element_manager: ElementManager | None = None):
        self._connection = connection
        self._element_manager = element_manager

    def load_all_elements(self) -> list[GenericElementKlass]:
        return GenericElementKlass.load_all(self._connection)

    def load_all_segments(self) -> list[GenericSegment]:
        return GenericSegment.load_all(self._connection)

    def load_all_datasets(self) -> list[GenericDataset]:
        return GenericDataset.load_all(self._connection)

    def get_element(self, name: str = None, *, label: str = None, version: str = None,
                    **filters) -> GenericElementKlass:
        """
        Finds one element template. The templates are loaded from the server on every call.

        >>> gm.get_element('wrk')
        >>> gm.get_element(label='Workflow', version='2.0')

        :param name: the internal name of the element type, e.g. 'wrk'
        :param label: the label of the element type, e.g. 'Workflow'
        :param version: the version of the template, e.g. '2.0'
        :param filters: further attributes of :class:`GenericElementKlass` and their values,
            e.g. ``identifier=...``, ``uuid=...``, ``id=...``, ``is_active=True``
        :return: the template

        :raises KeyError: if no or more than one template matches
        """
        return self._get_single_generic_entry(GenericElementKlass.load_all(self._connection),
                                              **self._filters(name=name, label=label, version=version), **filters)

    def get_segment(self, label: str = None, *, version: str = None, **filters) -> GenericSegment:
        """
        Finds one segment template. The templates are loaded from the server on every call.

        :param label: the label of the segment, e.g. 'Electrochemistry'
        :param version: the version of the template
        :param filters: further attributes of :class:`GenericSegment` and their values,
            e.g. ``identifier=...``, ``uuid=...``, ``id=...``, ``is_active=True``
        :return: the template

        :raises KeyError: if no or more than one template matches
        """
        return self._get_single_generic_entry(GenericSegment.load_all(self._connection),
                                              **self._filters(label=label, version=version), **filters)

    def get_dataset(self, label: str = None, *, version: str = None, **filters) -> GenericDataset:
        """
        Finds one dataset template. The templates are loaded from the server on every call.

        :param label: the label of the dataset, e.g. 'NMR'
        :param version: the version of the template
        :param filters: further attributes of :class:`GenericDataset` and their values,
            e.g. ``ols_term_id=...``, ``identifier=...``, ``id=...``
        :return: the template

        :raises KeyError: if no or more than one template matches
        """
        return self._get_single_generic_entry(GenericDataset.load_all(self._connection),
                                              **self._filters(label=label, version=version), **filters)

    @staticmethod
    def search_ontology_terms(query: str, rows: int = 30) -> list[dict]:
        """
        Searches ontology terms for template fields (TIB Terminology Service, NFDI4Chem collection), like the
        term selection of the Chemotion template designer. See :attr:`BaseField.ontology`.

        :param query: search text or term ID
        :param rows: maximum number of results
        :return: the terms
        """
        return ontology.search_terms(query, rows)

    @staticmethod
    def get_ontology_term(term_id: str) -> dict:
        """
        Looks up an ontology term by its OBO ID ('CHMO:0000593'), short form or IRI.

        :raises KeyError: if no term has this ID
        """
        return ontology.get_term(term_id)

    @staticmethod
    def _filters(**filters) -> dict:
        return {key: value for key, value in filters.items() if value is not None}

    @staticmethod
    def _describe(entry: GenericDataset | GenericSegment | GenericElementKlass) -> str:
        name = getattr(entry, 'name', None)
        return f"{entry.label} ({f'name={name}, ' if name else ''}version={entry.version}, id={entry.id})"

    def _get_single_generic_entry(self, generic_element: list[GenericDataset | GenericSegment | GenericElementKlass],
                                  **fiter_args) -> GenericDataset | GenericSegment | GenericElementKlass:
        def filter(element):
            for key, item in fiter_args.items():
                if not hasattr(element, key) or getattr(element, key) != item:
                    return False
            return True

        filtered = [x for x in generic_element if filter(x)]
        if len(filtered) >= 2:
            raise KeyError(f"Multiple results for {fiter_args}: "
                           f"{', '.join(self._describe(x) for x in filtered)}. Add a filter, e.g. version=...")
        if len(filtered) == 0:
            raise KeyError(f"No element found for {fiter_args}. Available: "
                           f"{', '.join(self._describe(x) for x in generic_element) or 'none'}")
        return filtered[0]

    def upload_elements_json(self, file_path: str) -> list[GenericElementKlass]:
        return GenericElementKlass.upload(self._connection, file_path)

    def upload_segment_json(self, file_path: str) -> list[GenericSegment]:
        return GenericSegment.upload(self._connection, file_path)

    def create_new_element(self, label: str, icon_name: str, description: str = '', prefix: str = '', name: str = '',
                           release: bool = True, activate: bool = True) -> GenericElementKlass:
        """
        Creates a new element template. By default, an (empty) version 0.1 is released and the template is
        activated, so elements can be created from it right away. After adding layers and fields, release the
        template again with ``klass.save(SaveActionType.MINOR)``; new elements always use the latest release.

        >>> klass = gm.create_new_element('Micro Biology', 'bug', prefix='MB')
        >>> layer = klass.properties.add_new_layer('General')
        >>> layer.add_field(FieldType.TEXT, 'Strain')
        >>> klass.save(SaveActionType.MINOR)

        :param label: the label shown in Chemotion, e.g. 'Workflow'
        :param icon_name: a Font Awesome 4 icon name, e.g. 'fa-flask'
        :param description: the description of the template (stored as ``desc``)
        :param prefix: the prefix of the elements' short labels (``<initials>-<prefix><counter>``). If empty, the
            first four letters of the label in capitals are used ('Workflow' -> 'WORK')
        :param name: the internal name. If empty, the first four lowercase letters of the label are used, with
            a letter appended if the name is taken
        :param release: if True, the template is released (version 0.1). Unreleased templates are not available
            for creating elements
        :param activate: if True, the template is activated. Inactive templates are hidden from users
        :return: the new template
        """
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
        icon_name = GenericElementKlass.preprocess_icon_name(icon_name)
        GenericElementKlass.create_new(self._connection, klass_prefix=prefix, label=label, icon_name=icon_name,
                                       name=name, desc=description)
        klass = self.get_element(name)
        if release:
            klass.save_template(SaveActionType.MINOR)
        if activate:
            klass.is_active = True
        if release or activate:
            klass = self.get_element(name)
        if self._element_manager is not None:
            self._element_manager.reload()
        return klass

    def create_new_segment(self, label: str, description: str, element: GenericElementKlass) -> list[GenericSegment]:
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
            # `unquote` decodes %2e%2e%2f, so a schema key containing `..` would escape the
            # output directory. The keys come from the in-repo SchemaRegistry today, so this is
            # not reachable from untrusted data — but it is the only write site in the package
            # that does not enforce containment, and it is the obvious regression if schema keys
            # ever become loadable from a crate or a server.
            base = Path(cwd) / 'schemas'
            file_path = str((base / file_path).resolve())
            if not Path(file_path).is_relative_to(base.resolve()):
                raise ValueError(f"Schema key {schema_key!r} escapes the output directory")
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path + '.json', 'w', encoding='utf-8') as f:
                f.write(json.dumps(schema_entry.contents, indent=4))
