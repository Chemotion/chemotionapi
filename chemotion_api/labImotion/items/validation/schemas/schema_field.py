from chemotion_api.labImotion.items.options import FieldType
from chemotion_api.labImotion.items.validation.registry import SchemaRegistry

generic_schema = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "chemotion://generic/field/draft-01",
    "title": "Schema for generic field",
    "type": "object",
    "properties": {
        # v4 emits `cols: 1` (and "1"), which the previous exclusiveMinimum/pattern pair rejected —
        # a single-column field is perfectly legal.
        "cols": {
            "oneOf": [
                {
                    "type": "number",
                    "minimum": 1
                },
                {
                    "type": "string",
                    "pattern": "^[1-9]\\d*(\\.\\d+)?$"
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
                    },
                    # ELN v4 / LabIMotion 2.3 additions.
                    "_checksum": {
                        "type": ["string", "null"]
                    },
                    "is_new": {
                        "type": ["boolean", "null"]
                    }
                },
                "additionalProperties": False,
                # `value` is no longer required — v4 omits it on freshly added sub-fields.
                "required": [
                    "id",
                    "type"
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
                    },
                    # ELN v4 / LabIMotion 2.3 additions.
                    "_checksum": {
                        "type": ["string", "null"]
                    },
                    "is_new": {
                        "type": ["boolean", "null"]
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
                "$ref": "chemotion://generic/cond_field/draft-01"
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
        },
        # ELN v4 / LabIMotion 2.3 additions.
        "placeholder": {
            "type": ["string", "null"]
        },
        "ontology": {
            "type": ["object", "array", "string", "null"]
        },
        "hasOwnRow": {
            "type": ["boolean", "string", "null"]
        },
        "value": {
            "type": ["string", "number", "boolean", "object", "array", "null"]
        }
    },
    "additionalProperties": False,
    # sub_fields / text_sub_fields dropped from required: v4 emits them only for the field types
    # that actually have sub-fields (2609 of 2792 fields in the reference instance carry them).
    # Everything below is present on every field observed, so it stays required.
    "required": [
        "type",
        "field",
        "label",
        "default",
        "position"
    ]

}

SchemaRegistry.instance().register(generic_schema)
