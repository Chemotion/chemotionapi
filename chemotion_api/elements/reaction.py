from requests import Response

from chemotion_api.elements.abstract_element import AbstractElement
from datetime import datetime

from chemotion_api.elements.sample import Sample
from chemotion_api.elements.schemas.reaction import schema, PURIFICATION_OPTIONS, STATUS_OPTIONS
from chemotion_api.utils import TypedList, quill_hedging


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


        Readonly properties:

        :key short_label: {str, readonly}
        :key tlc_solvents: {str, readonly}
        :key tlc_description: {str, readonly}
        :key reaction_svg_file: {str, readonly}
        :key role: {str, readonly}
        :key rf_value: {str, readonly}
        :key rxno: {str, readonly}
        :key literatures: {str, readonly}
        :key variations: {str, readonly}

        :return: Element properties
        """
        return super().properties

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
            'status': self.json_data.get('status')
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

        serialize_data['tlc_solvents'] = self.json_data.get('tlc_solvents')
        serialize_data['tlc_description'] = self.json_data.get('tlc_description')
        serialize_data['reaction_svg_file'] = self.json_data.get('reaction_svg_file')
        serialize_data['role'] = self.properties.get('role', '')
        serialize_data['rf_value'] = self.json_data.get('rf_value')
        serialize_data['rxno'] = self.json_data.get('rxno', '')
        serialize_data['short_label'] = self.json_data.get('short_label')
        serialize_data['literatures'] = self.json_data.get('literatures')

        serialize_data['variations'] = self.json_data.get('variations', [])

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
