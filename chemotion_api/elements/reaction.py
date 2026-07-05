"""Reaction element and its helpers.

Defines :class:`Reaction` (a Chemotion reaction, extending
:class:`~chemotion_api.elements.abstract_element.AbstractElement`) together with the supporting
:class:`MaterialList` (a role-bound list of :class:`~chemotion_api.elements.sample.Sample`\\ s) and
:class:`Temperature` (a temperature-time profile). Reactions map their starting materials, reactants,
products and solvents to chem-dcat-ap via :meth:`Reaction.to_dcat_ap`, and persist the product yield
through an ``equivalent`` cache.
"""
import logging
import re
from typing import Literal, cast
from collections.abc import Iterator
from pydantic import BaseModel

logger = logging.getLogger(__name__)


#: Chemotion duration display units (e.g. "Hour(s)") mapped to seconds.
_DURATION_UNIT_SECONDS = {
    "second": 1, "minute": 60, "hour": 3600, "day": 86400, "week": 604800,
}


def _chemotion_duration_to_iso8601(text) -> str | None:
    """Convert a Chemotion duration display string to an ISO-8601 duration.

    Chemotion stores a reaction duration as a human string such as ``"3.5 Hour(s)"`` or
    ``"3 Day(s)"``. chem-dcat-ap emits it as an ``xsd:duration`` literal, which must be ISO-8601
    (e.g. ``PT3H30M`` / ``P3D``) — a raw display string produces an invalid literal. Fractional
    amounts are normalised into whole H/M/S (``xsd:duration`` only allows a fraction on seconds).

    :param text: the Chemotion duration display string.
    :return: an ISO-8601 duration string, or ``None`` if it cannot be parsed (so callers omit the
        field rather than emit an invalid literal).
    """
    if not text:
        return None
    m = re.match(r"\s*([0-9]*\.?[0-9]+)\s*([A-Za-z]+)", str(text))
    if not m:
        return None
    unit = re.sub(r"[^a-z]", "", m.group(2).lower())
    if unit.endswith("s"):
        unit = unit[:-1]
    if unit not in _DURATION_UNIT_SECONDS:
        return None
    total = int(round(float(m.group(1)) * _DURATION_UNIT_SECONDS[unit]))
    if total < 0:
        return None
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    date_part = f"{days}D" if days else ""
    time_part = "".join(p for p in (f"{hours}H" if hours else "",
                                    f"{minutes}M" if minutes else "",
                                    f"{secs}S" if secs else ""))
    if not date_part and not time_part:
        return "PT0S"
    return f"P{date_part}{'T' + time_part if time_part else ''}"


from requests import Response

from chemotion_api.elements.abstract_element import AbstractElement, Analyses, AnalysesList
from datetime import datetime

