from chemotion_api.labImotion.items.validation.registry import SchemaRegistry

generic_schema = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "chemotion://generic/cond_field/draft-01",
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
        # v4 sends numbers and booleans here too, not just strings.
        "value": {
            "type": ["string", "number", "boolean", "null"]
        },
        # ELN v4 / LabIMotion 2.3 addition.
        "desc": {
            "type": ["string", "null"]
        }
    },
    "additionalProperties": False,
    # `label` only: v4 sends it on just 32 of 306 condition fields in the reference instance.
    # layer/value are present on all of them, so they stay required.
    "required": [
        "id",
        "field",
        "layer",
        "value"
    ]
}

SchemaRegistry.instance().register(generic_schema)