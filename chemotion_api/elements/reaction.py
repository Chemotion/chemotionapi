from enum import Enum
from typing import Callable, Optional, Iterator

from requests import Response

from chemotion_api.elements.abstract_element import AbstractElement, Analyses, AnalysesList
from datetime import datetime

from chemotion_api.elements.sample import Sample
from chemotion_api.elements.schemas.reaction import schema, PURIFICATION_OPTIONS, STATUS_OPTIONS
from chemotion_api.utils import TypedList, quill_hedging
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

    def __init__(self, *args):
        super().__init__(Sample, *args)

    def _prepare_element(self, element: Sample):
        if element.id is None:
            element.save()
        return element.split()

    def append_no_split(self, element: Sample):
        """
        Add a Sample without splitting it
        :param element: Sample to be added
        """

        self._check_element(element)
        return super(TypedList, self).append(element)


class SampleVariationType(Enum):
    STARTING_MATERIAL = 'startingMaterials'
    REACTANT = 'reactants'
    PRODUCT = 'products'
    SOLVENTS = 'solvents'


class QuantityUnit(Enum):
    Liter = 'l'
    Mole = 'mol'
    Gram = 'g'
    Equivalent = 'Equivalent'


class SampleVariation():

    def __init__(self, sample: Sample, sample_type: SampleVariationType, json_data: dict | None = None,
                 get_ref_amount: Optional[Callable] = None):
        self._sample = sample
        self._sample_type = sample_type
        if get_ref_amount is not None:
            self._get_ref_amount = get_ref_amount
        else:
            self._get_ref_amount = lambda: 1
        if json_data is None:
            self._values = {
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
                    "unit": "l"
                },
                "aux": {
                    "coefficient": 1,
                    "isReference": False,
                    "loading": None,
                    "purity": 1,
                    "molarity": 0,
                    "molecularWeight": 0,
                    "sumFormula": "C7H12O6",
                    "yield": None,
                    "equivalent": None
                }
            }
            self._set_aux()
            self._set_quantity_from_sample()
        else:
            self._values = json_data
            self._set_aux()

    def clean(self):
        self._update_equivalent()
        return self._values

    def potential_units(self):
        if self._sample_type is SampleVariationType.SOLVENTS:
            return [QuantityUnit.Liter]

        units = [QuantityUnit.Mole, QuantityUnit.Gram]
        if self._values['aux']['molarity'] != 0:
            units.append(QuantityUnit.Liter)
        elif self._sample_type is not SampleVariationType.PRODUCT and not self.is_ref:
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

    def _update_equivalent(self):
        self._values['mass']['value'] = self.get_mass()
        self._values['volume']['value'] = self.get_volume()
        if self._sample_type in [SampleVariationType.PRODUCT, SampleVariationType.SOLVENTS] or self.is_ref or self._get_ref_amount() == 0:
            self._values['aux']['equivalent'] = 0.0
            return
        self._values['aux']['equivalent'] = self.get_equivalent()

    def _set_quantity_from_sample(self):
        key = 'real_amount' if self._sample_type == SampleVariationType.PRODUCT else 'target_amount'
        value = self._sample.properties[key]
        self.set_quantity(**value)

    def set_quantity(self, value: float, unit: str | QuantityUnit):
        if value is None:
            value = 0.0
        if isinstance(unit, QuantityUnit):
            unit = unit.value

        if self._sample_type == SampleVariationType.SOLVENTS and unit == QuantityUnit.Liter.value:
            self._values['volume']['value'] = value
            return
        if unit is None:
            unit = QuantityUnit.Mole.value
        if unit == QuantityUnit.Equivalent.value:
            self.set_equivalent(value)
        elif unit == QuantityUnit.Gram.value:
            self._values['amount']['value'] = (value / self._molecular_weight()) * self._values['aux']['purity']
        elif unit == QuantityUnit.Mole.value:
            self._values['amount']['value'] = value
        elif unit == QuantityUnit.Liter.value and self._values['aux']['molarity'] != 0:
            self._values['amount']['value'] = (value / self._values['aux']['molarity'])
        else:
            raise ValueError(f"{self._sample_type.value} can't be quantified as {unit}.")
        self._values['volume']['value'] = 0.0
        self._values['mass']['value'] = 0.0

    def get_equivalent(self):
        return self._values['amount']['value'] / self._get_ref_amount()

    def get_amount(self):
        return self._values['amount']['value']

    def get_volume(self):
        if self._values['volume']['value'] != 0:
            return self._values['volume']['value']
        elif self._values['aux']['molarity']:
            return (self.get_amount() * self._values['aux']['molarity'])
        return 0

    def get_mass(self):
        return self.get_amount() * self._values['aux']['purity'] / self._molecular_weight()

    def _molecular_weight(self):
        if not self._values['aux']['molecularWeight']:
            return 1
        return self._values['aux']['molecularWeight']

    def _set_aux(self):
        self._values['aux']['coefficient'] = self._sample.properties['coefficient']
        self._values['aux']['purity'] = self._sample.properties['purity']
        self._values['aux']['isReference'] = self._sample.properties['reference']
        self._values['aux']['molecularWeight'] = self._sample.molecule['molecular_weight']
        self._values['aux']['sumFormula'] = self._sample.molecule['sum_formular']
        self._values['aux']['molarity'] = self._sample.properties['molarity']['value']
        if self._sample_type == SampleVariationType.PRODUCT:
            self._values['aux']['yield'] = self._sample.properties['equivalent']
        elif self._sample.properties['reference']:
            self._values['aux']['isReference'] = True
        else:
            self._values['aux']['equivalent'] = self._sample.properties['equivalent']

    @property
    def sample(self) -> Sample:
        return self._sample


