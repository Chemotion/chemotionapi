from chemotion_api.utils import FixedDict


class Condition(FixedDict):
    def __init__(self, id: str, field: str, label: str, layer: str, value:str):
        super().__init__({
            "id": id,
            "field": field,
            "label": label,
            "layer": layer,
            "value": value
        })
