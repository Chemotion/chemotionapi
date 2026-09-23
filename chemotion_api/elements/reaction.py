from enum import Enum
from typing import Callable, Optional, Iterator, Literal

from requests import Response

from chemotion_api.elements.abstract_element import AbstractElement, Analyses, AnalysesList
from datetime import datetime

from chemotion_api.elements.sample import Sample, SampleVariationType
from chemotion_api.elements.utils import QuantityUnit, GasType
from chemotion_api.elements.schemas.reaction import schema, PURIFICATION_OPTIONS, STATUS_OPTIONS
from chemotion_api.utils import TypedList, quill_hedging, merge_dicts, PropertyDict
from collections.abc import MutableSequence


class MaterialList(TypedList):
    """
    A list which accepts only :class:`chemotion_api.elements.sample.Sample`'s.
    If you add a sample using th standard list-methods a splited sample will be created.
    Then the created sample will be added to the list.
    If the element has no ID, it will be saved.

    In order to avoid the splitting and the pre saving use the 'append_no_split'
    methode.
    """

    def __init__(self, reaction: 'Reaction',
                 mat_type: Literal['starting_materials', 'reactants', 'products', 'solvents', 'purification_solvents'],
                 *args):
        super().__init__(Sample, *args)
        self._reaction = reaction
        self._mat_type = mat_type

    def _prepare_element(self, element: Sample):
        if self._mat_type == 'starting_materials':
            return_element = element.split()
        elif self._mat_type == 'reactants':
            return_element = element.split()
            return_element.properties['short_label'] = 'reactant'
        elif self._mat_type == 'products':
            return_element = element.copy()
        elif self._mat_type == 'solvents':
            return_element = element
        elif self._mat_type == 'purification_solvents':
            return_element = element
        else:
            raise ValueError("Unknown material type.")
        return_element.reaction = self._reaction
        return_element.role_in_reaction = self._mat_type
        return_element.set_ref(False, False)
        return_element.properties['position'] = len(self)

        return return_element

    def after_append(self, element: Sample):
        try:

            element.set_amount(**element.get_amount())
        except ValueError or KeyError:
            element.set_amount(0, element.allowed_quantity_units()[0])

    def append_no_split(self, element: Sample):
        """
        Add a Sample without splitting it
        :param element: Sample to be added
        """

        self._check_element(element)
        return super(TypedList, self).append(element)


