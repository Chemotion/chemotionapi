from chemotion_api.labImotion.items.validation.registry import SchemaRegistry

generic_schema = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "chemotion://generic/select_option/draft-01",
    "title": "Schema for generic selection options",
    "type": "object",
    # Option-set names are author-chosen, so key spelling is the server's business — validate the
    # bodies instead of policing the names with a regex real templates do not satisfy.
    "additionalProperties": {
        "type": "object",
        "properties": {
            "options": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "key": {
                            "type": ["string", "number", "boolean", "null"]
                        },
                        "label": {
                            "type": ["string", "number", "boolean", "null"]
                        },
                        # ELN v4 / LabIMotion 2.3 addition.
                        "desc": {
                            "type": ["string", "null"]
                        }
                    },
                    "additionalProperties": False,
                    "required": [
                        "key",
                        "label"
                    ]
                }
            },
            # ELN v4 / LabIMotion 2.3 adds a description alongside `options` on each option set.
            "desc": {
                "type": ["string", "null"]
            }
        },
        "additionalProperties": False,
        "required": [
            "options"
        ]
    },
}

SchemaRegistry.instance().register(generic_schema)
