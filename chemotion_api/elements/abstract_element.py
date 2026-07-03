"""Base class and shared building blocks for all Chemotion elements (lifecycle, analyses, datasets, attachments)."""
import json
import os.path
import re
import uuid
from datetime import datetime
from typing import Self, cast, Any

import dateutil.parser
from jsonschema.validators import validate

from chemotion_api.elements.analyses_manager import AnalysesManager

from chemotion_api.connection import Connection
from chemotion_api.elements.attachments import Attachments, MutableAttachments

from chemotion_api.generic_segments import GenericSegments
from chemotion_api.utils import add_to_dict, parse_generic_object_json, \
    clean_generic_object_json, merge_dicts, snake_to_camel_case, fixeddict_serializer, PropertyDict

from requests.exceptions import RequestException


class Dataset(dict):
    """
    A Dataset is an object that consists of a metadata set and a measurement file.
    If all components have been configured correctly in Chemotion, a BagIT
    container is created when a new file is uploaded. This container is then used
    to automatically fill in the metadata set and forward the measurement data to ChemSpectra.

    Usage::

    >>> from chemotion_api import Instance
    >>> import logging
    >>> try:
    >>>     instance = Instance('http(d)://xxx.xxx.xxx').test_connection().login('<USER>', "<PASSWORD>")
    >>> except ConnectionError as e:
    >>>     logging.error(f"A connection to Chemotion ({instance.host_url}) cannot be established")
    >>> s = instance.get_sample(1)
    >>> # Loads dataset V2024_08_23 from 'Analyses MT 1'
    >>> d1 = s.analyses.by_name('Analyses MT 1').dataset_by_name('V2024_08_23')
    >>> # Write BagIT zip and metadata set as xlsx file
    >>> d1.write_data_set_xlsx('./CWD')
    >>> d1.write_zip('./CWD')
    """

    def __init__(self, session: Connection, json_data: dict, attachments: MutableAttachments | None = None):
        self.id = json_data.get('id')
        self.name = json_data.get('name')
        self.description = json_data.get('description')
        ds_json = json_data.get('dataset')
        if ds_json is not None:
            res = parse_generic_object_json(ds_json)
            super().__init__(cast(dict, res.get('values')))
            self._mapping = res.get('obj_mapping')
        self._session = session
        self._json_data = json_data
        self._attachments = attachments

    @property
    def json_data(self) -> dict:
        """
        The raw JSON data of the dataset as fetched from the server.

        :return: The raw dataset JSON data
        """
        return self._json_data

    @property
    def attachments(self) -> MutableAttachments:
        """
        A list of all attached files. It contains the BagIt, the ChemSpectra results
         as well as the measurement file

        :return: A mutable attachment File
        """
        if self._attachments is None:
            attachments_data = self._json_data.get('attachments')
            if attachments_data is not None:
                self._attachments = MutableAttachments(self._session, attachments_data)
        return cast(MutableAttachments, self._attachments)

    def write_zip(self, destination=''):
        """
        Writes the BagIT zip file.

        :param destination: Director where the BagIT should be saved to
        :return: Abs filepath of the BagIT zip
        """
        image_url = f"/api/v1/attachments/zip/{self.id}"
        res = self._session.get(image_url)
        if res.status_code != 200:
            raise ConnectionRefusedError(f'{res.status_code} -> {res.text}')

        if not os.path.exists(destination) or os.path.isdir(destination):
            regex_file_name = re.search('filename="([^"]+)', res.headers['Content-Disposition'])
            destination = os.path.join(destination, regex_file_name.groups()[0])

        with open(destination, 'wb+') as f:
            f.write(res.content)

        return destination

    def write_data_set_xlsx(self, destination=''):
        """
        Writes the metadata set as xlsx.

        :param destination: Director where the BagIT should be saved to.
        :return: Abs filepath of the BagIT zip.
        """
        image_url = f"/api/v1/export_ds/dataset/{self.id}"
        res = self._session.get(image_url)
        if res.status_code != 200:
            raise ConnectionRefusedError(f'{res.status_code} -> {res.text}')

        if not os.path.exists(destination) or os.path.isdir(destination):
            regex_file_name = re.search('filename="([^"]+)', res.headers['Content-Disposition'])
            destination = os.path.join(destination, regex_file_name.groups()[0])

        with open(destination, 'wb+') as f:
            f.write(res.content)

        return destination

    def to_clean_json(self):
        """
        Cleans the data as perpetration to be saved
        """
        ds = self._json_data.get('dataset')
        if ds is not None:
            clean_generic_object_json(ds, self, self._mapping)
            ds['changed'] = True

    def save_attachments(self):
        """
        Uploads all attachments of the dataset and writes them back into the JSON data.
        """
        self.attachments.save()
        self.json_data['attachments'] = [x for x in self.attachments]