class SampleVariation:
    def __init__(self, sample: Sample, sample_type: SampleVariationType, vessel_volume: Optional[float],
                 json_data: Optional[dict] = None, get_ref_amount: Optional[Callable[[], float]] = None):
        self._sample = sample
        self._sample_type = sample_type
        if get_ref_amount is not None:
            self._get_ref_amount = get_ref_amount
        else:
            self._get_ref_amount = lambda: 1
        if json_data is None:
            self._values = {
                               "aux": {
                                   "coefficient": 1,
                                   "isReference": False,
                                   "loading": None,
                                   "density": None,
                                   "purity": 1,
                                   "molarity": 0,
                                   "molecularWeight": 0,
                                   "sumFormula": "",
                                   "gasType": "off",
                                   "vesselVolume": vessel_volume,
                                   "materialType": sample_type.value
                               }
                           } | self._new_default_quantities()
            self._set_aux(vessel_volume)
            self._set_quantity_from_sample()
        else:
            self._values = json_data
            self._set_aux(vessel_volume)

    def set_aux(self, vessel_volume: float):
        self._set_aux(vessel_volume)

    def clean(self):
        self._update_equivalent()
        return self._values

    def potential_units(self):
        if self._sample_type is SampleVariationType.SOLVENTS:
            return [QuantityUnit.Liter]

        units = [QuantityUnit.Mole, QuantityUnit.Gram]
        if self._sample_type is SampleVariationType.PRODUCT:
            units.append(QuantityUnit.Yield)
        elif not self.is_ref:
            units.append(QuantityUnit.Equivalent)

        return units

    @property
    def is_ref(self) -> bool:
        return bool(self._values['aux']['isReference'])

    def set_equivalent(self, value):
        if self._sample_type in [SampleVariationType.PRODUCT, SampleVariationType.SOLVENTS]:
            raise ValueError("Sample type must not be PRODUCT or SOLVENTS.")
        if self.is_ref:
            raise ValueError("Sample type must not be the reference material.")
        self._values['amount']['value'] = self._get_ref_amount() * value
        self._values['equivalent']['value'] = self._get_ref_amount() * value

    def set_yield(self, value):
        if self._sample_type != SampleVariationType.PRODUCT:
            raise ValueError("Sample type must be PRODUCT.")
        if self.is_ref:
            raise ValueError("Sample type must not be the reference material.")
        self._values['amount']['value'] = self._get_ref_amount() * value
        self._values['amount']['yield'] = value

    def _update_equivalent(self):
        if 'mass' in self._values:
            self._values['mass']['value'] = self.get_mass()
        if 'volume' in self._values:
            self._values['volume']['value'] = self.get_volume()
        if 'yield' in self._values:
            self._values['yield']['value'] = value = self.get_equivalent_or_yield()
        if 'equivalent' in self._values:
            self._values['equivalent']['value'] = value = self.get_equivalent_or_yield()

    def _set_quantity_from_sample(self):
        value = self._sample.get_amount()
        self.set_quantity(**value)

    def set_quantity(self, value: float, unit: str | QuantityUnit | None):
        # TODO: Gas Type not None elements!!!
        # ToDo: How are Gas Types calculated (Volume ????)
        if value is None:
            value = 0.0
        if isinstance(unit, QuantityUnit):
            unit = unit.value

        if self._sample_type == SampleVariationType.SOLVENTS:
            self._values['volume']['value'] = value
            return
        if unit is None:
            unit = QuantityUnit.Mole.value
        if unit == QuantityUnit.Equivalent.value:
            self.set_equivalent(value)
        elif unit == QuantityUnit.Yield.value:
            self.set_yield(value)
        elif unit == QuantityUnit.Gram.value:
            self._values['amount']['value'] = (value / self._molecular_weight()) * self._values['aux']['purity']
        elif unit == QuantityUnit.Mole.value:
            self._values['amount']['value'] = value
        elif unit == QuantityUnit.Liter.value and self._values['aux']['molarity'] != 0:
            self._values['amount']['value'] = (value / self._values['aux']['molarity'])
        else:
            raise ValueError(f"{self._sample_type.value} can't be quantified as {unit}.")
        self._update_equivalent()

    def get_equivalent_or_yield(self):
        try:
            return self._values['amount']['value'] / self._get_ref_amount()
        except ZeroDivisionError:
            return 0

    def get_amount(self):
        return self._values['amount']['value']

    def get_volume(self):
        if self._values.get('volume') is None:
            self._values['volume'] = {'value': 0, 'unit': 'l'}
        if self._values['volume']['value']:
            return self._values['volume']['value']
        elif self._values['aux']['molarity']:
            return self.get_amount() * self._values['aux']['molarity']
        elif self._values['aux']['density']:
            return self.get_mass() / (self._values['aux']['density'] * 1000)
        return 0

    def get_mass(self):
        return self.get_amount() * self._values['aux']['purity'] / self._molecular_weight()

    def _molecular_weight(self):
        if not self._values['aux']['molecularWeight']:
            return 1
        return self._values['aux']['molecularWeight']

    def _set_aux(self, vessel_volume: float):
        # TODO: [DONE] get density, molarity from sample (NOT only for new Variations)!!!!
        self._values['aux']['coefficient'] = self._sample.properties['coefficient']
        self._values['aux']['purity'] = self._sample.properties['purity']
        self._values['aux']['isReference'] = self._sample.properties['reference']
        self._values['aux']['molecularWeight'] = self._sample.molecule['molecular_weight']
        self._values['aux']['sumFormula'] = self._sample.molecule['sum_formular']
        self._values['aux']['molarity'] = self._sample.properties['molarity']['value']
        self._values['aux']['density'] = self._sample.properties['density']
        self._values['aux']['gasType'] = self._sample.properties['gas_type'].value
        self._values['aux']['vesselVolume'] = vessel_volume
        self._values['aux']['materialType'] = self._sample_type.value

    @property
    def sample(self) -> Sample:
        return self._sample

    def _new_default_quantities(self):
        if self._sample_type in [SampleVariationType.STARTING_MATERIAL, SampleVariationType.REACTANT]:
            return {
                "mass": {
                    "value": 0.0,
                    "unit": "g"
                },
                "amount": {
                    "value": 0.0,
                    "unit": "mol"
                },
                "volume": {
                    "value": 0.0,
                    "unit": 'l'
                },
                "equivalent": {
                    "value": 0.0,
                    "unit": None
                }
            }
        if self._sample_type == SampleVariationType.PRODUCT:
            return {
                "mass": {
                    "value": 0.0,
                    "unit": "g"
                },
                "amount": {
                    "value": 0.0,
                    "unit": "mol"
                },
                "volume": {
                    "value": 0.0,
                    "unit": 'l'
                },
                "yield": {
                    "value": 0.0,
                    "unit": None
                }
            }
        if self._sample_type == SampleVariationType.SOLVENTS:
            return {
                "volume": {
                    "value": 0.0,
                    "unit": "l"
                }
            }
        raise ValueError(f'Sample type: {self._sample_type.value} is not supported.')


