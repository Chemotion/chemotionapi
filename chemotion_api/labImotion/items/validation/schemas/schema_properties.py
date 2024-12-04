from chemotion_api.labImotion.items.validation.registry import SchemaRegistry

properties_schema = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "chmotion://generic/properties/draft-01",
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
                            "type": "string"
                        },
                        "current_revision": {
                            "type": ["string", "number"]
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
            "patternProperties": {
                "^[a-z][a-zA-Z_]{1,20}[a-z]$": {
                    "$ref": "chmotion://generic/layer/draft-01"
                }
            },
            "additionalProperties": False
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
                        "required": [
                            "id",
                            "data",
                            "type",
                            "width",
                            "height",
                            "position",
                            "positionAbsolute"
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
            "$ref": "chmotion://generic/select_option/draft-01"
        },
        "eln": {
            "type": "object",
            "properties": {
                "version": {
                    "type": "string"
                },
                "base_revision": {
                    "type": "string"
                },
                "current_revision": {
                    "type": "number"
                }
            },
            "required": [
                "version",
                "base_revision",
                "current_revision"
            ]
        }
    },
    "additionalProperties": False,
    "required": [
        "pkg",
        "uuid",
        "klass",
        "layers",
        "select_options"
    ]
}

SchemaRegistry.instance().register(properties_schema)