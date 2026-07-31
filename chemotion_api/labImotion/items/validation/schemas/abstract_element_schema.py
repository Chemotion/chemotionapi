"""Base JSON schema describing the shared structure of a generic-element klass.

Concrete element, segment and dataset schemas are derived from ``generic_element_schema``.
"""

from typing import Any

generic_element_schema: dict[str, Any] = {
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
            "$ref": "chemotion://generic/properties/draft-01"
        },
        "properties_release": {
            "$ref": "chemotion://generic/properties/draft-01"
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
        # Chemotion >= 3.x attaches a metadata object to every klass.
        "metadata": {
            "type": ["object", "null"]
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
        # created_by/updated_by/created_at/updated_at are audit fields Chemotion 2.x serialized
        # on every klass but 3.x omits; they stay allowed (see properties) but are not required.
    ]
}