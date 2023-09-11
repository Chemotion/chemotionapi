from chemotion_api.elements.abstract_element import AbstractElement
from datetime import datetime

from chemotion_api.elements.sample import Sample


class MaterialList(list):

    def __setitem__(self, index: int, value: Sample):
        return super().__setitem__(index, value.split())

    def append(self, value: Sample):
        if value.id is None:
            value.save()
        return super().append(value.split())

class Temperature(dict):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def add_time_point(self, hour, minute, second, temperature):
        data = self.get('data')
        if data is None:
            self['data'] = []
            data = self['data']
        data.append({'time': f'{hour}:{minute}:{second}', 'value': temperature})


class Reaction(AbstractElement):
    datetime_format = '%m/%d/%Y %H:%M:%S'

    def _set_json_data(self, json_data: dict):
        super()._set_json_data(json_data)
        self._svg_file = self.json_data.get('reaction_svg_file')

    def load_image(self) -> str:
        image_url = "/images/samples/{}".format(self._svg_file)
        res = self._session.get(image_url)
        return res.text

    def _parse_properties(self) -> dict:
        reaction_elements = {}
        for reaction_elm_names in ['starting_materials', 'reactants', 'products', 'solvents', 'purification_solvents']:
            temp = []
            for sample in self.json_data[reaction_elm_names]:
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
            'type_ontology': self.json_data.get('rxno'),
            'temperature' : Temperature(**self.json_data.get('temperature', {})),
            'status' : self.json_data.get('status')
            # 'tlc_solvents': self.json_data.get('tlc_solvents'),
            # 'tlc_description': self.json_data.get('tlc_description'),
            # 'rf_value': self.json_data.get('rf_value'),
        }

    def _clean_properties_data(self):
        self.json_data['materials'] = {}
        for reaction_elm_names in ['starting_materials', 'reactants', 'products', 'solvents', 'purification_solvents']:
            temp_json_sample = self.json_data[reaction_elm_names]
            self.json_data['materials'][reaction_elm_names] = []
            for sample in self.properties[reaction_elm_names]:
                origen = next((x for x in temp_json_sample if x['id'] == sample.id), {})
                self.json_data['materials'][reaction_elm_names].append(origen | sample.clean_data())

        try:
            timestamp_start = self.properties.get('timestamp_start').strftime(self.datetime_format)
        except:
            timestamp_start = ''
        try:
            timestamp_stop = self.properties.get('timestamp_stop').strftime(self.datetime_format)
        except:
            timestamp_stop = ''

        self.json_data['timestamp_start'] = timestamp_start
        self.json_data['timestamp_stop'] = timestamp_stop
        self.json_data['description'] = self.properties.get('description')
        self.json_data['name'] = self.properties.get('name')
        self.json_data['observation'] = self.properties.get('observation')
        self.json_data['purification'] = self.properties.get('purification')
        self.json_data['dangerous_products'] = self.properties.get('dangerous_products')
        self.json_data['conditions'] = self.properties.get('conditions')
        self.json_data['solvent'] = self.properties.get('solvent')
        self.json_data['rinchi_long_key'] = self.properties.get('rinchi_long_key')
        self.json_data['rinchi_short_key'] = self.properties.get('rinchi_short_key')
        self.json_data['rinchi_web_key'] = self.properties.get('rinchi_web_key')
        self.json_data['duration'] = self.properties.get('duration')
        self.json_data['rxno'] = self.properties.get('type_ontology')
        self.json_data['temperature'] = self.properties.get('temperature')
        self.json_data['status'] = self.properties.get('status')
