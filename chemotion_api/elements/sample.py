import json
import re
import copy
import warnings
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
from chemotion_api.utils import UnitDict, FixedDict, PropertyDict
from chemotion_api.utils.solvent_manager import get_solvent_info
from chemotion_api.elements.utils import GasType, QuantityUnit, calculate_quantity, GasCalculations


class GasPhaseObj(FixedDict):
    """
    Gas phase data of a gas product in a gas-phase reaction. Only the predefined keys can be set:
    ``time``, ``temperature`` and ``turnover_frequency`` (dicts with ``value`` and ``unit``),
    ``turnover_number`` and ``part_per_million``.
    """
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

    def __init__(self, sample: Sample, kwargs: dict | None = None):
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
        """Gas concentration in parts per million"""
        return self.data['part_per_million']

    @ppm.setter
    def ppm(self, value: float):
        self['part_per_million'] = value

    @property
    def time_in_h(self) -> float:
        """Reaction time in hours"""
        return convert_value_to_default(**self.data['time'])

    @time_in_h.setter
    def time_in_h(self, value: float):
        self['time'] = UnitDict(unit='h', value=value)

    @property
    def temperature_in_k(self) -> float:
        """Temperature in Kelvin"""
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

    def from_role(self, sample: Sample) -> Self:
        role = sample.role_in_reaction
        if role == 'starting_aterials':
            return SampleVariationType.STARTING_MATERIAL
        return SampleVariationType(role)


class SolventList(list):
    """
    A list of the solvents of a sample. Each entry is a dict with ``label``, ``smiles``, ``inchikey`` and ``ratio``.
    It allows to add molecules from the predefined solvent list or by SMILES code.
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

        :param name: Solvent Name (see :meth:`chemotion_api.Instance.get_solvent_list`)

        :raises KeyError: if the name is not in the solvent list
        """

        solvent_info = get_solvent_info(name)

        m = MoleculeManager(self._session).create_molecule_by_smiles(solvent_info['smiles'])
        self.append({
            "label": name,
            "smiles": m.get('cano_smiles'),
            "inchikey": m.get("inchikey"),
            "ratio": 1
        })


