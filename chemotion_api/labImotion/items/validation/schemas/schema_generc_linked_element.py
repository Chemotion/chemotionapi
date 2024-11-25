import copy

from chemotion_api.labImotion.items.validation.registry import SchemaRegistry
from chemotion_api.labImotion.items.validation.schemas.abstract_element_schema import generic_element_schema
from chemotion_api.labImotion.items.validation.schemas.schema_properties import properties_schema as properties

generic_schema = copy.deepcopy(generic_element_schema)
generic_schema['$id'] = "chmotion://generic/linked_element/draft-01"
generic_schema['title'] = "Schema for generic linked element"
generic_schema['properties']['properties_template']['$ref'] = 'chmotion://generic/linked_properties/draft-01'
generic_schema['properties']['properties_release']['$ref'] = 'chmotion://generic/linked_properties/draft-01'
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
    },
    "version": {
        "type": ["string", 'null']
    },
    "created_by": {
        "type": ["number", 'null']
    },
    "updated_by": {
        "type": ["number", 'null']
    }
}

generic_props_schema = copy.deepcopy(properties)
generic_props_schema['$id'] = 'chmotion://generic/linked_properties/draft-01'
generic_props_schema['title'] = "Schema for generic linked properties"

generic_props_schema['properties'] |= {
    "version": {
        "type": ["string", 'null']
    }
}

generic_props_schema['required'] = [x for x in generic_props_schema['required'] if x not in ['pkg', 'version', 'layers', 'identifier']]

SchemaRegistry.instance().register(generic_props_schema)
SchemaRegistry.instance().register(generic_schema)