from chemotion_api.elements.sample import Sample, SampleVariationType
from chemotion_api.elements.utils import GasType
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
        return_element.reaction = self._reaction
        return_element.role_in_reaction = self._mat_type
        return_element.set_ref(False, False)
        return_element.properties['position'] = len(self)

        return return_element

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
        """
        Add a Sample without splitting it
        :param element: Sample to be added
        """

        self._check_element(element)
        return super(TypedList, self).append(element)


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
        """
        The reaction variations, lazily populated from the reaction's json_data.

        .. note::
            The reaction-variations feature is only partially implemented in this client. Existing
            variations are skipped (with a warning) when loaded and cannot be created or edited here;
            the raw variation payload is round-tripped untouched on save.

        :return: The :class:`Variations` container of this reaction
        """
        if self._variations is None:
            mat_samples = {}
            for reaction_elm_names in ['starting_materials', 'reactants', 'products', 'solvents']:
                mat_samples[reaction_elm_names] = self.properties[reaction_elm_names]
            self._variations = Variations(self)
            # offline-reconstructed reactions have no 'variations' key; treat as none
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
        The reference sample of the reaction.

        Scans the starting materials and reactants for the one flagged as reference. If none is
        flagged, the last candidate is marked as the reference and returned.

        :return: The reference :class:`Sample`, or ``None`` if there are no candidates
        """
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

    def get_gas_component(self, gt: GasType):
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
            'temperature': Temperature(**(validated.temperature.to_dict() if validated.temperature else self.json_data.get('temperature', {}))),
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
                try:
                    products[0]._properties['equivalent'] = float(reaction_yield) / 100.0
                except (IndexError, KeyError, ValueError, TypeError, AttributeError) as e:
                    logger.warning("Could not persist reaction yield onto product[0].equivalent: %s", e)
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

    def to_dcat_ap(self) -> BaseModel:
        """
        Maps the reaction to a chem-dcat-ap ``ChemicalReaction``.

        Aggregates the chem-dcat-ap mappings of the reaction's starting materials, reactants,
        products and solvents and enriches them with the reaction's duration (ISO 8601), yield,
        temperature profile and status.

        :return: A chem-dcat-ap ``ChemicalReaction`` pydantic model describing the reaction
        """
        from chem_dcat_ap.datamodel.chem_dcat_ap_pydantic import (
            ChemicalReaction,
            Yield,
            Temperature,
            DefinedTerm
        )

        reaction_id = self.json_ld.get('@id') or f"{self._session._host_url}/api/v1/reactions/{self.id}"

        def get_plain_text(q) -> str:
            import collections.abc
            if isinstance(q, str):
                return q
            if isinstance(q, collections.abc.Mapping) and 'ops' in q:
                ops = q['ops']
                if isinstance(ops, collections.abc.Iterable):
                    return "".join(op.get('insert', '') for op in ops if isinstance(op, collections.abc.Mapping)).strip()
            return str(q) if q is not None else ""

        used_starting_material = [s.to_dcat_ap() for s in self.starting_materials]
        used_reactant = [s.to_dcat_ap() for s in self.reactants]
        generated_product = [s.to_dcat_ap() for s in self.products]
        used_solvent = [s.to_dcat_ap() for s in self.solvents]

        has_duration = None
        start = self.properties.get('timestamp_start')
        stop = self.properties.get('timestamp_stop')
        if isinstance(start, datetime) and isinstance(stop, datetime):
            diff = stop - start
            seconds = int(diff.total_seconds())
            if seconds >= 0:
                hours = seconds // 3600
                minutes = (seconds % 3600) // 60
                secs = seconds % 60
                has_duration = f"PT{hours}H{minutes}M{secs}S"
        if not has_duration and self.properties.get('duration'):
            # Chemotion stores a display string like "3.5 Hour(s)"; convert to ISO-8601 so the
            # xsd:duration literal is valid (a raw string like "4 Hour(s)" is not parseable).
            has_duration = _chemotion_duration_to_iso8601(self.properties.get('duration'))

        has_yield = None
        yield_val = self._current_yield()
        if yield_val is not None:
            try:
                has_yield = [Yield(
                    value=float(yield_val),
                    has_quantity_type="http://qudt.org/vocab/quantitykind/Dimensionless",
                    unit="http://qudt.org/vocab/unit/PERCENT",
                    title="Yield [%]"
                )]
            except (ValueError, TypeError) as e:
                logger.warning("Skipping yield in DCAT-AP mapping (value=%r): %s", yield_val, e)

        has_temperature = None
        temp_prop = self.properties.get('temperature')
        def get_qudt_unit(unit_str: str) -> str:
            if not unit_str:
                return "https://qudt.org/vocab/unit/UNITLESS"
            u = unit_str.strip().lower()
            if u in ('°c', 'c', 'deg_c', 'deg c'): return "https://qudt.org/vocab/unit/DEG_C"
            if u in ('k', 'kelvin'): return "https://qudt.org/vocab/unit/K"
            return f"https://qudt.org/vocab/unit/{unit_str}"

        if temp_prop and temp_prop.get('data'):
            temp_list = []
            for tp in temp_prop.get('data'):
                val_str = tp.get('value')
                if val_str:
                    try:
                        temp_list.append(Temperature(
                            value=float(val_str),
                            has_quantity_type="http://qudt.org/vocab/quantitykind/Temperature",
                            unit=get_qudt_unit(temp_prop.get('valueUnit', '°C')),
                            title="Temperature step"
                        ))
                    except (ValueError, TypeError) as e:
                        logger.warning("Skipping temperature step in DCAT-AP mapping (value=%r): %s", val_str, e)
            if temp_list:
                has_temperature = temp_list

        status_val = self.properties.get('status')
        has_qualitative_attribute = None
        if status_val:
            from chem_dcat_ap.datamodel.chem_dcat_ap_pydantic import QualitativeAttribute
            has_qualitative_attribute = [QualitativeAttribute(
                value=str(status_val),
                title="Status",
                description="The status of the reaction",
                rdf_type=DefinedTerm(id="SIO:001326", title="status descriptor")
            )]

        return ChemicalReaction(
            id=reaction_id,
            title=[self.name] if self.name else [f"Reaction-{self.id}"],
            description=[get_plain_text(self.properties.get('description') or self.properties.get('reaction_description'))] if (self.properties.get('description') or self.properties.get('reaction_description')) else None,
            used_starting_material=used_starting_material or None,
            used_reactant=used_reactant or None,
            generated_product=generated_product or None,
            used_solvent=used_solvent or None,
            has_duration=has_duration,
            has_yield=has_yield,
            has_temperature=has_temperature,
            has_qualitative_attribute=has_qualitative_attribute
        )

    def _clean_variations(self) -> dict:
        cleand_data = self.variations.clean()
        self._variations = None
        return cleand_data

class SampleVariation(Sample):
    """
    A read-only snapshot of a :class:`chemotion_api.elements.sample.Sample` within a reaction
    variation.

    .. note::
        Part of the incomplete reaction-variations feature of this client and not fully functional.
    """

    def __init__(self, sample: Sample):
        super().__init__(**sample.clone_init_args())  # type: ignore[attr-defined]  # incomplete upstream code: clone_init_args is undefined on Sample
        pass

    def save(self, *args, **kwargs):
        """
        Always fails: a sample variation is a snapshot and cannot be saved.

        :raises NotImplementedError: Always, since variation samples cannot be saved
        """
        raise NotImplementedError(f'This sample is only a Variation of {self.short_label} and cannot be saved!')

class Variation:
    """
    A single variation of a :class:`Reaction` (its own properties, notes and material snapshots).

    Standalone (not a :class:`Reaction` subclass): a variation is not substitutable for a
    reaction — its material properties hold :class:`SampleVariation` snapshots, not
    :class:`MaterialList` objects — and it never used the inherited behaviour.

    .. note::
        Part of the incomplete reaction-variations feature of this client and not fully functional.
    """

    def __init__(self):
        self.json_data = None
        self._json_data = None
        self.id = -1
        self._properties = {}
        self.notes = ""
        self._ref_mat = None
        self._materials: dict = {}
        self._analyses = None

    def populate(self, json_data: dict, analyses: AnalysesList, starting_materials: MaterialList,
                 reactants: MaterialList,
                 products: MaterialList, solvents: MaterialList, vessel_size: dict):
        """
        Populates the variation from its raw json data and the reaction's material lists.

        :param json_data: The raw variation data
        :param analyses: The analyses of the owning reaction
        :param starting_materials: The starting materials of the owning reaction
        :param reactants: The reactants of the owning reaction
        :param products: The products of the owning reaction
        :param solvents: The solvents of the owning reaction
        :param vessel_size: The vessel size of the owning reaction
        """
        self._json_data = json_data
        self.id = self._json_data['id']
        self._properties = json_data['properties']
        self.notes = json_data['metadata']['notes']
        self._analyses = analyses  # type: ignore[assignment]  # base infers _analyses as None; Variation stores an AnalysesList at runtime
        self._materials = {
            SampleVariationType.STARTING_MATERIAL: [
                self.sample_variation_factory(x, SampleVariationType.STARTING_MATERIAL) for x in
                starting_materials],
            SampleVariationType.REACTANT: [self.sample_variation_factory(x, SampleVariationType.REACTANT)
                                           for x in
                                           reactants],
            SampleVariationType.PRODUCT: [self.sample_variation_factory(x, SampleVariationType.PRODUCT) for
                                          x in
                                          products],
            SampleVariationType.SOLVENTS: [self.sample_variation_factory(x, SampleVariationType.SOLVENTS)
                                           for x in
                                           solvents],
        }

    def sample_variation_factory(self, sample: Sample, sample_type: SampleVariationType) -> SampleVariation:
        """
        Builds a :class:`SampleVariation` for a sample of the given variation type.

        :param sample: The reaction sample to snapshot
        :param sample_type: The variation category of the sample
        :return: The created :class:`SampleVariation`
        """
        json_data = None
        for key, data in self._json_data.get(sample_type.value, {}).items():
            if key == str(sample.id):
                json_data = data

        return SampleVariation(sample, json_data)  # type: ignore[call-arg]  # incomplete upstream code: SampleVariation.__init__ takes only `sample`

    @staticmethod
    def _get_vessel_volume(vessel_size):
        vessel_volume = vessel_size.get('amount')
        if vessel_volume is not None and vessel_size.get('unit') == 'l':
            vessel_volume *= 1000
        return vessel_volume

    def update_and_clean(self, vessel_size: float | None = None):
        """
        Recomputes the auxiliary data of all sample variations and serializes the variation.

        :param vessel_size: The vessel size used to recompute concentrations
        :return: The cleaned variation data
        """
        vessel_volume = self._get_vessel_volume(vessel_size)
        for _sample_type, sample_variations in self._materials.items():
            for sample_variation in sample_variations:
                sample_variation.set_aux(vessel_volume)
        return self.clean()

    def clean(self):
        """
        Serializes the variation back into its raw json representation.

        :return: The cleaned variation data
        """
        self._json_data['properties'] = self._properties
        self._json_data['metadata']['notes'] = self.notes
        for sample_type, sample_variations in self._materials.items():
            self._json_data[sample_type.value] = {}
            for sample_variation in sample_variations:
                self._json_data[sample_type.value][sample_variation.sample.id] = sample_variation.clean()
        return self._json_data

    def link_analyses(self, analyses: Analyses):
        """
        Links an already saved analysis to this variation.

        :param analyses: The analysis to link
        :raises ValueError: If the analysis has no id (i.e. the reaction has not been saved yet)
        """
        try:
            int(cast(int, analyses.id))
            self._json_data['metadata']['analyses'].append(analyses.id)
        except ValueError:
            raise ValueError("Analyses has no id. please save the Reaction first") from None

    def get_analyses(self) -> Iterator[Analyses]:
        """
        Yields the analyses linked to this variation.

        :return: An iterator over the linked :class:`Analyses`
        """
        for ana_id in self._json_data['metadata']['analyses']:
            yield cast(AnalysesList, self._analyses).by_id(ana_id)

    @property
    def properties(self):
        """
        The raw properties dict of the variation.

        :return: The variation properties
        """
        return self._properties

    @property
    def starting_materials(self) -> list[SampleVariation]:
        """
        The starting material variations.

        :return: A list of :class:`SampleVariation`
        """
        return self._materials[SampleVariationType.STARTING_MATERIAL]

    @property
    def reactants(self) -> list[SampleVariation]:
        """
        The reactant variations.

        :return: A list of :class:`SampleVariation`
        """
        return self._materials[SampleVariationType.REACTANT]

    @property
    def products(self) -> list[SampleVariation]:
        """
        The product variations.

        :return: A list of :class:`SampleVariation`
        """
        return self._materials[SampleVariationType.PRODUCT]

    @property
    def solvents(self) -> list[SampleVariation]:
        """
        The solvent variations.

        :return: A list of :class:`SampleVariation`
        """
        return self._materials[SampleVariationType.SOLVENTS]


class Variations(MutableSequence):
    """
    An ordered, mutable sequence of a reaction's :class:`Variation` objects.

    .. note::
        The reaction-variations feature is only partially implemented in this client. Existing
        variations are skipped (with a warning) when loaded and cannot be created here; the raw
        variation payload is round-tripped untouched on save.
    """

    def __init__(self, reaction: Reaction):
        # Initialize the list with given items
        self._data: list = list()
        self._reaction = reaction
        self._highest_id = 0

    def populate(self, json_data: dict):
        """
        Loads the variations from the reaction's raw variation data.

        Because the variations feature is incompletely implemented, any error during loading is
        caught and the variations are dropped with a warning rather than raised.

        :param json_data: The raw list of variation data from the reaction
        """
        # NOTE: the reaction-variations feature is incompletely implemented in this client (and
        # inherited as such from upstream chemotion_api): Variation/SampleVariation rely on
        # undefined helpers (`clone_init_args`, `set_aux`) and a signature mismatch. Rather than
        # crash when a reaction that happens to carry variations is inspected, we skip them with
        # a clear warning so the rest of the reaction stays usable. Saving is unaffected: the raw
        # variation payload is round-tripped untouched (see Reaction._clean_properties_data).
        if not json_data:
            return
        try:
            for variation in json_data:
                v = Variation()
                # Known-incomplete: Variation.populate's signature does not match this call (see
                # populate docstring); it raises and is handled below. Flagged for type checkers.
                v.populate(variation, self._reaction)  # type: ignore[call-arg, arg-type]
                self.append(v)
                self._highest_id = max(self._highest_id, variation['id'])
        except Exception as e:
            self._data = []
            logger.warning("Reaction variations are not supported by this client and were not "
                           "loaded (%d present): %s", len(json_data), e)

    def remove(self, value: Variation) -> None:
        """
        Removes a variation from the sequence by its id.

        Follows the :class:`~collections.abc.MutableSequence` contract.

        :param value: The variation to remove
        :raises ValueError: if no variation with the given id is present
        """
        try:
            idx = next(idx for idx, v in enumerate(self) if v.id == value.id)
        except StopIteration:
            raise ValueError(f'Variation with id {value.id} not in list') from None
        self.pop(idx)

    def add_new(self) -> Variation:
        """
        Not supported: creating reaction variations is not implemented by this client.

        :raises NotImplementedError: Always, as variations must be edited in the Chemotion web UI
        """
        raise NotImplementedError(
            "Creating reaction variations is not supported by this client: the underlying "
            "Variation/SampleVariation implementation is incomplete (missing clone_init_args/"
            "set_aux). Edit variations directly in the Chemotion web UI.")

    @classmethod
    def empty_variation(cls, highest_id: int) -> dict:
        """
        Builds the raw data of an empty variation with default temperature and duration.

        :param highest_id: The id to assign to the new variation
        :return: The raw variation data
        """
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
        """
        Sorts the variations in place by their id.
        """
        self._data = sorted(self._data, key=lambda v: v.id)

    def clean(self):
        """
        Serializes all variations into their raw data representation.

        :return: A list of cleaned variation data
        """
        return [variation.update_and_clean() for variation in self._data]

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
        """
        Inserts a variation at the given index and re-sorts the sequence.

        :param index: The index at which to insert
        :param value: The variation to insert
        """
        # Insert an item at the given index
        self._data.insert(index, value)
        self.sort()

    def __len__(self):
        # Return the length of the list
        return len(self._data)

    def __repr__(self):
        # Return a string representation of the list
        return f"{repr(self._data)}"