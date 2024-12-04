import copy
import re
import string
import uuid
from enum import Enum

from chemotion_api.labImotion.items.options import ElementType
from chemotion_api.labImotion.items.layer import Layer
from chemotion_api.labImotion.items.validation import validate_selection_options, validate_generic_properties, \
    validate_generic_dataset_properties, validate_generic_segment_properties
from chemotion_api.labImotion.structure import StructureRegistry
from chemotion_api.labImotion.utils import ChemotionSerializable
from chemotion_api.utils import FixedDict


class GenericProperties(ChemotionSerializable):
    def __init__(self, json_data: dict, element_type: ElementType, sr: StructureRegistry):
        self._json_data = json_data
        self._element_type = element_type
        self._pkg = FixedDict(copy.deepcopy(json_data.get('pkg', {})))
        self._select_options = {}
        self._identifier = None
        self._flow_object = []
        self._version = None
        self._uuid = ''
        self._klass = ElementType.ELEMENT
        self._layers = []
        self._sr = sr

        for key, value in json_data.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def to_dict(self) -> dict:
        for key, _ in self._json_data.items():
            if hasattr(self, key) and key != 'pkg':
                value = getattr(self, key)
                if isinstance(value, Enum):
                    value = value.value
                if key == 'layers':
                    self._json_data[key] = {x.key: x.to_dict() for x in value}
                else:
                    self._json_data[key] = value
        return self._json_data

    def validate(self, json_data: dict = None):
        if json_data is None:
            json_data = self._json_data
        if self._element_type == ElementType.DATASET:
            validate_generic_dataset_properties(json_data)
        if self._element_type == ElementType.SEGMENT:
            validate_generic_segment_properties(json_data)
        else:
            validate_generic_properties(json_data)

    def get_layer_by_label(self, label: str) -> Layer:
        return next(l for l in self.layers if l.label == label)

    def get_layer_by_key(self, key: str) -> Layer:
        return next(l for l in self.layers if l.key == key)

    @property
    def layers(self) -> list[Layer]:
        return self._layers

    @layers.setter
    def layers(self, values: dict | list[Layer]):
        if isinstance(values, dict):
            self._layers = []
            for key, value in values.items():
                self._layers.append(Layer(self._sr, value))
        else:
            if not isinstance(values, list):
                raise TypeError(f"layers {type(values)} not supported")
            for value in values:
                if not isinstance(value, Layer):
                    raise TypeError(f"layers -> list[{type(value)}] not supported")
                self._layers.append(value)

        self._layers.sort(key=lambda x: x.position)

    @property
    def version(self) -> str | None:
        return self._version

    @version.setter
    def version(self, value: str | None):
        if value is None:
            return
        if not isinstance(value, str):
            raise TypeError(f"version {type(value)} not supported")
        if self._version is not None:
            raise ValueError(f"version {self._version} already set")
        self._version = value

    @property
    def identifier(self) -> str:
        return self._identifier

    @identifier.setter
    def identifier(self, value: str | None):
        if value is None:
            self._identifier = uuid.uuid4().__str__()
            return
        if not isinstance(value, str):
            raise TypeError(f"identifier {type(value)} not supported")
        if self._identifier is not None:
            raise ValueError(f"identifier {self._identifier} already set")
        self._identifier = value

    @property
    def uuid(self) -> str:
        return self._uuid

    @uuid.setter
    def uuid(self, value: str):
        if not isinstance(value, str):
            raise TypeError(f"uuid {type(value)} not supported")
        if self._uuid != '':
            raise ValueError(f"uuid {self._uuid} already set")
        self._uuid = value

    @property
    def package_info(self):
        return self._pkg

    @property
    def klass(self) -> ElementType:
        return self._klass

    @klass.setter
    def klass(self, value: ElementType | str):
        if isinstance(value, str):
            value = ElementType(value)
        if not isinstance(value, ElementType):
            raise TypeError(f"klass {type(value)} not supported")
        self._klass = value

    @property
    def select_options(self) -> dict[str, dict[str, list[dict[str, str]]]]:
        return self._select_options

    @select_options.setter
    def select_options(self, value: dict[str, dict[str, list[dict[str, str]]]]):
        if not isinstance(value, dict):
            raise TypeError(f"select_options {type(value)} not supported")
        validate_selection_options(value)
        self._select_options = value

    def add_select_option(self, key: str, vals: list[str]):
        self.select_options[key] = {'options': [{'key': val, 'label': val} for val in vals]}

    def add_new_layer(self, label: str, key: str = '', idx: int = -1) -> Layer:
        all_keys = [l.key for l in self.layers]
        if key == '':
            key = re.sub(r'[^a-z]', '_', label.lower())
        t_key = key
        i = 0
        while key in all_keys or key.endswith('_'):
            key = t_key + string.ascii_lowercase[i]
            i += 1
        new_layer = Layer.generate_new_layer(self._sr, key, label)
        if idx < 0 :
            self.layers.append(new_layer)
        else:
            self.layers.insert(idx, new_layer)
        self.update_layer_position()

        return new_layer

    def update_layer_position(self):
        i = 10
        for layer in self.layers:
            if not layer.wf:
                layer.position = i
                i += 10