class Analyses(dict):
    """
    An analysis consists of a list of metadata schemas and associated data files.
    The schemas can be edited. And the files can be read and saved to your local device
    """

    def __init__(self, data: dict, session: Connection):
        super().__init__()
        self._session = session
        self.id = data.get('id')
        self.type = data.get('extended_metadata', {}).get('kind', '')

        self._data = data
        self['name'] = data['name']
        self['description'] = data['description']

        for k in ['report', 'status', 'kind', 'content']:
            if k in data['extended_metadata']:
                self[k] = data['extended_metadata'][k]
        self.datasets: list[Dataset] = []
        for jd in cast(list, self._data.get('children')):
            self.datasets.append(Dataset(session, jd))

    @property
    def is_new(self) -> bool:
        """
        :return: Returns true if the analyses has not been saved yet.
        """
        return self._data.get('is_new', False)

    def add_dataset(self, file_path: str) -> Dataset:
        """
        Loads a datafile up  and creates a new dataset.
        The Chemotion Instance will convert the date file and create a metadate set accordingly.
        However, this process only works if a Converter profile has been created

        :param file_path: the path on your local device to the datafile
        :return: A new Dataset object
        """
        ds = AnalysesManager.build_new_dataset()
        ds['name'] = os.path.basename(file_path)
        d = Dataset(self._session, ds, MutableAttachments(self._session, ds['attachments'], file_path))
        self.datasets.append(d)
        self._data['children'].append(d.json_data)
        return d

    def dataset_by_name(self, name: str) -> Dataset:
        """
        Find a dataset by its name.

        :param name: Name of the dataset
        :return: A Dataset object
        """
        return next(x for x in self.datasets if x.name == name)

    def preview_image(self) -> bytes | None:
        """
        Loads the image used as preview for the analyses.

        Usage::

        >>> from chemotion_api import Instance
        >>> import logging
        >>> try:
        >>>     instance = Instance('http(d)://xxx.xxx.xxx').test_connection().login('<USER>', "<PASSWORD>")
        >>> except ConnectionError as e:
        >>>     logging.error(f"A connection to Chemotion ({instance.host_url}) cannot be established")
        >>> s = instance.get_sample(1)
        >>> # Loads analysis 'Analyses MT 1'
        >>> analyses = s.analyses.by_name('Analyses MT 1')
        >>> with open('./img.svg', 'wb+') as f:
        >>>     f.write(analyses.preview_image())
        >>> s.save()

        :raises ConnectionError: If the request fails
        :return: byte representation of an image
        """

        if self._data.get('preview_img') is None or cast(dict, self._data.get('preview_img')).get('id') is None:
            return None
        return self._load_image(cast(int, cast(dict, self._data.get('preview_img')).get('id')))

    def _load_image(self, file_id: int) -> bytes:
        image_url = f"/api/v1/attachments/{file_id}"
        res = self._session.get(image_url)
        if res.status_code != 200:
            raise ConnectionError(f'{res.status_code} -> {res.text}')

        return res.content

    def to_json(self):
        """
        A savable representation of the Analyses
        :return: Json representation
        """
        self._data['name'] = self['name']
        self._data['description'] = self['description']
        for k in ['report', 'status', 'kind', 'content']:
            if k in self:
                self._data['extended_metadata'][k] = self[k]
        for ds in self.datasets:
            ds.to_clean_json()
        return self._data

    def save_attachments(self):
        """
        Do not use this methode! It is automatically used before the element is saved!
        """

        for _i, d in enumerate(self.datasets):
            d.save_attachments()

    def clean_up_after_save(self):
        """
        Do not use this methode! It is automatically used after the element is saved!
        """

        self._data['is_new'] = False
        for d in self.datasets:
            d.json_data['is_new'] = False



