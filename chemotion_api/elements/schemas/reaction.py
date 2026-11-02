"""JSON schema (and option lists) describing the validatable ``properties`` of a Reaction element."""

PURIFICATION_OPTIONS = ['Flash-Chromatography', 'TLC', 'HPLC', 'Extraction', 'Distillation', 'Dialysis', 'Filtration',
                        'Sublimation', 'Crystallisation', 'Recrystallisation', 'Precipitation']
STATUS_OPTIONS = ['', 'Planned', 'Running', 'Done', 'Analyses Pending', 'Successful',
 'Not Successful']
schema = {
    # `$schema` must name the JSON Schema dialect, not the document. This previously held
    # "chemotion:type/reaction/1.9.3/draft-01/schema#", which both misused the keyword and pinned
    # an ELN version (1.9.3) that no longer bears any relation to the server this client targets.
    # The document's own identity belongs in `$id`, without a version segment: this schema is
    # bundled with the client and versioned by the client's release, not by the server's.
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "chemotion://type/reaction/draft-01",
    "title": "Reaction Properties",
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "The reaction's name"
        },
        "conditions": {
            "type": "string",
            "description": "The reaction's conditions"
        },
        "description": {
            "type": "object",
            "description": "The reaction's description (Quill.js)",
            "properties": {
                "ops": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "insert": {
                                "type": "string"
                            }
                        }
                    }

                }
            }
        },
        "observation": {
            "type": "object",
            "description": "Important observations (Quill.js)",
            "properties": {
                "ops": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "insert": {
                                "type": "string"
                            }
                        }
                    }

                }
            }
        },
        "temperature": {
            "type": "object",
            "description": "A temperature profile of a chemical reaction",
            "properties": {
                "data": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "time": {
                                "type": "string",
                                "pattern": r"^\d{2}:\d{2}:\d{2}$",
                            },
                            "value": {
                                "type": "string",
                                "pattern": r"^-?(\d+\.?\d*|\.\d+)$",
                            }
                        },
                        "required": ["value", "time"]
                    }
                },
                "userText": {
                    "type": "string"
                },
                "valueUnit": {
                    "type": "string",
                    "enum": ["°C", "°F", "K"],
                }
            },
            "required": ["data", "userText", "valueUnit"]
        },
        "status": {
            "type": "string",
            "enum": ['', 'Planned', 'Running', 'Done', 'Analyses Pending', 'Successful',
                     'Not Successful']
        },
        "purification": {
            "type": ["array", "string"],
            "items": {
                "type": "string",
                "enum": PURIFICATION_OPTIONS
            }
        },
        "duration": {
            "type": "string"
        }
    },
    "required": ["name", "description", "observation",
                 "conditions", "temperature", "status",
                 "purification", "duration"]
}
