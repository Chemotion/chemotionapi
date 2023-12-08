import json
import re
import copy

from chemotion_api.elements.abstract_element import AbstractElement
from chemotion_api.elements.empty_elements import init_container
from collections.abc import MutableMapping
from chemotion_api.connection import Connection
from chemotion_api.utils.solvent_manager import get_solvent_list


class SolventList(list):

    def __init__(self, session: Connection, *args):
        if args is None or args[0] is None:
            args = []
        super().__init__(*args)
        self._session = session

    def add_new_smiles(self, smiles):
        m = MoleculeManager(self._session).create_molecule_by_smiles(smiles)
        self.append({
            "label": m.get('iupac_name', m.get('sum_formular')),
            "smiles": smiles,
            "inchikey": m.get("inchikey"),
            "ratio": 1
        })

    def add_new_name(self, name):
        solvent_info = get_solvent_list().get(name)
        if solvent_info is None:
            raise KeyError(
                'Solver: "{}" is not available. Run instance.get_solvent_list() to see all valid solver names'.format(
                    name))

        m = MoleculeManager(self._session).create_molecule_by_smiles(solvent_info['smiles'])
        self.append({
            "label": name,
            "smiles": m.get('cano_smiles'),
            "inchikey": m.get("inchikey"),
            "ratio": 1
        })


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
        self.all_store = dict(data)
        self.store = dict()
        self.id = data.get('id')
        for key in ["boiling_point", "cano_smiles", "density", "inchikey", "inchistring", "melting_point"]:
            self.store[key] = self.all_store.get(key)

    def __getitem__(self, key: str):
        key = self._keytransform(key)
        if key in self.store:
            return self.store[key]
        return self.all_store[key]

    def __setitem__(self, key: str, value):
        key = self._keytransform(key)
        if key in self.store:
            self.store[key] = value
        else:
            self.all_store[key] = value

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
        self.save()
        split_sample = copy.deepcopy(self.json_data)
        split_sample['parent_id'] = self.id
        split_sample['id'] = None

        if 'tag' in split_sample:
            del split_sample['tag']
        split_sample['created_at'] = None
        split_sample['updated_at'] = None
        split_sample['target_amount_value'] = 0
        split_sample['real_amount_value'] = None
        split_sample['is_split'] = True
        split_sample['is_new'] = True
        split_sample['split_label'] = split_sample['short_label']

        split_sample['container'] = init_container()
        return Sample(generic_segments=self._generic_segments, session=self._session, json_data=split_sample)

    def copy(self):
        raise NotImplementedError

    def toggle_decoupled(self):
        self.properties['decoupled'] = not self.properties['decoupled']

    def _parse_properties(self) -> dict:
        melting_range = re.split('\.{2,3}', self.json_data.get('melting_point')) if self.json_data.get(
            'melting_point') is not None else ['', '']
        boiling_range = re.split('\.{2,3}', self.json_data.get('boiling_point')) if self.json_data.get(
            'boiling_point') is not None else ['', '']
        return {
            'name': self.json_data.get('name'),
            'short_label': self.json_data.get('short_label'),
            'solvent': SolventList(self._session, self.json_data.get('solvent', [])),
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
            'user_labels': self.json_data.get('user_labels', []),
            'decoupled': self.json_data.get('decoupled'),
            'waste': self.json_data.get('waste', False),
            'reference': self.json_data.get('reference'),
            'metrics': self.json_data.get('metrics'),
            'sum_formula': self.json_data.get('sum_formula'),
            'equivalent': self.json_data.get('equivalent'),
            'coefficient': self.json_data.get('coefficient', 1),
            'reaction_description': self.json_data.get('reaction_description'),
            'molarity': {'unit': format(self.json_data.get('molarity_unit')),
                         'value': self.json_data.get('molarity_value')}
        }

    def _clean_properties_data(self, serialize_data: dict | None = None) -> dict:
        if serialize_data is None:
            serialize_data = {}

        serialize_data['name'] = self.properties.get('name')
        serialize_data['description'] = self.properties.get('description')
        serialize_data['external_label'] = self.properties.get('external_label')
        serialize_data['short_label'] = self.properties.get('short_label')
        serialize_data['solvent'] = self.properties.get('solvent')
        if self.properties.get('boiling_point_lowerbound') is not None:
            serialize_data['boiling_point_lowerbound'] = self.properties.get('boiling_point_lowerbound')
        if self.properties.get('boiling_point_upperbound') is not None:
            serialize_data['boiling_point_upperbound'] = self.properties.get('boiling_point_upperbound')
        if self.properties.get('melting_point_lowerbound') is not None:
            serialize_data['melting_point_lowerbound'] = self.properties.get('melting_point_lowerbound')
        if self.properties.get('melting_point_upperbound') is not None:
            serialize_data['melting_point_upperbound'] = self.properties.get('melting_point_upperbound')
        serialize_data['stereo'] = self.properties.get('stereo')
        serialize_data['location'] = self.properties.get('location')
        serialize_data['purity'] = self.properties.get('purity')
        serialize_data['user_labels'] = self.properties.get('user_labels')
        serialize_data['decoupled'] = self.properties.get('decoupled')
        serialize_data['density'] = self.properties.get('density')
        serialize_data['metrics'] = self.properties.get('metrics')

        serialize_data['is_top_secret'] = self.properties.get('is_top_secret')
        serialize_data['molarity_unit'] = self.properties.get('molarity').get('unit')
        serialize_data['molarity_value'] = self.properties.get('molarity').get('value')

        serialize_data['waste'] = self.properties.get('waste')
        serialize_data['reference'] = self.properties.get('reference', False)
        serialize_data['sum_formula'] = self.properties.get('sum_formula')
        serialize_data['equivalent'] = self.properties.get('equivalent')
        serialize_data['coefficient'] = self.properties.get('coefficient', 1)

        serialize_data['target_amount_unit'] = self.properties.get('target_amount').get('unit')
        serialize_data['target_amount_value'] = self.properties.get('target_amount').get('value')

        serialize_data['real_amount_unit'] = self.properties.get('real_amount').get('unit')
        serialize_data['real_amount_value'] = self.properties.get('real_amount').get('value')

        serialize_data['is_split'] = self.is_split

        serialize_data['molfile'] = self.json_data.get('molfile')

        serialize_data['sample_svg_file'] = self.json_data.get('sample_svg_file')
        serialize_data['dry_solvent'] = self.json_data.get('dry_solvent')
        serialize_data['parent_id'] = self.json_data.get('parent_id')
        serialize_data['residues'] = self.json_data.get('residues')
        serialize_data['imported_readout'] = self.json_data.get('imported_readout')
        serialize_data['xref'] = self.json_data.get('xref')
        serialize_data['molecular_mass'] = self.json_data.get('molecular_mass')
        serialize_data['elemental_compositions'] = self.json_data.get('elemental_compositions')
        serialize_data['inventory_sample'] = self.json_data.get('inventory_sample')

        if self.molecule is not None and self.molecule.id is not None:
            serialize_data['molecule'] = self.molecule.store
            serialize_data['molecule_id'] = self.molecule.id

        return serialize_data
