import json
import re
import copy
from enum import Enum
from typing import Literal, Optional, Self

from requests import Response

from chemotion_api.elements.utils.converter import convert_value_to_default
from chemotion_api.elements.utils.equivalent import get_equivalent
from chemotion_api.user import User
from chemotion_api.elements.abstract_element import AbstractElement
from chemotion_api.elements.empty_elements import init_container
from collections.abc import MutableMapping
from chemotion_api.connection import Connection
from chemotion_api.utils import UnitDict, FixedDict
from chemotion_api.utils.solvent_manager import get_solvent_list
from chemotion_api.elements.utils import GasType, QuantityUnit, calculate_quantity, GasCalculations


class GasPhaseObj(FixedDict):
    default_val = {
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
    }

    def __init__(self, sample: 'Sample', kwargs: Optional[dict] = None):
        self._sample = sample
        if kwargs is None:
            kwargs = {**self.default_val}
        else:
            kwargs = copy.deepcopy(kwargs)
        kwargs['turnover_frequency'] = UnitDict(**kwargs['turnover_frequency'])
        kwargs['temperature'] = UnitDict(**kwargs['temperature'])
        kwargs['time'] = UnitDict(**kwargs['time'])
        super().__init__(kwargs)

    @property
    def ppm(self) -> float:
        return self.data['part_per_million']

    @ppm.setter
    def ppm(self, value: float):
        self['part_per_million'] = value

    @property
    def time_in_h(self) -> float:
        return convert_value_to_default(**self.data['time'])

    @time_in_h.setter
    def time_in_h(self, value: float):
        self['time'] = UnitDict(unit='h', value=value)

    @property
    def temperature_in_k(self) -> float:
        return convert_value_to_default(**self.data['temperature'])

    @temperature_in_k.setter
    def temperature_in_k(self, value: float):
        self['temperature'] = UnitDict(unit='K', value=value)

    def to_dict(self):
        return {
            **self.data,
            'turnover_frequency': self.data['turnover_frequency'].to_dict(),
            'temperature': self.data['temperature'].to_dict(),
            'time': self.data['time'].to_dict()
        }


class SampleType(Enum):
    SAMPLE_TYPE_MIXTURE = 'Mixture'
    SAMPLE_TYPE_MICROMOLECULE = 'Micromolecule'


class SampleVariationType(Enum):
    STARTING_MATERIAL = 'startingMaterials'
    REACTANT = 'reactants'
    PRODUCT = 'products'
    SOLVENTS = 'solvents'

    def from_role(self, sample: 'Sample') -> Self:
        role = sample.role_in_reaction
        if role == 'starting_aterials':
            return SampleVariationType.STARTING_MATERIAL
        return SampleVariationType(role)


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
        self.id = data.get('id')
        for key in ["boiling_point", "molecular_weight", "exact_molecular_weight", "cano_smiles", "density", "inchikey",
                    "inchistring", "melting_point", "sum_formular"]:
            self.all_store[key] = self.all_store.get(key)

    def __getitem__(self, key: str):
        key = self._keytransform(key)
        return self.all_store[key]

    def __setitem__(self, key: str, value):
        key = self._keytransform(key)
        self.all_store[key] = value

    def __delitem__(self, key):
        del self.all_store[self._keytransform(key)]

    def __iter__(self):
        return iter(self.all_store)

    def __len__(self):
        return len(self.all_store)

    def _keytransform(self, key):
        return key

    def clean(self) -> dict:
        return {
            "density": self.all_store.get("density"),
            "melting_point": self.all_store.get("melting_point"),
            "boiling_point": self.all_store.get("boiling_point"),
            "inchistring": self.all_store.get("inchistring"),
            "cano_smiles": self.all_store.get("cano_smiles"),
            "inchikey": self.all_store.get("inchikey")
        }


