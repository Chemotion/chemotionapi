import copy

from chemotion_api.labImotion.items.validation.registry import SchemaRegistry
from chemotion_api.labImotion.items.validation.schemas.schema_generc_element import generic_element_schema
from chemotion_api.labImotion.items.validation.schemas.schema_properties import properties_schema as properties

generic_schema = copy.deepcopy(generic_element_schema)
generic_schema['$id'] = 'chmotion://generic/dataset/draft-01'
generic_schema['title'] = "Schema for generic dataset"
generic_schema['properties']['properties_template']['$ref'] = 'chmotion://generic/dataset_properties/draft-01'
generic_schema['properties']['properties_release']['$ref'] = 'chmotion://generic/dataset_properties/draft-01'


generic_schema['properties'] |= {
    "version": {
        "type": ["string", 'null']
    },
    "released_at": {
        "type": ["string", 'null']
    },
    "updated_by": {
        "type": ["number", 'null']
    },
    "ols_term_id": {
        "type": "string"
    }
}

generic_schema['required'] = [x for x in generic_schema['required'] if x not in ['pkg']]
generic_schema['required'].append('ols_term_id')

generic_props_schema = copy.deepcopy(properties)
generic_props_schema['$id'] = 'chmotion://generic/dataset_properties/draft-01'
generic_props_schema['title'] = "Schema for generic dataset properties"
generic_props_schema['required'] = [x for x in generic_props_schema['required'] if x not in ['pkg', 'version', 'identifier', 'uuid', 'klass', 'layers', 'select_options']]

SchemaRegistry.instance().register(generic_schema)
SchemaRegistry.instance().register(generic_props_schema)
