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
        "metadata": {
            "type": ["object", "null"]
        },
        # Added by LabIMotion 2.3.4 (shipped in ELN v4.0.1): the klass's own `metadata` follows
        # every save, drafts included, so the gem exposes the metadata the *release* was cut with
        # separately. It is present only where the endpoint preloaded the revision map, so it is
        # declared but not required — a klass payload without it is still valid.
        #
        # Declared explicitly rather than by relaxing `additionalProperties`. That flag is
        # deliberate: it is what turns a server-side field we have never seen into a loud test
        # failure instead of silence. The cost is a re-sync on each LabIMotion bump, which is the
        # same discipline the units mirror already needs.
        "metadata_release": {
            "type": ["object", "null"]
        },
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
        # created_by / updated_by are deliberately NOT required: ELN v4 stopped exposing them on
        # klass entities. Requiring a field the server no longer sends would reject every klass.
        "created_at",
        "updated_at",
    ]
}