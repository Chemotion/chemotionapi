import uuid
from enum import Enum
from string import ascii_lowercase
from typing import Optional, Literal, Generator

from rdflib.plugins.sparql.results.tsvresults import NONE_VALUE
from typing_extensions import Self

from chemotion_api.elements.reaction import Reaction
from chemotion_api.elements.sample import Sample
from chemotion_api.elements.abstract_element import AbstractElement


class BodyElements(Enum):
    richtext = 'richtext'
    ketcher = 'ketcher'
    table = 'table'
    image = 'image'
    sample = 'sample'
    reaction = 'reaction'


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

    def __init__(self, id: str, value: dict, start_collapsed: bool = False):
        value = {
            'columns': value.get('columns', []),
            'rows': value.get('rows', [])
        }
        super().__init__(value=value, type=BodyElements.table.value, id=id, startCollapsed=start_collapsed)

    @property
    def id(self) -> str:
        return self['id']

    def _get_col_id(self):
        for l in ascii_lowercase:
            if len([x for x in self['value']['columns'] if x['colId'] == l]) == 0:
                return l

    def column_id_by_label(self, label: str) -> str:
        """
        Finds a column ID of a column with a give label

        :param label: Label of the column

        :return: Column id
        """
        return next(self.column_ids_by_labels(label))

    def column_ids_by_labels(self, *labels: str) -> Generator[str, None, None]:
        """
        Finds all column IDs of columns with a given labels

        :param labels: Labels of the column

        :return: Column id
        """

        for l in labels:
            yield next(x['field'] for x in self['value']['columns'] if x['headerName'] == l)

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
            self['value']['columns'].append({
                'headerName': label,
                'field': id_letter,
                'colId': id_letter
            })
            ids.append(id_letter)
            for row in self['value']['rows']:
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
        for idx, colId in enumerate(x['field'] for x in self['value']['columns']):
            if colId in placed_entries:
                new_row[colId] = placed_entries[colId]
            elif len(entries) != 0:
                new_row[colId] = entries.pop(0)
            else:
                new_row[colId] = ''

        self['value']['rows'].append(new_row)
        return self

    def set_entry(self, row: int, column_id: str, value: any) -> Self:
        """
        Sets an entry to the table

        :param row: rwo idx starts with 0
        :param column_id: the column ID
        :param value: of the Entry

        :return self
        """

        self['value']['rows'][row][column_id] = value
        return self

    def get_column(self, column_id: str) -> list:
        """
        Adds an entry to the table

        :param column_id: the column ID
        :return: a list of all values of one column
        """

        result = []
        for row in self['value']['rows']:
            result.append(row[column_id])
        return result

    def __len__(self):
        return len(self['value']['rows'])


class RichText(dict):
    class HeaderType(Enum):
        H1 = 1
        H2 = 2
        H3 = 3

    def __init__(self, id: str, value: Optional[dict] = None):
        if value is None:
            value = {"ops": []}
        value = {"ops": value.get('ops', [])}

        super().__init__(**{
            'id': id,
            'type': BodyElements.richtext.value,
            'value': value
        })

    @property
    def id(self) -> str:
        return self['id']

    @property
    def value(self) -> list[dict]:
        return self['value']['ops']

    def add_text(self, text: str,
                 bold: Optional[bool] = None,
                 underline: Optional[bool] = None,
                 italic: Optional[bool] = None,
                 list: Optional[Literal['bullet', 'ordered']] = None,
                 header: Optional[HeaderType] = None) -> Self:
        attributes = {}
        if bold is not None:
            attributes['bold'] = bold
        if underline is not None:
            attributes['underline'] = underline
        if italic is not None:
            attributes['italic'] = italic
        if list is not None and list in ['bullet', 'ordered']:
            attributes['list'] = list
        if header is not None:
            attributes['header'] = header.value

        if len(attributes) == 0:
            self.value.append({"insert": text})
        else:
            self.value.append({"insert": text, 'attributes': attributes})

        return self


