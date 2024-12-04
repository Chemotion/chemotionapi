generic_element_schema = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "id": {
            "type": "number"
        },
        "uuid": {
            "type": ["string", "null"]
        },
        "label": {
            "type": "string"
        },
        "desc": {
            "type": "string"
        },
        "properties_template": {
            "$ref": "chmotion://generic/properties/draft-01"
        },
        "properties_release": {
            "$ref": "chmotion://generic/properties/draft-01"
        },
        "is_active": {
            "type": "boolean"
        },
        "version": {
            "type": ["null", "string"]
        },
        "place": {
            "type": "number"
        },
        "released_at": {
            "type": "string"
        },
        "identifier": {
            "type": ["string", "null"]
        },
        "sync_time": {},
        "created_by": {
            "type": "number"
        },
        "updated_by": {
            "type": "number"
        },
        "created_at": {
            "type": "string"
        },
        "updated_at": {
            "type": "string"
        },
    },
    "additionalProperties": False,
    "required": [
        "id",
        "uuid",
        "label",
        "desc",
        "properties_template",
        "properties_release",
        "is_active",
        "version",
        "place",
        "released_at",
        "identifier",
        "sync_time",
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
    ]
}