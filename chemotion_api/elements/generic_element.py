from chemotion_api.elements.abstract_element import AbstractElement
from chemotion_api.utils import parse_generic_object_json, clean_generic_object_json


class GenericElement(AbstractElement):

    def _set_json_data(self, json_data: dict):
        super()._set_json_data(json_data)

    def save_url(self) -> str:
        if self.id is not None:
            return "/api/v1/generic_elements/{}".format(self.id)
        return "/api/v1/generic_elements"

    def _parse_properties(self) -> dict:
       data = parse_generic_object_json(self.json_data)
       self._properties_mapping = data['obj_mapping']
       return data['values']

    def _clean_properties_data(self):
        clean_generic_object_json(self.json_data, self.properties, self._properties_mapping)
