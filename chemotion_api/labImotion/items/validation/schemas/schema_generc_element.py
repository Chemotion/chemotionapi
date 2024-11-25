import copy

from chemotion_api.labImotion.items.validation.registry import SchemaRegistry
from chemotion_api.labImotion.items.validation.schemas.abstract_element_schema import generic_element_schema

generic_schema = copy.deepcopy(generic_element_schema)
generic_schema['$id'] = "chmotion://generic/element/draft-01"
generic_schema['title'] = "Schema for generic element"
generic_schema['required'] += ['name', 'icon_name', 'is_generic', 'klass_prefix']

generic_schema['properties'] |= {
    "name": {
        "type": "string"
    },
    "icon_name": {
        "type": "string"
    },
    "klass_prefix": {
        "type": "string"
    },
    "is_generic": {
        "type": "boolean"
    }
}

SchemaRegistry.instance().register(generic_schema)