class Variation():
    def __init__(self):
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

    def populate(self, json_data: dict, analyses: AnalysesList, starting_materials: MaterialList, reactants: MaterialList,
                 products: MaterialList, solvents: MaterialList):
        self._json_data = json_data
        self.id = self._json_data['id']
        self._properties = json_data['properties']
        self.notes = json_data['notes']
        self._analyses = analyses
        self._materials = {
            SampleVariationType.STARTING_MATERIAL: [
                self.sample_variation_factory(x, SampleVariationType.STARTING_MATERIAL) for x in
                starting_materials],
            SampleVariationType.REACTANT: [self.sample_variation_factory(x, SampleVariationType.REACTANT) for x in
                                           reactants],
            SampleVariationType.PRODUCT: [self.sample_variation_factory(x, SampleVariationType.PRODUCT) for x in
                                          products],
            SampleVariationType.SOLVENTS: [self.sample_variation_factory(x, SampleVariationType.SOLVENTS) for x in
                                           solvents],
        }

    def sample_variation_factory(self, sample: Sample, sample_type: SampleVariationType) -> SampleVariation:
        json_data = None
        for key, data in self._json_data.get(sample_type.value, {}).items():
            if key == str(sample.id):
                json_data = data
        return SampleVariation(sample, sample_type, json_data, self.get_ref_amount)

    def clean(self):
        self._json_data['properties'] = self._properties
        self._json_data['notes'] = self.notes
        for sample_type, sample_variations in self._materials.items():
            self._json_data[sample_type.value] = {}
            for sample_variation in sample_variations:
                self._json_data[sample_type.value][sample_variation.sample.id] = sample_variation.clean()
        return self._json_data

    def link_analyses(self, analyses: Analyses):
        try:
            int(analyses.id)
            self._json_data['analyses'].append(analyses.id)
        except ValueError:
            raise ValueError("Analyses has no id. please save the Reaction first")

    def get_analyses(self) -> Iterator[Analyses]:
        for ana_id in self._json_data['analyses']:
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
    def __init__(self, analyses: AnalysesList, starting_materials: MaterialList, reactants: MaterialList, products: MaterialList,
                 solvents: MaterialList):
        # Initialize the list with given items
        self._data = list()
        self._materials = {'starting_materials': starting_materials, 'reactants': reactants, 'products': products,
                           'solvents': solvents}
        self._highest_id = 0
        self._analyses = analyses

    def populate(self, json_data: dict):
        for variation in json_data:
            v = Variation()
            v.populate(variation, self._analyses, **self._materials)
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
        variation = {
            "id": self._highest_id,
            "notes": "",
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
            "analyses": [],
            "reactants": {},
            "products": {},
            "solvents": {},
            "startingMaterials": {}
        }
        v = Variation()
        v.populate(variation, self._analyses, **self._materials)
        self.append(v)
        return v

    def clean(self):
        return [variation.clean() for variation in self._data]

    def __getitem__(self, index):
        # Retrieve the item at the given index
        return self._data[index]

    def __setitem__(self, index, value):
        # Set the item at the given index
        self._data[index] = value

    def __delitem__(self, index):
        # Delete the item at the given index
        del self._data[index]

    def insert(self, index, value):
        # Insert an item at the given index
        self._data.insert(index, value)

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
    >>> rea.properties['solvents'].append_no_split(solv)
    >>> # Add a split of sample with ID 1 as starting material
    >>> rea.properties['starting_materials'].append(instance.get_sample(1))
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
    def properties(self) -> dict:
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
    def variations(self) -> Variations:
        if self._variations is None:
            mat_samples = {}
            for reaction_elm_names in ['starting_materials', 'reactants', 'products', 'solvents']:
                mat_samples[reaction_elm_names] = self.properties[reaction_elm_names]
            self._variations = Variations(self.analyses, **mat_samples)
            self._variations.populate(self.json_data['variations'])

        return self._variations

    def _parse_properties(self) -> dict:
        reaction_elements = {}
        for reaction_elm_names in ['starting_materials', 'reactants', 'products', 'solvents', 'purification_solvents']:
            obj_list = self.json_data[reaction_elm_names]
            temp = []
            for sample in obj_list:
                temp.append(Sample(self._generic_segments, self._session, sample))
            reaction_elements[reaction_elm_names] = MaterialList(temp)

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
            'vessel_size': self.json_data.get('vessel_size')
            # 'tlc_solvents': self.json_data.get('tlc_solvents'),
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

        serialize_data['tlc_solvents'] = self.json_data.get('tlc_solvents')
        serialize_data['tlc_description'] = self.json_data.get('tlc_description')
        serialize_data['reaction_svg_file'] = self.json_data.get('reaction_svg_file')
        serialize_data['role'] = self.properties.get('role', '')
        serialize_data['rf_value'] = self.json_data.get('rf_value')
        serialize_data['rxno'] = self.json_data.get('rxno', '')
        serialize_data['short_label'] = self.json_data.get('short_label')
        serialize_data['literatures'] = self.json_data.get('literatures')

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

    def _clean_variations(self) -> dict:
        cleand_data = self.variations.clean()
        self._variations = None
        return cleand_data
