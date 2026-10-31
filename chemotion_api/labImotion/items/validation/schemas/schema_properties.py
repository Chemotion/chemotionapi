from chemotion_api.labImotion.items.validation.registry import SchemaRegistry

properties_schema = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "chemotion://generic/properties/draft-01",
    "title": "Schema for generic element properties",
    "type": "object",
    "properties": {
        "pkg": {
            "type": "object",
            "properties": {
                "eln": {
                    "type": "object",
                    "properties": {
                        "version": {
                            "type": ["string", "number"]
                        },
                        "base_revision": {
                            "type": ["string", "number", "null"]
                        },
                        "current_revision": {
                            "type": ["string", "number", "null"]
                        }
                    },
                    "required": [
                        "version",
                        "base_revision",
                        "current_revision"
                    ]
                },
                "name": {
                    "type": "string"
                },
                "version": {
                    "type": "string"
                },
                "labimotion": {
                    "type": "string"
                }
            },
            "required": [
                "eln",
                "labimotion"
            ]
        },
        "uuid": {
            "type": "string"
        },
        "klass": {
            "type": "string"
        },
        "layers": {
            "type": "object",
            # Layer keys are whatever the template author typed — real v4 templates carry keys with
            # spaces ('printing parameters') and digits ('liste1'), which the previous
            # `^[a-z][a-zA-Z_]{1,20}[a-z]$` pattern rejected outright. Validate the layer bodies and
            # leave key spelling to the server.
            "additionalProperties": {
                "$ref": "chemotion://generic/layer/draft-01"
            }
        },
        "version": {
            "type": "string"
        },
        "flowObject": {
            "type": "object",
            "properties": {
                "edges": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {
                                "type": "string"
                            },
                            "label": {
                                "type": "string"
                            },
                            "source": {
                                "type": "string"
                            },
                            "target": {
                                "type": "string"
                            },
                            "animated": {
                                "type": "boolean"
                            },
                            "markerEnd": {
                                "type": "object",
                                "properties": {
                                    "type": {
                                        "type": "string"
                                    }
                                },
                                "required": [
                                    "type"
                                ]
                            },
                            "sourceHandle": {},
                            "targetHandle": {}
                        },
                        "required": [
                            "id",
                            "label",
                            "source",
                            "target",
                            "animated",
                            "markerEnd",
                            "sourceHandle",
                            "targetHandle"
                        ]
                    }
                },
                "nodes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {
                                "type": "string"
                            },
                            "data": {
                                "type": "object",
                                "properties": {
                                    "label": {
                                        "type": "string"
                                    },
                                    "lKey": {
                                        "type": "string"
                                    },
                                    "layer": {
                                        "type": "object",
                                        "properties": {
                                            "wf": {
                                                "type": "boolean"
                                            },
                                            "key": {
                                                "type": "string"
                                            },
                                            "cols": {
                                                "type": "number"
                                            },
                                            "color": {
                                                "type": "string"
                                            },
                                            "label": {
                                                "type": "string"
                                            },
                                            "style": {
                                                "type": "string"
                                            },
                                            "fields": {
                                                "type": "array",
                                                "items": {}
                                            },
                                            "position": {
                                                "type": "number"
                                            },
                                            "timeRecord": {
                                                "type": "string"
                                            },
                                            "wf_position": {
                                                "type": "number"
                                            }
                                        },
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
                                },
                                "required": []
                            },
                            "type": {
                                "type": "string"
                            },
                            "width": {
                                "type": "number"
                            },
                            "height": {
                                "type": "number"
                            },
                            "position": {
                                "type": "object",
                                "properties": {
                                    "x": {
                                        "type": "number"
                                    },
                                    "y": {
                                        "type": "number"
                                    }
                                },
                                "required": [
                                    "x",
                                    "y"
                                ]
                            },
                            "deletable": {
                                "type": "boolean"
                            },
                            "positionAbsolute": {
                                "type": "object",
                                "properties": {
                                    "x": {
                                        "type": "number"
                                    },
                                    "y": {
                                        "type": "number"
                                    }
                                },
                                "required": [
                                    "x",
                                    "y"
                                ]
                            }
                        },
                        # Same as in schema_flow_obj: width/height/positionAbsolute are React Flow
                        # rendering hints that v4 does not persist, so they cannot be required.
                        "required": [
                            "id",
                            "data",
                            "type",
                            "position"
                        ]
                    }
                },
                "viewport": {
                    "type": "object",
                    "properties": {
                        "x": {
                            "type": "number"
                        },
                        "y": {
                            "type": "number"
                        },
                        "zoom": {
                            "type": "number"
                        }
                    },
                    "required": [
                        "x",
                        "y",
                        "zoom"
                    ]
                }
            },
            "required": [
                "edges",
                "nodes",
                "viewport"
            ]
        },
        "identifier": {
            "type": ["string", "null"]
        },
        "select_options": {
            "$ref": "chemotion://generic/select_option/draft-01"
        },
        "eln": {
            "type": "object",
            "properties": {
                "version": {
                    "type": ["string", "null"]
                },
                "base_revision": {
                    "type": ["string", "null"]
                },
                # Declared "number" before, but the server sends a git SHA — and sends it with a
                # trailing newline it never strips ('75f3702e…59\n'). Worth reporting upstream.
                "current_revision": {
                    "type": ["string", "number", "null"]
                },
                "describe_tag": {
                    "type": ["string", "null"]
                },
                "branch": {
                    "type": ["string", "null"]
                }
            },
            "required": [
                "version"
            ]
        },
        # ELN v4 / LabIMotion 2.3 additions.
        "labimotion": {
            "type": ["string", "null"]
        },
        "released_at": {
            "type": ["string", "null"]
        }
    },
    "additionalProperties": False,
    # `pkg` only: v4 omits it on 31 of 107 property templates in the reference instance.
    # layers/select_options are present on all of them, so they stay required.
    "required": [
        "uuid",
        "klass",
        "layers",
        "select_options"
    ]
}

SchemaRegistry.instance().register(properties_schema)