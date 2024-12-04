from chemotion_api.labImotion.items.options import ConditionOperator, LayerColor
from chemotion_api.labImotion.items.validation.registry import SchemaRegistry

generic_schema = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "chmotion://generic/layer/draft-01",
    "title": "Schema for generic layer",
    "type": "object",
    "properties": {
        "wf": {
            "type": "boolean"
        },
        "key": {
            "type": "string",
            "pattern": "^[a-z][a-zA-Z_]{1,20}[a-z]$"
        },
        "cols": {
            "type": "number"
        },
        "color": {
            "type": "string",
            "enum": LayerColor.list()
        },
        "label": {
            "type": "string"
        },
        "style": {
            "type": "string",
            "pattern": "^panel_generic_heading$|^panel_generic_heading_([bui])(?!.*\1)([bui])?(?!.*\1|.*\2)([bui])?$"
        },
        "fields": {
            "type": "array",
            "items": {
                "$ref": "chmotion://generic/field/draft-01"
            }
        },
        "position": {
            "type": "number",
            "minimum": 1
        },
        "timeRecord": {
            "type": "string"
        },
        "cond_fields": {
            "type": "array",
            "items": {
                "$ref": "chmotion://generic/cond_field/draft-01"
            }
        },
        "wf_position": {
            "type": "number",
            "minimum": 0
        },
        "cond_operator": {
            "type": "number",
            "enum": ConditionOperator.list()
        }
    },
    "additionalProperties": False,
    "required": [
        "wf",
        "key",
        "cols",
        "color",
        "label",
        "style",
        "fields",
        "position",
        "timeRecord",
        "wf_position"
    ]
}

SchemaRegistry.instance().register(generic_schema)