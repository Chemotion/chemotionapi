"""Reaction element and its helpers.

Defines :class:`Reaction` (a Chemotion reaction, extending
:class:`~chemotion_api.elements.abstract_element.AbstractElement`) together with the supporting
:class:`MaterialList` (a role-bound list of :class:`~chemotion_api.elements.sample.Sample`\\ s) and
:class:`Temperature` (a temperature-time profile). Reactions persist the product yield through an
``equivalent`` cache.
"""
import logging
import re
from enum import Enum
from typing import Optional, Literal, cast
from collections.abc import Callable, Iterator

logger = logging.getLogger(__name__)


#: Chemotion duration display units (e.g. "Hour(s)") mapped to seconds.
_DURATION_UNIT_SECONDS = {
    "second": 1, "minute": 60, "hour": 3600, "day": 86400, "week": 604800,
}


from requests import Response

from chemotion_api.elements.abstract_element import AbstractElement, Analyses, AnalysesList
from datetime import datetime

from chemotion_api.elements.sample import Sample, SampleVariationType, GasPhaseObj
from chemotion_api.elements.utils.converter import convert_value, TIME_UNITS, TEMPERATURE_UNITS, TON_UNITS
from chemotion_api.elements.utils import QuantityUnit, GasType
from chemotion_api.elements.schemas.reaction import schema, PURIFICATION_OPTIONS, STATUS_OPTIONS
from chemotion_api.utils import TypedList, quill_hedging, merge_dicts, PropertyDict
from chemotion_api.utils.segment_fields import SegmentField, VARIATION_FIELD_TYPES, iter_fields
from collections.abc import MutableSequence
from copy import deepcopy


