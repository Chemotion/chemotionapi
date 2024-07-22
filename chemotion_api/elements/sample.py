import json
import re
import copy

from requests import Response

from chemotion_api.elements.abstract_element import AbstractElement
from chemotion_api.elements.empty_elements import init_container
from collections.abc import MutableMapping
from chemotion_api.connection import Connection
from chemotion_api.utils.solvent_manager import get_solvent_list


class SolventList(list):
    """
    In generale it contains a list of molecules. It allows to add molecules from the solvents list.
    """

    def __init__(self, session: Connection, *args):
        if args is None or args[0] is None:
            args = []
        super().__init__(*args)
        self._session = session

    def add_new_smiles(self, smiles: str):
        """
        Add a solvent by smiles code

        :param smiles: Smiles code
        """

        m = MoleculeManager(self._session).create_molecule_by_smiles(smiles)
        self.append({
            "label": m.get('iupac_name', m.get('sum_formular')),
            "smiles": smiles,
            "inchikey": m.get("inchikey"),
            "ratio": 1
        })

    def add_new_name(self, name: str):
        """
        Add a solvent from the solvent list by name

        :param name: Solvent Name
        """

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


class Molecule(MutableMapping):
    """
    Contains the Molecule information. This class extents MutableMapping and can be used as normal dict object.
    However, it ensures that the following keys are set and used if the sample which contains the molecule is saved.

    :key: "boiling_point" {float}
    :key: "cano_smiles" {str}
    :key: "density" {float}
    :key: "inchikey" {str}
    :key: "inchistring" {str}
    :key: "melting_point" {float}
    """
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


class MoleculeManager:
    """
    The MoleculeManager can be used to load and crate molecules in teh Chemotion Instance
    """

    def __init__(self, session: Connection):
        self._session = session

    def create_molecule_by_smiles(self, smiles_code: str) -> Molecule:
        """
        Creates a new molecule for a given smiles code

        :param smiles_code: Simles code of te sample
        :return: Molecule obj
        """
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

    def create_molecule_by_cls(self, host_url, session, inchikey) -> Molecule:
        """Not implemented yet!!"""
        raise NotImplementedError


class Sample(AbstractElement):
    """
    A chemotion Sample object.
    It extends the :class:`chemotion_api.elements.abstract_element.AbstractElement`

    Usage::

    >>> from chemotion_api import Instance
    >>> import logging
    >>> try:
    >>>     instance = Instance('http(d)://xxx.xxx.xxx').test_connection().login('<USER>', "<PASSWORD>")
    >>> except ConnectionError as e:
    >>>     logging.error(f"A connection to Chemotion ({instance.host_url}) cannot be established")
    >>> # Get the sample with ID 1
    >>> s = instance.get_sample(1)
    >>> # Set the real amount to 3.7 g
    >>> s.properties["real_amount"]["value"] = 3.7
    >>> s.properties["real_amount"]["unit"] = "g"
    >>> # Set the boiling point range from 40 to 50
    >>> s.properties["boiling_point_lowerbound"] = 40
    >>> s.properties["boiling_point_upperbound"] = 50
    >>> # Set the external label to "Sample_X334D"
    >>> s.properties["external_label"] = "Sample_X334D"
    >>> # Save the structure Image
    >>> with open("./sample_structure.svg", "wb+") as f:
    >>>     f.write(s.load_image().content)
    >>> # Save the sample
    >>> s.save()
    """

    def _set_json_data(self, json_data):
        super()._set_json_data(json_data)
        self._molecule = Molecule(json_data.get('molecule'))
        self._svg_file = json_data.get('sample_svg_file')
        self.is_split = json_data.get('is_split', False)
        self._children_count = json_data.get('children_count', )



    @property
    def properties(self) -> dict:
        """
        The properties property contains all data which can be altered
        through the chemotion api from the main tab of the sample.


        :key solvent: {:class:`chemotion_api.elements.abstract_element.SolventList`}
        :key description: {string}
        :key external_label: {str}
        :key boiling_point_lowerbound: {float}
        :key boiling_point_upperbound: {float}
        :key melting_point_lowerbound: {float}
        :key melting_point_upperbound: {float}
        :key target_amount: {dict} with value: float and unit: str
        :key molarity: {dict} with value: float and unit: str
        :key real_amount: {dict} with value: float and unit: str
        :key stereo: {str}
        :key location: {str}
        :key is_top_secret: {bool}
        :key is_restricted: {bool}
        :key purity: {float}
        :key density: {float}
        :key user_labels: {list}
        :key decoupled: {bool}
        :key waste: {bool}
        :key metrics: {str}
        :key sum_formula: {str}
        :key equivalent: {str}
        :key coefficient: {str}
        :key reaction_description: {str}

        Readonly properties:

        :key name: {str, readonly}
        :key short_label: {str, readonly}

        :return: Element properties
        """
        return super().properties

    @property
    def molecule(self) -> Molecule:
        """
        The molecule of the sample
        """

        return self._molecule

    @molecule.setter
    def molecule(self, molecule: Molecule):
        """
        The molecule of the sample
        """

        self._molecule = molecule

    def load_image(self) -> Response:
        """
        Loads the sample structure as svg image

        :return: Response with the svg as content
        """

        image_url = "/images/samples/{}".format(self._svg_file)
        res = self._session.get(image_url)
        if res.status_code != 200:
            raise ConnectionError('{} -> {}'.format(res.status_code, res.text))
        return res

    def split(self):
        """
        Splits the sample.

        :return: A new sample object
        :rtype: :class:`chemotion_api.elements.sample.Sample`
        """
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
        """Decoupls the sample from the molecule"""
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
