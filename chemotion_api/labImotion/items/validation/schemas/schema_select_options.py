from chemotion_api.labImotion.items.validation.registry import SchemaRegistry

generic_schema = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "chmotion://generic/select_option/draft-01",
    "title": "Schema for generic selection options",
    "type": "object",
    "patternProperties": {
        "^[a-z][a-zA-Z_]{1,10}[a-z]$": {
            "type": "object",
            "properties": {
                "options": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {
                                "type": "string"
                            },
                            "label": {
                                "type": "string"
                            }
                        },
                        "additionalProperties": False,
                        "required": [
                            "key",
                            "label"
                        ]
                    }
                }
            },
            "additionalProperties": False,
            "required": [
                "options"
            ]
        }
    },
    "additionalProperties": False,
}

SchemaRegistry.instance().register(generic_schema)
