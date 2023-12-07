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
        raise NotImplementedError('Not jet implemented')
