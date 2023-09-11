from chemotion_api.elements.abstract_element import AbstractElement
from chemotion_api.generic_segments import GenericSegments


class ResearchPlan(AbstractElement):

    def _set_json_data(self, json_data):
        super()._set_json_data(json_data)

    def _parse_properties(self) -> dict:
        return {}