class Variation:
    def __init__(self):
        self.id = -1
        self._json_data = None
        self._properties = {}
        self.notes = ""
        self._ref_mat = None
        self._materials = {}
        self._analyses = None

    def get_ref_amount(self):
        if self._ref_mat is None:
            self._ref_mat = next((mat for key, x in self._materials.items() for mat in x if mat.is_ref), None)
        if self._ref_mat is None:
            return 1
        return self._ref_mat.get_amount()

    def populate(self, json_data: dict, analyses: AnalysesList, starting_materials: MaterialList,
                 reactants: MaterialList,
                 products: MaterialList, solvents: MaterialList, vessel_size: dict):
        self._json_data = json_data
        self.id = self._json_data['id']
        self._properties = json_data['properties']
        self.notes = json_data['metadata']['notes']
        self._analyses = analyses
        self._materials = {
            SampleVariationType.STARTING_MATERIAL: [
                self.sample_variation_factory(x, SampleVariationType.STARTING_MATERIAL, vessel_size) for x in
                starting_materials],
            SampleVariationType.REACTANT: [self.sample_variation_factory(x, SampleVariationType.REACTANT, vessel_size)
                                           for x in
                                           reactants],
            SampleVariationType.PRODUCT: [self.sample_variation_factory(x, SampleVariationType.PRODUCT, vessel_size) for
                                          x in
                                          products],
            SampleVariationType.SOLVENTS: [self.sample_variation_factory(x, SampleVariationType.SOLVENTS, vessel_size)
                                           for x in
                                           solvents],
        }

    def sample_variation_factory(self, sample: Sample, sample_type: SampleVariationType,
                                 vessel_size: dict) -> SampleVariation:
        json_data = None
        for key, data in self._json_data.get(sample_type.value, {}).items():
            if key == str(sample.id):
                json_data = data

        vessel_volume = self._get_vessel_volume(vessel_size)

        return SampleVariation(sample, sample_type, vessel_volume, json_data, self.get_ref_amount)

    @staticmethod
    def _get_vessel_volume(vessel_size):
        vessel_volume = vessel_size.get('amount')
        if vessel_volume is not None and vessel_size.get('unit') == 'l':
            vessel_volume *= 1000
        return vessel_volume

    def update_and_clean(self, vessel_size):
        vessel_volume = self._get_vessel_volume(vessel_size)
        for sample_type, sample_variations in self._materials.items():
            for sample_variation in sample_variations:
                sample_variation.set_aux(vessel_volume)
        return self.clean()

    def clean(self):
        self._json_data['properties'] = self._properties
        self._json_data['metadata']['notes'] = self.notes
        for sample_type, sample_variations in self._materials.items():
            self._json_data[sample_type.value] = {}
            for sample_variation in sample_variations:
                self._json_data[sample_type.value][sample_variation.sample.id] = sample_variation.clean()
        return self._json_data

    def link_analyses(self, analyses: Analyses):
        try:
            int(analyses.id)
            self._json_data['metadata']['analyses'].append(analyses.id)
        except ValueError:
            raise ValueError("Analyses has no id. please save the Reaction first")

    def get_analyses(self) -> Iterator[Analyses]:
        for ana_id in self._json_data['metadata']['analyses']:
            yield self._analyses.by_id(ana_id)

    @property
    def properties(self):
        return self._properties

    @property
    def starting_materials(self) -> list[SampleVariation]:
        return self._materials[SampleVariationType.STARTING_MATERIAL]

    @property
    def reactants(self) -> list[SampleVariation]:
        return self._materials[SampleVariationType.REACTANT]

    @property
    def products(self) -> list[SampleVariation]:
        return self._materials[SampleVariationType.PRODUCT]

    @property
    def solvents(self) -> list[SampleVariation]:
        return self._materials[SampleVariationType.SOLVENTS]


