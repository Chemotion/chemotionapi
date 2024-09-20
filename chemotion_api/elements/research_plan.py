import uuid
from enum import Enum
from string import ascii_lowercase
from typing_extensions import Self

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


class Table(dict):
    """
    Table is a dict subclass. It contains additional table management methods

    Usage::

    >>> from chemotion_api import Instance
    >>> from chemotion_api.collection import Collection
    >>> import logging
    >>> try:
    >>>     instance = Instance('http(d)://xxx.xxx.xxx').test_connection().login('<USER>', "<PASSWORD>")
    >>> except ConnectionError as e:
    >>>     logging.error(f"A connection to Chemotion ({instance.host_url}) cannot be established")
    >>> # Get the reaction with ID 1
    >>> plan = instance.get_research_plan(1)
    >>> # Add a new Table
    >>> table = plan.add_table()
    >>> # Add a new column Name, age
    >>> name_col_id, age_col_id = table.add_columns("Name", "Age")
    >>> table.add_columns("Is Developer")
    >>> table.add_row('Mr. X', False, **{age_col_id: 40}).add_row('Mr. Y')
    >>> table.set_entry(1, age_col_id, 30)
    >>> age_average = sum(table.get_column(age_col_id)) / len(table)
    >>> print(f'Average age {age_average}')
    >>> plan.save()
    >>> plan_test = instance.get_research_plan(plan.id)
    >>> table = plan_test.body[0]['value']
    >>> age_average = sum(table.get_column(age_col_id)) / len(table)
    >>> assert age_average == 35
    >>> assert table.get_column(name_col_id) == ['Mr. X', 'Mr. Y']
    """

    def __init__(self, columns, rows):
        super().__init__(columns=columns, rows=rows)

    def _get_col_id(self):
        for l in ascii_lowercase:
            if len([x for x in self['columns'] if x['colId'] == l]) == 0:
                return l

    def column_id_by_label(self, label: str) -> str:
        """
        Finds a column ID of a column with a give label

        :param label: Label of the column

        :return: Column id
        """
        return self.column_ids_by_labels(label)[0]

    def column_ids_by_labels(self, *labels: str) -> list[str]:
        """
        Finds all column IDs of columns with a given labels

        :param labels: Labels of the column

        :return: Column id
        """

        for l in labels:
            yield next(x['field'] for x in self['columns'] if x['headerName'] == l)



    def add_columns(self, *labels: str) -> list[str]:
        """
        Adds one or more  columns to the table. It adds a column for
        each label give as an argument

        :param labels: labels of columns to be added
        :return: list of the column IDs
        """

        ids = []
        for label in labels:
            id_letter = self._get_col_id()
            self['columns'].append({
                'headerName': label,
                'field': id_letter,
                'colId': id_letter
            })
            ids.append(id_letter)
            for row in self['rows']:
                if id_letter not in row:
                    row[id_letter] = []

        return ids

    def add_row(self, *entries, **placed_entries) -> Self:
        """
        Adds row to the table. You can create the table empty
        or filled. To fill the fields, the values can be entered
        as named arguments or as arguments without a keyword.
        For named arguments, you must use the column id

        :param entries: non-keyworded arguments entries
        :param placed_entries:  keyworded arguments entries
        :return: Self
        """

        new_row = {}
        entries = list(entries)
        for idx, colId in enumerate(x['field'] for x in self['columns']):
            if colId in placed_entries:
                new_row[colId] = placed_entries[colId]
            elif len(entries) != 0:
                new_row[colId] = entries.pop(0)
            else:
                new_row[colId] = ''

        self['rows'].append(new_row)
        return self

    def set_entry(self, row: int, column_id: str, value: any) -> Self:
        """
        Sets an entry to the table

        :param row: rwo idx starts with 0
        :param column_id: the column ID
        :param value: of the Entry

        :return self
        """

        self['rows'][row][column_id] = value
        return self

    def get_column(self, column_id: str) -> list:
        """
        Adds an entry to the table

        :param column_id: the column ID
        :return: a list of all values of one column
        """

        result = []
        for row in self['rows']:
            result.append(row[column_id])
        return result

    def __len__(self):
        return len(self['rows'])


class ResearchPlan(AbstractElement):
    """
    A chemotion Research Plan object.
    It extends the :class:`chemotion_api.elements.abstract_element.AbstractElement`

    Usage::

    >>> from chemotion_api import Instance
    >>> from chemotion_api.collection import Collection
    >>> from chemotion_api.elements.research_plan import Table
    >>> import logging
    >>> try:
    >>>     instance = Instance('http(d)://xxx.xxx.xxx').test_connection().login('<USER>', "<PASSWORD>")
    >>> except ConnectionError as e:
    >>>     logging.error(f"A connection to Chemotion ({instance.host_url}) cannot be established")
    >>> # Get the reaction with ID 1
    >>> plan = instance.get_research_plan(1)
    >>> # Add a table
    >>> table: Table = plan.add_table()
    >>> table.add_columns('Name')
    >>> table.add_row('Martin')
    >>> # Add a simple Text
    >>> plan.add_richtext("Hallo")
    >>> plan.save()
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @property
    def body(self):
        """
        Body is list which contains the same values as the Properties.
        Each entry has a type and a value filed.
        The type can be one of:  richtext, ketcher, table, image, sample or reaction

        :return: List of body entries
        """
        return self.properties['body']

    def _set_json_data(self, json_data):
        super()._set_json_data(json_data)

    def _parse_body_element(self, elem: dict):
        value = ''
        if elem.get('type') == 'richtext':
            value = self._parse_text(elem.get('value'))
        elif elem.get('type') == 'ketcher':
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
        return Table(**value)

    def _parse_ketcher(self, value):
        return value

    def _parse_properties(self) -> dict:
        body = self.json_data.get('body')
        return {
            'body':  [self._parse_body_element(x) for x in body]
        }

    def _clean_properties_data(self, serialize_data: dict | None = None) -> dict:
        self.json_data['body'] = []
        for elem in self.body:
            self.json_data['body'].append(self._reparse_body_element(elem))

        return self.json_data

    def add_richtext(self, text: str) -> dict:
        """
        Adds a text block to the Research plan

        :param text: to be added

        :return: body container
        """
        body_obj = self._add_new_element(BodyElements.richtext)
        body_obj['value'] = [{'insert': text}]
        return body_obj

    def add_image(self, image_path: str) -> dict:
        """
        Adds an image to the Research plan

        :param image_path: file path to image

        :return: body container
        """

        if not image_path.lower().endswith(('.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.gif')):
            raise ValueError('File is not a image!')
        file_obj = self.attachments.add_file(image_path)
        file_obj['is_image_field'] = True
        file_obj['ancestor'] = None
        body_obj = self._add_new_element(BodyElements.image)

        body_obj['value'] = file_obj
        return body_obj

    def add_table(self) -> Table:
        """
        Adds a new table to the Research plan

        :return: Table object
        """

        body_obj = self._add_new_element(BodyElements.table)
        return body_obj['value']

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
                'columns': [],
                'rows': []

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
