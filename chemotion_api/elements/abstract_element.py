"""Base class and shared building blocks for all Chemotion elements (lifecycle, analyses, datasets, attachments)."""
import copy
import json
import os.path
import re
import uuid
import webbrowser
from datetime import datetime
from operator import truediv
from collections.abc import Callable
from typing import Optional, Self, cast, Any

import dateutil.parser
from jsonschema.validators import validate

from chemotion_api.elements.analyses_manager import AnalysesManager

from chemotion_api.utils.withheld import mark_withheld
from pydantic import BaseModel
from chemotion_api.models import validate_field
from chemotion_api.connection import Connection, request_error
from chemotion_api.user import UserLabel
from chemotion_api.elements.attachments import Attachments, MutableAttachments
from chemotion_api.elements.registry import element_type_info, GENERIC_ELEMENTS_URL, GENERIC_RESPONSE_KEY
from chemotion_api.elements.comments import Comment, create_comment, load_comments
from chemotion_api.elements import private_notes, literature
from chemotion_api.elements.literature import Reference
from chemotion_api.elements.versions import Version, load_versions

from chemotion_api.generic_segments import GenericSegments
from chemotion_api.utils.segment_fields import SegmentField, iter_fields
from chemotion_api.utils import safe_join, add_to_dict, parse_generic_object_json, AttrAccessMixin, \
    clean_generic_object_json, merge_dicts, snake_to_camel_case, fixeddict_serializer, PropertyDict

import logging

from requests.exceptions import RequestException

logger = logging.getLogger(__name__)


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
    >>>     instance = Instance('http(d)://xxx.xxx.xxx').test_connection().login_token('<API TOKEN>')
    >>> except ConnectionError as e:
    >>>     logging.error(f"A connection to Chemotion ({instance.host_url}) cannot be established")
    >>> s = instance.get_sample(1)
    >>> # Loads dataset V2024_08_23 from 'Analyses MT 1'
    >>> d1 = s.analyses.by_name('Analyses MT 1').dataset_by_name('V2024_08_23')
    >>> # Write BagIT zip and metadata set as xlsx file
    >>> d1.write_data_set_xlsx('./CWD')
    >>> d1.write_zip('./CWD')

    The dict itself holds only the metadata set: ``{layer: {field: value}}``. It is empty if no metadata
    has been generated. The dataset's ``id``, ``name`` and ``description`` are attributes
    (``dataset.name``, not ``dataset['name']``); the raw data is in :attr:`json_data`.
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

        :param destination: Directory or file path where the BagIT should be saved to
        :return: filepath of the BagIT zip
        """
        image_url = f"/api/v1/attachments/zip/{self.id}"
        res = self._session.get(image_url)
        if res.status_code != 200:
            raise ConnectionRefusedError(f'{res.status_code} -> {res.text}')

        if not os.path.exists(destination) or os.path.isdir(destination):
            # The server names the file, so it is untrusted data: an absolute path would
            # discard `destination` entirely, and `../` would climb out of it. Also tolerate a
            # missing or unparsable header instead of raising KeyError/AttributeError.
            disposition = res.headers.get('Content-Disposition', '')
            match = re.search('filename="([^"]+)', disposition)
            destination = str(safe_join(destination, match.group(1) if match else 'download'))

        with open(destination, 'wb+') as f:
            f.write(res.content)

        return destination

    def write_data_set_xlsx(self, destination=''):
        """
        Writes the metadata set as xlsx.

        :param destination: Directory or file path where the xlsx file should be saved to.
        :return: filepath of the xlsx file.
        """
        image_url = f"/api/v1/export_ds/dataset/{self.id}"
        res = self._session.get(image_url)
        if res.status_code != 200:
            raise ConnectionRefusedError(f'{res.status_code} -> {res.text}')

        if not os.path.exists(destination) or os.path.isdir(destination):
            # The server names the file, so it is untrusted data: an absolute path would
            # discard `destination` entirely, and `../` would climb out of it. Also tolerate a
            # missing or unparsable header instead of raising KeyError/AttributeError.
            disposition = res.headers.get('Content-Disposition', '')
            match = re.search('filename="([^"]+)', disposition)
            destination = str(safe_join(destination, match.group(1) if match else 'download'))

        with open(destination, 'wb+') as f:
            f.write(res.content)

        return destination

    def to_clean_json(self):
        """
        Writes the edited metadata back into the raw data as preparation to be saved
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