class MaterialList(TypedList):
    """
    A list which accepts only :class:`chemotion_api.elements.sample.Sample`'s.
    If you add a sample to the starting materials or reactants using the standard list-methods,
    a split of the sample is created and added to the list. Products get a copy of the sample.
    Solvents and purification solvents are added as they are.
    Splitting and copying save the original sample first.

    In order to avoid the splitting and the pre saving use the 'append_no_split'
    method. It adds the sample itself, but like the other methods it assigns the reaction, role and position
    and initializes the amount.
    """

    def __init__(self, reaction: Reaction,
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
        self._attach(return_element)
        return_element.set_ref(False, False)

        return return_element

    def _attach(self, element: Sample) -> None:
        """Bind a sample to this reaction: back-reference, role and position.

        Position is taken *before* the append, so it is the index the sample is about to occupy.
        """
        element.reaction = self._reaction
        element.role_in_reaction = self._mat_type
        element.properties['position'] = len(self)

    def after_append(self, element: Sample):
        """
        Initializes the amount of a sample just added to the list.

        Falls back to a zero amount in the first allowed unit if the sample's current amount cannot
        be set.

        :param element: The sample that was appended
        """
        try:

            element.set_amount(**element.get_amount())
        except (ValueError, KeyError):
            element.set_amount(0, element.allowed_quantity_units()[0])

    def append_no_split(self, element: Sample):
        """Add a Sample to this reaction without splitting or copying it.

        The sample is bound to the reaction (back-reference, role, position) and its amount is
        initialised, exactly as the splitting path does, and the equivalents are updated.
        Previously this only type-checked and appended, so the sample arrived detached: no
        reaction, no role, no position and no amount — and it was then saved that way.

        :param element: Sample to be added
        :return: the added sample
        """
        self._check_element(element)
        self._attach(element)
        super(TypedList, self).append(element)
        self.after_append(element)
        return element


class SampleVariation:
    """
    The quantities of one material (sample) in a reaction variation.

    The amount is stored in mol. Mass and volume are computed from the amount, using the molecular weight,
    purity, molarity and density of the sample. Equivalents (starting materials and reactants) and yields
    (products) are relative to the amount of the reference material in the same variation.
    Solvents only have a volume.

    Usage::

    >>> from chemotion_api.elements.utils import QuantityUnit
    >>> variation = reaction.variations[0]
    >>> variation.starting_materials[0].set_quantity(2, QuantityUnit.Gram)
    >>> variation.reactants[0].set_equivalent(1.5)
    >>> variation.products[0].set_yield(85)  # in percent
    >>> reaction.save()
    """

    def __init__(self, sample: Sample, sample_type: SampleVariationType, vessel_volume: float | None,
                 json_data: dict | None = None, get_ref_amount: Callable[[], float] | None = None):
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
        """
        Updates the auxiliary values (purity, molecular weight, ...) from the sample.

        :param vessel_volume: vessel volume of the reaction
        """
        self._set_aux(vessel_volume)

    def clean(self):
        """
        :return: the quantities in the format of the Chemotion frontend, with updated mass, volume,
            equivalent and yield
        """
        self._update_equivalent()
        return self._values

    def potential_units(self) -> list[QuantityUnit]:
        """
        :return: the units the quantity can be set in with :meth:`set_quantity`
        """
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
        """
        True if the sample is the reference material of the reaction
        """
        return bool(self._values['aux']['isReference'])

    def set_equivalent(self, value):
        """
        Sets the equivalent of a starting material or reactant. The amount is computed from the amount of
        the reference material.

        :param value: equivalent

        :raises ValueError: if the sample is a product, a solvent or the reference material
        """
        if self._sample_type in [SampleVariationType.PRODUCT, SampleVariationType.SOLVENTS]:
            raise ValueError("Sample type must not be PRODUCT or SOLVENTS.")
        if self.is_ref:
            raise ValueError("Sample type must not be the reference material.")
        self._values['amount']['value'] = self._get_ref_amount() * value
        self._values['equivalent']['value'] = value

    def set_yield(self, value):
        """
        Sets the yield of a product. The amount is computed from the amount of the reference material.

        :param value: yield in percent (e.g. 85 for 85 %)

        :raises ValueError: if the sample is not a product
        """
        if self._sample_type != SampleVariationType.PRODUCT:
            raise ValueError("Sample type must be PRODUCT.")
        if self.is_ref:
            raise ValueError("Sample type must not be the reference material.")
        self._values['amount']['value'] = self._get_ref_amount() * value / 100
        self._values['yield']['value'] = value

    def _update_equivalent(self):
        if 'mass' in self._values:
            self._values['mass']['value'] = self.get_mass()
        if 'volume' in self._values:
            self._values['volume']['value'] = self.get_volume()
        if 'yield' in self._values:
            self._values['yield']['value'] = self.get_equivalent_or_yield() * 100
        if 'equivalent' in self._values:
            self._values['equivalent']['value'] = self.get_equivalent_or_yield()

    def _set_quantity_from_sample(self):
        value = self._sample.get_amount()
        self.set_quantity(**value)

    def set_quantity(self, value: float, unit: str | QuantityUnit | None):
        """
        Sets the quantity of the material. For solvents, the value is always the volume in liter.

        :param value: the quantity
        :param unit: unit of the value, see :meth:`potential_units`. Liter needs a molarity of the sample.
            If None, mol is used. Yield is given in percent.

        :raises ValueError: if the material cannot be quantified in this unit
        :raises NotImplementedError: if the sample is a mixture
        """
        # TODO: Gas Type not None elements!!!
        # ToDo: How are Gas Types calculated (Volume ????)
        if self._sample.is_mixture:
            raise NotImplementedError("Quantities of mixtures in variations are not supported yet.")
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
            self._values['amount']['value'] = value * self._values['aux']['molarity']
        elif unit == QuantityUnit.Liter.value and self._values['aux']['density']:
            # The inverse of get_volume()'s density branch: volume -> mass -> amount. A sample
            # with a density but no molarity is offered litres by Sample.allowed_quantity_units(),
            # and _set_quantity_from_sample() passes that unit straight through.
            mass = value * self._values['aux']['density'] * 1000
            self._values['amount']['value'] = (mass / self._molecular_weight()) * self._values['aux']['purity']
        else:
            raise ValueError(f"{self._sample_type.value} can't be quantified as {unit}.")
        self._update_equivalent()

    def get_equivalent_or_yield(self) -> float:
        """
        :return: the amount relative to the reference material (the yield as a fraction, not in percent)
        """
        try:
            return self._values['amount']['value'] / self._get_ref_amount()
        except ZeroDivisionError:
            return 0

    def get_amount(self) -> float:
        """
        :return: the amount in mol
        """
        return self._values['amount']['value']

    def get_volume(self) -> float:
        """
        :return: the volume in liter, computed from the molarity or density if no volume is set
        """
        if self._values.get('volume') is None:
            self._values['volume'] = {'value': 0, 'unit': 'l'}
        if self._values['volume']['value']:
            return self._values['volume']['value']
        if self._sample_type is SampleVariationType.SOLVENTS:
            # A solvent variation holds a volume and nothing else -- there is no `amount` to
            # derive one from, so the branches below would raise KeyError. An unset volume is 0.
            return 0
        elif self._values['aux']['molarity']:
            return self.get_amount() / self._values['aux']['molarity']
        elif self._values['aux']['density']:
            return self.get_mass() / (self._values['aux']['density'] * 1000)
        return 0

    def get_mass(self) -> float:
        """
        :return: the mass in gram
        """
        purity = self._values['aux']['purity']
        if not purity:
            return 0
        return self.get_amount() * self._molecular_weight() / purity

    def _molecular_weight(self):
        if not self._values['aux']['molecularWeight']:
            return 1
        return self._values['aux']['molecularWeight']

    def _set_aux(self, vessel_volume: float):
        # TODO: [DONE] get density, molarity from sample (NOT only for new Variations)!!!!
        self._values['aux']['coefficient'] = self._sample.properties['coefficient']
        self._values['aux']['purity'] = self._sample.properties['purity']
        self._values['aux']['isReference'] = bool(self._sample.properties['reference'])
        self._values['aux']['molecularWeight'] = self._sample.molecule['molecular_weight']
        self._values['aux']['sumFormula'] = self._sample.molecule['sum_formular']
        self._values['aux']['molarity'] = self._sample.properties['molarity']['value']
        self._values['aux']['density'] = self._sample.properties['density']
        self._values['aux']['gasType'] = self._sample.properties['gas_type'].value
        self._values['aux']['vesselVolume'] = vessel_volume
        self._values['aux']['materialType'] = self._sample_type.value
        self._ensure_gas_entries()

    def _ensure_gas_entries(self):
        # The frontend shows a gas product with extra entries (getMaterialEntries in
        # ReactionVariationsMaterials.js) and reads each one as {'value', 'unit'}. A missing or null
        # entry makes the variations tab crash, so fill them like the frontend does (getStandardValue).
        # A null value inside an entry is fine: the frontend creates such entries itself.
        if self._sample_type != SampleVariationType.PRODUCT or self._values['aux']['gasType'] != GasType.GAS.value:
            return
        for entry, default in self._new_gas_entries().items():
            if not isinstance(self._values.get(entry), dict):
                self._values[entry] = default

    def _new_gas_entries(self) -> dict:
        gas_phase_data = self._sample.properties.get('gas_phase_data')
        gas_phase_data = gas_phase_data.to_dict() if gas_phase_data is not None else GasPhaseObj.default_val

        def convert(value_unit: dict | None, out_unit: str):
            value_unit = value_unit or {}
            try:
                return convert_value(value_unit.get('value'), value_unit.get('unit'), out_unit)
            except ValueError:
                return None

        return {
            "duration": {
                "value": convert(gas_phase_data.get('time'), TIME_UNITS.SECONDS.value),
                "unit": "Second(s)"
            },
            "temperature": {
                "value": convert(gas_phase_data.get('temperature'), TEMPERATURE_UNITS.CELSIUS.value),
                "unit": "°C"
            },
            "concentration": {
                "value": gas_phase_data.get('part_per_million'),
                "unit": "ppm"
            },
            "turnoverNumber": {
                "value": gas_phase_data.get('turnover_number'),
                "unit": None
            },
            # Unitless in the frontend, which computes it per hour (turnover number / duration in hours)
            "turnoverFrequency": {
                "value": convert(gas_phase_data.get('turnover_frequency'), TON_UNITS.PER_HOUR.value),
                "unit": None
            }
        }

    @property
    def sample(self) -> Sample:
        """
        The sample of the reaction this entry belongs to
        """
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


class VariationSegments(dict):
    """
    Segment values of one reaction variation: ``{segment: {layer: {field: value}}}``, named like
    ``reaction.segments``. Only text, integer, select and system-defined fields can be varied.

    Select fields take the option key or label, system-defined fields take ``{'value': ..., 'unit': ...}``
    or a number in the field's default unit. Accessing a segment the variation does not have adds it with
    default values. On save, every variation of the reaction gets the same segments.
    """

    def __init__(self, raw: dict, segment_klasses: Callable[[], dict[str, dict]]):
        super().__init__()
        self._segment_klasses = segment_klasses
        # Segments without an active template are passed through unchanged
        self._unknown = {}
        for label, entries in raw.items():
            klass = segment_klasses().get(label)
            if klass is None:
                self._unknown[label] = entries
                continue
            super().__setitem__(label, {
                layer: {name: field.from_variation_entry(entries[field.variation_key])
                        if field.variation_key in entries else field.default_variation_value()
                        for name, field in fields.items()}
                for layer, fields in self._fields(klass).items()})

    def __missing__(self, label: str) -> dict:
        klass = self._segment_klasses().get(label)
        if klass is None:
            raise KeyError(f'"{label}" is not an active reaction segment.')
        values = {layer: {name: field.default_variation_value() for name, field in fields.items()}
                  for layer, fields in self._fields(klass).items()}
        super().__setitem__(label, values)
        return values

    @staticmethod
    def _fields(klass: dict) -> dict[str, dict[str, SegmentField]]:
        fields: dict[str, dict[str, SegmentField]] = {}
        for layer, name, field in iter_fields(klass.get('properties_release', {})):
            if field.type in VARIATION_FIELD_TYPES:
                fields.setdefault(layer, {})[name] = field
        return fields

    def clean(self) -> dict:
        """
        :return: segments in the format of the Chemotion frontend, with an entry for every field
        :raises ValueError: if a value does not fit its field
        """
        cleaned = dict(self._unknown)
        for label, values in self.items():
            entries = {}
            for layer, fields in self._fields(self._segment_klasses()[label]).items():
                layer_values = values.get(layer, {})
                unknown = set(layer_values) - set(fields)
                if unknown:
                    raise KeyError(f'Segment "{label}", layer "{layer}" has no variable field(s) {sorted(unknown)}.')
                for name, field in fields.items():
                    value = layer_values.get(name, field.default_variation_value())
                    try:
                        entries[field.variation_key] = field.to_variation_entry(value)
                    except ValueError as e:
                        raise ValueError(f'Variation segment "{label}": {e}') from None
            cleaned[label] = entries
        return cleaned


class Variation:
    """
    One reaction variation (one row in the variations tab of a reaction).

    * :attr:`properties`: ``{'temperature': {'value', 'unit'}, 'duration': {'value', 'unit'}}``
    * ``notes``: free text
    * :attr:`starting_materials`, :attr:`reactants`, :attr:`products`, :attr:`solvents`:
      lists of :class:`SampleVariation`, one per material of the reaction
    * :attr:`segments`: values of the reaction segments, see :class:`VariationSegments`
    """

    def __init__(self):
        self.id = -1
        self._json_data = None
        self._properties = {}
        self.notes = ""
        self._ref_mat = None
        self._materials = {}
        self._analyses = None
        self._segments = None

    def get_ref_amount(self) -> float:
        """
        :return: the amount (mol) of the reference material in this variation, or 1 if there is none
        """
        if self._ref_mat is None:
            self._ref_mat = next((mat for key, x in self._materials.items() for mat in x if mat.is_ref), None)
        if self._ref_mat is None:
            return 1
        return self._ref_mat.get_amount()

    def populate(self, json_data: dict, analyses: AnalysesList, starting_materials: MaterialList,
                 reactants: MaterialList,
                 products: MaterialList, solvents: MaterialList, vessel_size: dict,
                 segment_klasses: Callable[[], dict[str, dict]]):
        """
        Do not use this method! It is used by :class:`Variations` to load a variation.
        """
        self._json_data = json_data
        self.id = self._json_data['id']
        self._properties = json_data.setdefault('properties', {})
        self.notes = json_data.setdefault('metadata', {}).get('notes', '')
        self._analyses = analyses
        self._segments = VariationSegments(json_data.get('segments', {}), segment_klasses)
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
        self._json_data['segments'] = self._segments.clean()
        for sample_type, sample_variations in self._materials.items():
            self._json_data[sample_type.value] = {}
            for sample_variation in sample_variations:
                self._json_data[sample_type.value][sample_variation.sample.id] = sample_variation.clean()
        return self._json_data

    def link_analyses(self, analyses: Analyses):
        """
        Links an analysis of the reaction to this variation.

        :param analyses: a saved analysis of the reaction

        :raises ValueError: if the analysis has not been saved yet
        """
        try:
            int(analyses.id)
            self._json_data['metadata']['analyses'].append(analyses.id)
        except ValueError:
            raise ValueError("Analyses has no id. please save the Reaction first")

    def get_analyses(self) -> Iterator[Analyses]:
        """
        :return: the analyses linked to this variation
        """
        for ana_id in self._json_data['metadata']['analyses']:
            yield self._analyses.by_id(ana_id)

    @property
    def properties(self) -> dict:
        """
        Temperature and duration of the variation:
        ``{'temperature': {'value': ..., 'unit': '°C'}, 'duration': {'value': ..., 'unit': 'Second(s)'}}``
        """
        return self._properties

    @property
    def segments(self) -> VariationSegments:
        """
        Segment values of this variation: ``{segment: {layer: {field: value}}}``.
        """
        return self._segments

    @property
    def starting_materials(self) -> list[SampleVariation]:
        """Quantities of the starting materials"""
        return self._materials[SampleVariationType.STARTING_MATERIAL]

    @property
    def reactants(self) -> list[SampleVariation]:
        """Quantities of the reactants"""
        return self._materials[SampleVariationType.REACTANT]

    @property
    def products(self) -> list[SampleVariation]:
        """Quantities of the products"""
        return self._materials[SampleVariationType.PRODUCT]

    @property
    def solvents(self) -> list[SampleVariation]:
        """Volumes of the solvents"""
        return self._materials[SampleVariationType.SOLVENTS]


class Variations(MutableSequence):
    """
    The variations of a reaction, a list of :class:`Variation` sorted by id.
    Changes are saved with the reaction.

    Usage::

    >>> from chemotion_api.elements.utils import QuantityUnit
    >>> reaction = instance.get_reaction(1)
    >>> variation = reaction.variations.add_new()
    >>> variation.properties['temperature']['value'] = 80
    >>> variation.starting_materials[0].set_quantity(2, QuantityUnit.Gram)
    >>> variation.segments['Electrochemistry']['Cell']['Electrode type'] = 'disk'
    >>> reaction.save()
    >>> # Remove the last variation
    >>> reaction.variations.remove(reaction.variations[-1])
    >>> reaction.save()
    """

    def __init__(self, analyses: AnalysesList, starting_materials: MaterialList, reactants: MaterialList,
                 products: MaterialList,
                 solvents: MaterialList, vessel_size: Callable[[], dict],
                 segment_klasses: Callable[[], dict[str, dict]] = dict):
        # Initialize the list with given items
        self._data = list()
        self._segment_klasses = segment_klasses
        self._materials = {'starting_materials': starting_materials, 'reactants': reactants, 'products': products,
                           'solvents': solvents}
        self._highest_id = 0
        self._analyses = analyses
        self._get_vessel_size = vessel_size

    def populate(self, json_data: dict):
        """
        Do not use this method! It is used by the reaction to load the variations.
        """
        for variation in json_data:
            v = Variation()
            v.populate(variation, self._analyses, **self._materials, vessel_size=self._get_vessel_size(),
                       segment_klasses=self._segment_klasses)
            self.append(v)
            self._highest_id = max(self._highest_id, variation['id'])

    def remove(self, value: Variation) -> bool:
        """
        Removes a variation.

        :param value: the variation
        :return: True if the variation was removed, False if it was not in the list
        """
        try:
            idx = next(idx for idx, v in enumerate(self) if v.id == value.id)
            self.pop(idx)
        except StopIteration:
            return False
        return True

    def add_new(self) -> Variation:
        """
        Adds a new variation. Its quantities are taken from the current amounts of the reaction materials.

        :return: the new variation
        """
        self._highest_id += 1
        variation = self.empty_variation(self._highest_id)
        v = Variation()
        v.populate(variation, self._analyses, **self._materials, vessel_size=self._get_vessel_size(),
                   segment_klasses=self._segment_klasses)
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
            "segments": {},
            "reactants": {},
            "products": {},
            "solvents": {},
            "startingMaterials": {}
        }

    def sort(self):
        self._data = sorted(self._data, key=lambda v: v.id)

    def clean(self):
        """
        :return: all variations in the format of the Chemotion frontend
        """
        # The frontend builds its columns from the first variation, so all variations need the same segments,
        # metadata and properties
        segment_labels = {label for variation in self._data for label in variation.segments}
        for variation in self._data:
            for label in segment_labels:
                variation.segments[label]
        cleaned = [variation.update_and_clean(self._get_vessel_size()) for variation in self._data]
        defaults = self.empty_variation(0)
        defaults['metadata']['group'] = {'group': 1, 'subgroup': 1}
        for section in ('metadata', 'properties'):
            keys = {key for variation in cleaned for key in variation.get(section, {})}
            for variation in cleaned:
                values = variation.setdefault(section, {})
                for key in keys - values.keys():
                    values[key] = deepcopy(defaults[section].get(key))
        return cleaned

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
    This object contains the temperature-time profile, the temperature unit and a user text.
    Each entry contains a time as 'hh:mm:ss' and a temperature value as string.

    :key data: {list} the temperature-time profile, entries ``{'time': 'hh:mm:ss', 'value': '100'}``
    :key userText: {str}
    :key valueUnit: {str} one of '°C', '°F' or 'K'
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
        :param temperature: temperature in the unit given by 'valueUnit' (default °C), may be negative
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
    >>> # Get or create the collection 'Solv'
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

    # Narrowed from the base class's `dict | None`: a Reaction always has its
    # json_data/_properties populated via _set_json_data/load before any method
    # that reads them runs. Annotation-only.
    json_data: dict

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._variations: Variations | None = None
        self._yield_value_cache = None

    datetime_format = '%m/%d/%Y %H:%M:%S'

    def _set_json_data(self, json_data: dict):
        super()._set_json_data(json_data)
        self._svg_file = self.json_data.get('reaction_svg_file')

    def load_image(self) -> Response:
        """
        Loads the reaction structure as svg image

        :return: Response with the svg as content
        """

        image_url = f"/images/reactions/{self._svg_file}"
        res = self._session.get(image_url)
        if res.status_code != 200:
            raise ConnectionError(f'{res.status_code} -> {res.text}')
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
        :key timestamp_stop: {datetime.datetime} the duration is computed from start and stop
        :key name: {str}
        :key description: {str|dict} A Quill.js text (https://quilljs.com/docs/delta). A plain string is converted.
        :key observation: {str|dict} A Quill.js text (https://quilljs.com/docs/delta). A plain string is converted.
        :key purification: {list[str]} values must be in ['Flash-Chromatography', 'TLC', 'HPLC', 'Extraction', 'Distillation', 'Dialysis', 'Filtration', 'Sublimation', 'Crystallisation', 'Recrystallisation', 'Precipitation']; other values are dropped
        :key status: {str} value must be in ['', 'Planned', 'Running', 'Done', 'Analyses Pending', 'Successful',
                                          'Not Successful']; other values are ignored
        :key vessel_size: {dict} has a unit {str} ('l' or 'ml') and an amount {float}
        :key dangerous_products: {list}
        :key conditions: {str}
        :key duration: {str}
        :key gaseous: {bool} True for a gas-phase reaction, see :attr:`gas_schema`

        Readonly properties:

        :key rxno: {str, readonly} reaction type
        :key rinchi_long_key: {str, readonly}
        :key rinchi_short_key: {str, readonly}
        :key rinchi_web_key: {str, readonly}

        Variations are accessible through :attr:`variations`.

        :return: Element properties
        """
        return super().properties

    @property
    def variations(self) -> Variations:
        """
        The variations of the reaction (variations tab in Chemotion). They are saved with the reaction.

        :return: the variations
        """
        if self._variations is None:
            mat_samples = {}
            for reaction_elm_names in ['starting_materials', 'reactants', 'products', 'solvents']:
                mat_samples[reaction_elm_names] = self.properties[reaction_elm_names]
            self._variations = Variations(self.analyses, **mat_samples,
                                          vessel_size=lambda: self.properties.get('vessel_size'),
                                          segment_klasses=self._variation_segment_klasses)
            # offline-reconstructed reactions carry no 'variations' key at all
            self._variations.populate(self.json_data.get('variations') or {})

        return self._variations

    @property
    def starting_materials(self) -> MaterialList:
        """
        The starting materials of the reaction.

        :return: The :class:`MaterialList` of starting material samples
        """
        return self.properties['starting_materials']

    @property
    def reactants(self) -> MaterialList:
        """
        The reactants of the reaction.

        :return: The :class:`MaterialList` of reactant samples
        """
        return self.properties['reactants']

    @property
    def products(self) -> MaterialList:
        """
        The products of the reaction.

        :return: The :class:`MaterialList` of product samples
        """
        return self.properties['products']

    @property
    def solvents(self) -> MaterialList:
        """
        The solvents of the reaction.

        :return: The :class:`MaterialList` of solvent samples
        """
        return self.properties['solvents']

    @property
    def purification_solvents(self) -> MaterialList:
        """
        The purification solvents of the reaction.

        :return: The :class:`MaterialList` of purification solvent samples
        """
        return self.properties['purification_solvents']

    @property
    def reference_sample(self) -> Sample | None:
        """
        The reference material of the reaction: the starting material or reactant explicitly
        flagged as the reference. Equivalents and yields are relative to it. Setting it to None
        removes the reference.

        **No reference is invented when none is flagged.** This mirrors the ELN itself: its
        `Reaction.referenceMaterial` is `allReactionMaterials.find(s => s.reference)`, which is
        simply undefined when nothing carries the flag, and its only fallback —
        `_setAsReferenceMaterial(starting_materials[0])` in `rebuildReference` — exists to recover
        a flagged reference that has gone missing, not to pick one from nothing.

        Earlier versions of this client auto-selected a candidate, which meant the equivalents it
        computed and saved were relative to a material the ELN had not chosen. Reading this
        property no longer has that side effect.

        :return: The flagged reference :class:`Sample`, or ``None`` if nothing is flagged
        """
        for mat in [*self.starting_materials, *self.reactants]:
            if mat.properties['reference']:
                return mat
        return None

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
        """
        Whether the reaction uses the gas (gaseous) schema.

        :return: ``True`` if the reaction is a gas-schema reaction
        """
        return cast(dict, self._properties).get('gaseous', False)

    @gas_schema.setter
    def gas_schema(self, gaseous: bool):
        cast(dict, self._properties)['gaseous'] = gaseous
        if not gaseous:
            for mat in [*self.starting_materials, *self.reactants, *self.products, *self.solvents,
                        *self.purification_solvents]:
                mat.set_gas_type('off', False)
        self.update_equivalent()

    def get_feedstock(self) ->  Sample | None:
        """
        Returns the sample acting as feedstock in this gas-schema reaction.

        :return: The feedstock :class:`Sample`, or ``None`` if there is none
        """
        return self.get_gas_component(GasType.FEEDSTOCK)

    def get_catalyst(self) -> Sample | None:
        """
        Returns the sample acting as catalyst in this gas-schema reaction.

        :return: The catalyst :class:`Sample`, or ``None`` if there is none
        """
        return self.get_gas_component(GasType.CATALYST)

    def get_gas_component(self, gt: GasType) -> Sample | None:
        """
        Returns the starting material or reactant carrying the given gas type.

        :param gt: The gas type to look for
        :return: The matching :class:`Sample`, or ``None`` if the reaction is not a gas schema or no
            sample carries the gas type
        """
        if self.gas_schema:
            for mat in [*self.starting_materials, *self.reactants]:
                if mat.gas_type == gt:
                    return mat
        return None


    def update_amount(self):
        """
        Recomputes the amount of every material (sample) of the reaction.
        """
        for mat in [*self.starting_materials, *self.reactants, *self.products, *self.solvents,
                    *self.purification_solvents]:
            mat.update_amount()

    def update_equivalent(self):
        """
        Recomputes the molar equivalent of every material (sample) of the reaction.
        """
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
            reaction_elements[reaction_elm_names] = MaterialList(self, cast(Literal['starting_materials', 'reactants', 'products', 'solvents', 'purification_solvents'], reaction_elm_names), temp)

        try:
            timestamp_start = datetime.strptime(cast(str, self.json_data.get('timestamp_start')), self.datetime_format)
        except (ValueError, TypeError):
            timestamp_start = None
        try:
            timestamp_stop = datetime.strptime(cast(str, self.json_data.get('timestamp_stop')), self.datetime_format)
        except (ValueError, TypeError):
            timestamp_stop = None

        raw_dict = {
            'name': self.json_data.get('name'),
            'short_label': self.json_data.get('short_label'),
            'status': self.json_data.get('status'),
            'duration': self.json_data.get('duration'),
            'temperature': self.json_data.get('temperature', {}),
            'vessel_size': self.json_data.get('vessel_size', {}).get('amount') if isinstance(self.json_data.get('vessel_size'), dict) else self.json_data.get('vessel_size'),
            'yield_value': self.json_data.get('yield') if self.json_data.get('yield') is not None else (
                float(self.json_data['products'][0]['equivalent']) * 100.0 if (
                    self.json_data.get('products') and self.json_data['products'][0].get('equivalent') is not None
                ) else getattr(self, '_yield_value_cache', None)
            ),
            'tlc_description': self.json_data.get('tlc_description'),
            'dangerous_products': self.json_data.get('dangerous_products'),
            'description': self.json_data.get('description'),
            'reaction_description': self.json_data.get('reaction_description') or self.json_data.get('description'),
            'observation': self.json_data.get('observation'),
            'user_labels': self.json_data.get('user_labels', []),
            'vessel': self.json_data.get('vessel'),
            'gas_schema': self.json_data.get('gaseous', False),
            'position': self.json_data.get('position'),
            'show_label': self.json_data.get('show_label'),
            'rxno': self.json_data.get('rxno'),
            'conditions': self.json_data.get('conditions'),
            'purification': self.json_data.get('purification'),
            'tlc_solvents': self.json_data.get('tlc_solvents'),
            'rf_value': self.json_data.get('rf_value'),
            'volume': self.json_data.get('volume'),
            'use_reaction_volume': self.json_data.get('use_reaction_volume'),
            'concentration_mode': self.json_data.get('concentration_mode'),
            'weight_percentage': self.json_data.get('weight_percentage'),
            'rinchi_string': self.json_data.get('rinchi_string'),
            'rinchi_web_key': self.json_data.get('rinchi_web_key'),
            'variations': self.json_data.get('variations')
        }

        from chemotion_api.models import ReactionPropertiesModel, UnitDictModel
        validated = ReactionPropertiesModel.model_validate(raw_dict)

        res = reaction_elements | {
            'timestamp_start': timestamp_start,
            'timestamp_stop': timestamp_stop,
            'description': validated.description or validated.reaction_description or self.json_data.get('description'),
            'name': validated.name,
            'observation': validated.observation or self.json_data.get('observation'),
            'purification': validated.purification or self.json_data.get('purification'),
            'dangerous_products': validated.dangerous_products,
            'conditions': validated.conditions or self.json_data.get('conditions'),
            'rinchi_long_key': self.json_data.get('rinchi_long_key'),
            'rinchi_web_key': validated.rinchi_web_key or self.json_data.get('rinchi_web_key'),
            'rinchi_short_key': self.json_data.get('rinchi_short_key'),
            'rinchi_string': validated.rinchi_string or self.json_data.get('rinchi_string'),
            'duration': validated.duration.to_dict() if isinstance(validated.duration, UnitDictModel) else (validated.duration or self.json_data.get('duration')),
            'rxno': validated.rxno or self.json_data.get('rxno'),
            'concentration_mode': validated.concentration_mode,
            # `.get('temperature', {})` covers a missing key but not an explicit null, which
            # would make this `Temperature(**None)` -> TypeError and abort the whole parse.
            'temperature': Temperature(**(validated.temperature.to_dict() if validated.temperature
                                          else (self.json_data.get('temperature') or {}))),
            'status': validated.status,
            'vessel_size': {'amount': validated.vessel_size, 'unit': self.json_data.get('vessel_size', {}).get('unit', 'ml')} if isinstance(self.json_data.get('vessel_size'), dict) else {'amount': validated.vessel_size, 'unit': 'ml'},
            'gaseous': validated.gas_schema,
            'yield': validated.yield_value,
            'yield_value': validated.yield_value,
            'tlc_solvents': validated.tlc_solvents or self.json_data.get('tlc_solvents'),
            'rf_value': validated.rf_value or self.json_data.get('rf_value'),
            'volume': validated.volume or self.json_data.get('volume'),
            'use_reaction_volume': validated.use_reaction_volume or self.json_data.get('use_reaction_volume'),
            'weight_percentage': validated.weight_percentage or self.json_data.get('weight_percentage'),
            'variations': validated.variations or self.json_data.get('variations')
        }
        return res


    def _current_yield(self):
        """The reaction yield in percent, preferring ``yield_value`` over ``yield``.

        None-aware on purpose: ``0.0`` is a legitimate yield (failed reaction) and must not be
        dropped the way an ``or``-chain would drop it.
        """
        yield_value = self.properties.get('yield_value')
        return yield_value if yield_value is not None else self.properties.get('yield')

    def save(self, load_after_save: bool = False):
        """Save the reaction, first bringing the equivalents in line with the current amounts.

        ``update_equivalent()`` deliberately runs here rather than in
        :meth:`_clean_properties_data`: serialising must stay side-effect free, so that merely
        inspecting or exporting a reaction does not alter the in-memory model.

        :param load_after_save: If true, the element is reloaded from the server after saving
        """
        self.update_equivalent()
        return super().save(load_after_save)

    def _clean_properties_data(self, serialize_data: dict | None = None) -> dict:
        if serialize_data is None:
            serialize_data = {}
        reaction_yield = self._current_yield()
        if reaction_yield is not None:
            # Chemotion has no explicit yield field; it is persisted as the first product's
            # `equivalent` (yield / 100). Multi-product reactions only carry yield on product[0].
            products = self.properties.get('products') or []
            if not products:
                logger.warning("Reaction %s has no products; its yield (%r%%) cannot be persisted "
                               "(Chemotion stores yield as product[0].equivalent) and will be lost on save.",
                               getattr(self, 'id', '?'), reaction_yield)
            else:
                if len(products) > 1:
                    logger.warning("Reaction %s has %d products; yield is stored only on the first product.",
                                   getattr(self, 'id', '?'), len(products))
        serialize_data['materials'] = {}
        for reaction_elm_names in ['starting_materials', 'reactants', 'products', 'solvents', 'purification_solvents']:
            temp_json_sample = self.json_data[reaction_elm_names]
            serialize_data['materials'][reaction_elm_names] = []
            for sample in self.properties[reaction_elm_names]:
                origen: dict = next((x for x in temp_json_sample if x['id'] == sample.id), {})
                clean_s = sample.clean_data()
                if 'attachments' in clean_s:
                    del clean_s['attachments']
                serialize_data['materials'][reaction_elm_names].append(origen | clean_s)

        if reaction_yield is not None and serialize_data['materials']['products']:
            # Applied to the serialised product rather than to `products[0]._properties`, which is
            # a live object: writing there made *serialising* a reaction change the in-memory
            # model, so inspecting or exporting one silently altered it. The wire format is
            # unchanged — index 0 here is `self.properties['products'][0]`.
            try:
                serialize_data['materials']['products'][0]['equivalent'] = \
                    float(reaction_yield) / 100.0
            except (ValueError, TypeError) as e:
                logger.warning("Could not persist reaction yield onto product[0].equivalent: %s", e)

        try:
            timestamp_start = cast(datetime, self.properties.get('timestamp_start')).strftime(self.datetime_format)
        except (AttributeError, ValueError, TypeError):
            timestamp_start = ''
        try:
            timestamp_stop = cast(datetime, self.properties.get('timestamp_stop')).strftime(self.datetime_format)
        except (AttributeError, ValueError, TypeError):
            timestamp_stop = ''
        serialize_data['name'] = self.properties.get('name')
        serialize_data['yield'] = self._current_yield()
        serialize_data['description'] = quill_hedging(cast('str | dict', self.properties.get('description')), 'Description')
        serialize_data['dangerous_products'] = self.properties.get('dangerous_products')
        serialize_data['conditions'] = self.properties.get('conditions')
        serialize_data['duration'] = self.properties.get('duration')
        serialize_data |= self._calc_duration()
        serialize_data['timestamp_start'] = timestamp_start
        serialize_data['timestamp_stop'] = timestamp_stop
        serialize_data['temperature'] = self.properties.get('temperature')
        serialize_data['observation'] = quill_hedging(cast('str | dict', self.properties.get('observation')), 'Observation')

        serialize_data['status'] = self.properties.get('status')
        if self.properties.get('status') in STATUS_OPTIONS:
            serialize_data['status'] = self.properties.get('status')
        else:
            serialize_data['status'] = self.json_data.get('status')

        purif = self.properties.get('purification')
        if isinstance(purif, list):
            serialize_data['purification'] = [x for x in purif if x in PURIFICATION_OPTIONS]
        else:
            serialize_data['purification'] = purif if purif is not None else self.json_data.get('purification')

        if self.properties.get('vessel_size') is not None:
            serialize_data['vessel_size'] = self.properties.get('vessel_size')

        serialize_data['role'] = self.properties.get('role', '')
        serialize_data['gaseous'] = self.properties.get('gaseous')
        
        def get_prop_or_json(name, default=None):
            val = self.properties.get(name)
            if val is not None:
                return val
            val_json = self.json_data.get(name)
            if val_json is not None:
                return val_json
            return default

        serialize_data['tlc_solvents'] = get_prop_or_json('tlc_solvents')
        serialize_data['tlc_description'] = self.json_data.get('tlc_description')
        serialize_data['reaction_svg_file'] = self.json_data.get('reaction_svg_file')

        serialize_data['rf_value'] = get_prop_or_json('rf_value')
        serialize_data['rxno'] = get_prop_or_json('rxno', '')
        # v4 derives concentration_mode from `use_reaction_volume` only when the mode is
        # absent, so sending the mode wins and the legacy boolean stays for older servers.
        # Without this the client could never select 'combined' — the boolean has no value
        # that maps to it.
        _mode = get_prop_or_json('concentration_mode')
        if _mode:
            serialize_data['concentration_mode'] = _mode
        serialize_data['short_label'] = self.json_data.get('short_label')
        serialize_data['literatures'] = self.json_data.get('literatures')

        serialize_data['research_plans'] = self.json_data.get('research_plans')
        serialize_data['user_labels'] = self.json_data.get('user_labels')
        serialize_data['solvent'] = self.json_data.get('solvent')

        serialize_data['volume'] = get_prop_or_json('volume')
        serialize_data['use_reaction_volume'] = get_prop_or_json('use_reaction_volume', False)
        serialize_data['weight_percentage'] = get_prop_or_json('weight_percentage', False)
        serialize_data['rinchi_string'] = get_prop_or_json('rinchi_string')
        serialize_data['rinchi_web_key'] = get_prop_or_json('rinchi_web_key')
        serialize_data['variations'] = get_prop_or_json('variations') or self._clean_variations()

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
                    "memValue": f"{total_time:0.15f}"
                }
                }

    def on_properties_change(self, dict_obj, name, value):
        """
        Validates and applies a change to one of the reaction's properties.

        The proposed value is validated and coerced via ``ReactionPropertiesModel`` (with the
        material lists excluded) and then dispatched to the appropriate side-effect handler (gas
        schema, vessel size or yield cache).

        :param dict_obj: The chain of dicts leading to the changed value
        :param name: The chain of keys identifying the changed value
        :param value: The chain of values, the last being the new value
        :return: ``False``, as the handler applies the change itself
        """
        import copy
        from pydantic import BaseModel
        from chemotion_api.models import ReactionPropertiesModel

        # 1. Build proposed dictionary state
        current_dict = {}
        for k, v in self._properties.items():
            if k in ['starting_materials', 'reactants', 'products', 'solvents', 'purification_solvents']:
                continue
            if hasattr(v, 'to_dict'):
                current_dict[k] = v.to_dict()
            elif isinstance(v, list):
                current_dict[k] = list(v)
            else:
                current_dict[k] = v

        pydantic_dict = {
            'name': current_dict.get('name'),
            'short_label': current_dict.get('short_label'),
            'status': current_dict.get('status'),
            'duration': current_dict.get('duration'),
            'temperature': current_dict.get('temperature'),
            'vessel_size': current_dict.get('vessel_size', {}).get('amount') if isinstance(current_dict.get('vessel_size'), dict) else current_dict.get('vessel_size'),
            'yield_value': current_dict.get('yield_value') if current_dict.get('yield_value') is not None else current_dict.get('yield'),
            'tlc_description': current_dict.get('tlc_description'),
            'dangerous_products': current_dict.get('dangerous_products'),
            'description': current_dict.get('description'),
            'reaction_description': current_dict.get('reaction_description') or current_dict.get('description'),
            'observation': current_dict.get('observation'),
            'user_labels': current_dict.get('user_labels'),
            'vessel': current_dict.get('vessel'),
            'gas_schema': current_dict.get('gaseous'),
            'position': current_dict.get('position'),
            'show_label': current_dict.get('show_label')
        }

        proposed_dict = copy.deepcopy(pydantic_dict)
        pyd_name = list(name)
        if pyd_name[0] == 'gaseous':
            pyd_name[0] = 'gas_schema'
        elif pyd_name[0] == 'yield':
            pyd_name[0] = 'yield_value'
        elif pyd_name[0] == 'vessel_size' and len(pyd_name) > 1 and pyd_name[1] == 'amount':
            pyd_name = ['vessel_size']

        temp = proposed_dict
        for key in pyd_name[:-1]:
            if key not in temp:
                temp[key] = {}
            temp = temp[key]
        temp[pyd_name[-1]] = value[-1]

        # Validate proposed dict using ReactionPropertiesModel
        validated = ReactionPropertiesModel.model_validate(proposed_dict)

        # Get coerced value
        coerced_val = validated
        for key in pyd_name:
            if isinstance(coerced_val, BaseModel):
                coerced_val = getattr(coerced_val, key)
            elif isinstance(coerced_val, dict):
                coerced_val = coerced_val[key]
            else:
                coerced_val = getattr(coerced_val, key)

        from chemotion_api.models import UnitDictModel
        from chemotion_api.utils import UnitDict
        if isinstance(coerced_val, UnitDictModel):
            if name[0] == 'temperature':
                coerced_val = Temperature(**coerced_val.model_dump())
            else:
                coerced_val = UnitDict(unit=coerced_val.unit, value=coerced_val.value)

        # Write coerced value to dict_obj[-1]
        dict_obj[-1][name[-1]] = coerced_val
        value[-1] = coerced_val
        if name[0] in ['yield', 'yield_value']:
            dict_obj[-1]['yield'] = coerced_val
            dict_obj[-1]['yield_value'] = coerced_val
            self._yield_value_cache = coerced_val

        # Execute original handlers
        if name[-1] == 'gaseous':
            self.gas_schema = value[-1]
            return False
        if name[-1] == 'vessel_size':
            self._properties['vessel_size'] = value[-1]
            self.update_amount()
            return False

        return False


    def _variation_segment_klasses(self) -> dict[str, dict]:
        return {klass.get('label'): klass for klass in self._generic_segments.all_classes
                if klass.get('element_klass', {}).get('name') == 'reaction' and klass.get('is_active', True)}

    def _clean_variations(self) -> dict:
        cleand_data = self.variations.clean()
        self._variations = None
        return cleand_data