class AnalysesList(list):
    """
    List of :class:`chemotion_api.elements.abstract_element.Analyses`.


    Usage::

    >>> from chemotion_api import Instance
    >>> import logging
    >>> try:
    >>>     instance = Instance('http(d)://xxx.xxx.xxx').test_connection().login('<USER>', "<PASSWORD>")
    >>> except ConnectionError as e:
    >>>     logging.error(f"A connection to Chemotion ({instance.host_url}) cannot be established")
    >>> s = instance.get_sample(1)
    >>> # Download of all analysis files of data set 'V2024_08_23' from 'Analyses MT 1'
    >>> analyses = s.analyses.by_name('Analyses MT 1')
    >>> dataset = analyses.dataset_by_name('V2024_08_23')
    >>> os.makedirs('./TO_DEL', exist_ok=True)
    >>> for atta in dataset.attachments:
    >>>     atta.save_file('./dataset_files')
    >>> # Change value in the metadate set
    >>> dataset['General Information']['Label'] = 'V2024_08_23'
    >>> # Create a new
    >>> ana = s.analyses.add_analyses("Analyses MT 2")
    >>> ana.add_dataset('./V2024_08_24.json')
    >>> s.save()
    """

    def __init__(self, conn: Connection):
        super().__init__()
        self.conn = conn

    def by_name(self, name: str) -> Analyses:
        """
        Find an analysis by its name.

        :param name: Name of the analysis
        :return: The matching :class:`Analyses` object
        """
        return next(x for x in self if x['name'] == name)

    def by_id(self, id: str | int) -> Analyses:
        """
        Find an analysis by its database id.

        :param id: ID of the analysis
        :return: The matching :class:`Analyses` object
        """
        return next(x for x in self if str(x.id) == str(id))

    def add_analyses(self, name: str = 'New') -> Analyses:
        """
        Creates a new (empty) analysis and appends it to the list.

        :param name: Name of the new analysis
        :return: The newly created :class:`Analyses` object
        """
        new_a = Analyses(AnalysesManager.build_new_analyses(), self.conn)
        self.append(new_a)
        new_a['name'] = name
        return new_a

    def save_attachments(self):
        """
        Uploads the attachments of every analysis in the list.

        Do not use this methode! It is automatically used before the element is saved!
        """
        for ana in self:
            ana.save_attachments()

    def clean_up_after_save(self):
        """
        Resets the new-flags of every analysis in the list after a save.

        Do not use this methode! It is automatically used after the element is saved!
        """
        for ana in self:
            ana.clean_up_after_save()


class Segment(dict):
    """
    A dict of the generic segments (tabs) available for a given element type.

    Each key is a segment label; the value is lazily instantiated on first access via the
    ``on_add`` callback. Only segments whose generic class matches the element type are allowed.
    """

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
        """
        Returns the segment for the given label, creating it on first access.

        :param key: The segment label
        :return: The segment data
        :raises TypeError: If the segment does not exist for this element type
        """
        val = super().get(key)
        if val is None:
            seg = next((x for x in self._all_seg_classes if x.get('label') == key), None)
            if seg is None or seg.get('element_klass').get('name') != self._element_type:
                raise TypeError(f'Segemnt "{key}" is not for element "{self._element_type}"')
            new_seq_obj = GenericSegments.new_session(seg)
            key = add_to_dict(self, key, None)
            val = self[key] = self._on_add(key, new_seq_obj)
        return val


