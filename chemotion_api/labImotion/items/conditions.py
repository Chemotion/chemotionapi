"""Fixed-shape dict representing a single visibility condition on a field/layer."""

from chemotion_api.utils import FixedDict


class Condition(FixedDict):
    """A single condition entry mapping a referenced field/layer to an expected value."""

    def __init__(self, id: str, field: str, label: str, layer: str, value:str):
        """Build a condition entry.

        :param id: Unique identifier of the condition.
        :param field: Key of the field the condition references.
        :param label: Human-readable label of the referenced field.
        :param layer: Key of the layer the referenced field belongs to.
        :param value: Value the referenced field must hold for the condition to match.
        """
        super().__init__({
            "id": id,
            "field": field,
            "label": label,
            "layer": layer,
            "value": value
        })
