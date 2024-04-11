import uuid
from enum import Enum

from chemotion_api.elements.reaction import Reaction
from chemotion_api.elements.sample import Sample
from chemotion_api.elements.abstract_element import AbstractElement


class BodyElements(Enum):
    richtext = 1
    ketcher = 2
    table = 3
    image = 4
    sample = 5
    reaction = 6


COLUMNS_DEFAULT = [
    {
        'headerName': 'a',
        'field': 'a',
        'colId': 'a'
    },
    {
        'headerName': 'b',
        'field': 'b',
        'colId': 'b'
    },
    {
        'headerName': 'c',
        'field': 'c',
        'colId': 'c'
    },
    {
        'headerName': 'd',
        'field': 'd',
        'colId': 'd'
    },
    {
        'headerName': 'e',
        'field': 'e',
        'colId': 'e'
    },
    {
        'headerName': 'f',
        'field': 'f',
        'colId': 'f'
    }
]


class ResearchPlan(AbstractElement):

    def _set_json_data(self, json_data):
        super()._set_json_data(json_data)

    def _parse_body_element(self, elem: dict):
        value = ''
        if elem.get('type') == 'richtext':
            value = self._parse_text(elem.get('value'))
        if elem.get('type') == 'ketcher':
            value = self._parse_ketcher(elem.get('value'))
        elif elem.get('type') == 'table':
            value = self._parse_table(elem.get('value'))
        elif elem.get('type') == 'image':
            value = self._parse_image(elem.get('value'))
        elif elem.get('type') == 'sample':
            value = self._parse_sample(elem.get('value'))
        elif elem.get('type') == 'reaction':
            value = self._parse_reaction(elem.get('value'))

        return {
            'id': elem.get('id'),
            'type': elem.get('type'),
            'value': value
        }

    def _parse_sample(self, value):
        if value is None or value.get('sample_id') is None:
            return None
        return Sample(self._generic_segments,
                      self._session,
                      id=value.get('sample_id'), element_type='sample')

    def _parse_reaction(self, value):
        if value is None or value.get('reaction_id') is None:
            return None
        return Reaction(self._generic_segments,
                        self._session,
                        id=value.get('reaction_id'), element_type='reaction')

    def _parse_text(self, value):
        if isinstance(value, str):
            return value
        return value.get('ops')

    def _parse_image(self, value):
        if value is None: return None
        try:
            res = self.attachments.load_attachment(identifier=value.get('public_name'))
        except ValueError:
            return None
        return res

    def _parse_table(self, value):
        return value

    def _parse_ketcher(self, value):
        return value

    def _parse_properties(self) -> dict:
        body = self.json_data.get('body')
        self.body = [self._parse_body_element(x) for x in body]
        return {
            'body': self.body
        }

    def _clean_properties_data(self, serialize_data: dict | None = None) -> dict:
        self.json_data['body'] = []
        for elem in self.body:
            self.json_data['body'].append(self._reparse_body_element(elem))

        return self.json_data

    def save(self):
        return super().save()

    def add_richtext(self, text: str) -> dict:
        body_obj = self._add_new_element(BodyElements.richtext)
        body_obj['value'] = [{'insert': text}]
        return body_obj

    def add_image(self, image_path: str) -> dict:
        file_obj = self.attachments.add_file(image_path)
        body_obj = self._add_new_element(BodyElements.image)

        body_obj['value'] = file_obj
        return body_obj

    def add_table(self) -> dict:
        body_obj = self._add_new_element(BodyElements.table)
        return body_obj

    def _add_new_element(self, element_type: BodyElements):
        body_elem = {
            'id': uuid.uuid4().__str__(),
            'type': element_type.name,
            'value': self._default_body_element(element_type)
        }

        new_element = self._parse_body_element(body_elem)
        self.body.append(new_element)
        return new_element

    def _reparse_body_element(self, elem: dict):
        value = ''
        if elem.get('type') == 'richtext':
            value = self._reparse_text(elem.get('value'))
        if elem.get('type') == 'ketcher':
            value = self._reparse_ketcher(elem.get('value'))
        elif elem.get('type') == 'table':
            value = self._reparse_table(elem.get('value'))
        elif elem.get('type') == 'image':
            value = self._reparse_image(elem.get('value'))
        elif elem.get('type') == 'sample':
            value = self._reparse_sample(elem.get('value'))
        elif elem.get('type') == 'reaction':
            value = self._reparse_reaction(elem.get('value'))

        elem_data = {
            'id': elem.get('id'),
            'type': elem.get('type'),
            'value': value
        }

        if elem.get('type') == 'richtext':
            elem_data['title'] = 'Text'
        return elem_data

    def _reparse_sample(self, value: Sample | None):
        if value is None:
            return {'sample_id': None}
        return {'sample_id': value.id}

    def _reparse_reaction(self, value: Reaction | None):
        if value is None:
            return {'reaction_id': None}
        return {'reaction_id': value.id}

    def _reparse_text(self, value):
        return {'ops': value}

    def _reparse_image(self, value):
        return {
            'public_name': value['identifier'],
            'file_name': value['filename']
        }

    def _reparse_table(self, value):
        return value

    def _reparse_ketcher(self, value):
        return value

    @staticmethod
    def _default_body_element(element_type: BodyElements) -> dict:
        if element_type == BodyElements.richtext:
            return {'ops': [{'insert': ''}]}
        if element_type == BodyElements.ketcher:
            return {
                'svg_file': None,
                'thumb_svg': None
            }
        if element_type == BodyElements.table:
            return {
                'columns': COLUMNS_DEFAULT,
                'rows': [
                    {'a': '', 'b': '', 'c': '', 'd': '', 'e': '', 'f': ''},
                    {'a': '', 'b': '', 'c': '', 'd': '', 'e': '', 'f': ''},
                    {'a': '', 'b': '', 'c': '', 'd': '', 'e': '', 'f': ''}
                ]

            }
        if element_type == BodyElements.image:
            return {
                'file_name': None,
                'public_name': None,
                'zoom': None
            }
        if element_type == BodyElements.sample:
            return {
                'sample_id': None
            }
        if element_type == BodyElements.reaction:
            return {
                'reaction_id': None
            }
        raise ValueError(f"{element_type} not exists!")
