import json
import re
import copy
from enum import Enum
from typing import Literal, Optional

from requests import Response

from chemotion_api.elements.abstract_element import AbstractElement
from chemotion_api.elements.empty_elements import init_container
from collections.abc import MutableMapping
from chemotion_api.connection import Connection
from chemotion_api.utils import UnitDict, FixedDict
from chemotion_api.utils.solvent_manager import get_solvent_list
from chemotion_api.elements.utils import QuantityUnit, calculate_quantity


class SampleType(Enum):
    SAMPLE_TYPE_MIXTURE = 'Mixture'
    SAMPLE_TYPE_MICROMOLECULE = 'Micromolecule'


class SampleVariationType(Enum):
    STARTING_MATERIAL = 'startingMaterials'
    REACTANT = 'reactants'
    PRODUCT = 'products'
    SOLVENTS = 'solvents'


class GasType(Enum):
    OFF = 'off'
    GAS = 'gas'
    CATALYST = 'catalyst'
    FEEDSTOCK = 'feedstock'


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
        for key in ["boiling_point", "molecular_weight", "exact_molecular_weight", "cano_smiles", "density", "inchikey",
                    "inchistring", "melting_point", "sum_formular"]:
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

    def clean(self) -> dict:
        return {
            "density": self.store.get("density"),
            "melting_point": self.store.get("melting_point"),
            "boiling_point": self.store.get("boiling_point"),
            "inchistring": self.store.get("inchistring"),
            "cano_smiles": self.store.get("cano_smiles"),
            "inchikey": self.store.get("inchikey")
        }


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

    def __init__(self, *args, **kwargs):
        self._molecule = None
        self.is_split = False
        self._reaction = None
        self._role_in_reaction = None
        super().__init__(*args, **kwargs)

    def _set_json_data(self, json_data):
        super()._set_json_data(json_data)
        self._molecule = Molecule(json_data.get('molecule'))
        self._svg_file = json_data.get('sample_svg_file')
        self.is_split = json_data.get('is_split', False)
        self._children_count = json_data.get('children_count', )

    @property
    def reaction(self):
        if self._reaction is None:
            try:
                self._reaction = self.reload_reaction()
            except KeyError:
                return None
        return self._reaction

    @reaction.setter
    def reaction(self, reaction):
        self._reaction = reaction

    def reload_reaction(self):
        from chemotion_api import Instance
        try:
            return Instance(self._session).get_reaction(self.json_data['tag']['taggable_data']['reaction_id'])
        except (KeyError, IndexError):
            raise KeyError(f'Could not find Reaction of Sample: {self}')

    @property
    def role_in_reaction(self) -> Literal[
        'starting_materials', 'reactants', 'products', 'solvents', 'purification_solvents']:
        if self._role_in_reaction is None:
            self._role_in_reaction = self.reload_role_in_reaction()
        return self._role_in_reaction

    def reload_role_in_reaction(self) -> Optional[Literal[
        'starting_materials', 'reactants', 'products', 'solvents', 'purification_solvents']]:
        if self.reaction is None:
            return None
        elements = ['starting_materials', 'reactants', 'products', 'solvents', 'purification_solvents']
        element: Literal['starting_materials', 'reactants', 'products', 'solvents', 'purification_solvents']
        for element in elements:
            mat_list = self.reaction.properties[element]
            for mat in mat_list:
                if mat.id == self.id:
                    return element
        raise KeyError(f'Could not find Role In {self}')

    @property
    def properties(self) -> dict:
        """
        The properties property contains all data which can be altered
        through the chemotion api from the main tab of the sample.


        :key solvent: {:class:`chemotion_api.elements.abstract_element.SolventList`}
        :key description: {str}
        :key external_label: {str}
        :key boiling_point_lowerbound: {float}
        :key boiling_point_upperbound: {float}
        :key melting_point_lowerbound: {float}
        :key melting_point_upperbound: {float}
        :key target_amount: {dict} has a unit {str} ('l', 'g' or 'mol') and an amount {float}. The amount of the sample used as starting material or reactant.
        :key molarity: {dict} with value: float and unit: str
        :key real_amount: {dict} has a unit {str} ('l', 'g' or 'mol') and an amount {float}. The amount of sample obtained from a reaction.
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
        :key gas_type {:class:`chemotion_api.elements.sample.GasType`}
        :key inventory_sample: {bool}
        :key gas_phase_data: {dict}

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
        if self._molecule is None:
            return Molecule({})
        return self._molecule

    @molecule.setter
    def molecule(self, molecule: Molecule):
        """
        The molecule of the sample
        """

        self._molecule = molecule

    @property
    def gram(self):
        key = 'real_amount' if self.role_in_reaction == 'products' else 'target_amount'
        return calculate_quantity(
            current_value=self.properties[key]['value'],
            current_unit=self.properties[key]['unit'],
            output_unit=QuantityUnit.Gram,
            molecular_weight=self.molecule['molecular_weight'],
            purity=self.properties[key]['purity'],
            molarity=self.properties['molarity'],
            density=self.properties['density']
        )

    @property
    def mol(self):
        key = 'real_amount' if self.role_in_reaction == 'products' else 'target_amount'
        return calculate_quantity(
            current_value=self.properties[key]['value'],
            current_unit=self.properties[key]['unit'],
            output_unit=QuantityUnit.Mole,
            molecular_weight=self.molecule['molecular_weight'],
            purity=self.properties[key]['purity'],
            molarity=self.properties['molarity'],
            density=self.properties['density']
        )

    @property
    def liter(self):
        key = 'real_amount' if self.role_in_reaction == 'products' else 'target_amount'
        return calculate_quantity(
            current_value=self.properties[key]['value'],
            current_unit=self.properties[key]['unit'],
            output_unit=QuantityUnit.Liter,
            molecular_weight=self.molecule['molecular_weight'],
            purity=self.properties[key]['purity'],
            molarity=self.properties['molarity'],
            density=self.properties['density']
        )

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
        melting_range = re.split(r'\.{2,3}', self.json_data.get('melting_point')) if self.json_data.get(
            'melting_point') is not None else ['', '']
        boiling_range = re.split(r'\.{2,3}', self.json_data.get('boiling_point')) if self.json_data.get(
            'boiling_point') is not None else ['', '']

        gas_props = {}
        if self.json_data.get('gas_type') is not None:
            gas_props['gas_type'] = GasType(self.json_data.get('gas_type'))
        else:
            gas_props['gas_type'] = GasType.OFF

        if self.json_data.get('gas_phase_data') is None:
            gas_props['gas_phase_data'] = FixedDict({
                "time": {
                    "unit": "h",
                    "value": None
                },
                "temperature": {
                    "unit": "K",
                    "value": None
                },
                "turnover_number": None,
                "part_per_million": None,
                "turnover_frequency": {
                    "unit": "TON/h",
                    "value": None
                }
            })
        else:
            gas_props['gas_phase_data'] = FixedDict(self.json_data.get('gas_phase_data'))

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
            'target_amount': UnitDict(unit=self.json_data.get('target_amount_unit'),
                                      value=self.json_data.get('target_amount_value')),
            'real_amount': UnitDict(unit=self.json_data.get('real_amount_unit'),
                                    value=self.json_data.get('real_amount_value')),
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
            'molarity': UnitDict(unit=format(self.json_data.get('molarity_unit')),
                                 value=self.json_data.get('molarity_value')),

            'molecular_mass': self.json_data.get('molecular_mass'),
            'inventory_sample': self.json_data.get('inventory_sample'),
            'position': self.json_data.get('position'),
            'show_label': self.json_data.get('show_label')

        } | gas_props

    def _clean_properties_data(self, serialize_data: dict | None = None) -> dict:
        if serialize_data is None:
            serialize_data = {}

        serialize_data['name'] = self.properties.get('name')
        serialize_data['description'] = self.properties.get('description')
        serialize_data['external_label'] = self.properties.get('external_label')
        serialize_data['short_label'] = self.properties.get('short_label')
        serialize_data['solvent'] = self.properties.get('solvent')
        serialize_data['boiling_point_lowerbound'] = self.properties.get('boiling_point_lowerbound')
        serialize_data['boiling_point_upperbound'] = self.properties.get('boiling_point_upperbound')
        serialize_data['melting_point_lowerbound'] = self.properties.get('melting_point_lowerbound')
        serialize_data['melting_point_upperbound'] = self.properties.get('melting_point_upperbound')
        serialize_data['stereo'] = self.properties.get('stereo')
        serialize_data['location'] = self.properties.get('location')
        serialize_data['purity'] = self.properties.get('purity')
        serialize_data['user_labels'] = self.properties.get('user_labels')
        serialize_data['decoupled'] = self.properties.get('decoupled')
        serialize_data['density'] = self.properties.get('density')
        serialize_data['metrics'] = self.properties.get('metrics')
        serialize_data['dry_solvent'] = self.properties.get('dry_solvent')

        serialize_data['is_top_secret'] = self.properties.get('is_top_secret')
        serialize_data['molarity_unit'] = self.properties.get('molarity').get('unit')
        serialize_data['molarity_value'] = self.properties.get('molarity').get('value')
        serialize_data['molecular_mass'] = self.properties.get('molecular_mass')

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
        serialize_data['inventory_sample'] = self.properties.get('inventory_sample')
        serialize_data['gas_type'] = self.properties.get('gas_type').value
        if self.properties.get('gas_type') != GasType.OFF.value and self.properties.get('gas_phase_data') is not None:
            serialize_data['gas_phase_data'] = self.properties.get('gas_phase_data')
        else:
            serialize_data['gas_phase_data'] = None

        serialize_data['sample_svg_file'] = self.json_data.get('sample_svg_file')
        serialize_data['dry_solvent'] = self.json_data.get('dry_solvent')
        serialize_data['parent_id'] = self.json_data.get('parent_id')
        serialize_data['residues'] = self.json_data.get('residues')
        serialize_data['imported_readout'] = self.json_data.get('imported_readout')
        serialize_data['xref'] = self.json_data.get('xref')
        serialize_data['elemental_compositions'] = self.json_data.get('elemental_compositions')

        self._set_serialized_if_exist('molecule_name_id', serialize_data, self.json_data)
        self._set_serialized_if_exist('collection_id', serialize_data, self.json_data)
        self._set_serialized_if_exist('position', serialize_data)
        self._set_serialized_if_exist('show_label', serialize_data)
        self._set_serialized_if_exist('components', serialize_data)
        self._set_serialized_if_exist('sample_type', serialize_data)

        

        if self.molecule is not None and self.molecule.id is not None:
            serialize_data['molecule'] = self.molecule.clean()
            serialize_data['molecule_id'] = self.molecule.id

        return serialize_data

    def _set_serialized_if_exist(self, key: str, serialize_data :dict, origen_data: Optional[dict] = None):
        if origen_data is None:
            value = self.properties.get(key, self.json_data.get(key))
        else:
            value = origen_data.get(key)
        if value is not None:
            serialize_data[key] = value

    def allowed_quantity_units(self):
        return self._allowed_quantity_units()

    def _allowed_quantity_units(self):
        if self.role_in_reaction == 'solvents':
            return [QuantityUnit.Liter]
        elif self.role_in_reaction == 'purification_solvents':
            return [QuantityUnit.Liter]
        else:
            default_set = [QuantityUnit.Gram]
            if self.properties['density'] != 0 or self.properties['molarity'] != 0:
                default_set += [QuantityUnit.Liter]

            if self.role_in_reaction in ['starting_materials', 'reactants']:
                return default_set + [QuantityUnit.Mole, QuantityUnit.Equivalent]
            elif self.role_in_reaction == 'products':
                return default_set + [QuantityUnit.Yield]
        return default_set + [QuantityUnit.Mole]

    def update_equivalent(self):
        self._set_equivalent()

    def _set_equivalent(self, value: Optional[float] = None):
        unit = QuantityUnit.Equivalent
        if unit not in self.allowed_quantity_units():
            raise KeyError(
                f'The value {unit.value}  cannot be set for this sample. This is most likely due to the role of this sample in the reaction.')
        if self.properties['reference']:
            self._properties['equivalent'] = 1
        elif value is None:
            try:
                self._properties['equivalent'] = self.mol / self.reaction.reference_sample.mol
            except ZeroDivisionError:
                self._properties['equivalent'] = None
        else:
            self._properties['equivalent'] = value
            self.set_amount(self.reaction.reference_sample.mol * value, QuantityUnit.Mole)

    def set_ref(self, is_ref: bool, check_ref: bool):
        if check_ref:
            self.properties['reference'] = is_ref
        else:
            self._properties['reference'] = is_ref

    def set_amount(self, value: float, unit: Optional[QuantityUnit | str] = None):
        if isinstance(unit, str):
            unit_str = unit
            unit = QuantityUnit.from_string(unit_str)
            if unit is None:
                raise ValueError(f'{unit_str} is not a valid unit')
        amount_dict = ['target_amount', 'real_amount']
        [key, zero_key] = amount_dict.__reversed__() if self.role_in_reaction == 'products' else amount_dict
        if unit is None:
            unit = QuantityUnit.from_string(self.properties[key]['unit'])

        if unit not in self.allowed_quantity_units():
            raise ValueError(f'This sample can set the {unit.value}')
        if value < 0:
            raise ValueError(f'The amount must be >= 0 {unit.value}')
        if unit == QuantityUnit.Yield:
            raise KeyError('Yield cannot be set!!')
        elif unit == QuantityUnit.Equivalent:
            self._set_equivalent(value)
        else:
            self._properties[key] = UnitDict(unit=str(unit.value), value=value)
            self._properties[zero_key] = UnitDict(unit=str(unit.value), value=None)
            try:
                self._set_equivalent()
            except (KeyError, ValueError, TypeError, ZeroDivisionError):
                pass

    def on_properties_change(self, dict_obj, name, value):
        try:
            if name in ['target_amount', 'real_amount']:
                if len(name) > 1:
                    dict_copy = {**dict_obj[-1], name[-1]: value[-1]}
                    self.set_amount(**dict_copy)
                return False
        except ValueError:
            pass
        if name[-1] == 'purity' and (value[-1] <= 0 or value[-1] > 1):
            raise ValueError('The purity must be >= 0 and <= 1')
        if name[-1] == 'reference':
            self.reaction.reference_sample = self

        unit = QuantityUnit.from_string(name[-1])
        if unit == QuantityUnit.Yield:
            self.set_amount(value[-1], unit)
            return False
        if unit == QuantityUnit.Equivalent:
            dict_obj[-1]['yield'] = 0
            dict_obj[-1]['equivalent'] = 0
            self.set_amount(value[-1], unit)
            return False

        return True