class Molecule(MutableMapping):
    """
    Contains the Molecule information. This class extends MutableMapping and can be used as normal dict object.
    It contains all data sent by the server and ensures that the following keys are set:
    ``boiling_point``, ``molecular_weight``, ``exact_molecular_weight``, ``cano_smiles``, ``density``,
    ``inchikey``, ``inchistring``, ``melting_point`` and ``sum_formular``.

    When the sample containing the molecule is saved, only these keys are sent:

    :key boiling_point: {float}
    :key cano_smiles: {str}
    :key density: {float}
    :key inchikey: {str}
    :key inchistring: {str}
    :key melting_point: {float}
    """

    def __init__(self, data):
        self.all_store = dict(data)
        self.id = data.get('id')
        for key in ["boiling_point", "molecular_weight", "exact_molecular_weight", "cano_smiles", "density", "inchikey",
                    "inchistring", "melting_point", "sum_formular"]:
            self.all_store[key] = self.all_store.get(key)

    def __getattr__(self, key: str):
        # Read-only attribute access to the keys, e.g. molecule.molecular_weight
        try:
            return self.__dict__['all_store'][key]
        except KeyError:
            raise AttributeError(f"'Molecule' object has no attribute or key '{key}'") from None

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
        """
        :return: the molecule data sent to the server when the sample is saved
        """
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
    The MoleculeManager can be used to load and create molecules in the Chemotion Instance
    """

    def __init__(self, session: Connection):
        self._session = session

    def create_molecule_by_smiles(self, smiles_code: str, density: float | None = None) -> Molecule:
        """
        Creates a new molecule for a given smiles code. If the molecule already exists on the server,
        the existing molecule is returned.

        :param smiles_code: SMILES code of the molecule
        :param density: density of the molecule. If None, the density stored on the server is kept
        :return: Molecule obj

        :raises ConnectionError: if the molecule cannot be created
        :raises ValueError: if the server cannot resolve the SMILES code (e.g. 'Mg' instead of '[Mg]')
        """
        smiles_url = "/api/v1/molecules/smiles"
        payload = {
            "editor": "ketcher",
            "smiles": smiles_code
        }
        res = self._session.post(smiles_url,
                                 data=json.dumps(payload))
        if res.status_code != 201:
            raise ConnectionError(f'{res.status_code} -> {res.text}')
        res_json = res.json()
        # For unresolvable SMILES the server answers 201 with an empty molecule. Saving a sample with it fails (500)
        if not res_json or res_json.get('id') is None:
            raise ValueError(f'The server could not create a molecule for the SMILES "{smiles_code}". '
                             f'Elements and ions need brackets, e.g. "[Mg]" instead of "Mg".')
        if density is not None:
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
    >>> # Save the structure image
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
        """
        The reaction the sample is part of, or None. It is loaded from the server if needed.
        """
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
        """
        Loads the reaction the sample is part of from the server.

        :raises KeyError: if the sample is not part of a reaction
        """
        from chemotion_api import Instance
        try:
            # A new sample has no tag (None)
            reaction_id = self.json_data['tag']['taggable_data']['reaction_id']
        except (KeyError, IndexError, TypeError):
            reaction_id = None
        if reaction_id is None:
            raise KeyError(f'Could not find Reaction of Sample: {self}')
        return Instance(self._session).get_reaction(reaction_id)

    @property
    def role_in_reaction(self) -> Literal[
        'starting_materials', 'reactants', 'products', 'solvents', 'purification_solvents']:
        """
        The material list of the reaction the sample is in: 'starting_materials', 'reactants', 'products',
        'solvents' or 'purification_solvents'. None if the sample is not part of a reaction.
        """
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

    def reload_role_in_reaction(self) -> Literal['starting_materials', 'reactants', 'products', 'solvents', 'purification_solvents'] | None:
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
    def properties(self) -> PropertyDict:
        """
        The properties property contains all data which can be altered
        through the chemotion api from the main tab of the sample.


        :key solvent: {:class:`chemotion_api.elements.sample.SolventList`}
        :key description: {str}
        :key external_label: {str}
        :key boiling_point_lowerbound: {int}
        :key boiling_point_upperbound: {int}
        :key melting_point_lowerbound: {int}
        :key melting_point_upperbound: {int}
        :key target_amount: {dict} has a unit {str} ('l', 'g' or 'mol') and a value {float}. The amount of the sample used as starting material or reactant.
        :key molarity: {dict} with value: float and unit: str
        :key real_amount: {dict} has a unit {str} ('l', 'g' or 'mol') and a value {float}. The amount of sample obtained from a reaction.
        :key stereo: {dict}
        :key location: {str}
        :key is_top_secret: {bool}
        :key is_restricted: {bool}
        :key purity: {float} between 0 (exclusive) and 1
        :key density: {float}
        :key user_labels: {list}
        :key decoupled: {bool}
        :key waste: {bool}
        :key reference: {bool} True if the sample is the reference material of its reaction
        :key metrics: {str}
        :key sum_formula: {str}
        :key equivalent: {float}
        :key coefficient: {int} must be > 0
        :key reaction_description: {str}
        :key molecular_mass: {float}
        :key gas_type: {:class:`chemotion_api.elements.utils.GasType`}
        :key inventory_sample: {bool}
        :key gas_phase_data: {:class:`chemotion_api.elements.sample.GasPhaseObj`} only for gas products
        :key position: {int} position in the material list of the reaction
        :key show_label: {bool}

        Setting the amount (``target_amount``, or ``real_amount`` for products), ``equivalent``, ``purity``,
        ``coefficient``, ``reference`` or ``gas_type`` of a sample in a reaction updates the dependent values of the
        reaction materials. Amounts can also be set with :meth:`set_amount`.

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
        self._load_if_partial()
        if self._molecule is None:
            return Molecule({})
        return self._molecule

    @molecule.setter
    def molecule(self, molecule: Molecule):
        """
        The molecule of the sample. Its density (or molarity) is copied to the sample if the sample has
        neither a density nor a molarity yet.
        """

        self._molecule = molecule
        self._apply_molecule_density_or_molarity()

    def _apply_molecule_density_or_molarity(self):
        if self._molecule is None:
            return
        properties = self.properties
        if properties.get('density') or properties['molarity'].get('value'):
            return
        density = self._molecule.get('density')
        # The server does not send a molarity for molecules, but it can be set on the Molecule object
        molarity = self._molecule.get('molarity')
        if density:
            properties['density'] = density
        elif isinstance(molarity, dict) and molarity.get('value'):
            properties['molarity'] = {'value': molarity['value'], 'unit': molarity.get('unit') or 'M'}
        elif isinstance(molarity, (int, float)) and molarity:
            properties['molarity'] = {'value': molarity, 'unit': 'M'}

    @property
    def vessel_size(self):
        """
        The vessel size of the reaction the sample is part of, or None
        """
        if self.reaction is None:
            return None
        return self.reaction.properties['vessel_size']

    @property
    def gram(self) -> float:
        """
        The amount of the sample in gram. For products the real amount is used, otherwise the target amount.
        """
        return self._get_converted_amount(QuantityUnit.Gram)

    @property
    def mol(self) -> float:
        """
        The amount of the sample in mol. For products the real amount is used, otherwise the target amount.
        """
        return self._get_converted_amount(QuantityUnit.Mole)

    @property
    def liter(self) -> float:
        """
        The amount of the sample in liter. For products the real amount is used, otherwise the target amount.
        Needs a density or molarity unless the amount is given in liter.
        """
        return self._get_converted_amount(QuantityUnit.Liter)

    def _get_converted_amount(self, output_unit):
        key = 'real_amount' if self.role_in_reaction == 'products' else 'target_amount'
        gp: GasPhaseObj = self.properties.get('gas_phase_data')
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
        """
        The equivalent of the sample relative to the reference material of its reaction
        """
        return self.properties['equivalent']

    @equivalent.setter
    def equivalent(self, equivalent: float):
        self.properties['equivalent'] = equivalent

    @property
    def is_mixture(self) -> bool:
        """
        True if the sample is a mixture. Mixtures are only partially supported: their components are
        passed through unchanged, and they can't be quantified in reaction variations.
        """
        sample_type = self.properties.get('sample_type', (self.json_data or {}).get('sample_type'))
        return sample_type == SampleType.SAMPLE_TYPE_MIXTURE.value

    @property
    def gas_type(self) -> GasType:
        """
        The gas type of the sample. Can only be set if the sample is part of a gas-phase reaction
        (``reaction.gas_schema``). See :meth:`set_gas_type`.
        """
        gt = self._properties.get('gas_type', GasType.OFF)
        if self.reaction is None and gt is not GasType.OFF:
            self.set_gas_type(GasType.OFF)
            return GasType.OFF
        return gt

    @property
    def reference(self) -> bool:
        """
        True if the sample is the reference material of its reaction
        """
        return self.properties['reference']

    @reference.setter
    def reference(self, ref: bool):
        self.set_ref(ref)

    @gas_type.setter
    def gas_type(self, gas_type: GasType | str):
        self.set_gas_type(gas_type)

    def set_gas_type(self, gas_type: GasType | str, reaction_update: bool = True):
        """
        Sets the gas type of the sample. Feedstock and catalyst can only be set for starting materials and
        reactants, gas only for products. A reaction has at most one feedstock and one catalyst; setting a
        new one resets the old one.

        :param gas_type: the gas type
        :param reaction_update: if true, the amounts of the reaction materials are updated

        :raises ValueError: if the gas type is not allowed for this sample
        """
        if isinstance(gas_type, str):
            gas_type = GasType(gas_type)

        if gas_type != GasType.OFF and self.reaction is None:
            raise ValueError('The sample is not part of a reaction. Set the gas type on the reaction material, '
                             'e.g. reaction.starting_materials[0].')
        if gas_type != GasType.OFF and not self.reaction.gas_schema:
            raise ValueError('Reaction is not a gas schema reaction. Set reaction.gas_schema = True first.')
        allowed_gas_types = self.allowed_gas_types()
        if gas_type not in allowed_gas_types:
            raise ValueError(f'Gas type {gas_type.value} is not allowed for {self.role_in_reaction}. '
                             f'Allowed: {", ".join(g.value for g in allowed_gas_types)}')
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

        image_url = f"/images/samples/{self._svg_file}"
        res = self._session.get(image_url)
        if res.status_code != 200:
            raise ConnectionError(f'{res.status_code} -> {res.text}')
        return res

    def split(self):
        """
        Splits the sample. The sample is saved first. The split is not saved.

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
        Copies the sample. The sample is saved first. The copy gets the next short label of the user
        and is not saved.

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
        """Toggles whether the sample is decoupled from its molecule"""
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

    def _set_serialized_if_exist(self, key: str, serialize_data: dict, origen_data: dict | None = None):
        if origen_data is None:
            value = self.properties.get(key, self.json_data.get(key, '____NOT_EXISTING____'))
        else:
            value = origen_data.get(key, '____NOT_EXISTING____')
        if value != '____NOT_EXISTING____':
            serialize_data[key] = value

    def allowed_gas_types(self) -> list[GasType]:
        """
        :return: the gas types this sample can have, depending on its role in the reaction
        """
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

    def allowed_quantity_units(self) -> list[QuantityUnit]:
        """
        :return: the units the amount of this sample can be set in, depending on its role in the
            reaction, gas type, density and molarity
        """
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
                # The amount of gas products is computed from the gas phase data
                if self.gas_type == GasType.GAS:
                    return default_set
                return default_set + [QuantityUnit.Mole]
        return default_set + [QuantityUnit.Mole]

    def update_equivalent(self):
        try:
            self._set_equivalent()
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            # Incomplete data (no amount, molecular weight or reference amount): the equivalent is unknown
            self._properties['equivalent'] = None

    def update_amount(self):
        amount = self.get_amount()
        unit = QuantityUnit.from_string(amount['unit'])
        allowed_units = self.allowed_quantity_units()
        if unit not in allowed_units:
            self.set_amount(0.0, allowed_units[-1])

    def _set_equivalent(self, value: float | None = None):
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
            self._properties['equivalent'] = get_equivalent(self, self.mol, ref_mol, ppm=ppm,
                                                            temperature_in_k=temperature_in_k)

    def set_ref(self, is_ref: bool, check_ref: bool = True):
        if check_ref:
            self.properties['reference'] = is_ref
        else:
            self._properties['reference'] = is_ref

    def get_amount(self):
        """
        :return: the real amount for products, otherwise the target amount, as dict with ``value`` and ``unit``
        """
        return self._properties[self._amount_key()]

    def _amount_key(self) -> str:
        return 'real_amount' if self.role_in_reaction == 'products' else 'target_amount'

    def set_amount(self, value: float, unit: QuantityUnit | str | None = None):
        """
        Sets the amount of the sample: the real amount for products, otherwise the target amount.
        The equivalents of the reaction materials are updated.

        :param value: the amount, must be >= 0
        :param unit: unit of the amount, see :meth:`allowed_quantity_units`. If None, the current unit is kept,
            or the first allowed unit is used if the sample has no unit yet.
            With :attr:`QuantityUnit.Equivalent <chemotion_api.elements.utils.QuantityUnit>` the amount is
            computed from the reference material.

        :raises ValueError: if the unit is not allowed or the value is negative
        :raises KeyError: if the unit is Yield
        """
        if isinstance(unit, str):
            unit_str = unit
            unit = QuantityUnit.from_string(unit_str)
            if unit is None:
                hint = ' The ppm of a gas product is properties["gas_phase_data"].ppm.' if unit_str.lower() == 'ppm' else ''
                raise ValueError(f'{unit_str} is not a valid unit. Valid units: '
                                 f'{", ".join(u.value for u in QuantityUnit if u is not QuantityUnit.Yield)}.{hint}')
        amount_dict = ['target_amount', 'real_amount']
        [key, zero_key] = amount_dict.__reversed__() if self.role_in_reaction == 'products' else amount_dict
        if unit is None:
            unit = QuantityUnit.from_string(self.properties[key]['unit'])

        allowed_units = self.allowed_quantity_units()
        if unit is None:
            # No unit stored yet (e.g. a new sample or a product without real amount): use the default unit
            unit = allowed_units[0]
        if unit not in allowed_units:
            raise ValueError(f'The amount of this sample cannot be set in {unit.value}. '
                             f'Allowed units: {", ".join(u.value for u in allowed_units)}')
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
            if self.reaction is not None:
                try:
                    self.reaction.update_equivalent()
                except (KeyError, ValueError, TypeError, ZeroDivisionError, AttributeError) as e:
                    warnings.warn(f'The equivalents of the reaction could not be updated: {e!r}')

    def on_properties_change(self, dict_obj, name, value):
        if name[0] in ['target_amount', 'real_amount']:
            amount = {**dict_obj[-1], name[-1]: value[-1]} if len(name) > 1 else dict(value[-1])
            # In a reaction, the amount of the sample's role goes through set_amount to update the equivalents
            if self.reaction is not None and name[0] == self._amount_key():
                try:
                    self.set_amount(amount.get('value'), amount.get('unit'))
                    return False
                except ValueError:
                    # Unit not (yet) allowed for this sample: store the value as it is
                    pass
            if len(name) > 1:
                return True
            self._properties[name[0]] = UnitDict(unit=amount.get('unit'), value=amount.get('value'))
            return False
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
                raise ValueError('The purity must be > 0 and <= 1')
            else:
                self._properties[name[-1]] = float(value[-1])
                if self.reaction is not None:
                    self.reaction.update_equivalent()
                return False
        if name[-1] == 'coefficient':
            if value[-1] <= 0:
                raise ValueError('The coefficient must be > 0')
            else:
                self._properties[name[-1]] = int(value[-1])
                if self.reaction is not None:
                    self.reaction.update_equivalent()
                return False
        if name[-1] == 'reference' and self.reaction is not None:
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