class Analyses(AttrAccessMixin, dict):
    """
    An analysis consists of a list of metadata schemas and associated data files.
    The schemas can be edited. And the files can be read and saved to your local device.

    The analysis is a dict with the keys ``name``, ``description`` and, if set, ``report``, ``status``,
    ``kind`` and ``content``. The keys can be used as attributes as well (``analysis.name`` is
    ``analysis['name']``). Its datasets are in the attribute ``datasets`` (``analysis.datasets``, a list of
    :class:`Dataset`), not in the dict. ``id`` and ``type`` are attributes only.
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
        Uploads a datafile and creates a new dataset. The file is uploaded when the element is saved.
        The Chemotion Instance will convert the data file and create a metadata set accordingly.
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

        :raises StopIteration: if no dataset has this name
        """
        return next(x for x in self.datasets if x.name == name)

    def preview_image(self) -> bytes | None:
        """
        Loads the image used as preview for the analyses.

        Usage::

        >>> from chemotion_api import Instance
        >>> import logging
        >>> try:
        >>>     instance = Instance('http(d)://xxx.xxx.xxx').test_connection().login_token('<API TOKEN>')
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
        Do not use this method! It is automatically used before the element is saved!
        """

        for i, d in enumerate(self.datasets):
            d.save_attachments()

    def clean_up_after_save(self):
        """
        Do not use this method! It is automatically used after the element is saved!
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
    >>>     instance = Instance('http(d)://xxx.xxx.xxx').test_connection().login_token('<API TOKEN>')
    >>> except ConnectionError as e:
    >>>     logging.error(f"A connection to Chemotion ({instance.host_url}) cannot be established")
    >>> s = instance.get_sample(1)
    >>> # Download of all analysis files of data set 'V2024_08_23' from 'Analyses MT 1'
    >>> analyses = s.analyses.by_name('Analyses MT 1')
    >>> dataset = analyses.dataset_by_name('V2024_08_23')
    >>> os.makedirs('./dataset_files', exist_ok=True)
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

        :raises StopIteration: if no analysis has this name
        """
        return next(x for x in self if x['name'] == name)

    def by_id(self, id: str | int) -> Analyses:
        """
        Find an analysis by its database id.

        :param id: ID of the analysis
        :return: The matching :class:`Analyses` object

        :raises StopIteration: if no analysis has this id
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
    All segments (tabs) of an element: ``{segment: {layer: {field: value}}}``.

    Select fields hold the option key (the label is accepted as well), system-defined fields hold
    ``{'value': ..., 'unit': ...}``. Changed values are checked against the segment template on save.
    Use :meth:`field_type`, :meth:`options` and :meth:`units` to look up what a field accepts.

    Every generic segment available for the element type is a key. A segment the element does not
    have yet has the value None; :meth:`get` adds it with the default values of the template.

    Usage::

    >>> s = instance.get_sample(1)
    >>> # Adds the segment 'Electrochemistry' if the sample does not have it yet
    >>> cell = s.segments.get('Electrochemistry')['Cell']
    >>> # [{'key': 'traditional', 'label': 'disk'}, {'key': 'mesh', 'label': 'mesh'}]
    >>> s.segments.options('Electrochemistry', 'Cell', 'Electrode type')
    >>> cell['Electrode type'] = 'disk'  # stored as the key 'traditional'
    >>> cell['Temperature'] = {'value': 25, 'unit': 'C'}
    >>> s.save()
    """

    def __init__(self, generic_segments: GenericSegments, element_type: str, on_add, *args,
                 field_lookup: Callable[[str, str, str], SegmentField] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._field_lookup = field_lookup
        self._generic_segments = generic_segments
        self._all_seg_classes = [seg for seg in generic_segments.all_classes if
                                 seg.get('element_klass').get('name') == element_type]
        self._element_type = element_type
        self._on_add = on_add

        for seg in self._all_seg_classes:
            self[seg.get('label')] = super().get(seg.get('label'))

    def get(self, key):
        """
        Returns the values of a segment. If the element does not have the segment yet, it is added
        with the default values of the template.

        :param key: segment name
        :return: the segment values ``{layer: {field: value}}``

        :raises TypeError: if there is no segment of this name for the element type
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

    def available(self) -> list[str]:
        """
        :return: the labels of all generic segments available for the element type, whether the element has
            them yet or not (the keys that are None in this dict are not added yet)
        """
        return [seg.get('label') for seg in self._all_seg_classes]

    def field(self, segment: str, layer: str, field: str) -> SegmentField:
        """
        Looks up the template of a segment field.

        :param segment: segment name as used as key in this dict
        :param layer: layer name as used in the segment
        :param field: field name as used in the layer
        :return: the template field

        :raises KeyError: if the segment, layer or field does not exist
        """
        if self._field_lookup is None:
            raise TypeError('Field lookup is not available for these segments.')
        return self._field_lookup(segment, layer, field)

    def field_type(self, segment: str, layer: str, field: str) -> str:
        """
        Parameters as in :meth:`field`.

        :return: type of the field, e.g. 'text', 'select', 'integer' or 'system-defined'
        """
        return self.field(segment, layer, field).type

    def options(self, segment: str, layer: str, field: str) -> list[dict[str, str]]:
        """
        Parameters as in :meth:`field`.

        :return: options of a select field as ``[{'key': ..., 'label': ...}]``

        :raises TypeError: if the field is not a select field
        """
        return self.field(segment, layer, field).options()

    def units(self, segment: str, layer: str, field: str) -> list[str]:
        """
        Parameters as in :meth:`field`.

        :return: units of a system-defined field

        :raises TypeError: if the field is not a system-defined field
        """
        return self.field(segment, layer, field).units()


def _plain(value):
    """A validated value as properties hold it: nested models become plain dicts."""
    return value.model_dump() if isinstance(value, BaseModel) else value


class AbstractElement:
    """
    This abstract element is the basis for all chemotion-api elements. It provides all the necessary functions and properties to work with these elements.
    For more details check the Element classes out.

    Attributes:

    * ``json_data``: the raw data of the element as sent by the server
    * ``json_ld``: JSON-LD description of the element. It contains ``@id`` and ``@type``
    * ``last_update``: time of the last update on the server
    * ``is_new``: True if the element has not been saved yet
    """

    def __init__(self, generic_segments: GenericSegments, session: Connection, json_data: dict | None = None,
                 id: int | None = None, element_type: str | None = None, avoid_load: bool = False):
        # Elements from a listing or search are only partially loaded; they load fully on first data access
        self._is_partial = False
        self._attachments: Attachments | None = None
        self._generic_segments = generic_segments
        self._session = session

        self._short_label = None
        self._properties = None
        self._analyses: AnalysesList | None = None
        self._segments = None
        # Name of element instance
        self._name: str = ''
        # Last update of the element
        self.last_update: datetime | None = None
        # When the element was created. Some payloads carry no timestamps at all.
        self.created_at: datetime | None = None
        self._element_type = element_type
        self.json_ld: dict = {}
        # Json data contains the raw data fetched from the server
        self.json_data: dict | None = None
        self.id = id or uuid.uuid4().__str__()
        # Json LD description of the element. It contains @type and @ID

        self._data_loaded = False
        self._loading = False
        # Set once a fetch has failed, so a permanently-unfetchable element is not retried on
        # every single property access. It deliberately does NOT mark the element loaded: `save()`
        # re-fetches through its own path and raises on failure, rather than writing back the
        # list-derived nulls.
        self._load_failed = False
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
        # Load first: otherwise `s.name = 'x'; s.save()` never touches `properties`, so
        # `_data_loaded` stays False, and the assignment would be re-applied on top of the
        # list-derived payload. Renaming is the most obvious bulk edit there is.
        self._ensure_loaded()
        self._name = name
        if self.json_data and 'name' in self.json_data:
            self.json_data['name'] = name
        if self._properties is not None and 'name' in self._properties:
            self._properties['name'] = name


    @property
    def short_label(self) -> str | None:
        """
        The short label of an element if available

        :return: short label of an element
        """
        return self._short_label

    @property
    def is_loaded(self) -> bool:
        """Whether the element's full record has been fetched from the server.

        An element from a listing starts with part of its data and fetches the rest on first use
        of its properties, segments, analyses or attachments; :meth:`load` fetches it explicitly.
        A new (unsaved) element is complete by definition.
        """
        return self.is_new or self._data_loaded

    @property
    def is_restricted(self) -> bool:
        """Whether the server withheld fields of this element from you.

        True when the element reached you through a share below the full detail level (10). The
        withheld fields read as :data:`~chemotion_api.utils.withheld.WITHHELD`, and :meth:`save`
        refuses the element.
        """
        return bool((self.json_data or {}).get('is_restricted'))

    @property
    def can_update(self) -> bool | None:
        """Whether the server says *this user* may write this element.

        ELN v4.0.0 added `can_update` to the research-plan, screen and wellplate entities. It is a
        permission hint computed per request, so it is read-only and deliberately **not** part of
        :attr:`properties` — writing it back would be meaningless.

        ``None`` means the server did not say: either an element type that does not expose it, or
        a payload from a listing rather than a detail fetch. ``None`` is not "no" — do not treat it
        as a refusal.
        """
        # `json_data` is nullable by design (a freshly constructed element has none), and a
        # property whose entire contract is "None means the server did not say" must not raise.
        json_data = self.json_data
        value = json_data.get('can_update') if isinstance(json_data, dict) else None
        return value if isinstance(value, bool) else None

    @property
    def properties(self) -> PropertyDict:
        """
        The properties property contains all data from the main tab of the elements in Chemotion.

        An element obtained by *iterating* a collection carries only what the list endpoint sends,
        and v4 gates `description`, `location`, `solvent`, `target_amount_*`, `real_amount_*`,
        `boiling_point`, `melting_point`, `container`, `segments` and more behind
        ``unless: :displayed_in_list``. Reading them would silently yield ``None``, and — worse —
        saving such an element wrote those ``None``s back, destroying the values on the server.
        (``declared(params, include_missing: false)`` preserves *omitted* keys but not explicit
        nulls.) Indexing already called ``load()``; iteration did not, so the two disagreed.

        So the full record is fetched here, on first access, rather than at iteration time: a loop
        that only reads ``name`` or ``id`` still costs one request in total.

        :return: Element properties
        """
        self._ensure_loaded()
        return PropertyDict(self.on_properties_change, self._properties)

    def _ensure_loaded(self) -> None:
        """Fetch the element's full record if only the list payload has been seen so far.

        Guarded against re-entry: ``load()`` itself walks ``properties`` while parsing.
        """
        if self._data_loaded or self.is_new or self._loading or self._load_failed:
            return
        if self.id is None or isinstance(self.id, str):
            return                                  # never saved; nothing to fetch
        self._loading = True
        try:
            self.load()
        except Exception as e:                      # reading must not become fatal
            self._load_failed = True                # ...but do not retry it on every access
            logger.warning("Could not load the full record for %s %s: %s",
                           self.element_type, self.id, e)
        finally:
            self._loading = False

    @property
    def user_labels_resolved(self) -> list[UserLabel]:
        """The element's user labels, resolved from ids to :class:`UserLabel` objects.

        .. note::
           Populated for samples, reactions, wellplates, research plans and screens. Generic
           elements keep their labels elsewhere, so this is empty for them.


        Elements carry user labels as bare numeric ids (``properties['user_labels']``), which on
        their own say nothing about what the label means. This resolves them against the label
        list, which is fetched **once per connection** — resolving labels across many elements
        costs one request in total, not one per element.

        An element can carry a label owned by another user, which the server's ``my_labels``
        filter will not return. Such an id is **never** an error here: it resolves to a
        placeholder :class:`UserLabel` carrying only the ``id``, with ``title`` ``None``,
        :attr:`~chemotion_api.user.UserLabel.is_resolved` ``False`` and
        :attr:`~chemotion_api.user.UserLabel.display_title` ``"#<id>"``. The returned list
        therefore always has one entry per id, in the element's own order.

        This is read-only and derived: ``properties['user_labels']`` keeps the raw id list, so
        saving the element round-trips the ids unchanged.

        :return: one :class:`UserLabel` per id on the element.
        :raise PermissionError: if the label list cannot be fetched. Make sure you are logged in.
        """
        # `properties` fetches the full record on first access; reading `_properties` directly
        # skipped that, so an element that had not been loaded reported no labels at all.
        label_ids = self.properties.get('user_labels') or []
        if not label_ids:
            return []
        by_id = {row.get('id'): row for row in self._session.user_labels}
        return [
            UserLabel.from_json(by_id[label_id]) if label_id in by_id else UserLabel(id=label_id)
            for label_id in label_ids
        ]

    @property
    def _properties(self) -> dict:
        self._load_if_partial()
        # Set by `_set_json_data` before anything reads it; `None` only on an element that was
        # never given data, which no accessor is reached on.
        return cast(dict, self._properties_data)

    @_properties.setter
    def _properties(self, properties: dict | None):
        self._properties_data = properties

    @property
    def analyses(self) -> AnalysesList:
        """
        With the analyses object one can read and write all information from the analysis Tab in Chemotion.

        :return: Analyses object
        """
        self._load_if_partial()
        return cast(AnalysesList, self._analyses)

    @property
    def segments(self) -> Segment:
        """
        Contains all segments (tabs) of elements in Chemotion: ``{segment: {layer: {field: value}}}``.
        It contains the generic segments as well as the 'Properties' and the 'Analyses' segment.
        A generic segment the element does not have yet is None; use ``segments.get(name)`` to add it.

        :return: Segment object
        """
        self._load_if_partial()
        return cast(Segment, self._segments)

    @property
    def attachments(self) -> Attachments:
        """
        Attachment container of the element.
 
        :return: Attachments container
        """
        self._load_if_partial()
        if self._attachments is None:
            attachments_data = cast(dict, self.json_data).get('attachments')
            if attachments_data is None:
                attachments_data = []
            self._attachments = Attachments(self._session, attachments_data)
        return self._attachments

    @property
    def id(self) -> int:
        """
        Database ID of the element. A new (not yet saved) element has a UUID string instead.

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
        Element type: is either 'sample', 'reaction', 'wellplate', 'research_plan' or, if the element is a generic one, the name of its generic element type

        :return: The element type
        """
        return cast(str, self._element_type)

    @element_type.setter
    def element_type(self, element_type_val: str):
        """
        Element type: is either 'sample', 'reaction', 'wellplate', 'research_plan' or, if the element is a generic one, the name of its generic element type
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


    def load(self):
        """
        Loads and parses the data of an element from the server.
        The standard Values can be found in the properties property or the segment

        :raises RequestException: If the element could not be loaded!

        :raises ValueError: If no ID available!
        """

        # Set before the request, not after: `_set_json_data` walks `properties`, which would
        # re-enter `_ensure_loaded` and recurse. But it must not *stay* true if the fetch fails —
        # `_ensure_loaded` deliberately swallows the exception, so one transient 500 would
        # otherwise pin the element to its list-derived properties for the rest of its life and
        # the next `save()` would PUT those nulls back.
        self._data_loaded = True
        self._is_partial = False

        try:
            attachments_data, json_data = self._load_data_from_server()
            self._load_failed = False
            if attachments_data is not None:
                self._attachments = Attachments(self._session, attachments_data)
            self._set_json_data(json_data)
        except BaseException:
            self._data_loaded = False
            raise

    def mark_partial(self):
        """
        Marks the element as partially loaded (e.g. from a listing): it is loaded completely the first time
        its properties, segments, analyses or attachments are accessed, so neither reading nor saving
        uses the incomplete data. Used by :class:`chemotion_api.elements.ElementSet`.
        """
        self._is_partial = not self.is_new

    def _load_if_partial(self):
        if self._is_partial:
            self.load()

    def _load_data_from_server(self):

        if self.is_new:
            raise ValueError("No ID available")
        payload = {}
        res = self._session.get(f"{self.__class__.get_url(self.element_type)}/{self.id}.json",
                                data=payload)
        if res.status_code != 200:
            raise request_error(res, f'loading {self.element_type} {self.id}')
        res_json = res.json()
        attachments_data = res_json.get('attachments')
        return attachments_data, self._record_from_detail(res_json)

    def _record_from_detail(self, res_json: dict) -> dict:
        """The element's record inside a detail response — wrapped under its type by most routes."""
        return res_json[self.get_response_key(self.element_type)]

    def _record_from_create(self, res_json: dict) -> dict | None:
        """The element's record inside a create response — wrapped under its type by most routes."""
        return res_json.get(self.element_type, res_json.get('element'))


    @staticmethod
    def _parse_timestamp(value: str | None) -> datetime | None:
        """Parse a Chemotion timestamp, tolerating the several formats the ELN emits.

        :param value: the raw timestamp string, or ``None``.
        :return: the parsed :class:`datetime`, or ``None`` if it is absent or unparseable.
        """
        if not value:
            return None
        for pattern in ['%Y-%m-%d %H:%M:%S %Z', '%d.%m.%Y, %H:%M:%S %z']:
            try:
                return datetime.strptime(value, pattern)
            except ValueError:
                pass
        try:
            return dateutil.parser.parse(value)
        except (ValueError, OverflowError, TypeError):
            return None

    def _set_json_data(self, json_data):
        if json_data.get('is_restricted') is True:
            # Shared below full detail: the server put '***' where it withheld a value.
            mark_withheld(json_data)
        self.json_data = json_data
        # Only overwrite when a value actually parses, so a payload without them leaves what we
        # already knew intact.
        updated = self._parse_timestamp(json_data.get('updated_at'))
        if updated is not None:
            self.last_update = updated
        created = self._parse_timestamp(json_data.get('created_at'))
        if created is not None:
            self.created_at = created
        self.name = json_data.get('name', '')

        self._short_label = self.json_data.get('short_label')
        self.element_type = json_data.get('type')
        self.id = json_data.get('id', self._id)

        self._properties = self._parse_properties()
        self._analyses = self._parse_analyses()
        segment_temp = self._parse_segments()
        self._segments_mapping = segment_temp.get('obj_mapping')
        self._segments = Segment(self._generic_segments,
                                 json_data.get('type'),
                                 self._on_add_segment,
                                 segment_temp.get('values'),
                                 field_lookup=self._segment_field)
        # Build the wrapper directly rather than reading `self.properties`: that getter calls
        # `_ensure_loaded()`, and at this point `id` is set and `_data_loaded` is not, so it
        # issued a full `load()` for every element constructed from a *listing* row — a 50-row
        # page cost 51 requests, and a transient failure left `_load_failed` on an element that
        # had merely been listed. Loading stays lazy: the first real property read triggers it.
        add_to_dict(self.segments, 'Properties', PropertyDict(self.on_properties_change, self._properties))
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
        New attachments and datasets are uploaded as well.

        :param load_after_save: If true, the element is reloaded from the server after saving

        :raises ValueError: If a changed segment value does not fit its field
        :raises RequestException: If request was not successful
        :raises jsonschema.exceptions.ValidationError: If the properties are not valid
        """
        self._load_if_partial()
        if self._load_failed and not self.is_new:
            # The full record never arrived, so `properties` is whatever the *list* payload
            # carried. Saving from here either writes list-derived nulls over real values, or —
            # if the refetch below now succeeds — re-parses over edits the caller has already
            # made and discards them, with the PUT still reporting success. Both are silent data
            # loss, so refuse instead. Re-fetch the element and retry.
            raise ConnectionError(
                f'The full record for {self.element_type} {self.id} could not be loaded, so '
                f'saving it would discard data. Fetch the element again before saving.')
        if not self._data_loaded and not self.is_new:
            # `self.json_data = json_data` left `_properties` parsed from the *list* payload while
            # marking the element loaded, so the accessor-level fix could never fire for the rest
            # of the save: `for s in col.get_samples(): s.save()` re-serialised list-derived nulls
            # over description, location, solvent and both amount fields. Re-parsing is safe here
            # precisely because `_data_loaded` is False — nothing lazily-derived has been handed
            # out yet to be clobbered.
            _attachment_data, json_data = self._load_data_from_server()
            self._set_json_data(json_data)

        if self.is_restricted:
            raise PermissionError(
                f'{self.element_type} {self.id} is shared with you below the full detail level, so '
                f'the server withheld some of its fields. Saving it would write placeholders over '
                f'the real values, so it is refused.')
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
            raise request_error(res, f'saving {self.element_type} {"(new)" if is_created else self.id}')
        if is_created:
            res_json = res.json()
            res_json = merge_dicts(self.json_data, self._record_from_create(res_json))
            self._set_json_data(res_json)
        if self.attachments is not None:
            self.attachments.save(self.id, self._attachable_type or
                                  snake_to_camel_case(self.get_response_key(self.element_type)))
        self.analyses.clean_up_after_save()
        if load_after_save:
            self.load()

    def save_analyses(self) -> None:
        """
        Saves only the analyses of this element — names, descriptions, status, content, dataset
        metadata, new analyses and new dataset files — without saving its other properties, the way
        the UI's analysis tab does (``PUT /api/v1/containers/container``).

        Unsaved changes to the element's properties are kept locally but not sent.

        :raises ValueError: if the element has not been saved yet.
        :raises PermissionError: if you may not edit the element.
        """
        self._saved_id_for('analyses')
        container = cast(dict, self.json_data).get('container')
        if container is None:
            raise ValueError(f'{self.element_type} {self.id} has no analyses container.')
        self.analyses.save_attachments()
        payload = merge_dicts(copy.deepcopy(container), self._clean_analyses_data()['container'])
        self._put_container(payload)
        self.analyses.clean_up_after_save()
        self._analyses = self._parse_analyses()

    def delete_analysis(self, analysis: Analyses) -> None:
        """
        Deletes one analysis of this element, with its datasets and their files, right away.
        Deleted files cannot be restored.

        Sent like the UI's analysis tab does: the element's container with the analysis marked
        deleted (``PUT /api/v1/containers/container``). ``DELETE /api/v1/containers/:id`` is not
        used: on ELN main it refuses element owners (the inbox owner check of the neighbouring
        ``PATCH`` route also guards it).

        :param analysis: one of :attr:`analyses`.
        :raises ValueError: if the analysis is not one of this element's analyses.
        :raises PermissionError: if you may not edit the element.
        """
        # By identity: analyses are dicts, so `in`/`remove` would match an equal-looking other one.
        index = next((i for i, a in enumerate(self.analyses) if a is analysis), None)
        if index is None:
            raise ValueError('The analysis is not one of this element\'s analyses.')
        if analysis.is_new or analysis.id is None:
            del self.analyses[index]
            return
        self._saved_id_for('analyses')
        container = copy.deepcopy(cast(dict, self.json_data).get('container') or {})
        for group in container.get('children') or []:
            for child in group.get('children') or []:
                if child.get('id') == analysis.id:
                    child['is_deleted'] = True
        self._put_container(container)
        del self.analyses[index]
        self._analyses = self._parse_analyses()

    def _put_container(self, container: dict) -> None:
        res = self._session.put('/api/v1/containers/container',
                                data=json.dumps({'container': container}, default=fixeddict_serializer))
        if res.status_code == 401:
            raise PermissionError(f'You may not edit the analyses of {self.element_type} {self.id}.')
        if res.status_code not in (200, 201):
            raise request_error(res, f'saving the analyses of {self.element_type} {self.id}')
        answer = res.json()
        cast(dict, self.json_data)['container'] = answer['container']
        if 'variations' in answer and 'variations' in cast(dict, self.json_data):
            cast(dict, self.json_data)['variations'] = answer['variations']

    def clean_data(self) -> dict:
        """
        Takes the values from the segments object and attachment object
        and overwrites the json_data values accordingly.

        :raises jsonschema.exceptions.ValidationError: If the properties are not valid

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

    def url(self, collection_id: int | str | None = None) -> str:
        """
        The URL of the element in the Chemotion web client.

        :param collection_id: ID of the collection the element is shown in. If None, a collection of the
            element is used, or the 'All' collection if none is known.
        :return: URL of the element

        :raises ValueError: if the element has not been saved yet
        """
        if self.is_new:
            raise ValueError('The element has not been saved yet. Save it before opening it.')
        if collection_id is None:
            collection_id = self._web_collection_id()
        return f"{self._session.host_url}/mydb/collection/{collection_id}/{self.element_type}/{self.id}"

    def open(self, collection_id: int | str | None = None) -> str:
        """
        Opens the element in a new tab of the default web browser.
        You need to be logged in to Chemotion in this browser.

        :param collection_id: ID of the collection the element is shown in, see :meth:`url`
        :return: URL of the element

        :raises ValueError: if the element has not been saved yet
        """
        element_url = self.url(collection_id)
        webbrowser.open_new_tab(element_url)
        return element_url

    def move_to(self, dest, source):
        """
        Moves this element from the source collection into the dest collection. The request is sent right away.
        See :meth:`chemotion_api.collection.AbstractCollection.move_elements`

        :param dest: Destination collection
        :param source: Collection the element is currently in (not the root collection)
        """
        source.move_elements(dest, self)

    def assign_to(self, dest, source=None):
        """
        Adds this element to the dest collection as well. The request is sent right away.
        See :meth:`chemotion_api.collection.AbstractCollection.assign_elements`

        :param dest: Destination collection
        :param source: Collection the element is currently in. Defaults to the root ('All') collection of dest,
            which only works if dest is an owned collection.
        """
        (source or dest.get_root()).assign_elements(dest, self)

    def remove_from(self, collection):
        """
        Removes this element from the collection. The element is not deleted. The request is sent right away.
        See :meth:`chemotion_api.collection.AbstractCollection.remove_elements`

        :param collection: Collection the element is currently in (not the root collection)
        """
        collection.remove_elements(self)

    def delete(self, delete_subsamples: bool = False) -> bool:
        """
        Deletes this element the way the web UI does. The request is sent right away.

        This **withdraws** the element from every collection *you own* and destroys the record only
        if that leaves it in no collection at all. An element someone else also holds in their own
        collections survives for them. See :func:`delete_elements` for the details.

        :param delete_subsamples: when deleting a reaction, also withdraw all of its samples
            (products included). By default only its reactants and solvents go with it.
        :return: ``True`` if the element left your collections, ``False`` if the server kept it
            (a sample still bound to a reaction or wellplate, or an element that is in none of
            your own collections, e.g. one only shared with you).
        :raises ValueError: if the element has not been saved.
        """
        return not delete_elements(self._session, [self], delete_subsamples=delete_subsamples)

    def comments(self) -> list[Comment]:
        """
        The comments on this element and its sections, fetched right away. Pending comments come
        first, then by section, newest first.

        :raises ValueError: if the element is unsaved, or of a type that takes no comments
            (LabIMotion generic elements).
        """
        return load_comments(self._session, self.element_type, self._saved_id_for('comments'))

    def add_comment(self, content: str, section: str | None = None) -> Comment:
        """
        Comments on this element, or on one of its sections. Sent right away.

        :param content: the comment text.
        :param section: ``None`` for the element as a whole, or a section such as
            ``'properties'`` or ``'analyses'`` (see :data:`chemotion_api.elements.comments.SECTIONS`;
            the server's full value, e.g. ``'sample_analyses'``, works too).
        :return: the new comment.
        :raises ValueError: if the element is unsaved, takes no comments, or has no such section.
        """
        return create_comment(self._session, self.element_type, self._saved_id_for('comments'),
                              content, section)

    def private_note(self) -> str | None:
        """
        Your private note on this element — visible only to you — or ``None`` if you have none.
        Fetched right away.

        :raises ValueError: if the element is unsaved, or of a type that takes no private notes
            (LabIMotion generic elements).
        """
        return private_notes.get_private_note(self._session, self.element_type,
                                              self._saved_id_for('private note'))

    def set_private_note(self, content: str) -> None:
        """
        Writes your private note on this element, creating it or replacing its text. Sent right
        away. There is one private note per user per element.

        :raises ValueError: if the element is unsaved or takes no private notes.
        """
        private_notes.set_private_note(self._session, self.element_type,
                                       self._saved_id_for('private note'), content)

    def delete_private_note(self) -> bool:
        """
        Deletes your private note on this element. Sent right away.

        :return: ``False`` if you had none.
        """
        return private_notes.delete_private_note(self._session, self.element_type,
                                                 self._saved_id_for('private note'))

    def versions(self) -> list[Version]:
        """
        This element's change history, newest first, fetched right away. Each
        :class:`~chemotion_api.elements.versions.Version` can be reverted, whole or field by field;
        reload the element afterwards to see the result.

        :raises ValueError: if the element is unsaved, or of a type without a history (LabIMotion
            generic elements).
        """
        return load_versions(self._session, self.element_type, self._saved_id_for('version history'))

    def references(self) -> list[Reference]:
        """
        The literature references of this element, fetched right away.

        :raises ValueError: if the element is unsaved, or of a type without references (generic
            elements).
        """
        return literature.load_references(self._session, self.element_type, self._saved_id_for('references'))

    def add_reference(self, doi: str | None = None, url: str | None = None, title: str | None = None,
                      isbn: str | None = None, bibtex: str | None = None,
                      litype: str = 'citedOwn') -> list[Reference]:
        """
        Cites a reference on this element, sent right away. The server reuses an existing
        literature record with the same DOI, URL, title and ISBN. Fetch BibTeX for a DOI with
        :meth:`chemotion_api.Instance.doi_metadata`.

        :param litype: one of :data:`chemotion_api.elements.literature.REFERENCE_TYPES`.
        :return: the element's references afterwards.
        """
        return literature.add_reference(self._session, self.element_type, self._saved_id_for('references'),
                                        doi=doi, url=url, title=title, isbn=isbn, bibtex=bibtex, litype=litype)

    def remove_reference(self, reference: Reference) -> None:
        """Removes a reference from this element (the literature record itself stays). Sent right away."""
        literature.remove_reference(self._session, self.element_type, self._saved_id_for('references'),
                                    reference)

    def set_reference_type(self, reference: Reference, litype: str) -> list[Reference]:
        """Changes how this element cites a reference, e.g. to ``'citedRef'``. Sent right away."""
        return literature.set_reference_type(self._session, self.element_type,
                                             self._saved_id_for('references'), reference, litype)

    def _saved_id_for(self, what: str) -> int:
        if self.is_new or self.id is None:
            raise ValueError(f'Save the {self.element_type} before using its {what}.')
        return self.id

    def _web_collection_id(self) -> int | str:
        data = self.json_data or {}
        if data.get('collection_id') is not None:
            return data['collection_id']
        try:
            labels = data['tag']['taggable_data']['collection_labels'] or []
        except (KeyError, TypeError):
            labels = []
        # Shared and synchronized collections have different URLs in the web client
        owned = next((x for x in labels if not x.get('is_shared') and not x.get('is_synchronized')), None)
        return owned['id'] if owned is not None else 'all'

    #: The pydantic model that validates this element type's properties, or ``None`` for none
    #: (LabIMotion generic elements validate against their klass's JSON schema instead). Sample
    #: and Reaction set it too but keep their own handlers, which carry stoichiometry side effects.
    _properties_model: type[BaseModel] | None = None

    #: The server's model name for attachments of this element type, when it is not the
    #: camel-cased element type (``Attachment::ELEMENT_ATTACHABLE_TYPES`` in the ELN).
    _attachable_type: str | None = None

    #: Properties the ELN stores as Quill rich text (a delta). They read as the stored delta;
    #: :func:`chemotion_api.utils.quill_to_text` flattens it. A write may be a plain string, which
    #: is stored via :func:`chemotion_api.utils.text_to_quill`, or a well-formed delta (formatting
    #: included, so content read from the ELN can be written back). Owner, 2026-11-13.
    _rich_text_fields: tuple[str, ...] = ()

    def _rich_text_write(self, name: list, value: list) -> None:
        """Convert a plain string to a delta and check the field stays a well-formed delta."""
        from chemotion_api.utils import is_quill_document, text_to_quill
        top = name[0]
        if top not in self._rich_text_fields:
            return
        if len(name) == 1:
            if isinstance(value[-1], str):
                value[-1] = text_to_quill(value[-1])
            elif not is_quill_document(value[-1]):
                raise ValueError(f"properties[{top!r}] is rich text: assign a string or a Quill "
                                 f"delta ({{'ops': [{{'insert': ...}}, ...]}}); see text_to_quill().")
            else:
                value[-1] = value[-1].to_dict() if hasattr(value[-1], 'to_dict') else dict(value[-1])
            return
        # A write *into* the delta: the field must still be a delta afterwards.
        source: Any = self._properties.get(top)
        proposed: Any = copy.deepcopy(source.to_dict() if hasattr(source, 'to_dict') else source)
        temp: Any = proposed
        for key in name[1:-1]:
            temp = temp[key] if isinstance(temp, dict) else None
        if not isinstance(temp, dict):
            raise ValueError(f"properties[{top!r}] has no mapping to write into.")
        temp[name[-1]] = value[-1]
        if not is_quill_document(proposed):
            raise ValueError(f"properties[{top!r}] would no longer be a Quill delta after this write.")

    def _validated_properties(self, props: dict) -> dict:
        """Run freshly parsed properties through :attr:`_properties_model` and keep the coerced values.

        Keys the model does not declare pass through unchanged (the models allow extras).
        """
        model = self._properties_model
        if model is None:
            return props
        validated = model.model_validate(props)
        return {key: (_plain(getattr(validated, key)) if key in model.model_fields else value)
                for key, value in props.items()}

    def on_properties_change(self, dict_obj, name, value):
        """
        Hook invoked when a value in the :attr:`properties` dict is changed.

        With a :attr:`_properties_model`, the written field alone is validated and coerced (a
        nested write is applied to a copy of its field first), and the coerced value is stored.
        Without one, every change is accepted unchanged. Subclasses override this to add side
        effects.

        :param dict_obj: The chain of dicts leading to the changed value
        :param name: The chain of keys identifying the changed value
        :param value: The chain of values, the last being the new value
        :return: ``True`` to let the default assignment proceed, ``False`` when it was applied here
        :raises pydantic.ValidationError: if the new value does not fit the field.
        """
        self._rich_text_write(name, value)
        model = self._properties_model
        if model is None:
            if name[0] in self._rich_text_fields:
                dict_obj[-1][name[-1]] = value[-1]
                return False
            return True
        top = name[0]
        if len(name) == 1:
            proposed = value[-1]
        else:
            source = self._properties.get(top)
            proposed = copy.deepcopy(source.to_dict() if hasattr(source, 'to_dict') else source)
            temp = proposed
            for key in name[1:-1]:
                if not isinstance(temp, dict):
                    raise ValueError(f'properties[{top!r}] has no mapping at {key!r} to write into.')
                temp = temp.setdefault(key, {})
            if not isinstance(temp, dict):
                raise ValueError(f'properties[{top!r}] is a single value; assign the whole field.')
            temp[name[-1]] = value[-1]
        coerced = validate_field(model, top, proposed)
        for key in name[1:]:
            coerced = coerced[key] if isinstance(coerced, dict) else getattr(coerced, key)
        dict_obj[-1][name[-1]] = _plain(coerced)
        return False

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
        # A *copy*: `container['children'][0]['children']` is live inside `json_data`, and the
        # `+=` below mutated it in place. `clean_up_after_save()` only clears `is_new` after a
        # successful PUT, so a failed save left the new analysis already appended to `json_data`
        # while still flagged new — and the retry appended it a second time, creating two
        # identical analyses server-side.
        res_list = list(container.get('children', [{}])[0].get('children', []))
        for (idx, analyses) in enumerate(res_list):
            analyses_obj: list[Analyses] = [item for (index, item) in enumerate(self.analyses) if
                                            item.id == analyses.get('id')]
            if len(analyses_obj) == 1:
                new_data = analyses_obj[0].to_json()
                for (key, item) in analyses.items():
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

    def _segment_field(self, segment: str, layer: str, field: str) -> SegmentField:
        mapping = self._segments_mapping.get(segment)
        if mapping is not None:
            segment_json = next(x for x in (self.json_data or {}).get('segments', []) if x.get('id') == mapping['__id'])
            properties = segment_json.get('properties', {})
        else:
            # A segment the element does not have yet: look the field up in the template
            klass = next((x for x in self._generic_segments.all_classes if x.get('label') == segment
                          and x.get('element_klass', {}).get('name') == self.element_type), None)
            if klass is None:
                raise KeyError(f'"{segment}" is not a generic segment of {self.element_type}.')
            properties = klass.get('properties_release', {})
        for layer_name, field_name, segment_field in iter_fields(properties):
            if layer_name == layer and field_name == field:
                return segment_field
        raise KeyError(f'Segment "{segment}" has no field "{field}" in layer "{layer}".')

    def _clean_segments_data(self) -> dict:
        res_list = cast(dict, self.json_data).get('segments', [])
        for (seg_key, segment_mapping) in self._segments_mapping.items():
            if seg_key in self.segments and self.segments[seg_key] is not None:
                list_idx = next((i for (i, x) in enumerate(res_list)
                                 if isinstance(x, dict) and x.get('id') == segment_mapping['__id']), -1)
                if list_idx == -1:
                    # `list_idx = len(res_list)` indexed one past the end -> IndexError. Appending a
                    # blank entry would be worse: clean_generic_object_json reads
                    # properties.layers.<key>.fields, which only the server's klass template
                    # provides, so a fabricated skeleton would silently discard the segment's
                    # values instead. There is nothing to write into, so say so.
                    raise RuntimeError(
                        f"Segment {seg_key!r} of {self.element_type} {self.id} has no entry in the "
                        "element's json_data['segments'], so its values cannot be serialised. "
                        "Reload the element before saving.")
                clean_generic_object_json(res_list[list_idx], self.segments[seg_key], segment_mapping)

        return {'segments': res_list}

    @classmethod
    def get_response_key(cls, name: str) -> str:
        """
        Returns the element name used to construct the save and load URL

        :param name: The name of the element type

        :return: the key of the element in the server response
        """
        info = element_type_info(name)
        return info.response_key if info is not None else GENERIC_RESPONSE_KEY

    @classmethod
    def get_url(cls, name: str) -> str:
        """
        Returns the load URL based on the element type

        :param name: The name of the element type

        :return: The load url
        """
        info = element_type_info(name)
        return info.url if info is not None else GENERIC_ELEMENTS_URL


def ui_state_selection(elements, action: str) -> dict[str, dict[str, Any]]:
    """
    The per-type part of a UI ``ui_state`` selecting exactly ``elements``:
    ``{type: {'checkedAll': False, 'checkedIds': [...]}}``.

    ``checkedAll`` is deliberately never set: the server resolves it to every element of the type in
    the collection, so one request could reach a user's whole library.

    :param action: what the selection is for, used in the error message.
    :raises ValueError: if no elements are given or one is unsaved.
    """
    selection: dict[str, dict[str, Any]] = {}
    for element in elements:
        if getattr(element, 'is_new', False) or element.id is None:
            raise ValueError(f'The element has not been saved yet, so it cannot be used to {action}.')
        selection.setdefault(element.element_type, {'checkedAll': False, 'checkedIds': []})['checkedIds'] \
            .append(element.id)
    if not selection:
        raise ValueError('No elements given.')
    return selection


def delete_elements(session: Connection, elements, collection_id: int | None = None,
                    delete_subsamples: bool = False) -> list[AbstractElement]:
    """
    Deletes elements the way the web UI does: ``DELETE /api/v1/ui_state``.

    ELN v4 does not destroy the selected records outright. It **withdraws** them from every
    collection the current user owns (their "All" included) and then destroys only the records left
    in no collection at all. So:

    * an element another user also holds in their own collections survives for them;
    * a sample still bound to a reaction or wellplate in one of your collections is kept;
    * an element that is in none of your own collections (one only shared with you) is untouched.

    Deleting a reaction also withdraws its reactants and solvents, or all of its samples with
    ``delete_subsamples=True``.

    The elements must be named one by one: this never sends the UI's ``checkedAll``, which would
    select every element of a type.

    :param session: the connection to send the request on.
    :param elements: saved elements; samples, reactions, wellplates, research plans and generic
        elements.
    :param collection_id: the collection the elements are selected in. Elements not in it are
        ignored. Defaults to your "All" collection.
    :param delete_subsamples: also withdraw all samples of deleted reactions.
    :return: the given elements the server **kept** (they still load afterwards), empty when all of
        them are gone. Like :meth:`chemotion_api.collection.AbstractCollection.remove_elements`, a
        2xx answer is not proof that everything went. Finding out costs one GET per element.
    :raises ValueError: if no elements are given or one is unsaved.
    :raises PermissionError: if the collection is one shared with you (403).
    :raises ConnectionError: if the request fails, or checking an element afterwards does.
    """
    elements = list(elements)
    ui_state: dict[str, Any] = {
        'currentCollection': {'id': collection_id} if collection_id is not None else {},
        'options': {'deleteSubsamples': bool(delete_subsamples)},
    }
    ui_state |= ui_state_selection(elements, 'delete')
    ui_state['selecteds'] = [{'type': e.element_type, 'id': e.id} for e in elements]

    res = session.delete('/api/v1/ui_state', data=json.dumps(ui_state),
                         headers=session.get_json_session_header())
    if res.status_code == 403:
        raise PermissionError(f'You may not delete elements of this collection: {res.text}')
    if res.status_code == 404:
        raise ValueError('Collection not found')
    if res.status_code not in (200, 204):
        raise ConnectionError(f'{res.status_code} -> {res.text}')

    # Which elements went has to be asked afterwards. The response's `selecteds` is meant to echo
    # the selection minus what left the view, but ELN main (a8b47c7) returns built-in elements
    # there even after destroying them (generic ones are filtered correctly), so it is not used.
    # An element that still loads was kept; one that answers 404 (destroyed, or no longer in any
    # collection you can see) is gone.
    kept_elements = []
    for element in elements:
        check = session.get(f'{AbstractElement.get_url(element.element_type)}/{element.id}.json')
        if check.status_code == 200:
            kept_elements.append(element)
        elif check.status_code not in (401, 403, 404):
            raise ConnectionError(
                f'The delete request was accepted, but checking {element.element_type} {element.id} '
                f'afterwards failed: {check.status_code} -> {check.text}')
    if kept_elements:
        logger.warning('delete_elements: the server kept %d of %d element(s): %s', len(kept_elements),
                       len(elements), ', '.join(f'{e.element_type} {e.id}' for e in kept_elements))
    return kept_elements
