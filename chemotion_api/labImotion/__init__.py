"""LabIMotion generic-element subsystem: build and manage user-defined element, segment and dataset classes."""
import json
import os
import re
import string
from typing import TypeVar
from collections.abc import Callable

from chemotion_api.labImotion.icons import all_icons
from chemotion_api.labImotion.items.options import ElementType
from chemotion_api.labImotion.items.validation import validate_generic_element, validate_generic_dataset, \
    validate_generic_segment, SchemaRegistry
from chemotion_api.labImotion.base_generic_obj import GenericObj
from chemotion_api.connection import Connection
from urllib.parse import urlparse, unquote

_GenericT = TypeVar("_GenericT", bound=GenericObj)


class GenericElement(GenericObj):
    """A user-defined generic element klass, with a Font Awesome icon and a unique name."""

    url = "/api/v1/generic_elements/klasses_all.json"
    url_create = "/api/v1/generic_elements/create_element_klass"
    url_upload = '/api/v1/generic_elements/upload_klass'
    url_activate = "/api/v1/generic_elements/de_activate_klass"
    url_save = "/api/v1/generic_elements/update_element_klass"
    url_save_template = "/api/v1/generic_elements/update_template"

    element_type = ElementType.ELEMENT

    @staticmethod
    def preprocess_icon_name(icon_name: str) -> str:
        """Normalise an icon name to its ``fa fa-`` prefixed Font Awesome v4 form.

        :param icon_name: An icon name, with or without the ``fa fa-`` prefix.
        :return: The validated, ``fa fa-`` prefixed icon name.
        :raises TypeError: If ``icon_name`` is not a string or is not a valid v4 icon.
        """
        fa_prefix = 'fa fa-'
        if not isinstance(icon_name, str):
            raise TypeError(f"icon_name {type(icon_name)} not supported")
        if icon_name.startswith(fa_prefix):
            icon_name = icon_name[len(fa_prefix):]
        if icon_name not in all_icons:
            raise TypeError("icon_name is no valid icon name check https://fontawesome.com/v4/icons/")
        return fa_prefix + icon_name

    def __init__(self, json_data: dict, connection: Connection):
        """Build a generic element, reading its icon name from the klass JSON.

        :param json_data: The raw element klass dict.
        :param connection: Authenticated connection used for persistence.
        """
        super().__init__(json_data, connection)
        self._icon_name = json_data["icon_name"]

    def to_dict(self) -> dict:
        """Serialise the element, including its icon name and name, to a dict.

        :return: The updated raw element klass dict.
        """
        super().to_dict()
        self._json_data |= {
            'icon_name': self._icon_name,
            'name': self.name
        }
        return self._json_data

    @property
    def icon_name(self) -> str:
        """The Font Awesome icon name of the element."""
        return self._icon_name

    @icon_name.setter
    def icon_name(self, value: str):
        """Set the icon name, normalising and validating it first.

        :raises TypeError: If ``value`` is not a valid Font Awesome v4 icon name.
        """
        self._icon_name = self.preprocess_icon_name(value)

    @property
    def name(self) -> str:
        """The internal name of the element (empty string if unset)."""
        return self._json_data.get("name", '')

    @name.setter
    def name(self, value: str):
        """Set the element name once.

        :raises ValueError: If a name was already set.
        :raises TypeError: If ``value`` is not a string.
        """
        if self.name != '':
            raise ValueError(f"name {self.name} already set")
        if not isinstance(value, str):
            raise TypeError(f"name {type(value)} not supported")
        self._json_data['name'] = value

    @classmethod
    def validator(cls) -> Callable[[dict], None]:
        """Return the validator for generic element klasses."""
        return validate_generic_element


class GenericSegment(GenericObj):
    """A user-defined generic segment klass attached to a parent generic element."""

    url = "/api/v1/segments/list_segment_klass.json"
    url_create = "/api/v1/segments/create_segment_klass"
    url_upload = '/api/v1/segments/upload_klass'
    url_activate = "/api/v1/generic_elements/de_activate_klass"
    url_save = "/api/v1/segments/update_segment_klass"
    url_save_template = "/api/v1/generic_elements/update_template"

    element_type = ElementType.SEGMENT

    def __init__(self, json_data: dict, connection: Connection):
        """Build a generic segment, also constructing its parent element klass.

        :param json_data: The raw segment klass dict, including ``element_klass``.
        :param connection: Authenticated connection used for persistence.
        """
        super().__init__(json_data, connection)
        self._element_klass = GenericElement(json_data["element_klass"], connection)
        pass

    @property
    def element_klass(self):
        """The parent :class:`GenericElement` this segment is attached to."""
        return self._element_klass

    def to_dict(self) -> dict:
        """Serialise the segment, including its parent element klass, to a dict.

        :return: The updated raw segment klass dict.
        """
        dict_val = super().to_dict()
        dict_val |= {
            'element_klass': self._element_klass.to_dict()
        }
        return dict_val

    @classmethod
    def validator(cls) -> Callable[[dict], None]:
        """Return the validator for generic segment klasses."""
        return validate_generic_segment


