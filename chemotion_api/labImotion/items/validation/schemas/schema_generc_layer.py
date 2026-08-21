from chemotion_api.labImotion.items.options import ConditionOperator, LayerColor
from chemotion_api.labImotion.items.validation.registry import SchemaRegistry

generic_schema = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "chemotion://generic/layer/draft-01",
    "title": "Schema for generic layer",
    "type": "object",
    "properties": {
        "wf": {
            "type": "boolean"
        },
        # No pattern: real v4 templates use keys the old
        # `^[a-z][a-zA-Z_]{1,20}[a-z]$` rejected — trailing digits ('general_procparamv2'),
        # spaces ('printing parameters'). Layer key spelling is the server's business.
        "key": {
            "type": "string"
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
                "$ref": "chemotion://generic/field/draft-01"
            }
        },
        # v4 emits position 0.
        "position": {
            "type": "number",
            "minimum": 0
        },
        "timeRecord": {
            "type": "string"
        },
        "cond_fields": {
            "type": "array",
            "items": {
                "$ref": "chemotion://generic/cond_field/draft-01"
            }
        },
        "wf_position": {
            "type": "number",
            "minimum": 0
        },
        "cond_operator": {
            "type": "number",
            "enum": ConditionOperator.list()
        },
        # ELN v4 / LabIMotion 2.3 additions.
        "condition": {
            "type": ["object", "string", "null"]
        },
        "desc": {
            "type": ["string", "null"]
        },
        "layer": {
            "type": ["string", "object", "null"]
        }
    },
    "additionalProperties": False,
    # Dropped from required because v4 genuinely omits them on some layers (counts from the
    # reference instance, 534 layers): color 434, style 434, wf 337, wf_position 472,
    # timeRecord only 86. The rest are present on every layer observed.
    "required": [
        "key",
        "cols",
        "fields",
        "label",
        "position"
    ]
}

SchemaRegistry.instance().register(generic_schema)