class AbstractElement:
    """
    This abstract element is the basis for all chemotion-api elements. It provides all the necessary functions and properties to work with these elements.
    It contains. For more details check the Element classes out.
    """

    def __init__(self, generic_segments: GenericSegments, session: Connection, json_data: dict | None = None, id: int | None = None,
                 element_type: str | None = None, avoid_load:bool = False):
        self._attachments: Attachments | None = None
        self._generic_segments = generic_segments
        self._session = session

        self._short_label = None
        self._properties = None
        self._analyses = None
        self._segments = None
        # Name of element instance
        self._name: str = ''
        # Last update of the element
        self.last_update: datetime | None = None
        self._element_type = element_type
        self.json_ld: dict = {}
        # Json data contains the raw data fetched from the server
        self.json_data: dict | None = None
        self.id = id or uuid.uuid4().__str__()
        # Json LD description of the element. It contains @type and @ID

        self._data_loaded = False
        if avoid_load:
            return
        if json_data is not None:
            self._set_json_data(json_data)
        elif not self.is_new and element_type is not None:
            self.load()
        else:
            raise ValueError("Either 'json_data' or 'id' and 'element_type' must be provided during initialization")


    @property
    def name(self) -> str:
        """
        The name of the element, falling back to the ``name`` entry of its properties.

        :return: The element name, or an empty string if unset
        """
        if not self._name and self._properties is not None and 'name' in self._properties:
            return self._properties['name'] or ''
        return self._name or ''

    @name.setter
    def name(self, name: str) -> None:
        self._name = name
        if self.json_data and 'name' in self.json_data:
            self.json_data['name'] = name
        if self._properties is not None and 'name' in self._properties:
            self._properties['name'] = name


    @property
    def short_label(self) -> str | None:
        """
        The short label of en element if available

        :return: short label of en element
        """
        return self._short_label

    @property
    def properties(self) -> PropertyDict:
        """
        The properties property contains all data from the main tab of the elements in Chemotion.

        :return: Element properties
        """
        return PropertyDict(self.on_properties_change, self._properties)

    @property
    def analyses(self) -> AnalysesList:
        """
        With the analyses object one can read and write all information from the analysis Tab in Chemotion.

        :return: Analyses object
        """
        return cast(AnalysesList, self._analyses)

    @property
    def segments(self) -> Segment:
        """
        Contains all segments (tabs) of elements in Chemotion.
        It contains generic elements as well as the proerties and the analyses segment

        :return: Segment object
        """
        return cast(Segment, self._segments)

    @property
    def attachments(self) -> Attachments:
        """
        Attachment container of the element.
 
        :return: Attachments container
        """
        if self._attachments is None:
            attachments_data = cast(dict, self.json_data).get('attachments')
            if attachments_data is None:
                attachments_data = []
            self._attachments = Attachments(self._session, attachments_data)
        return self._attachments

    @property
    def id(self) -> int:
        """
        Database ID of the element

        :return: Database ID of the element
        """
        return cast(int, self._id)

    @id.setter
    def id(self, id_val: int | str | None):
        """
        Database ID of the element
        """
        if id_val is None:
            self.is_new = True
        elif isinstance(id_val, str):
            if id_val.isdigit():
                id_val = int(id_val)
                self.is_new = False
            else:
                self.is_new = True
        elif isinstance(id_val, int):
            self.is_new = False

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
        return cast(str, self._element_type)

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


    def __copy__(self) -> Self:
        return cast(Self, {'generic_segments': self._generic_segments,
                'element_type': self._element_type, 'avoid_load': True,
                'session': self._session, 'json_data': self.json_data, 'id': self.id})

    def properties_schema(self) -> dict:
        """
        Returns the JSON.org schema of the cleaned properties.

        :return: JSON.org schema
        """
        return {}

    def eln_node_content(self) -> dict:
        """Extra RO-Crate ``Dataset`` properties for elements without a ``to_dcat_ap`` mapping.

        Elements not (yet) mapped to chem-dcat-ap (Wellplate / ResearchPlan / GenericElement) are
        exported as RO-Crate ``Dataset`` nodes. Subclasses override this to enrich that node with
        real structured content (a ``description`` and/or schema.org ``PropertyValue`` entries for
        ``variableMeasured``) instead of an empty dataset. Returns ``{}`` by default.

        :return: dict with optional ``"description"`` (str) and ``"variableMeasured"`` (list of
            ``PropertyValue`` dicts) keys.
        """
        return {}

    def load(self):
        """
        Loads and parses the data of an element from the server.
        The standard Values can be found in the properties property or the segment

        :raises RequestException: If the element could not be loaded!

        :raises ValueError: If no ID available!
        """

        self._data_loaded = True

        attachments_data, json_data = self._load_data_from_server()
        if attachments_data is not None:
            self._attachments = Attachments(self._session, attachments_data)
        self._set_json_data(json_data)

    def _load_data_from_server(self):

        if self.is_new:
            raise ValueError("No ID available")
        payload = {}
        res = self._session.get(f"{self.__class__.get_url(self.element_type)}/{self.id}.json",
                                data=payload)
        if res.status_code != 200:
            raise RequestException(f"{res.status_code} -> {res.text}")
        res_json = res.json()
        attachments_data = res_json.get('attachments')
        return attachments_data, res_json[self.get_response_key(self.element_type)]


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
        self.id = json_data.get('id', self._id)

        self._properties: dict = self._parse_properties()
        self._analyses: AnalysesList = self._parse_analyses()
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
        cast(dict, self.json_data)['segments'] = cast(dict, self.json_data).get('segments', [])
        cast(dict, self.json_data)['segments'].append(segment_data)
        return cast(dict, temp_segment.get('values'))

    def save(self, load_after_save: bool = False):
        """
        Saves or creates an object according to the set properties. It overwrites the
        json_data entries by the values set in the segments object.

        :raises RequestException: If request was not successful
        :raises jsonschema.exceptions.ValidationError: If the properties ar not valid
        """
        if not self._data_loaded and not self.is_new:
            _attachment_data, json_data = self._load_data_from_server()
            self.json_data = json_data

        self._data_loaded = True
        self.analyses.save_attachments()
        data = self.clean_data()
        is_created = False
        json_dumps_data = json.dumps(data, default=fixeddict_serializer)
        # Uncomment  after Chem update to write upload json to compare with Chemotion Browser upload
        # dump_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'test_config/dumps/upload_jsons')
        # os.makedirs(dump_dir, exist_ok=True)
        # with open(os.path.join(dump_dir, f'{self.element_type}_{self.id}_{uuid.uuid4().__str__()}.json'), 'w+') as outfile:
        #     outfile.write(json_dumps_data)
        if self.is_new:
            res = self._session.post(self.save_url(), data=json_dumps_data)
            is_created = True
        else:
            res = self._session.put(self.save_url(), data=json_dumps_data)
        if res.status_code != 200 and res.status_code != 201:
            raise RequestException(f'{res.status_code} -> {res.text}')
        if is_created:
            res_json = res.json()
            res_json = merge_dicts(self.json_data, res_json.get(self.element_type, res_json.get('element')))
            self._set_json_data(res_json)
        if self.attachments is not None:
            self.attachments.save(self.id, snake_to_camel_case(self.get_response_key(self.element_type)))
        self.analyses.clean_up_after_save()
        if load_after_save:
            self.load()

    def clean_data(self) -> dict:
        """
        Takes the values from the segments object and attachment object
        and overwrites the json_data values accordingly.

        :raises jsonschema.exceptions.ValidationError: If the properties ar not valid

        :return: cleaned data
        """
        cleaned_data: dict[str, Any] = {
            'id': self.id or uuid.uuid4().__str__(),
            'is_new': self.is_new,
            'type': self.element_type
        }
        if isinstance(self.name, str):
            cleaned_data['name'] = self.name
        if 'collection_id' in cast(dict, self.json_data):
            cleaned_data['collection_id'] = cast(dict, self.json_data)['collection_id']
        if 'container' in cast(dict, self.json_data):
            cleaned_data['container'] = cast(dict, self.json_data)['container']
        if self.attachments is not None:
            cleaned_data['attachments'] = self.attachments.attachment_data

        cleaned_prop_data = self._clean_properties_data()
        for key, value in cleaned_prop_data.items():
            if isinstance(value, PropertyDict):
                cleaned_prop_data[key] = value.to_dict()
        validate(cleaned_prop_data, self.properties_schema())

        merge_dicts(cleaned_data, self._clean_segments_data(), cleaned_prop_data,
                    self._clean_analyses_data())
        return cleaned_data

    def save_url(self) -> str:
        """
        Retrieves the save URL, which varies based on whether the element already has an ID.

        :return: The save URL
        """
        if not self.is_new:
            return "/api/v1/{}s/{}".format(cast(dict, self.json_data).get('type'), self.id)
        return "/api/v1/{}s/".format(cast(dict, self.json_data).get('type'))

    def on_properties_change(self, dict_obj, name, value):
        """
        Hook invoked when a value in the :attr:`properties` dict is changed.

        Subclasses override this to validate, coerce and propagate side effects of a change. The
        base implementation accepts every change unchanged.

        :param dict_obj: The chain of dicts leading to the changed value
        :param name: The chain of keys identifying the changed value
        :param value: The chain of values, the last being the new value
        :return: ``True`` to let the default assignment proceed
        """
        return True

    def __eq__(self, other):
        return isinstance(other, AbstractElement) and self.json_ld['@id'] == other.json_ld['@id']

    def __ne__(self, other):
        return not isinstance(other, AbstractElement) or self.json_ld['@id'] != other.json_ld['@id']

    def __str__(self) -> str:
        name_val = self.name or (self.properties.get('name') if self.properties else '') or ''
        return f"{self.__class__.__name__}(id={self.id}, name={name_val!r})"

    def __repr__(self) -> str:
        return self.__str__()


    def _parse_properties(self) -> dict:
        raise NotImplementedError

    def _clean_properties_data(self, serialize_data: dict | None = None) -> dict:
        raise NotImplementedError

    def _parse_analyses(self) -> AnalysesList:
        analyses_list = AnalysesList(self._session)
        container = cast(dict, self.json_data).get('container')
        if container is not None and len(container.get('children', [])) > 0:
            for analyses in container.get('children', [{}])[0].get('children', []):
                analyses_list.append(Analyses(analyses, self._session))
        return analyses_list

    def _clean_analyses_data(self) -> dict:
        container = cast(dict, self.json_data).get('container')
        if container is None:
            return {}
        obj: dict = {"container": {
            "children": [{"children": []}]
        }}
        res_list = container.get('children', [{}])[0].get('children', [])
        for (idx, analyses) in enumerate(res_list):
            analyses_obj: list[Analyses] = [item for (index, item) in enumerate(self.analyses) if
                                            item.id == analyses.get('id')]
            if len(analyses_obj) == 1:
                new_data = analyses_obj[0].to_json()
                for (key, _item) in analyses.items():
                    if key in new_data:
                        res_list[idx][key] = new_data.get(key, res_list[idx][key])
        res_list += [item.to_json() for item in self.analyses if item.is_new]
        obj["container"]["children"][0]["children"] = res_list
        return obj

    def _parse_segments(self) -> dict[str, dict]:
        results: dict[str, dict] = {}
        results_mapping: dict[str, dict] = {}
        for segment in cast(dict, self.json_data).get('segments', []):
            a = [x for x in self._generic_segments.all_classes if x['id'] == segment['segment_klass_id']]
            temp_segment = parse_generic_object_json(segment)
            key = add_to_dict(results, a[0].get('label', 'no_label'), temp_segment.get('values'))
            results_mapping[key] = cast(dict, temp_segment.get('obj_mapping'))
        return {'values': results, 'obj_mapping': results_mapping}

    def _clean_segments_data(self) -> dict:
        res_list = cast(dict, self.json_data).get('segments', [])
        for (seg_key, segment_mapping) in self._segments_mapping.items():
            if seg_key in self.segments and self.segments[seg_key] is not None:
                list_idx = next((i for (i, x) in enumerate(res_list) if x.get('id') == segment_mapping['__id']), -1)
                if list_idx == -1:
                    list_idx = len(res_list)
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
        return '/api/v1/generic_elements'
