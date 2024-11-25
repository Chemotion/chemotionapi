from chemotion_api.labImotion.items.validation.registry import SchemaRegistry

generic_schema = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "chmotion://generic/cond_field/draft-01",
    "title": "Schema for generic condition field",
    "type": "object",
    "properties": {
        "id": {
            "type": "string"
        },
        "field": {
            "type": "string"
        },
        "label": {
            "type": "string"
        },
        "layer": {
            "type": "string"
        },
        "value": {
            "type": "string"
        }
    },
    "additionalProperties": False,
    "required": [
        "id",
        "field",
        "label",
        "layer",
        "value"
    ]
}

SchemaRegistry.instance().register(generic_schema)