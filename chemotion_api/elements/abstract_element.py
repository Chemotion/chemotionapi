import json
import os.path
import re
import uuid
from datetime import datetime

import dateutil.parser

from chemotion_api.connection import Connection
from chemotion_api.elements.attachments import Attachments

from chemotion_api.generic_segments import GenericSegments
from chemotion_api.utils import add_to_dict, parse_generic_object_json, \
    clean_generic_object_json, merge_dicts, snake_to_camel_case

from requests.exceptions import RequestException


class Dataset(dict):
    def __init__(self, session: Connection, json_data: dict):
        self.id = json_data.get('id')
        self.name = json_data.get('name')
        self.description = json_data.get('description')
        ds_json = json_data.get('dataset')
        if ds_json is not None:
            res = parse_generic_object_json(ds_json)
            super().__init__(res.get('values'))
            self._mapping = res.get('obj_mapping')
        self._session = session
        self._json_data = json_data

    def write_zip(self, destination=''):
        image_url = "/api/v1/attachments/zip/{}".format(self.id)
        res = self._session.get(image_url)
        if res.status_code != 200:
            raise ConnectionRefusedError('{} -> {}'.format(res.status_code, res.text))

        if not os.path.exists(destination) or os.path.isdir(destination):
            regex_file_name = re.search('filename="([^"]+)', res.headers['Content-Disposition'])
            destination = os.path.join(destination, regex_file_name.groups()[0])

        with open(destination, 'wb+') as f:
            f.write(res.content)

        return destination

    def write_data_set_xlsx(self, destination=''):
        image_url = "/api/v1/attx/dataset/{}".format(self.id)
        res = self._session.get(image_url)
        if res.status_code != 200:
            raise ConnectionRefusedError('{} -> {}'.format(res.status_code, res.text))

        if not os.path.exists(destination) or os.path.isdir(destination):
            regex_file_name = re.search('filename="([^"]+)', res.headers['Content-Disposition'])
            destination = os.path.join(destination, regex_file_name.groups()[0])

        with open(destination, 'wb+') as f:
            f.write(res.content)

        return destination

    def to_json(self):
        ds = self._json_data.get('dataset')
        if ds is not None:
            clean_generic_object_json(ds, self, self._mapping)
            ds['changed'] = True


class Analyses(dict):
    def __init__(self, data, session: Connection):
        super().__init__()
        self._session = session
        self.id = data.get('id')
        self.type = data.get('extended_metadata', {}).get('kind', '')

        self._data = data
        self['name'] = data['name']
        self['description'] = data['description']
        self.datasets = []
        for jd in self._data.get('children'):
            self.datasets.append(Dataset(session, jd))

    def preview_image(self):
        if self._data.get('preview_img') is None or self._data.get('preview_img').get('id') is None:
            return None
        return self._load_image(self._data.get('preview_img').get('id'))

    def _load_image(self, file_id: int):
        image_url = "/api/v1/attachments/{}".format(file_id)
        res = self._session.get(image_url)
        if res.status_code != 200:
            raise ConnectionRefusedError('{} -> {}'.format(res.status_code, res.text))

        return res.content

    def to_josn(self):
        self._data['name'] = self['name']
        self._data['description'] = self['description']
        for ds in self.datasets:
            ds.to_json()
        return self._data


