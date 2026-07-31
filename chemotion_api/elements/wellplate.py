"""Wellplate element: a grid of wells, each optionally holding a :class:`~chemotion_api.elements.sample.Sample`."""
from chemotion_api.elements.abstract_element import AbstractElement

from chemotion_api.elements.sample import Sample
from collections.abc import MutableMapping
import string

class WellplateCol(MutableMapping):
    """
    One column of a well plate: a mapping from row key ``'A'``-``'H'`` to a
    :class:`~chemotion_api.elements.sample.Sample` (or None for an empty well).

    Keys are case-insensitive; any key outside ``A``-``H`` raises an ``IndexError``.
    """

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
            raise IndexError("A Wellplate column only allows keys from A-H")
        return key

class Wellplate(AbstractElement):
    """
    Wellplates represent the localization of materials (chemicals)
    for biological experiments and are therefore some kind of link between chemical and biological operations.
    It extends the :class:`chemotion_api.elements.abstract_element.AbstractElement`

    - Plate size: 12 x 8
    - Verical indexing: 0-11
    - Horizontal indexing: 'A' - 'H'

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
        for element in (self.json_data.get('wells') or []):
            if element.get('sample') is not None:
                x = int(element['position']['x']) - 1
                y = chr(int(element['position']['y']) + ord('A') - 1)
                self.wells[x][y] = Sample(self._generic_segments, self._session, element['sample'])

    def _parse_properties(self) -> dict:
        if self.json_data is None:
            return {'name': None, 'description': None}
        return {
            'name': self.json_data.get('name'),
            'description': self.json_data.get('description')
        }

    def _clean_properties_data(self, serialize_data : dict | None =None) -> dict:
        json_data = self.json_data
        if not isinstance(json_data, dict):
            raise TypeError(f"Expected dict for json_data, got {type(json_data)}")
        wells = json_data.get('wells')
        if wells is not None and not isinstance(wells, list):
            raise TypeError(f"Expected list for wells, got {type(wells)}")
        size = json_data.get('size')
        if size is not None and not isinstance(size, int):
            raise TypeError(f"Expected int for size, got {type(size)}")
        json_data['wells'] = wells[:size] if wells and size is not None else (wells or [])
        for element in json_data.get('wells', []):
            x = int(element['position']['x']) - 1
            y = chr(int(element['position']['y']) + ord('A') - 1)
            element['is_new'] = element.get('is_new', False)
            if self.wells[x][y] is None:
                element['sample'] = None
            else:
                element['sample'] = self.wells[x][y].clean_data()


        json_data['name'] = self.properties.get('name')
        json_data['description'] = self.properties.get('description')
        return json_data

    def eln_node_content(self) -> dict:
        """Emit each occupied well as a schema.org ``PropertyValue`` (position → sample label)."""
        property_values: list[dict] = []
        for x, col in enumerate(self.wells or []):
            for y, sample in col.items():
                if sample is None:
                    continue
                try:
                    label = sample.properties.get('short_label') or sample.name
                    if not label and sample.molecule:
                        label = sample.molecule.get('cano_smiles')
                except (AttributeError, TypeError):
                    label = None
                property_values.append({
                    "@type": "PropertyValue",
                    "name": f"well {y}{x + 1}",
                    "value": label or "occupied",
                })
        content: dict = {}
        if property_values:
            content["variableMeasured"] = property_values
        desc = self.properties.get('description') if self._properties is not None else None
        if isinstance(desc, str) and desc.strip():
            content["description"] = desc
        return content

    def save(self):
        """
        Save the well plate to the server and reload it to refresh the well/sample data.
        """
        super().save()
        self.load()