class GenericDataset(GenericObj):
    """A user-defined generic dataset klass, identified by an OLS term."""

    url = "/api/v1/generic_dataset/list_dataset_klass.json"
    url_activate = "/api/v1/generic_elements/de_activate_klass"
    url_save_template = "/api/v1/generic_elements/update_template"
    element_type = ElementType.DATASET

    def __init__(self, json_data: dict, connection: Connection):
        """Build a generic dataset, reading its OLS term id from the klass JSON.

        :param json_data: The raw dataset klass dict, including ``ols_term_id``.
        :param connection: Authenticated connection used for persistence.
        """
        super().__init__(json_data, connection)
        self._ols_term_id = json_data["ols_term_id"]

    @property
    def ols_term_id(self) -> str:
        """The OLS ontology term id identifying the dataset type."""
        return self._ols_term_id

    @ols_term_id.setter
    def ols_term_id(self, value: str):
        """Set the OLS term id of the dataset."""
        self._ols_term_id = value

    @classmethod
    def validator(cls) -> Callable[[dict], None]:
        """Return the validator for generic dataset klasses."""
        return validate_generic_dataset


class GenericManager:
    """High-level entry point to load, query, create and upload generic klasses."""

    def __init__(self, connection: Connection, element_manager=None):
        """Store the connection used for all generic-klass operations.

        :param connection: Authenticated connection to the Chemotion backend.
        :param element_manager: Optional :class:`~chemotion_api.element_manager.ElementManager`
            whose class/version caches are invalidated when klasses are created or uploaded.
        """
        self._connection = connection
        self._element_manager = element_manager

    def _invalidate_klass_caches(self):
        """Drop cached klass data after a mutation so subsequent reads refetch it."""
        self._connection.reset_generic_segment_cache()
        if self._element_manager is not None:
            self._element_manager.reset_cache()

    def load_all_elements(self) -> list[GenericElement]:
        """Load all generic element klasses.

        :return: All generic elements.
        """
        return GenericElement.load_all(self._connection)

    def load_all_segments(self) -> list[GenericSegment]:
        """Load all generic segment klasses.

        :return: All generic segments.
        """
        return GenericSegment.load_all(self._connection)

    def load_all_datasets(self) -> list[GenericDataset]:
        """Load all generic dataset klasses.

        :return: All generic datasets.
        """
        return GenericDataset.load_all(self._connection)

    def get_element(self, **fiter_args) -> GenericElement:
        """Return the single generic element matching the given attribute filters.

        :param fiter_args: Attribute name/value pairs the element must match.
        :return: The matching :class:`GenericElement`.
        :raises KeyError: If no element or more than one element matches.
        """
        return self._get_single_generic_entry(GenericElement.load_all(self._connection), **fiter_args)

    def get_segment(self, **fiter_args) -> GenericSegment:
        """Return the single generic segment matching the given attribute filters.

        :param fiter_args: Attribute name/value pairs the segment must match.
        :return: The matching :class:`GenericSegment`.
        :raises KeyError: If no segment or more than one segment matches.
        """
        return self._get_single_generic_entry(GenericSegment.load_all(self._connection), **fiter_args)

    def get_dataset(self, **fiter_args) -> GenericDataset:
        """Return the single generic dataset matching the given attribute filters.

        :param fiter_args: Attribute name/value pairs the dataset must match.
        :return: The matching :class:`GenericDataset`.
        :raises KeyError: If no dataset or more than one dataset matches.
        """
        return self._get_single_generic_entry(GenericDataset.load_all(self._connection), **fiter_args)

    def _get_single_generic_entry(self, generic_element: list[_GenericT],
                                  **fiter_args) -> _GenericT:
        """Return the unique entry from ``generic_element`` matching all filter args.

        :raises KeyError: If no entry or more than one entry matches.
        """
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
        """Upload an element klass definition from a JSON file.

        :param file_path: Path to the element klass JSON file.
        :return: All generic elements after the upload.
        """
        result = GenericElement.upload(self._connection, file_path)
        self._invalidate_klass_caches()
        return result

    def upload_segment_json(self, file_path: str) -> list[GenericSegment]:
        """Upload a segment klass definition from a JSON file.

        :param file_path: Path to the segment klass JSON file.
        :return: All generic segments after the upload.
        """
        result = GenericSegment.upload(self._connection, file_path)
        self._invalidate_klass_caches()
        return result

    def create_new_element(self, label: str, icon_name: str, description: str = '', prefix: str = '', name: str = '') -> \
            list[GenericElement]:
        """Create a new generic element, deriving a unique name and prefix if omitted.

        :param label: Display label of the new element.
        :param icon_name: Font Awesome icon name (validated before sending).
        :param description: Optional description of the element.
        :param prefix: Optional klass prefix; derived from ``label`` when empty.
        :param name: Optional internal name; derived and made unique when empty.
        :return: All generic elements after creation.
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
        icon_name = GenericElement.preprocess_icon_name(icon_name)
        result = GenericElement.create_new(self._connection, klass_prefix=prefix, label=label, icon_name=icon_name,
                                           name=name,
                                           desc=description)
        self._invalidate_klass_caches()
        return result

    def create_new_segment(self, label: str, description: str, element: GenericElement) -> list[GenericSegment]:
        """Create a new generic segment attached to an active generic element.

        :param label: Display label of the new segment.
        :param description: Description of the new segment.
        :param element: The active parent element the segment is attached to.
        :return: All generic segments after creation.
        :raises ValueError: If ``element`` is not active or not available.
        """
        all_elements = self.load_all_elements()
        all_names = [(x.id, x.identifier) for x in all_elements if x.is_active]
        if (element.id, element.identifier) not in all_names:
            raise ValueError("Element is not active or not available")
        result = GenericSegment.create_new(self._connection, element_klass=element.id, label=label,
                                           desc=description)
        self._invalidate_klass_caches()
        return result

    def check_schema_drift(self) -> dict[str, list[dict]]:
        """Validate every klass served by the connected instance against the bundled schemas.

        Fetches all element, segment and dataset klasses over the REST API and checks each
        against the JSON schemas packaged with this client (see
        :mod:`chemotion_api.labImotion.items.validation`). The bundled schemas track
        **LabIMotion 2.1.1 as shipped with Chemotion ELN v3.1.2**; run this against an
        instance on a different version to detect schema drift before editing or uploading
        templates.

        Only the REST API is used — no access to the server beyond its HTTP endpoints.

        :return: mapping of kind (``element`` / ``segment`` / ``dataset``) to a list of
            non-conforming klasses, each ``{'name': ..., 'label': ..., 'errors': [...]}``
            with human-readable validation messages. All lists empty means no drift detected.
        :raises ConnectionError: if a klass listing cannot be fetched.
        """
        kinds: list[tuple[str, type[GenericObj]]] = [
            ('element', GenericElement), ('segment', GenericSegment), ('dataset', GenericDataset)]
        report: dict[str, list[dict]] = {}
        for kind, cls in kinds:
            issues: list[dict] = []
            if cls.url is None:
                continue
            res = self._connection.get(cls.url)
            if res.status_code != 200:
                raise ConnectionError(f"{res.status_code} -> {res.text}")
            validator = SchemaRegistry.instance().validator_for(f'chemotion://generic/{kind}/draft-01')
            for obj in res.json().get('klass', []):
                # the element listing also serves the built-in klasses (sample, reaction, ...);
                # those are not LabIMotion templates and the schemas do not apply to them
                if obj.get('is_generic') is False:
                    continue
                errors = [e.message for e in validator.iter_errors(obj)]
                if errors:
                    issues.append({'name': obj.get('name'), 'label': obj.get('label'), 'errors': errors})
            report[kind] = issues
        return report

    @staticmethod
    def write_all_validation_schemas():
        """Write every registered JSON schema to disk under a ``schemas`` directory.

        Files are placed relative to the current working directory, using the schema ``$id``
        URL path as the file path. The schemas are bundled with the package (registered in
        :class:`SchemaRegistry` at import time) — no server connection is needed.
        """
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
