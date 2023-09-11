import json
import re
import copy
import uuid

from chemotion_api.elements.abstract_element import AbstractElement
from chemotion_api.elements.empty_elements import init_container
from collections.abc import MutableMapping
from chemotion_api.connection import Connection


class MoleculeManager:
    def __init__(self, session: Connection):
        self._session = session

    def load_molecule(self, host_url, session, inchikey):
        raise NotImplementedError

    def create_molecule_by_smiles(self, smiles_code: str):
        smiles_url = "/api/v1/molecules/smiles"
        payload = {
            "editor": "ketcher",
            "smiles": smiles_code
        }
        res = self._session.post(smiles_url,
                                 data=json.dumps(payload))
        if res.status_code != 201:
            raise ConnectionError('{} -> {}'.format(res.status_code, res.text))

        return Molecule(res.json())

    def create_molecule_by_cls(self, host_url, session, inchikey):
        raise NotImplementedError


class Molecule(MutableMapping):
    def __init__(self, data):
        self.store = dict(data)
        self.id = data['id']

    def __getitem__(self, key: str):
        return self.store[self._keytransform(key)]

    def __setitem__(self, key: str, value):
        self.store[self._keytransform(key)] = value

    def __delitem__(self, key):
        del self.store[self._keytransform(key)]

    def __iter__(self):
        return iter(self.store)

    def __len__(self):
        return len(self.store)

    def _keytransform(self, key):
        return key


class Sample(AbstractElement):

    def _set_json_data(self, json_data):
        super()._set_json_data(json_data)
        self.molecule = Molecule(json_data.get('molecule'))
        self._svg_file = json_data.get('sample_svg_file')
        self.is_split = json_data.get('is_split', False)
        self._children_count = json_data.get('children_count', )


    def load_image(self):
        image_url = "/images/samples/{}".format(self._svg_file)
        res = self._session.get(image_url)
        if res.status_code != 200:
            raise ConnectionError('{} -> {}'.format(res.status_code, res.text))
        return res.text

    def split(self):
        split_sample = copy.deepcopy(self.clean_data())
        split_sample['parent_id'] = self.id
        split_sample['id'] = uuid.uuid4().__str__()

        if 'tag' in split_sample:
            del split_sample['tag']
        split_sample['created_at'] = None
        split_sample['updated_at'] = None
        split_sample['target_amount_value'] = 0
        split_sample['real_amount_value'] = None
        split_sample['is_split'] = True
        split_sample['is_new'] = True
        split_sample['short_label'] += '-{}'.format(self._children_count)
        split_sample['split_label'] = split_sample['short_label']

        split_sample['container'] = init_container()
        return Sample(generic_segments=self._generic_segments, session=self._session, json_data=split_sample)

    def copy(self):
        raise NotImplementedError


    def _parse_properties(self) -> dict:
        melting_range = re.split('\.{2,3}', self.json_data.get('melting_point')) if self.json_data.get(
            'melting_point') is not None else ['', '']
        boiling_range = re.split('\.{2,3}', self.json_data.get('boiling_point')) if self.json_data.get(
            'boiling_point') is not None else ['', '']
        return {
            'name': self.json_data.get('name'),
            'description': self.json_data.get('description'),
            'external_label': self.json_data.get('external_label'),
            'boiling_point_lowerbound': int(boiling_range[0]) if boiling_range[0].isdigit() else None,
            'boiling_point_upperbound': int(boiling_range[1]) if boiling_range[1].isdigit() else None,
            'melting_point_lowerbound': int(melting_range[0]) if melting_range[0].isdigit() else None,
            'melting_point_upperbound': int(melting_range[1]) if melting_range[1].isdigit() else None,
            'target_amount': {
                'value': self.json_data.get('target_amount_value'),
                'unit': self.json_data.get('target_amount_unit'),
            },
            'real_amount': {
                'value': self.json_data.get('real_amount_value'),
                'unit': self.json_data.get('real_amount_unit'),
            },
            'stereo': self.json_data.get('stereo'),
            'location': self.json_data.get('location'),
            'is_top_secret': self.json_data.get('is_top_secret'),
            'is_restricted': self.json_data.get('is_restricted'),
            'purity': self.json_data.get('purity'),
            'density': self.json_data.get('density'),
            'showed_name': self.json_data.get('showed_name'),
            'waste': self.json_data.get('waste'),
            'reference': self.json_data.get('reference'),
            'sum_formula': self.json_data.get('sum_formula'),
            'equivalent': self.json_data.get('equivalent'),
            'coefficient': self.json_data.get('coefficient'),
            'reaction_description': self.json_data.get('reaction_description'),
            'molarity': {'unit': format(self.json_data.get('molarity_unit')),
                         'value': self.json_data.get('molarity_value')}
        }

    def _clean_properties_data(self):
        self.json_data['name'] = self.properties.get('name')
        self.json_data['description'] = self.properties.get('description')
        self.json_data['external_label'] = self.properties.get('external_label')
        self.json_data['boiling_point_lowerbound'] = self.properties.get('boiling_point_lowerbound')
        self.json_data['boiling_point_upperbound'] = self.properties.get('boiling_point_upperbound')
        self.json_data['melting_point_lowerbound'] = self.properties.get('melting_point_lowerbound')
        self.json_data['melting_point_upperbound'] = self.properties.get('melting_point_upperbound')
        self.json_data['stereo'] = self.properties.get('stereo')
        self.json_data['location'] = self.properties.get('location')
        self.json_data['purity'] = self.properties.get('purity')
        self.json_data['showed_name'] = self.properties.get('showed_name')
        self.json_data['purity'] = self.properties.get('purity')
        self.json_data['density'] = self.properties.get('density')
        self.json_data['is_restricted'] = self.properties.get('is_restricted')
        self.json_data['is_top_secret'] = self.properties.get('is_top_secret')
        self.json_data['molarity_unit'] = self.properties.get('molarity').get('unit')
        self.json_data['molarity_value'] = self.properties.get('molarity').get('value')

        self.json_data['waste'] = self.properties.get('waste')
        self.json_data['reference'] = self.properties.get('reference')
        self.json_data['sum_formula'] = self.properties.get('sum_formula')
        self.json_data['equivalent'] = self.properties.get('equivalent')
        self.json_data['coefficient'] = self.properties.get('coefficient')

        self.json_data['target_amount_unit'] = self.properties.get('target_amount').get('unit')
        self.json_data['target_amount_value'] = self.properties.get('target_amount').get('value')

        self.json_data['real_amount_unit'] = self.properties.get('real_amount').get('unit')
        self.json_data['real_amount_value'] = self.properties.get('real_amount').get('value')
        if self.molecule is not None and self.molecule.id is not None:
            self.json_data['molecule'] = self.molecule.store
            self.json_data['molecule_id'] = self.molecule.id