class Variations(MutableSequence):
    def __init__(self, analyses: AnalysesList, starting_materials: MaterialList, reactants: MaterialList,
                 products: MaterialList,
                 solvents: MaterialList, vessel_size: Callable[[], dict]):
        # Initialize the list with given items
        self._data = list()
        self._materials = {'starting_materials': starting_materials, 'reactants': reactants, 'products': products,
                           'solvents': solvents}
        self._highest_id = 0
        self._analyses = analyses
        self._get_vessel_size = vessel_size

    def populate(self, json_data: dict):
        for variation in json_data:
            v = Variation()
            v.populate(variation, self._analyses, **self._materials, vessel_size=self._get_vessel_size())
            self.append(v)
            self._highest_id = max(self._highest_id, variation['id'])

    def remove(self, value: Variation) -> bool:
        try:
            idx = next(idx for idx, v in enumerate(self) if v.id == value.id)
            self.pop(idx)
        except StopIteration:
            return False
        return True

    def add_new(self) -> Variation:
        self._highest_id += 1
        variation = self.empty_variation(self._highest_id)
        v = Variation()
        v.populate(variation, self._analyses, **self._materials, vessel_size=self._get_vessel_size())
        self.append(v)
        return v

    @classmethod
    def empty_variation(cls, highest_id: int) -> dict:
        return {
            "id": highest_id,
            "properties": {
                "temperature": {
                    "value": 0,
                    "unit": "°C"
                },
                "duration": {
                    "value": 0,
                    "unit": "Second(s)"
                }
            },
            "metadata": {
                "notes": "",
                "analyses": []
            },
            "reactants": {},
            "products": {},
            "solvents": {},
            "startingMaterials": {}
        }

    def sort(self):
        self._data = sorted(self._data, key=lambda v: v.id)

    def clean(self):
        return [variation.update_and_clean(self._get_vessel_size()) for variation in self._data]

    def _prepare_variation(self, json_data: dict):
        empty_variation = self.empty_variation(self._highest_id)
        return merge_dicts(empty_variation, json_data)

    def __getitem__(self, index):
        # Retrieve the item at the given index
        return self._data[index]

    def __setitem__(self, index, value):
        # Set the item at the given index
        self._data[index] = value
        self.sort()

    def __delitem__(self, index):
        # Delete the item at the given index
        del self._data[index]

    def insert(self, index, value):
        # Insert an item at the given index
        self._data.insert(index, value)
        self.sort()

    def __len__(self):
        # Return the length of the list
        return len(self._data)

    def __repr__(self):
        # Return a string representation of the list
        return f"{repr(self._data)}"


class Temperature(dict):
    """
    This object contains the  temperature-time profile, the temperature unit and a user text.
    Each entry contains a time as 'hh:mm:ss' and a temperature as integer.

    :key data: {list} the temperature-time profile
    :key userText: {str}
    :key valueUnit: {str}
    """

    def __init__(self, **kwargs):
        super().__init__(data=kwargs.get('data', []),
                         userText=kwargs.get('userText', ''),
                         valueUnit=kwargs.get('valueUnit', "°C")
                         )

    def add_time_point(self, hour: int, minute: int, second: int, temperature: float):
        """
        Adds an entry to the Temperature timeline

        :param hour: since the reaction has started
        :param minute: since the reaction has started
        :param second: since the reaction has started
        :param temperature: degrees
        """
        data = self.get('data')
        if data is None:
            self['data'] = []
            data = self['data']
        data.append(
            {'time': f'{str(hour).zfill(2)}:{str(minute).zfill(2)}:{str(second).zfill(2)}', 'value': str(temperature)})


