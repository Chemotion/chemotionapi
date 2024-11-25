from chemotion_api.labImotion.items.validation.registry import SchemaRegistry

generic_schema = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "chmotion://generic/flow_obj/draft-01",
    "title": "Schema for generic element properties",
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
                        "additionalProperties": False,
                        "required": [
                            "type"
                        ]
                    },
                    "sourceHandle": {},
                    "targetHandle": {}
                },
                "additionalProperties": False,
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
                                "additionalProperties": False,
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
                        "additionalProperties": False,
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
                        "additionalProperties": False,
                        "required": [
                            "x",
                            "y"
                        ]
                    }
                },
                "additionalProperties": False,
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

}

SchemaRegistry.instance().register(generic_schema)
