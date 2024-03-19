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

    def append_no_split(self, value: Sample):
        if value.id is None:
            value.save()
        return super().append(value)


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
            'type_ontology': self.json_data.get('rxno'),
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
        serialize_data['description'] = self.properties.get('description')
        serialize_data['dangerous_products'] = self.properties.get('dangerous_products')
        serialize_data['conditions'] = self.properties.get('conditions')
        serialize_data['duration'] = self.properties.get('duration')
        serialize_data |= self._calc_duration()
        serialize_data['timestamp_start'] = timestamp_start
        serialize_data['timestamp_stop'] = timestamp_stop
        serialize_data['temperature'] = self.properties.get('temperature')
        serialize_data['observation'] = self.properties.get('observation')
        serialize_data['purification'] = self.properties.get('purification')
        serialize_data['status'] = self.properties.get('status')

        serialize_data['tlc_solvents'] = self.json_data.get('tlc_solvents')
        serialize_data['tlc_description'] = self.json_data.get('tlc_description')
        serialize_data['reaction_svg_file'] = self.json_data.get('reaction_svg_file')
        serialize_data['role'] = self.json_data.get('role', '')
        serialize_data['rf_value'] = self.json_data.get('rf_value')
        serialize_data['rxno'] = self.json_data.get('rxno', '')
        serialize_data['short_label'] = self.json_data.get('short_label')
        serialize_data['status'] = self.json_data.get('status')
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