class MoleculeManager:
    """
    The MoleculeManager can be used to load and crate molecules in teh Chemotion Instance
    """

    def __init__(self, session: Connection):
        self._session = session

    def create_molecule_by_smiles(self, smiles_code: str, density: float = 0.0) -> Molecule:
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
        res_json = res.json()
        res_json['density'] = density
        return Molecule(res_json)

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

    material_types = ['starting_materials', 'reactants', 'products', 'solvents', 'purification_solvents']

    def __init__(self, *args, **kwargs):
        self._molecule = None
        self.is_split = False
        self._reaction = None
        self._role_in_reaction = None
        self._is_solvent = kwargs.pop("is_solvent", False)
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
        self._role_in_reaction = None
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

    @role_in_reaction.setter
    def role_in_reaction(self, role_in_reaction: Literal[
        'starting_materials', 'reactants', 'products', 'solvents', 'purification_solvents']):
        self._role_in_reaction = role_in_reaction
        if role_in_reaction not in self.material_types:
            raise ValueError(f'Unknown role: {role_in_reaction}')
        self._role_in_reaction = role_in_reaction

    def reload_role_in_reaction(self) -> Optional[Literal[
        'starting_materials', 'reactants', 'products', 'solvents', 'purification_solvents']]:
        if self.reaction is None:
            return None

        element: Literal['starting_materials', 'reactants', 'products', 'solvents', 'purification_solvents']
        for element in self.material_types:
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
    def vessel_size(self):
        if self.reaction is None:
            return None
        return self.reaction.properties['vessel_size']

    @property
    def gram(self):
        return self._get_converted_amount(QuantityUnit.Gram)

    @property
    def mol(self):
        return self._get_converted_amount(QuantityUnit.Mole)

    @property
    def liter(self):
        return self._get_converted_amount(QuantityUnit.Liter)

    def _get_converted_amount(self, output_unit):
        key = 'real_amount' if self.role_in_reaction == 'products' else 'target_amount'
        gp: GasPhaseObj= self.properties.get('gas_phase_data')
        if gp is not None:
            gas_attres = {'temperature_in_k': gp.temperature_in_k, 'ppm': gp.ppm, 'time_in_h': gp.time_in_h}

        else:
            gas_attres = {}
        return calculate_quantity(
            current_value=self.properties[key]['value'],
            current_unit=QuantityUnit.from_string(self.properties[key]['unit']),
            output_unit=output_unit,
            molecular_weight=self.molecule['molecular_weight'],
            purity=self.properties['purity'],
            molarity=self.properties['molarity']['value'],
            density=self.properties['density'],
            gas_type=self.gas_type,
            vessel_size=self.vessel_size,
            **gas_attres
        )

    @property
    def equivalent(self) -> float:
        return self.properties['equivalent']

    @equivalent.setter
    def equivalent(self, equivalent: float):
        self.properties['equivalent'] = equivalent

    @property
    def gas_type(self) -> GasType:
        gt = self._properties.get('gas_type', GasType.OFF)
        if self.reaction is None and gt is not GasType.OFF:
            self.set_gas_type(GasType.OFF)
            return GasType.OFF
        return gt

    @property
    def reference(self) -> bool:
        return self.properties['reference']

    @reference.setter
    def reference(self, ref: bool):
        self.set_ref(ref)

    @gas_type.setter
    def gas_type(self, gas_type: GasType | str):
        self.set_gas_type(gas_type)

    def set_gas_type(self, gas_type: GasType | str, reaction_update: bool = True):
        if isinstance(gas_type, str):
            gas_type = GasType(gas_type)

        if gas_type != GasType.OFF and self.reaction is not None and not self.reaction.gas_schema:
            raise ValueError(f'Reaction is not a gas schema reaction')
        if gas_type not in self.allowed_gas_types():
            raise ValueError(f'Reaction is not a gas schema reaction')
        has_change = self._properties['gas_type'] != gas_type and self.reaction is not None
        if has_change and gas_type in [GasType.FEEDSTOCK, GasType.CATALYST]:
            gas_elem = self.reaction.get_gas_component(gas_type)
            if gas_elem is not None:
                gas_elem.set_gas_type(GasType.OFF, False)
        origin_gas_type = self.gas_type
        self._properties['gas_type'] = gas_type
        if has_change and gas_type == GasType.GAS:
            self.properties['gas_phase_data'] = GasPhaseObj(self)
        if has_change and origin_gas_type == GasType.FEEDSTOCK:
            cat_sample = self.reaction.get_catalyst()
            if cat_sample is not None:
                cat_sample.gas_type = GasType.OFF
        if has_change and reaction_update:
            self.reaction.update_amount()

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
        self.save(True)
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
        split_sample['short_label'] += '-NaN'

        split_sample['container'] = init_container()
        return Sample(generic_segments=self._generic_segments, session=self._session, json_data=split_sample)

    def copy(self):
        """
        Splits the sample.

        :return: A new sample object
        :rtype: :class:`chemotion_api.elements.sample.Sample`
        """
        self.save()
        split_sample = copy.deepcopy(self.json_data)
        split_sample['id'] = None

        if 'tag' in split_sample:
            del split_sample['tag']
        split_sample['created_at'] = None
        split_sample['updated_at'] = None
        split_sample['is_split'] = False
        split_sample['is_new'] = True
        split_sample['short_label'] = User.load_me(self._session).get_next_short_label('sample')

        split_sample['container'] = init_container()
        return Sample(generic_segments=self._generic_segments, session=self._session, json_data=split_sample)

    def toggle_decoupled(self):
        """Decoupls the sample from the molecule"""
        self.properties['decoupled'] = not self.properties['decoupled']

    def clean_data(self, *args, **kwargs):
        serialize_data = super().clean_data(*args, **kwargs)
        if self._is_solvent:
            keys = ["real_amount_value", "gas_phase_data", "name", "boiling_point_lowerbound",
                    "boiling_point_upperbound", "melting_point_lowerbound",
                    "melting_point_upperbound", "dry_solvent", "equivalent", "sample_svg_file", "parent_id"]
            for key in keys:
                if key in serialize_data:
                    del serialize_data[key]
        return serialize_data

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

        if self.json_data.get('gas_phase_data') is not None:
            gas_props['gas_phase_data'] = GasPhaseObj(self, self.json_data.get('gas_phase_data'))

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

        keys = ["name", "boiling_point_lowerbound", "boiling_point_upperbound", "melting_point_lowerbound",
                "melting_point_upperbound", "dry_solvent", "equivalent", "sample_svg_file", "parent_id"]

        for key in keys:
            self._set_serialized_if_exist(key, serialize_data)

        serialize_data['description'] = self.properties.get('description')
        serialize_data['external_label'] = self.properties.get('external_label')
        serialize_data['short_label'] = self.properties.get('short_label')
        serialize_data['solvent'] = self.properties.get('solvent')
        serialize_data['stereo'] = self.properties.get('stereo').to_dict()
        serialize_data['location'] = self.properties.get('location')
        serialize_data['purity'] = self.properties.get('purity')
        serialize_data['user_labels'] = self.properties.get('user_labels')
        serialize_data['decoupled'] = self.properties.get('decoupled')
        serialize_data['density'] = self.properties.get('density')
        serialize_data['metrics'] = self.properties.get('metrics')

        serialize_data['is_top_secret'] = self.properties.get('is_top_secret')
        serialize_data['molarity_unit'] = self.properties.get('molarity').get('unit')
        serialize_data['molarity_value'] = self.properties.get('molarity').get('value')
        serialize_data['molecular_mass'] = self.properties.get('molecular_mass')

        serialize_data['waste'] = self.properties.get('waste')
        serialize_data['reference'] = self.properties.get('reference', False)
        serialize_data['sum_formula'] = self.properties.get('sum_formula')
        serialize_data['coefficient'] = self.properties.get('coefficient', 1)

        serialize_data['target_amount_unit'] = self.properties.get('target_amount').get('unit')
        serialize_data['target_amount_value'] = self.properties.get('target_amount').get('value')

        serialize_data['real_amount_unit'] = self.properties.get('real_amount').get('unit')
        serialize_data['real_amount_value'] = self.properties.get('real_amount').get('value')

        serialize_data['is_split'] = self.is_split

        serialize_data['molfile'] = self.json_data.get('molfile')
        serialize_data['inventory_sample'] = self.properties.get('inventory_sample')
        serialize_data['gas_type'] = self.properties.get('gas_type').value
        if self.gas_type == GasType.GAS and self.properties.get('gas_phase_data') is not None:
            serialize_data['gas_phase_data'] = self.properties.get('gas_phase_data').to_dict()
        else:
            serialize_data['gas_phase_data'] = None

        serialize_data['dry_solvent'] = self.json_data.get('dry_solvent')
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
            serialize_data['molfile'] = self.molecule['molfile']

        return serialize_data

    def _set_serialized_if_exist(self, key: str, serialize_data: dict, origen_data: Optional[dict] = None):
        if origen_data is None:
            value = self.properties.get(key, self.json_data.get(key, '____NOT_EXISTING____'))
        else:
            value = origen_data.get(key, '____NOT_EXISTING____')
        if value != '____NOT_EXISTING____':
            serialize_data[key] = value

    def allowed_gas_types(self):
        if self.reaction is None:
            return [GasType.OFF]
        if self.role_in_reaction in ['starting_materials', 'reactants']:
            feedstock_mat = self.reaction.get_feedstock()
            if feedstock_mat is not None:
                return [GasType.OFF, GasType.FEEDSTOCK, GasType.CATALYST]
            else:
                return [GasType.OFF, GasType.FEEDSTOCK]
        if self.role_in_reaction == 'products':
            return [GasType.OFF, GasType.GAS]
        return [GasType.OFF]

    def allowed_quantity_units(self):
        return self._allowed_quantity_units()

    def _allowed_quantity_units(self):
        if self.role_in_reaction == 'solvents':
            return [QuantityUnit.Liter]
        elif self.role_in_reaction == 'purification_solvents':
            return [QuantityUnit.Liter]
        else:
            if self.gas_type == GasType.FEEDSTOCK:
                default_set = [QuantityUnit.Liter]
            else:
                default_set = [QuantityUnit.Gram]
                if self.properties['density'] != 0 or self.properties['molarity']['value'] != 0:
                    default_set += [QuantityUnit.Liter]

            if self.role_in_reaction in ['starting_materials', 'reactants']:
                return default_set + [QuantityUnit.Mole, QuantityUnit.Equivalent]
            elif self.role_in_reaction == 'products':
                return default_set + []
        return default_set + [QuantityUnit.Mole]

    def update_equivalent(self):
        try:
            self._set_equivalent()
        except KeyError:
            self._properties['equivalent'] = None

    def update_amount(self):
        amount = self.get_amount()
        unit = QuantityUnit.from_string(amount['unit'])
        allowed_units = self.allowed_quantity_units()
        if unit not in allowed_units:
            self.set_amount(0.0, allowed_units[-1])

    def _set_equivalent(self, value: Optional[float] = None):
        unit = QuantityUnit.Equivalent
        if value is not None:
            if unit not in self.allowed_quantity_units():
                raise KeyError(
                    f'The value {unit.value}  cannot be set for this sample. This is most likely due to the role of this sample in the reaction.')
            self._properties['equivalent'] = value
            self.set_amount(self.reaction.reference_sample.mol * value, QuantityUnit.Mole)
        elif self.properties['reference']:
            self._properties['equivalent'] = 1
        else:
            try:
                ref_mol = self.reaction.reference_sample.mol
            except AttributeError:
                ref_mol = None
            try:
                ppm = self.properties.get('gas_phase_data').ppm
                temperature_in_k = self.properties.get('gas_phase_data').temperature_in_k
            except AttributeError:
                ppm = None
                temperature_in_k = None
            self._properties['equivalent'] = get_equivalent(self, self.mol, ref_mol, ppm=ppm, temperature_in_k=temperature_in_k)

    def set_ref(self, is_ref: bool, check_ref: bool = True):
        if check_ref:
            self.properties['reference'] = is_ref
        else:
            self._properties['reference'] = is_ref

    def get_amount(self):
        key = 'real_amount' if self.role_in_reaction == 'products' else 'target_amount'
        return self._properties[key]

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
        if value is None:
            value = 0.0
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
                self.reaction.update_equivalent()
            except (KeyError, ValueError, TypeError, ZeroDivisionError, AttributeError):
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
        if name[-1] == 'vessel_size':
            self._properties[name[-1]] = value[-1]
            return False
        if name[0] == 'gas_phase_data':
            dict_obj[-1][name[-1]] = value[-1]
            self.update_equivalent()
            return False
        if name[-1] == 'gas_type':
            self.gas_type = value[-1]
            return False

        if name[-1] == 'purity':
            if value[-1] <= 0 or value[-1] > 1:
                raise ValueError('The purity must be >= 0 and <= 1')
            else:
                self._properties[name[-1]] = float(value[-1])
                self.reaction.update_equivalent()
                return False
        if name[-1] == 'coefficient':
            if value[-1] <= 0:
                raise ValueError('The coefficient must be > 0')
            else:
                self._properties[name[-1]] = int(value[-1])
                self.reaction.update_equivalent()
                return False
        if name[-1] == 'reference':
            if value[-1]:
                self.reaction.reference_sample = self
            else:
                self.reaction.reference_sample = None

        unit = QuantityUnit.from_string(name[-1])
        if unit == QuantityUnit.Yield:
            self.set_amount(value[-1], unit)
            return False
        if unit == QuantityUnit.Equivalent:
            dict_obj[-1]['equivalent'] = 0
            self.set_amount(value[-1], unit)
            return False

        return True
