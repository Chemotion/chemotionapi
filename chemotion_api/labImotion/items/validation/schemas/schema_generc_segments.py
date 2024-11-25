import copy

from chemotion_api.labImotion.items.validation.registry import SchemaRegistry
from chemotion_api.labImotion.items.validation.schemas.abstract_element_schema import generic_element_schema
from chemotion_api.labImotion.items.validation.schemas.schema_properties import properties_schema as properties

generic_schema = copy.deepcopy(generic_element_schema)
generic_schema['$id'] = 'chmotion://generic/segment/draft-01'
generic_schema['title'] = "Schema for generic segment"
generic_schema['properties']['properties_template']['$ref'] = 'chmotion://generic/segment_properties/draft-01'
generic_schema['properties']['properties_release']['$ref'] = 'chmotion://generic/segment_properties/draft-01'


generic_schema['required'] += ['element_klass']

generic_schema['properties'] |= {
    "element_klass": {
        "$ref": "chmotion://generic/linked_element/draft-01"
    }
}


generic_props_schema = copy.deepcopy(properties)
generic_props_schema['$id'] = 'chmotion://generic/segment_properties/draft-01'
generic_props_schema['title'] = "Schema for generic segment properties"

SchemaRegistry.instance().register(generic_schema)
SchemaRegistry.instance().register(generic_props_schema)