class Segment(dict):
    def __init__(self, generic_segments: GenericSegments, element_type: str, on_add, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._generic_segments = generic_segments
        self._all_seg_classes = [seg for seg in generic_segments.all_classes if
                                 seg.get('element_klass').get('name') == element_type]
        self._element_type = element_type
        self._on_add = on_add

        for seg in self._all_seg_classes:
            self[seg.get('label')] = super().get(seg.get('label'))

    def get(self, key):
        val = super().get(key)
        if val is None:
            seg = next((x for x in self._all_seg_classes if x.get('label') == key), None)
            if seg is None or seg.get('element_klass').get('name') != self._element_type:
                raise TypeError('Segemnt "{}" is not for element "{}"'.format(key, self._element_type))
            new_seq_obj = GenericSegments.new_session(seg)
            key = add_to_dict(self, key, None)
            val = self[key] = self._on_add(key, new_seq_obj)
        return val


class AbstractElement:
    """
    This abstract element is the basis for all chemotion-api elements. It provides all the necessary functions and properties to work with these elements.
    It contains. For more details check the Element classes out.
    """

    def __init__(self, generic_segments: GenericSegments, session: Connection, json_data: dict = None, id: int = None,
                 element_type: str = None):
        self._attachments: Attachments | None = None
        self._generic_segments = generic_segments
        self._session = session

        self._short_label = None
        self._properties = None
        self._analyses = None
        self._segments = None
        # Name of element
        self.name: str = ''
        # Last update of the element
        self.last_update: datetime | None = None
        self._element_type = element_type
        self._id = id
        # Json LD description of the element. It contains @type and @ID
        self.json_ld: dict = {}
        # Json data contains the raw data fetched from the server
        self.json_data: dict | None = None
        if json_data is not None:
            self._set_json_data(json_data)
        elif id is not None and element_type is not None:
            self.load()
        else:
            raise ValueError("Either 'json_data' or 'id' and 'element_type' must be provided during initialization")

    @property
    def short_label(self) -> str | None:
        """
        The short label of en element if available

        :return: short label of en element
        """
        return self._short_label

    @property
    def properties(self) -> dict:
        """
        The properties property contains all data from the main tab of the elements in Chemotion.

        :return: Element properties
        """
        return self._properties

    @property
    def analyses(self) -> Analyses:
        """
        With the analyses object one can read and write all information from the analysis Tab in Chemotion.

        :return: Analyses object
        """
        return self._analyses

    @property
    def segments(self) -> Segment:
        """
        Contains all segments (tabs) of elements in Chemotion.
        It contains generic elements as well as the proerties and the analyses segment

        :return: Segment object
        """
        return self._segments

    @property
    def attachments(self) -> Attachments | None:
        """
        Attachment container of the element. This s None if the element has no Attachments

        :return: Attachments container
        """
        if self._attachments is None:
            attachments_data = self.json_data.get('attachments')
            if attachments_data is not None:
                self._attachments = Attachments(self._session, attachments_data)
        return self._attachments

    @property
    def id(self) -> int:
        """
        Database ID of the element

        :return: Database ID of the element
        """
        return self._id

    @id.setter
    def id(self, id_val: int):
        """
        Database ID of the element
        """
        self._id = id_val
        if self.json_data is not None:
            self.json_ld[
                '@id'] = f"{self._session._host_url}{self.get_url(self.element_type)}/{self.id}.json" if self.id is not None else uuid.uuid4().__str__()

    @property
    def element_type(self) -> str:
        """
        Element type: is either 'sample', 'sample', 'reaction', 'wellplate', 'research_plan' or if the element is a generic one it is only 'element'

        :return: The element type
        """
        return self._element_type

    @element_type.setter
    def element_type(self, element_type_val: str):
        """
        Element type: is either 'sample', 'sample', 'reaction', 'wellplate', 'research_plan' or if the element is a generic one it is only 'element'
        Has to be set if json data is not available at the moment of creation
        """
        self._element_type = element_type_val
        if self.json_data is not None:
            schema_version = self.json_data.get('properties', {}).get('version')
            self.json_ld['@type'] = self._session.schema_manager.generate_model_type(self.element_type, schema_version)

    def load(self):
        """
        Loads and parses the data of an element from the server.
        The standard Values can be found in the properties property or the segment

        :raises RequestException: If the element could not be loaded!

        :raises ValueError: If no ID available!
        """

        if self._id is None:
            raise ValueError("No ID available")
        payload = {}
        res = self._session.get(f"{self.__class__.get_url(self.element_type)}/{self.id}.json",
                                data=payload)
        if res.status_code != 200:
            raise RequestException("{} -> {}".format(res.status_code, res.text))
        res_json = res.json()
        json_data = res_json[self.get_response_key(self.element_type)]
        attachments_data = res_json.get('attachments')
        if attachments_data is not None:
            self._attachments = Attachments(self._session, attachments_data)
        self._set_json_data(json_data)

    def _set_json_data(self, json_data):
        self.json_data = json_data
        if json_data.get('updated_at') is not None:
            try:
                for pattern in ['%Y-%m-%d %H:%M:%S %Z', '%d.%m.%Y, %H:%M:%S %z']:
                    try:
                        self.last_update = datetime.strptime(json_data.get('updated_at'), pattern)
                        break
                    except:
                        pass

                if self.last_update is None:
                    self.last_update = dateutil.parser.parse(json_data.get('updated_at'))
            except:
                pass
        self.name = json_data.get('name', '')

        self._short_label = self.json_data.get('short_label')
        self.element_type = json_data.get('type')
        self.id = json_data.get('id')

        self._properties: dict = self._parse_properties()
        self._analyses: list[dict] = self._parse_analyses()
        segment_temp = self._parse_segments()
        self._segments_mapping = segment_temp.get('obj_mapping')
        self._segments = Segment(self._generic_segments,
                                 json_data.get('type'),
                                 self._on_add_segment,
                                 segment_temp.get('values'))
        add_to_dict(self.segments, 'Properties', self.properties)
        add_to_dict(self.segments, 'Analyses', self.analyses)

    def _on_add_segment(self, key: str, segment_data: dict) -> dict:
        temp_segment = parse_generic_object_json(segment_data)
        self._segments_mapping[key] = temp_segment.get('obj_mapping')
        self.json_data['segments'] = self.json_data.get('segments', [])
        self.json_data['segments'].append(segment_data)
        return temp_segment.get('values')

    def save(self):
        """
        Saves or creates an object according to the set properties. It overwrites the
        json_data entries by the values set in the segments object.

        :raises RequestException: If request was not successful
        """
        data = self.clean_data()
        is_created = False
        if self.id is None:
            res = self._session.post(self.save_url(), data=json.dumps(data))
            is_created = True
        else:
            res = self._session.put(self.save_url(), data=json.dumps(data))
        if res.status_code != 200 and res.status_code != 201:
            raise RequestException('{} -> '.format(res.status_code, res.text))
        if is_created:
            res_json = res.json()
            res_json = merge_dicts(self.json_data, res_json.get(self.element_type, res_json.get('element')))
            self._set_json_data(res_json)
        if self.attachments is not None:
            self.attachments.save(self.id, snake_to_camel_case(self.get_response_key(self.element_type)))

    def clean_data(self) -> dict:
        """
        Takes the values from the segments object and attachment object
        and overwrites the json_data values accordingly.

        :return: cleaned data
        """
        cleaned_data = {
            'id': self.id or uuid.uuid4().__str__(),
            'is_new': self.id is None,
            'type': self.element_type
        }
        if isinstance(self.name, str):
            self.json_data['name'] = self.name
        if 'collection_id' in self.json_data:
            cleaned_data['collection_id'] = self.json_data['collection_id']
        if 'container' in self.json_data:
            cleaned_data['container'] = self.json_data['container']
        if self.attachments is not None:
            cleaned_data['attachments'] = self.attachments.attachment_data

        merge_dicts(cleaned_data, self._clean_segments_data(), self._clean_properties_data(),
                    self._clean_analyses_data())
        return cleaned_data

    def save_url(self) -> str:
        """
        Retrieves the save URL, which varies based on whether the element already has an ID.

        :return: The save URL
        """
        if self.id is not None:
            return "/api/v1/{}s/{}".format(self.json_data.get('type'), self.id)
        return "/api/v1/{}s/".format(self.json_data.get('type'))

    def __eq__(self, other):
        return isinstance(other, AbstractElement) and self.json_ld['@id'] == other.json_ld['@id']

    def __ne__(self, other):
        return not isinstance(other, AbstractElement) or self.json_ld['@id'] != other.json_ld['@id']

    def _parse_properties(self) -> dict:
        raise NotImplemented

    def _clean_properties_data(self, serialize_data: dict | None = None) -> dict:
        raise NotImplemented

    def _parse_analyses(self) -> list:
        analyses_list = []
        container = self.json_data.get('container')
        if container is not None and len(container.get('children', [])) > 0:
            for analyses in container.get('children', [{}])[0].get('children', []):
                analyses_list.append(Analyses(analyses, self._session))
        return analyses_list

    def _clean_analyses_data(self) -> dict:
        container = self.json_data.get('container')
        if container is None:
            return {}
        obj = {"container": {
            "children": [{"children": []}]
        }}
        res_list = container.get('children', [{}])[0].get('children', [])
        for (idx, analyses) in enumerate(res_list):
            analyses_obj: list[Analyses] = [item for (index, item) in enumerate(self.analyses) if
                                            item.id == analyses.get('id')]
            if len(analyses_obj) == 1:
                new_data = analyses_obj[0].to_josn()
                for (key, item) in analyses.items():
                    if key in new_data:
                        res_list[idx][key] = new_data.get(key, res_list[idx][key])

        obj["container"]["children"][0]["children"] = res_list
        return obj

    def _parse_segments(self) -> dict[str: dict]:
        results: dict[str: dict] = {}
        results_mapping: dict[str: dict] = {}
        for segment in self.json_data.get('segments', []):
            a = [x for x in self._generic_segments.all_classes if x['id'] == segment['segment_klass_id']]
            temp_segment = parse_generic_object_json(segment)
            key = add_to_dict(results, a[0].get('label', 'no_label'), temp_segment.get('values'))
            results_mapping[key] = temp_segment.get('obj_mapping')
        return {'values': results, 'obj_mapping': results_mapping}

    def _clean_segments_data(self) -> dict:
        res_list = self.json_data.get('segments', [])
        for (seg_key, segment_mapping) in self._segments_mapping.items():
            if seg_key in self.segments and self.segments[seg_key] is not None:
                list_idx = next((i for (i, x) in enumerate(res_list) if x.get('id') == segment_mapping['__id']), -1)
                if list_idx == -1:
                    list_idx = len(res_list)
                    res_list.append()
                clean_generic_object_json(res_list[list_idx], self.segments[seg_key], segment_mapping)

        return {'segments': res_list}

    @classmethod
    def get_response_key(cls, name: str) -> str:
        """
        Returns the element name used to construct the save and load URL

        :param name: The name of the element type

        :return: 
        """
        if name == 'sample':
            return 'sample'
        elif name == 'reaction':
            return 'reaction'
        elif name == 'wellplate':
            return 'wellplate'
        elif name == 'research_plan':
            return 'research_plan'
        return 'element'

    @classmethod
    def get_url(cls, name: str) -> str:
        """
        Returns the load URL based on the element type

        :param name: The name of the element type

        :return: The load url
        """
        if name == 'sample':
            return '/api/v1/samples'
        elif name == 'reaction':
            return '/api/v1/reactions'
        elif name == 'wellplate':
            return '/api/v1/wellplates'
        elif name == 'research_plan':
            return '/api/v1/research_plans'
        return f'/api/v1/generic_elements'
