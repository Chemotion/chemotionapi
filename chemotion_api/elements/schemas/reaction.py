PURIFICATION_OPTIONS = ['Flash-Chromatography', 'TLC', 'HPLC', 'Extraction', 'Distillation', 'Dialysis', 'Filtration',
                        'Sublimation', 'Crystallisation', 'Recrystallisation', 'Precipitation']
STATUS_OPTIONS = ['', 'Planned', 'Running', 'Done', 'Analyses Pending', 'Successful',
 'Not Successful']
schema = {
    "$schema": "chmotion:type/reaction/1.9.3/draft-01/schema#",
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
                                "pattern": "^\d{2}:\d{2}:\d{2}$",
                            },
                            "value": {
                                "type": "string",
                                "pattern": "^[\d\.]+$",
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
