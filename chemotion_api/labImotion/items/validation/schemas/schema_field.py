from chemotion_api.labImotion.items.options import FieldType
from chemotion_api.labImotion.items.validation.registry import SchemaRegistry

generic_schema = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "chmotion://generic/field/draft-01",
    "title": "Schema for generic field",
    "type": "object",
    "properties": {
        "cols": {
            "oneOf": [
                {
                    "type": "number",
                    "exclusiveMinimum": 1
                },
                {
                    "type": "string",
                    "pattern": "^[2-9]\\d*(\\.\\d+)?$|^1\\.\\d+$"
                }
            ]
        },
        "type": {
            "type": "string",
            "enum": FieldType.list()
        },
        "field": {
            "type": "string"
        },
        "label": {
            "type": "string"
        },
        "default": {
            "type": "string"
        },
        "position": {
            "type": "number",
            "minimum": 0
        },
        "required": {
            "type": "boolean"
        },
        "readonly": {
            "type": "boolean"
        },
        "canAdjust": {
            "type": "boolean"
        },
        "description": {
            "type": "string"
        },
        "sub_fields": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string"
                    },
                    "type": {
                        "type": "string"
                    },
                    "value": {
                        "type": "string"
                    },
                    "value_system": {
                        "type": "string"
                    },
                    "option_layers": {
                        "type": "string"
                    },
                    "col_name": {
                        "type": "string"
                    }
                },
                "additionalProperties": False,
                "required": [
                    "id",
                    "type",
                    "value"
                ]
            }
        },
        "text_sub_fields": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string"
                    },
                    "field": {
                        "type": "string"
                    },
                    "layer": {
                        "type": "string"
                    },
                    "separator": {
                        "type": "string"
                    }
                },
                "additionalProperties": False,
                "required": [
                    "id",
                    "field",
                    "layer",
                    "separator"
                ]
            }
        },
        "cond_fields": {
            "type": "array",
            "item": {
                "$ref": "chmotion://generic/cond_field/draft-01"
            }
        },
        "cond_operator": {
            "type": "number"
        },
        "decimal": {
            "type": "string"
        },
        "formula": {
            "type": "string"
        },
        "option_layers": {
            "type": "string"
        },
        "value_system": {
            "type": "string"
        }
    },
    "additionalProperties": False,
    "required": [
        "type",
        "field",
        "label",
        "default",
        "position",
        "sub_fields",
        "text_sub_fields"
    ]

}

SchemaRegistry.instance().register(generic_schema)