class Reaction(AbstractElement):
    """
    A chemotion Reaction object.
    It extends the :class:`chemotion_api.elements.abstract_element.AbstractElement`

    Usage::

    >>> from chemotion_api import Instance
    >>> from chemotion_api.collection import Collection
    >>> import logging
    >>> try:
    >>>     instance = Instance('http(d)://xxx.xxx.xxx').test_connection().login('<USER>', "<PASSWORD>")
    >>> except ConnectionError as e:
    >>>     logging.error(f"A connection to Chemotion ({instance.host_url}) cannot be established")
    >>> # Get the reaction with ID 1
    >>> rea = instance.get_reaction(1)
    >>> # Set the real amount to 3.7 g
    >>> col_solv: Collection = instance.get_root_collection().get_or_create_collection('Solv')
    >>> # Create a new solvent CDCl3
    >>> solv = col_solv.new_solvent('CDCl3')
    >>> # Add CDCl3 as solvent to the reaction
    >>> rea.solvents.append(solv)
    >>> # Add a split of sample with ID 1 as starting material
    >>> rea.starting_materials.append(instance.get_sample(1))
    >>> # Add a new time/temperature step to the temperature timeline
    >>> rea.properties['temperature'].add_time_point(2,3,0,100)
    >>> rea.save()
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._variations = None

    datetime_format = '%m/%d/%Y %H:%M:%S'

    def _set_json_data(self, json_data: dict):
        super()._set_json_data(json_data)
        self._svg_file = self.json_data.get('reaction_svg_file')

    def load_image(self) -> Response:
        """
        Loads the reaction structure as svg image

        :return: Response with the svg as content
        """

        image_url = "/images/reactions/{}".format(self._svg_file)
        res = self._session.get(image_url)
        if res.status_code != 200:
            raise ConnectionError('{} -> {}'.format(res.status_code, res.text))
        return res

    def properties_schema(self) -> dict:
        """
        Returns the JSON.org schema of the cleaned properties.

        :return: JSON.org schema
        """

        return schema

    @property
    def properties(self) -> PropertyDict:
        """
        The properties property contains all data which can be altered
        through the chemotion api from the main tab of the reaction.


        :key starting_materials: {:class:`chemotion_api.elements.reaction.MaterialList`}
        :key reactants:  {:class:`chemotion_api.elements.reaction.MaterialList`}
        :key products: {:class:`chemotion_api.elements.reaction.MaterialList`}
        :key solvents: {:class:`chemotion_api.elements.reaction.MaterialList`}
        :key purification_solvents: {:class:`chemotion_api.elements.reaction.MaterialList`}
        :key temperature: {:class:`chemotion_api.elements.reaction.Temperature`}
        :key timestamp_start: {datetime.datetime}
        :key timestamp_stop: {datetime.datetime}
        :key name: {str}
        :key description: {str|dict} A Guill.js text (https://quilljs.com/docs/delta)
        :key observation: {str|dict} A Guill.js text (https://quilljs.com/docs/delta)
        :key purification: {list[str]} values must be in ['Flash-Chromatography', 'TLC', 'HPLC', 'Extraction', 'Distillation', 'Dialysis', 'Filtration', 'Sublimation', 'Crystallisation', 'Recrystallisation', 'Precipitation']
        :key status: {str} value must be in ['', 'Planned', 'Running', 'Done', 'Analyses Pending', 'Successful',
                                          'Not Successful']
        :key vessel_size: {dict} has a unit {str} ('l' or 'ml') and an amount {float}

        Readonly properties:

        :key short_label: {str, readonly}
        :key tlc_solvents: {str, readonly}
        :key tlc_description: {str, readonly}
        :key reaction_svg_file: {str, readonly}
        :key role: {str, readonly}
        :key rf_value: {str, readonly}
        :key rxno: {str, readonly}
        :key literatures: {str, readonly}
        :key variations: {str, readonly} Can be used with the reaction class property variations

        :return: Element properties
        """
        return super().properties

    @property
    def variations(self) -> 'Variations':
        if self._variations is None:
            mat_samples = {}
            for reaction_elm_names in ['starting_materials', 'reactants', 'products', 'solvents']:
                mat_samples[reaction_elm_names] = self.properties[reaction_elm_names]
            self._variations = Variations(self.analyses, **mat_samples,
                                          vessel_size=lambda: self.properties.get('vessel_size'))
            self._variations.populate(self.json_data['variations'])

        return self._variations

    @property
    def starting_materials(self) -> MaterialList:
        return self.properties['starting_materials']

    @property
    def reactants(self) -> MaterialList:
        return self.properties['reactants']

    @property
    def products(self) -> MaterialList:
        return self.properties['products']

    @property
    def solvents(self) -> MaterialList:
        return self.properties['solvents']

    @property
    def purification_solvents(self) -> MaterialList:
        return self.properties['purification_solvents']

    @property
    def reference_sample(self) -> Optional[Sample]:
        first_sample = None
        for mat in [*self.starting_materials, *self.reactants]:
            if first_sample is None:
                first_sample = mat
            if mat.properties['reference']:
                return mat
        if mat is not None:
            mat.properties['reference'] = True
        return mat

    @reference_sample.setter
    def reference_sample(self, value: Sample | None):
        id = None if value is None else value.id
        for mat in [*self.starting_materials, *self.reactants]:
            mat.set_ref(mat.id == id, False)
        for mat in [*self.products, *self.solvents, *self.purification_solvents]:
            mat.set_ref(mat.id == id, False)
        self.update_equivalent()

    @property
    def gas_schema(self) -> bool:
        return self._properties.get('gaseous', False)

    @gas_schema.setter
    def gas_schema(self, gaseous: bool):
        self._properties['gaseous'] = gaseous
        if not gaseous:
            for mat in [*self.starting_materials, *self.reactants, *self.products, *self.solvents,
                        *self.purification_solvents]:
                mat.set_gas_type('off', False)
        self.update_equivalent()

    def get_feedstock(self) ->  Sample | None:
        return self.get_gas_component(GasType.FEEDSTOCK)

    def get_catalyst(self) -> Sample | None:
        return self.get_gas_component(GasType.CATALYST)

    def get_gas_component(self, gt: GasType):
        if self.gas_schema:
            for mat in [*self.starting_materials, *self.reactants]:
                if mat.gas_type == gt:
                    return mat
        return None


    def update_amount(self):
        for mat in [*self.starting_materials, *self.reactants, *self.products, *self.solvents,
                    *self.purification_solvents]:
            mat.update_amount()

    def update_equivalent(self):
        for mat in [*self.starting_materials, *self.reactants, *self.products, *self.solvents,
                    *self.purification_solvents]:
            mat.update_equivalent()

    def _parse_properties(self) -> dict:
        reaction_elements = {}
        for reaction_elm_names in ['starting_materials', 'reactants', 'products', 'solvents', 'purification_solvents']:
            obj_list = self.json_data[reaction_elm_names]
            temp = []
            for sample in obj_list:
                sample_obj = Sample(self._generic_segments, self._session, sample)
                sample_obj.reaction = self
                temp.append(sample_obj)
            reaction_elements[reaction_elm_names] = MaterialList(self, reaction_elm_names, temp)

        try:
            timestamp_start = datetime.strptime(self.json_data.get('timestamp_start'), self.datetime_format)
        except:
            timestamp_start = None
        try:
            timestamp_stop = datetime.strptime(self.json_data.get('timestamp_stop'), self.datetime_format)
        except:
            timestamp_stop = None
        return reaction_elements | {
            'timestamp_start': timestamp_start,
            'timestamp_stop': timestamp_stop,
            'description': self.json_data.get('description'),
            'name': self.json_data.get('name'),
            'observation': self.json_data.get('observation'),
            'purification': self.json_data.get('purification'),
            'dangerous_products': self.json_data.get('dangerous_products'),
            'conditions': self.json_data.get('conditions'),
            'rinchi_long_key': self.json_data.get('rinchi_long_key'),
            'rinchi_web_key': self.json_data.get('rinchi_web_key'),
            'rinchi_short_key': self.json_data.get('rinchi_short_key'),
            'duration': self.json_data.get('duration'),
            'rxno': self.json_data.get('rxno'),
            'temperature': Temperature(**self.json_data.get('temperature', {})),
            'status': self.json_data.get('status'),
            'vessel_size': self.json_data.get('vessel_size'),
            'gaseous': self.json_data.get('gaseous')
            # 'tlc_solvents': self.jreaction.properties['reactants']son_data.get('tlc_solvents'),
            # 'tlc_description': self.json_data.get('tlc_description'),
            # 'rf_value': self.json_data.get('rf_value'),
        }

    def _clean_properties_data(self, serialize_data: dict | None = None) -> dict:
        if serialize_data is None:
            serialize_data = {}
        serialize_data['materials'] = {}
        for reaction_elm_names in ['starting_materials', 'reactants', 'products', 'solvents', 'purification_solvents']:
            temp_json_sample = self.json_data[reaction_elm_names]
            serialize_data['materials'][reaction_elm_names] = []
            for sample in self.properties[reaction_elm_names]:
                origen = next((x for x in temp_json_sample if x['id'] == sample.id), {})
                serialize_data['materials'][reaction_elm_names].append(origen | sample.clean_data())

        try:
            timestamp_start = self.properties.get('timestamp_start').strftime(self.datetime_format)
        except:
            timestamp_start = ''
        try:
            timestamp_stop = self.properties.get('timestamp_stop').strftime(self.datetime_format)
        except:
            timestamp_stop = ''
        serialize_data['name'] = self.properties.get('name')
        serialize_data['description'] = quill_hedging(self.properties.get('description'), 'Description')
        serialize_data['dangerous_products'] = self.properties.get('dangerous_products')
        serialize_data['conditions'] = self.properties.get('conditions')
        serialize_data['duration'] = self.properties.get('duration')
        serialize_data |= self._calc_duration()
        serialize_data['timestamp_start'] = timestamp_start
        serialize_data['timestamp_stop'] = timestamp_stop
        serialize_data['temperature'] = self.properties.get('temperature')
        serialize_data['observation'] = quill_hedging(self.properties.get('observation'), 'Observation')

        serialize_data['status'] = self.properties.get('status')
        if self.properties.get('status') in STATUS_OPTIONS:
            serialize_data['status'] = self.properties.get('status')
        else:
            serialize_data['status'] = self.json_data.get('status')

        if self.properties.get('purification') is list:
            serialize_data['purification'] = [x for x in self.properties.get('purification') if
                                              x in PURIFICATION_OPTIONS]
        else:
            serialize_data['purification'] = self.json_data.get('purification')

        if self.properties.get('vessel_size') is not None:
            serialize_data['vessel_size'] = self.properties.get('vessel_size')

        serialize_data['role'] = self.properties.get('role', '')
        serialize_data['gaseous'] = self.properties.get('gaseous')
        serialize_data['tlc_solvents'] = self.json_data.get('tlc_solvents')
        serialize_data['tlc_description'] = self.json_data.get('tlc_description')
        serialize_data['reaction_svg_file'] = self.json_data.get('reaction_svg_file')

        serialize_data['rf_value'] = self.json_data.get('rf_value')
        serialize_data['rxno'] = self.json_data.get('rxno', '')
        serialize_data['short_label'] = self.json_data.get('short_label')
        serialize_data['literatures'] = self.json_data.get('literatures')

        serialize_data['research_plans'] = self.json_data.get('research_plans')
        serialize_data['user_labels'] = self.json_data.get('user_labels')
        serialize_data['solvent'] = self.json_data.get('solvent')

        serialize_data['variations'] = self._clean_variations()

        return serialize_data

    def _calc_duration(self):
        a, b = self.properties.get('timestamp_stop'), self.properties.get('timestamp_start')
        if not isinstance(a, datetime) or not isinstance(b, datetime):
            return {
                'durationDisplay': self.json_data.get('durationDisplay'),
                'durationCalc': self.json_data.get('durationCalc')
            }
        c = a - b

        h = int(c.seconds / (60 * 60))
        m = int(c.seconds % (60 * 60) / 60)
        s = c.seconds % 60
        text = []
        total_unit = None
        total_time = 0
        total_factor = 0
        for (time, unit, factor) in ((c.days, 'day', 1), (h, 'hour', 24), (m, 'minute', 60), (s, 'second', 60)):
            total_factor *= factor
            if time > 0:
                if total_unit is None:
                    total_unit = unit + "(s)"
                    total_factor = 1
                total_time += time / total_factor
                text.append(f"{time} {unit}{'s' if time > 1 else ''}")
        return {'durationCalc': ' '.join(text),
                'durationDisplay': {
                    "dispUnit": total_unit,
                    "dispValue": f"{int(total_time)}",
                    "memUnit": total_unit,
                    "memValue": "{:0.15f}".format(total_time)
                }
                }

    def on_properties_change(self, dict_obj, name, value):
        if name[-1] == 'gaseous':
            self.gas_schema = value[-1]
            return False
        if name[-1] == 'vessel_size':
            self._properties['vessel_size'] = value[-1]
            self.update_amount()
            return False
        return True

    def _clean_variations(self) -> dict:
        cleand_data = self.variations.clean()
        self._variations = None
        return cleand_data