class ResearchPlan(AbstractElement):
    """
    A chemotion Research Plan object.
    It extends the :class:`chemotion_api.elements.abstract_element.AbstractElement`

    Usage::

    >>> from chemotion_api import Instance
    >>> from chemotion_api.collection import Collection
    >>> from chemotion_api.elements.research_plan import Table, RichText
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
    >>> # Add more advanced text
    >>> rt = plan.add_richtext()
    >>> # Add header to the text
    >>> rt.add_text('Header 1\\n', header=RichText.HeaderType.H1).add_text('Header 2\\n', header=RichText.HeaderType.H2)
    >>> # Add Bold,  Italic & underline text
    >>> rt.add_text('Bold,  Italic & underline\\n', bold=True, italic=True, underline=True)
    >>> # Add ordered and  list
    >>> rt.add_text('a\\nb\\nc\\n', list='ordered').add_text('a\\nb\\nc\\n', list='bullet')
    >>> plan.save()
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @property
    def body(self) -> list[dict]:
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
        if elem.get('type') == BodyElements.richtext.value:
            return self._parse_text(elem)
        elif elem.get('type') == BodyElements.ketcher.value:
            value = self._parse_ketcher(elem.get('value'))
        elif elem.get('type') == BodyElements.table.value:
            return self._parse_table(elem)
        elif elem.get('type') == BodyElements.image.value:
            value = self._parse_image(elem.get('value'))
        elif elem.get('type') == BodyElements.sample.value:
            value = self._parse_sample(elem.get('value'))
        elif elem.get('type') == BodyElements.reaction.value:
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
        return RichText(value['id'], value['value'])

    def _parse_image(self, value):
        if value is None: return None
        try:
            res = self.attachments.load_attachment(identifier=value.get('public_name'))
        except ValueError:
            return None
        return res

    def _parse_table(self, value):
        return Table(value['id'], value['value'], value.get('startCollapsed', False))

    def _parse_ketcher(self, value):
        return value

    def _parse_properties(self) -> dict:
        body = self.json_data.get('body')
        return {
            'body': [self._parse_body_element(x) for x in body]
        }

    def _clean_properties_data(self, serialize_data: dict | None = None) -> dict:
        self.json_data['body'] = []
        for elem in self.body:
            self.json_data['body'].append(self._reparse_body_element(elem))

        return self.json_data

    def add_richtext(self, text: Optional[str] = None, at_idx: Optional[int] = None) -> RichText:
        """
        Adds a text block to the Research plan

        :param text: to be added

        :return: body container
        """
        body_obj: RichText = self._add_new_element(BodyElements.richtext, at_idx)
        if text is not None:
            body_obj.add_text(text)
        return body_obj

    def add_image(self, image_path: str, at_idx: Optional[int] = None) -> dict:
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
        body_obj = self._add_new_element(BodyElements.image, at_idx)

        body_obj['value'] = file_obj
        return body_obj

    def add_table(self, at_idx: Optional[int] = None) -> Table:
        """
        Adds a new table to the Research plan

        :return: Table object
        """

        body_obj = self._add_new_element(BodyElements.table, at_idx)
        return body_obj

    def _add_new_element(self, element_type: BodyElements, at_idx: Optional[int]):
        body_elem = {
            'id': uuid.uuid4().__str__(),
            'type': element_type.name,
            'value': self._default_body_element(element_type)
        }

        new_element = self._parse_body_element(body_elem)
        if at_idx is None:
            self.body.append(new_element)
        else:
            self.body.insert(at_idx, new_element)
        return new_element

    def _reparse_body_element(self, elem: dict):
        if elem.get('type') == BodyElements.richtext.value:
            value = {'value': self._reparse_text(elem.get('value'))}
        elif elem.get('type') == BodyElements.ketcher.value:
            value = {'value': self._reparse_ketcher(elem.get('value'))}
        elif elem.get('type') == BodyElements.table.value:
            value = self._reparse_table(elem)
        elif elem.get('type') == BodyElements.image.value:
            value = {'value': self._reparse_image(elem.get('value'))}
        elif elem.get('type') == BodyElements.sample.value:
            value = {'value': self._reparse_sample(elem.get('value'))}
        elif elem.get('type') == BodyElements.reaction.value:
            value = {'value': self._reparse_reaction(elem.get('value'))}
        else:
            value = {'value': ''}

        elem_data = {
            'id': elem.get('id'),
            'type': elem.get('type'),
        } | value

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
        return value

    def _reparse_image(self, value):
        return {
            'public_name': value['identifier'],
            'file_name': value['filename']
        }

    def _reparse_table(self, value):
        return dict(value)

    def _reparse_ketcher(self, value):
        return value

    @staticmethod
    def _default_body_element(element_type: BodyElements) -> dict:
        if element_type == BodyElements.richtext:
            return {'ops': []}
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
