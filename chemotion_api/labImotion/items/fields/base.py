import copy
from enum import Enum

from chemotion_api.labImotion.items.condition_handler import ConditionHandler
from chemotion_api.labImotion.items.fields.abstract_fields import _report_unknown_unit as _report_unknown_value
from chemotion_api.labImotion.items.options import FieldType
from chemotion_api.labImotion.ontology import clean_term, get_term
from chemotion_api.labImotion.structure import StructureRegistry

from chemotion_api.labImotion.utils import all_instances_of, ChemotionSerializable


class BaseField(ChemotionSerializable, ConditionHandler):
    _default_required_fields = ["field_type", "field", "required", "label", "default", "position", "sub_fields",
                                "text_sub_fields"]
    _default_optional_fields = ["cols", "cond_fields", "cond_operator", "ontology"]
    required_fields = []
    optional_fields = []
    field_type = FieldType.TEXT
    mapping = {"field_type": "type"}

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        ConditionHandler.__init__(self, sr)
        self._field = None
        self._label = None
        self._json_data = json_data
        self._default = ""
        self._required = False
        self._position = 1
        self._sr = sr
        self._layer_key = layer_key
        self._cols = None
        self._ontology: dict | None = None

    def _parse_json(self):
        """Populate this field from its server payload.

        Assignment goes through the property setters, which validate — that is what we want for
        user code. But it means *parsing* inherits that strictness, and a klass the server is
        perfectly happy with then becomes unreadable here: an unmodelled unit, a select field
        pointing at an option set the klass no longer defines, a formula naming a missing layer.
        Klasses authored by older chem-generic-ui versions do all three.

        So a rejected value is kept verbatim on the backing attribute instead, and reported once.
        Degrading loses a validation guarantee we never had over someone else's data; raising
        loses the whole element.
        """
        for key, value in self._json_data.items():
            key = self.mapping.get(key, key)
            if not hasattr(self, key):
                continue
            try:
                setattr(self, key, value)
            except (ValueError, TypeError, KeyError) as e:
                private = f'_{key}'
                if hasattr(self, private):
                    object.__setattr__(self, private, value)
                _report_unknown_value(
                    f"{type(self).__name__}.{key} rejected the server's value {value!r} "
                    f"({type(e).__name__}: {e})")

    @property
    def layer_key(self) -> str:
        return self._layer_key

    def to_dict(self) -> dict:
        self._json_data = {}
        for key in self._default_required_fields + self.required_fields:
            json_key = self.mapping.get(key, key)
            value = getattr(self, key)
            if isinstance(value, Enum):
                value = value.value
            if all_instances_of(value, ChemotionSerializable):
                self._json_data[json_key] = [x.to_dict() for x in value]
            else:
                self._json_data[json_key] = value

        for key in self._default_optional_fields + self.optional_fields:
            json_key = self.mapping.get(key, key)
            value = getattr(self, key, None)
            if value is not None:
                if isinstance(value, Enum):
                    value = value.value
                self._json_data[json_key] = value

        return self._json_data

    @property
    def cols(self) -> int:
        return self._cols

    @cols.setter
    def cols(self, value: int):
        if not isinstance(value, int):
            try:
                value = int(value)
            except ValueError:
                raise TypeError(f"Required {type(value)} not supported")
        self._cols = value

    @property
    def ontology(self) -> dict | None:
        """
        The ontology term linked to the field (as set in the template designer), or None. It can be set to a
        term dict (e.g. from :func:`chemotion_api.labImotion.ontology.search_terms`), to a term ID
        ('CHMO:0000593', 'CHMO_0000593' or the IRI), which is looked up in the TIB Terminology Service, or to
        None to remove the link.
        """
        return self._ontology

    @ontology.setter
    def ontology(self, value: dict | str | None):
        if value is None or value == {}:
            self._ontology = None
        elif isinstance(value, str):
            self._ontology = get_term(value)
        else:
            self._ontology = clean_term(value)

    @property
    def default(self):
        return self._default

    @default.setter
    def default(self, value: str):
        if not isinstance(value, str):
            raise TypeError(f"default {type(value)} not supported")
        self._default = value

    @property
    def field(self) -> str | None:
        return self._field

    @field.setter
    def field(self, value: str):
        if not isinstance(value, str):
            raise TypeError(f"Required {type(value)} not supported")
        if self.field is None:
            self._field = value
        else:
            raise ValueError("Field is already set and cannot be changed")

    @property
    def label(self) -> str:
        return self._label

    @label.setter
    def label(self, value: str):
        if not isinstance(value, str):
            raise TypeError(f"Required {type(value)} not supported")
        self._label = value

    @property
    def position(self) -> int:
        return self._position

    @position.setter
    def position(self, value: int):
        if not isinstance(value, int):
            raise TypeError(f"Required {type(value)} not supported")
        self._position = value

    @property
    def required(self) -> bool:
        return self._required

    @required.setter
    def required(self, value: bool):
        if not isinstance(value, bool):
            raise TypeError(f"required {type(value)} not supported")
        self._required = value

    @property
    def sub_fields(self) -> list:
        return []

    @sub_fields.setter
    def sub_fields(self, value: list):
        pass

    @property
    def text_sub_fields(self) -> list[dict]:
        return []

    @text_sub_fields.setter
    def text_sub_fields(self, value: list[dict]):
        pass
