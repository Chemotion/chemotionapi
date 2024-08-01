from chemotion_api.elements.abstract_element import AbstractElement

from chemotion_api.elements.sample import Sample
from collections.abc import MutableMapping
import string

class WellplateCol(MutableMapping):

    def __init__(self, *args, **kwargs):
        self._keys = [letter for letter in string.ascii_uppercase[0:8]]
        self.store = dict.fromkeys(self._keys, None)
        self.update(dict(*args, **kwargs))  # use the free update to set keys

    def __getitem__(self, key: str):
        return self.store[self._keytransform(key)]

    def __setitem__(self, key: str, value: Sample| None):
        self.store[self._keytransform(key)] = value.split() if value is not None else None

    def __delitem__(self, key):
        del self.store[self._keytransform(key)]

    def __iter__(self):
        return iter(self.store)

    def __len__(self):
        return len(self.store)

    def _keytransform(self, key):
        key = key.upper()
        if key not in self._keys:
            raise IndexError("A Wallplate column only allows keys from A-H")
        return key

class Wellplate(AbstractElement):
    """
    Wellplates represent the localization of materials (chemicals)
    for biological experiments and are therefore some kind of link between chemical and biological operations.
    It extends the :class:`chemotion_api.elements.abstract_element.AbstractElement`

    - Plate size: 12 x 8
    - Verical indexing: 0-11
    - Horiconcal indexing: 'A' - 'H'

    Usage::

    >>> from chemotion_api import Instance
    >>> from chemotion_api.collection import Collection
    >>> import logging
    >>> try:
    >>>     instance = Instance('http(d)://xxx.xxx.xxx').test_connection().login('<USER>', "<PASSWORD>")
    >>> except ConnectionError as e:
    >>>     logging.error(f"A connection to Chemotion ({instance.host_url}) cannot be established")
    >>> # Get the reaction with ID 1
    >>> wp = instance.get_wellplate(1)
    >>> # Add samples to wellplate
    >>> wp.wells[0]['A'] = instance.get_sample(1)
    >>> wp.wells[0]['B'] = instance.get_sample(1)
    >>> wp.wells[0]['C'] = instance.get_sample(1)
    >>> wp.wells[1]['A'] = instance.get_sample(2)
    >>> wp.wells[1]['B'] = instance.get_sample(2)
    >>> wp.wells[1]['C'] = instance.get_sample(2)
    >>> wp.save()

    """

    def _set_json_data(self, json_data):
        super()._set_json_data(json_data)
        self.wells = [WellplateCol() for i in range(12)]
        for element in self.json_data.get('wells'):
            if element.get('sample') is not None:
                x = int(element['position']['x']) - 1
                y = chr(int(element['position']['y']) + ord('A') - 1)
                self.wells[x][y] = Sample(self._generic_segments, self._session, element['sample'])

    def _parse_properties(self) -> dict:

        return {
            'name': self.json_data.get('name'),
            'description': self.json_data.get('description')
        }

    def _clean_properties_data(self, serialize_data : dict | None =None) -> dict:
        self.json_data['wells'] = self.json_data.get('wells')[:self.json_data.get('size')]
        for element in self.json_data.get('wells'):
            x = int(element['position']['x']) - 1
            y = chr(int(element['position']['y']) + ord('A') - 1)
            element['is_new'] = element.get('is_new', False)
            if self.wells[x][y] is None:
                element['sample'] = None
            else:
                element['sample'] = self.wells[x][y].clean_data()


        self.json_data['name'] = self.properties.get('name')
        self.json_data['description'] = self.properties.get('description')
        return self.json_data

    def save(self):
        super().save()
        self.load()
