import json
import os
import typing
from datetime import datetime
from urllib.parse import urlparse
from enum import Enum
from random import random
from typing import TypeVar, Iterator, Optional, Self, Any, Generator

from chemotion_api.elements import Wellplate, Sample, Reaction, GenericElement, ResearchPlan
from chemotion_api.user import Person, Group

from chemotion_api.elements.sample import MoleculeManager
from chemotion_api.connection import Connection

from chemotion_api.element_manager import ElementManager
from chemotion_api.elements import ElementSet, AbstractElement

TAbstractCollection = TypeVar("TAbstractCollection", bound="AbstractCollection")
TRootCollection = TypeVar("TRootCollection", bound="RootCollection")


def _col_path_join(path_part: str, *path_parts: str) -> str:
    path_parts_list = list(path_parts)
    path_parts_list.reverse()
    for i, x in enumerate(path_parts):
        if x.startswith('/'):
            if i == 0:
                return _col_path_join(x)
            return _col_path_join(x, *path_parts[-i:])
    path_parts_str = '/'.join(path_parts)
    return f'{path_part}/{path_parts_str}'.replace('//', '/').replace('//', '/')


class SyncPermission(Enum):
    """
    Permission level used to share (synchronize) a collection with other users or groups.
    Each level includes the rights of the levels above it.
    """
    Read = 0
    Write = 1
    Share = 2
    Delete = 3
    ImportElements = 4
    PassOwnership = 5


class AbstractCollection:

    def __init__(self):
        self.is_sync = False
        self._children: list[Self] = []
        self._label: str | None = None
        self._parent: Self | None = None
        self._id: int | None = None

    @property
    def children(self) -> list[Self]:
        """
        A list of all children collection

        :return: A list of all children collection
        """
        return self._children

    @property
    def id(self) -> int | None:
        """
        The chemotion DB ID

        :return: The chemotion DB ID
        """
        return self._id

    @id.setter
    def id(self, id: int):
        """
        The chemotion DB ID
        """
        self._id = id

    @property
    def label(self) -> str | None:
        """
        The collection label

        :return: The collection label
        """
        return self._label

    @label.setter
    def label(self, label: str):
        """
        The collection label
        """
        self._label = label

    @property
    def name(self) -> str | None:
        """
        Alias of :attr:`label` (read only)

        :return: The collection label
        """
        return self.label

    def get_label(self) -> str | None:
        """
        Alias of :attr:`label`

        :return: The collection label
        """
        return self.label

    def get_name(self) -> str | None:
        """
        Alias of :attr:`label`

        :return: The collection label
        """
        return self.label

    def prepare_label(self, case_insensitive: bool) -> str:
        """
        Prepares the label of a collection

        :param case_insensitive: If true it returns the lower case label

        :return: The collection's label
        """
        if case_insensitive:
            return self.label.lower()
        return self.label

    def __str__(self) -> str:
        return self.get_path()

    def __iter__(self) -> Generator[tuple[str, list[Self]], None, None]:
        """
        Iterate over all children

        :return: Iterator
        """
        yield 'collections', self._children

    def move(self, dest: str | list[str], case_insensitive: bool = False):
        raise NotImplementedError('Cannot not move this Collection')

    def _set_children(self, new_children: list[dict]):
        if new_children is None:
            self._children = []
            return
        ids = []
        for child in new_children:
            ids.append(child['id'])
            child_obj: Self | None = next((x for x in self._children if x.id == child['id']), None)
            if child_obj is None:
                self._children.append(Collection(child))
            else:
                child_obj.set_json(child)
        self._children = [child_obj for child_obj in self._children if child_obj.id in ids]
        self._update_relations()

    def _update_relations(self):
        for child in self._children:
            child._parent = self
            child.is_sync = self.is_sync
            child._update_relations()

    def to_json(self) -> dict:
        """
        Generates a dict containing all list of all children collection

        :return: list of children as savable JSON
        """
        return {'children': [x.to_json() for x in self._children]}

    def find(self, label: str | None = None, **kwargs) -> list[typing.Union['AbstractCollection', 'Collection']]:
        """
        Finds collections by label or other properties in this collection and all of its
        descendants. A path is not needed.

        :param label: label of the collection or None.
        :param kwargs: Other properties (attribute name = value) used to search Collections, e.g. ``id=12``

        :return: All found Collections
        """

        results: list[Collection | AbstractCollection] = []
        if label is not None: kwargs['label'] = label
        hit = True
        for (key, val) in kwargs.items():
            if getattr(self, key) != val:
                hit = False
                break
        if hit:
            results.append(self)
        for x in self._children:
            results += x.find(**kwargs)
        return results

    def walk(self, include_self: bool = False, max_depth: int | None = None) -> Generator[Self, None, None]:
        """
        Walks through the collection tree below this collection (depth-first, pre-order:
        a parent is yielded before its children).

        Usage::

        >>> for col in instance.get_root_collection().walk():
        >>>     print(col.get_path())

        :param include_self: If true, this collection is yielded first
        :param max_depth: Maximum depth below this collection (1 = only direct children). None means no limit

        :return: Generator yielding the collections
        """

        if include_self:
            yield self
        if max_depth is not None and max_depth < 1:
            return
        next_depth = None if max_depth is None else max_depth - 1
        for child in list(self._children):
            yield from child.walk(include_self=True, max_depth=next_depth)

    def get_path(self) -> str:
        """
        Generates the absolute path of the collection, e.g. ``'/Projects/Team One'``

        :return: Absolute path of a collection
        """

        abs_path = []
        col = self
        while col._parent is not None:
            abs_path.append(col.label)
            col = col._parent
        abs_path.append('')
        abs_path.reverse()
        return '/'.join(abs_path)

    def get_root(self) -> TRootCollection:
        """
        Get root Collection

        :return: Instance of the RootCollection
        """

        col = self
        while col._parent is not None:
            col = col._parent
        return col

    def get_collection(self, col_path: str | list[str], case_insensitive: bool = False) -> 'AbstractCollection':
        """
        Gets a collection a path points to. Relative paths (e.g. ``'P 123'``) start
        at this collection, absolute paths (e.g. ``'/Projects/P 123'``) at the root collection.
        ``.`` and ``..`` are not supported.

        :param col_path: is either a string based on a unix path or a list
        :param case_insensitive: If true, the path is matched ignoring upper and lower case

        :return: Collection the path points to

        :raises ModuleNotFoundError: if the collection does not exist
        """

        abs_path = self.get_path()
        if col_path.__class__ is not str:
            col_path = '/'.join(col_path)
        return self.get_root().get_collection(_col_path_join(abs_path, col_path), case_insensitive)

    def get_or_create_collection(self, col_path: str | list[str],
                                 case_insensitive: bool = False) -> TAbstractCollection:
        """
        Gets or creates a collection the col_path path points to. If the collection needs to be created
        the collection is saved right away. Missing parent collections are not created.

        :param col_path: is either a string based on a unix path or a list
        :param case_insensitive: If true, the path is matched ignoring upper and lower case

        :return: Collection the path points to
        """

        try:
            return self.get_collection(col_path, case_insensitive)
        except:
            new_col = self.add_collection(col_path)
            root = self.get_root()
            new_path = new_col.get_path()
            root.save()
            return root.get_collection(new_path)

    def add_collection(self, col_path: str | list[str]):
        """
        Creates a new collection at the path_to_new path. The collection is not saved.
        Please reload the collection after saving it.

        :param col_path: is either a string based on a unix path or a list

        :return: new Collection (not saved)

        :raises: Exception if collection is synced. This is not yet implemented
        """

        if self.is_sync:
            raise Exception("You cannot add a collection to a synced collection!")
        raise NotImplementedError('This collection cannot add a collection')

    def move_elements(self, dest: 'AbstractCollection', *elements: AbstractElement):
        """
        Moves elements from this collection into the dest collection. The request is sent right away.
        Elements cannot be moved out of the root ('All') collection, use :meth:`assign_elements` instead.

        :param dest: Destination collection (owned or synced with write permission)
        :param elements: Saved elements contained in this collection. Elements not in this collection are ignored by the server.

        :raises ConnectionError: if the elements could not be moved
        """
        self._send_elements_request('put', elements, dest)

    def assign_elements(self, dest: 'AbstractCollection', *elements: AbstractElement):
        """
        Adds elements of this collection to the dest collection as well (copy without duplicating the elements).
        The request is sent right away.

        :param dest: Destination collection (owned or synced with write permission)
        :param elements: Saved elements contained in this collection. Elements not in this collection are ignored by the server.

        :raises ConnectionError: if the elements could not be assigned
        """
        self._send_elements_request('post', elements, dest)

    def remove_elements(self, *elements: AbstractElement):
        """
        Removes elements from this collection. The elements are not deleted and stay in the root ('All') collection.
        The request is sent right away. Elements cannot be removed from the root ('All') collection.

        :param elements: Saved elements contained in this collection

        :raises ConnectionError: if the elements could not be removed
        """
        self._send_elements_request('delete', elements)

    def _send_elements_request(self, method: str, elements: tuple[AbstractElement, ...],
                               dest: Optional['AbstractCollection'] = None):
        if self.id is None:
            raise ValueError(f'Collection "{self.label}" cannot hold elements')
        ui_state: dict[str, Any] = {'currentCollection': {'id': self.id, 'is_sync_to_me': self.is_sync}}
        for element in elements:
            if element.is_new:
                raise ValueError('The element has not been saved yet. Save it first.')
            ui_state.setdefault(element.element_type, {'checkedAll': False, 'checkedIds': []})['checkedIds'].append(element.id)
        data: dict[str, Any] = {'ui_state': ui_state}
        if dest is not None:
            if dest.id is None:
                raise ValueError(f'Collection "{dest.label}" cannot hold elements')
            data |= {'collection_id': dest.id, 'is_sync_to_me': dest.is_sync}
        session = self.get_root()._session
        # DELETE is not sent as JSON by default
        res = getattr(session, method)('/api/v1/collections/elements', data=data,
                                       headers=session.get_json_session_header())
        if res.status_code != 204:
            raise ConnectionError(f"{res.status_code} -> {res.text}")

    def get_elements_of_iri(self, element_type: str, per_page: Optional[int] = 10, updated_to_date: Optional[datetime] = None,
                      updated_from_date: Optional[datetime] = None) -> ElementSet:
        """
        Gets all elements of given IRI type (``element.json_ld['@type']``).
        Since the filter is applied on the client side, the returned set has no length and cannot be indexed;
        iterate over it instead.

        :param element_type: IRI string chemotion:xxx/xxx/xxx (see :meth:`chemotion_api.Instance.get_all_types`)
        :param per_page: How many Elements per page
        :param updated_to_date: Set date time to fetch only elements which are updated before 'updated_to_date'
        :param updated_from_date: Set date time to fetch only elements which are updated after 'updated_from_date'

        :return: ElementSet based on the IRI
        """

        root = self.get_root()
        if element_type in root._element_manager.all_types:
            o = urlparse(element_type)
            e = ElementSet(root._session, root._element_manager.all_classes.get(o.path.split('/')[1]), self.id,
                           self.is_sync)
            e.load_elements(per_page, updated_to_date, updated_from_date)
            e.set_iri_filter(element_type)
            return e
        raise ValueError(f'Could not find a element with the IRI: "{element_type}"')

    def get_samples(self, per_page: Optional[int] = 10, updated_to_date: Optional[datetime] = None,
                      updated_from_date: Optional[datetime] = None, product_only: bool = False) -> ElementSet:
        """
        List of all samples.

        :param per_page: How many Elements per page
        :param updated_to_date: Set date time to fetch only elements which are updated before 'updated_to_date'
        :param updated_from_date: Set date time to fetch only elements which are updated after 'updated_from_date'
        :param product_only: If True only samples which are products in a reaction are returned

        :return: ElementSet of samples
        """

        root = self.get_root()
        e = ElementSet(root._session, root._element_manager.all_classes.get('sample'), self.id,
                       self.is_sync)
        e.load_elements(per_page, updated_to_date, updated_from_date, product_only)
        return e

    def get_reactions(self, per_page: Optional[int] = 10, updated_to_date: Optional[datetime] = None,
                      updated_from_date: Optional[datetime] = None) -> ElementSet:
        """
        List of all reactions.

        :param per_page: How many Elements per page
        :param updated_to_date: Set date time to fetch only elements which are updated before 'updated_to_date'
        :param updated_from_date: Set date time to fetch only elements which are updated after 'updated_from_date'

        :return: ElementSet of reactions
        """

        root = self.get_root()
        e = ElementSet(root._session, root._element_manager.all_classes.get('reaction'), self.id,
                       self.is_sync)
        e.load_elements(per_page, updated_to_date, updated_from_date)
        return e

    def get_research_plans(self, per_page: Optional[int] = 10, updated_to_date: Optional[datetime] = None,
                      updated_from_date: Optional[datetime] = None) -> ElementSet:
        """
        List of all research plans.

        :param per_page: How many Elements per page
        :param updated_to_date: Set date time to fetch only elements which are updated before 'updated_to_date'
        :param updated_from_date: Set date time to fetch only elements which are updated after 'updated_from_date'

        :return: ElementSet of research plans
        """

        root = self.get_root()
        e = ElementSet(root._session, root._element_manager.all_classes.get('research_plan'), self.id,
                       self.is_sync)
        e.load_elements(per_page, updated_to_date, updated_from_date)
        return e

    def get_wellplates(self, per_page: Optional[int] = 10, updated_to_date: Optional[datetime] = None,
                      updated_from_date: Optional[datetime] = None) -> ElementSet:
        """
        List of all well plates.

        :param per_page: How many Elements per page
        :param updated_to_date: Set date time to fetch only elements which are updated before 'updated_to_date'
        :param updated_from_date: Set date time to fetch only elements which are updated after 'updated_from_date'

        :return: ElementSet of well plates
        """

        root = self.get_root()
        e = ElementSet(root._session, root._element_manager.all_classes.get('wellplate'), self.id,
                       self.is_sync)
        e.load_elements(per_page, updated_to_date, updated_from_date)
        return e

    def get_generics_by_name(self, name: str, per_page: Optional[int] = 10, updated_to_date: Optional[datetime] = None,
                      updated_from_date: Optional[datetime] = None) -> ElementSet:
        """
        List of all generic elements of a given name.

        :param name: generic element's name
        :param per_page: How many Elements per page
        :param updated_to_date: Set date time to fetch only elements which are updated before 'updated_to_date'
        :param updated_from_date: Set date time to fetch only elements which are updated after 'updated_from_date'

        :return: ElementSet of generic elements of a given name
        """

        root = self.get_root()
        elem = root._element_manager.all_classes.get(name)
        if elem is None:
            raise ValueError(f'Could not find a generic element under the name: "{name}"')

        e = ElementSet(root._session, elem, self.id, self.is_sync)
        e.load_elements(per_page, updated_to_date, updated_from_date)
        return e

    def get_generics_by_label(self, label: str, per_page: Optional[int] = 10, updated_to_date: Optional[datetime] = None,
                      updated_from_date: Optional[datetime] = None) -> ElementSet:
        """
        List of all generic elements of a given label.

        :param label: generic element's label
        :param per_page: How many Elements per page
        :param updated_to_date: Set date time to fetch only elements which are updated before 'updated_to_date'
        :param updated_from_date: Set date time to fetch only elements which are updated after 'updated_from_date'

        :return: ElementSet of generic elements of a given name
        """

        root = self.get_root()
        for (elem_name, elem) in root._element_manager.all_classes.items():
            if elem['label'] == label:
                return self.get_generics_by_name(elem_name, per_page, updated_to_date, updated_from_date)
        raise ValueError(f'Could not find a generic element with the label: "{label}"')


class AbstractEditableCollection(AbstractCollection):

    def new_sample(self) -> Sample:
        """
        Creates a new sample in this collection.

        :return: New (unsaved) Sample
        """
        return typing.cast(Sample, self._create_new_element('sample'))

    def new_sample_smiles(self, smiles_code: str) -> Sample:
        """
        Creates a new sample with a molecule generated with a smiles code in this collection.

        :param smiles_code: SMILES code of the molecule
        :return: New (unsaved) Sample
        """
        sample = self._create_new_element('sample')
        mol = MoleculeManager(self.get_root()._session).create_molecule_by_smiles(smiles_code)
        sample.molecule = mol
        return typing.cast(Sample, sample)

    def new_solvent(self, name) -> Sample:
        """
        Creates a new solvent in this collection.

        :param name: Name of a predefined solvent (see :meth:`chemotion_api.Instance.get_solvent_list`)
        :return: New (unsaved) solvent as Sample
        """
        root = self.get_root()
        new_json = root._element_manager.build_solvent_sample(name, self.id)
        e = ElementSet(root._session, root._element_manager.all_classes.get('sample'), self.id,
                       self.is_sync)
        return typing.cast(Sample, e.new_element(new_json, is_solvent=True))

    def new_reaction(self) -> Reaction:
        """
        Creates a new reaction in this collection.

        :return: New (unsaved) Reaction
        """
        return typing.cast(Reaction, self._create_new_element('reaction'))

    def new_research_plan(self) -> ResearchPlan:
        """
        Creates a new research plan in this collection.

        :return: New (unsaved) ResearchPlan
        """
        return typing.cast(ResearchPlan, self._create_new_element('research_plan'))

    def new_wellplate(self) -> Wellplate:
        """
        Creates a new well plate in this collection.

        :return: New (unsaved) Wellplate
        """

        return typing.cast(Wellplate, self._create_new_element('wellplate'))

    def new_generic(self, type_name: str) -> GenericElement:
        """
        Creates a new element of given type name in this collection.

        :param type_name: Generic element's type name

        :return: New (unsaved) GenericElement
        """

        return typing.cast(GenericElement, self._create_new_element(type_name))

    def new_generic_by_label(self, label: str) -> GenericElement:
        """
        Creates a new element of given label in this collection.

        :param label: Generic element's label

        :return: GenericElement
        """

        for (elem_name, elem) in self.get_root()._element_manager.all_classes.items():
            if elem['label'] == label:
                return typing.cast(GenericElement, self._create_new_element(elem_name))
        raise ValueError(f'Could not find a generic element with the label: "{label}"')

    def new_element_by_iri(self, element_type: str) -> AbstractElement:
        """
        Creates a new element of given IRI type. However, if the type is generic the generated element is of the newest version.

        :param element_type: IRI string chemotion:xxx/xxx/xxx

        :return: AbstractElement
        """

        if element_type in self.get_root()._element_manager.all_types:
            o = urlparse(element_type)
            return self._create_new_element(o.path.split('/')[1])
        raise ValueError(f'Could not find a generic element with the label: "{element_type}"')

    def _create_new_element(self, type_name) -> AbstractElement:
        root = self.get_root()
        new_json = root._element_manager.build_new(type_name, self.id)

        e = ElementSet(root._session, root._element_manager.all_classes.get(type_name), self.id,
                       self.is_sync)
        return e.new_element(new_json)


class Collection(AbstractEditableCollection):
    """
    The collection object represents the standard collection owned by the current user.
    Changes to the collection tree (add, move, delete) are only sent to the server when
    :meth:`chemotion_api.collection.RootCollection.save` is called.
    """

    def __init__(self, collection_json: dict = None):
        super().__init__()
        self.permission_level: int | None = None
        self.reaction_detail_level: int | None = None
        self.sample_detail_level: int | None = None
        self.screen_detail_level: int | None = None
        self.wellplate_detail_level: int | None = None
        self.element_detail_level: int | None = None
        self.sync_collections_users: dict | None = None
        self.is_locked: bool | None = None
        self.is_shared: bool | None = None
        self.is_synchronized: bool | None = None
        self.set_json(collection_json)

    collection_json: dict = None

    def set_json(self, collection_json):
        """
        Set the json data received from the server

        :param collection_json: JSON object representing the collection
        """
        if collection_json is None:
            collection_json = self._get_new_json()

        self.collection_json = collection_json
        self._set_children(collection_json.get('children', []))
        if 'children' in collection_json: del collection_json['children']

        for (key, val) in collection_json.items():
            if hasattr(self, key):
                setattr(self, key, val)

    def _get_new_json(self):
        return {
            "id": random(),
            "label": 'New Collection',
            "isNew": True
        }

    def __iter__(self):
        for (key, val) in self.collection_json.items():
            if hasattr(self, key):
                val = getattr(self, key)
            yield (key, val)

    def to_json(self):
        """
        Generates a dict containing all list of all children collection

        :return: list of children as savable JSON
        """
        as_dict = dict(self)
        return super().to_json() | as_dict

    def move(self, dest: str | list[str], case_insensitive: bool = False):
        """
        Moves this collection into the collection at the dest path.
        Relative paths start at the parent of this collection. The move is not saved.

        :param dest: is either a string based on a unix path or a list
        :param case_insensitive: If true, the path is matched ignoring upper and lower case
        """

        abs_path = self.get_path()
        dest = _col_path_join(os.path.dirname(abs_path), dest)
        self.get_root().move(abs_path, dest, case_insensitive)

    def delete(self):
        """
        Deletes this collection. The deletion is not saved.
        """
        abs_path = self.get_path()
        self.get_root().delete(abs_path)

    def add_collection(self, name: str):
        """
        Creates a new child collection. The collection is not saved.
        Please reload the collection after saving it.

        :param name: new collection`s name

        :return: new Collection (not saved)
        """
        abs_path = _col_path_join(self.get_path(), name)
        return self.get_root().add_collection(abs_path)

    def share(self, permission_level: SyncPermission, *users: Person | Group):
        """
        Shares (synchronizes) a collection with a set of users or groups. The request is sent right away.

        :param permission_level: Element from SyncPermission
        :param users: users or groups

        :raises ConnectionError: if the collection could not be shared
        """
        data = {
            "collection_attributes": {
                "permission_level": permission_level.value,
                "sample_detail_level": 10,
                "reaction_detail_level": 10,
                "wellplate_detail_level": 10,
                "screen_detail_level": 10,
                "element_detail_level": 10
            },
            "user_ids": [
                {'label': f'{user.name} ({user.initials} - {user.user_type})',
                 'name': user.name,
                 'value': user.id} for user in users if user.is_group() or user.is_person()
            ],
            "id": self.id
        }

        res = self.get_root()._session.post('/api/v1/syncCollections/', data=data)
        if res.status_code != 201:
            raise ConnectionError(f"{res.status_code} -> {res.text}")


class RootSyncCollection(AbstractCollection):
    """
    This can be used almost like the root collection object. It contains all collections shared with you.
    However, you cannot move, delete or create its child collections
    """

    def __init__(self, session: Connection, element_manager: ElementManager):
        super().__init__()
        self.is_sync = True
        self._session = session
        self._element_manager = element_manager
        self.label = 'sync_root'

    def to_json(self):
        as_dict = dict(self)
        return super().to_json() | as_dict

    def move(self, *args, **kwargs):
        raise Exception("You cannot move a synced collection collection!")

    def delete(self, *args, **kwargs):
        raise Exception("You cannot delete a synced collection collection!")


class RootCollection(AbstractCollection):
    """
    The root collection is the foundation of working with collections. It serves with methods to navigate through the
    collections and creating new collections



    Usage::

    >>> from chemotion_api import Instance
    >>> import logging
    >>> try:
    >>>     instance = Instance('http(d)://xxx.xxx.xxx').test_connection().login('<USER>', "<PASSWORD>")
    >>> except ConnectionError as e:
    >>>     logging.error(f"A connection to Chemotion ({instance.host_url}) cannot be established")
    >>> rc = instance.get_root_collection(True)
    >>> # Navigate to collection 'Team One' in 'Projects'
    >>> col = rc.get_collection('/Projects/Team One')
    >>> # Create collection 'P 123' in '/Projects/Team One'
    >>> col.get_or_create_collection('P 123')
    >>> # Move collection P 122 into collection '/Done Projects' and save the change
    >>> col.get_collection('P 122').move('/Done Projects')
    >>> rc.save()
    >>> for sample in col.get_samples():
    >>>     pass # Do something
    """

    def __init__(self, session: Connection):
        super().__init__()
        self._sync_root: RootSyncCollection | None = None
        self._all: dict | None = None
        self._element_manager: ElementManager
        self._session = session
        self.label = 'root'
        self._deleted_ids = []
        self._id = None

    @property
    def id(self) -> int:
        """
        The 'All' collection ID

        :return: The ID of the 'All' collection
        """

        if self._id is None:
            self.load_collection()
        return self._id

    @property
    def sync_root(self) -> RootSyncCollection:
        """
        The RootSyncCollection collection can be used to access all collection synced with you.

        :return: instance of RootSyncCollection
        """

        if self._sync_root is None:
            self.load_sync_collection()
        return self._sync_root

    @property
    def all(self) -> dict[str,dict]:
        """
        Returns all information of the 'All' collections

        :return: information of the 'All' collection
        """

        if self._all is None:
            self.load_collection()
        return self._all

    def set_element_manager(self, element_manager: ElementManager):
        """
        Set the ElementManager class

        :param element_manager: instance of ElementManager
        """

        self._element_manager = element_manager

    def load_collection(self) -> dict[str,dict]:
        """
        Loads the collection tree from the server. Unsaved changes are lost.

        :return: information of the 'All' collection
        """

        collection_url = '/api/v1/collections/roots.json'

        res = self._session.get(collection_url)

        if res.status_code != 200:
            raise ConnectionError('{} -> {}'.format(res.status_code, res.text))

        collections = json.loads(res.content)
        self._all = self._load_all_collection()['collection']
        self._id = self._all['id']
        self._set_children(collections['collections'])
        return self._all

    def load_sync_collection(self) -> RootSyncCollection:
        """
        Loads the RootSyncCollection. The RootSyncCollection collection can be used to access all collection synced with you.

        :return: instance of RootSyncCollection
        """

        collection_url = '/api/v1/syncCollections/sync_remote_roots'

        res = self._session.get(collection_url)

        if res.status_code != 200:
            raise ConnectionError('{} -> {}'.format(res.status_code, res.text))
        collections = json.loads(res.content)
        self._sync_root = RootSyncCollection(self._session, self._element_manager)
        self._sync_root._set_children(collections['syncCollections'])
        return self._sync_root

    def save(self):
        """
        Saves ALL updates done to owned (not synced) collections and reloads the collection tree.
        """

        collection_url = '/api/v1/collections'
        payload = self.to_json()
        payload['deleted_ids'] = self._deleted_ids
        res = self._session.patch(collection_url,
                                  data=payload)
        if res.status_code != 200:
            raise ConnectionError('{} -> {}'.format(res.status_code, res.text))
        self.load_collection()

    def get_collection(self, col_path: str | list[str], case_insensitive: bool = False) -> 'AbstractCollection':
        """
        Gets a collection a path points to.

        :param col_path: is either a string based on a unix path or a list
        :param case_insensitive: If true, the path is matched ignoring upper and lower case

        :return: Collection the path points to
        """

        col_path = self._prepare_path(col_path)
        current_pos = self
        for col_label in self._prepare_path(col_path):
            current_pos = next((x for x in current_pos.children if
                                x.prepare_label(case_insensitive) == col_label), None)
            if current_pos is None:
                raise ModuleNotFoundError("'{}' Collection Not Found".format('/'.join(col_path)))
        return current_pos

    def move(self, src: str | list[str], dest: str | list[str], case_insensitive: bool = False):
        """
        Moves a collection from a src path into the collection at the dest path. The move is not saved.

        :param src: is either a string based on a unix path or a list
        :param dest: is either a string based on a unix path or a list
        :param case_insensitive: If true, the path is matched ignoring upper and lower case
        """

        prepared_src = self._prepare_path(src, case_insensitive)
        src_col = self.get_collection(prepared_src, case_insensitive)

        idx = next((i for (i, x) in enumerate(src_col._parent.children) if
                    x.prepare_label(case_insensitive) == prepared_src[-1]), None)
        dest_col = self.get_collection(dest, case_insensitive)

        src_col._parent.children.pop(idx)
        dest_col.children.append(src_col)
        self._update_relations()

    def delete(self, src: str | list[str], case_insensitive: bool = False):
        """
        Deletes a collection at the src path. The deletion is not saved.

        :param src: is either a string based on a unix path or a list
        :param case_insensitive: If true, the path is matched ignoring upper and lower case
        """

        prepared_src = self._prepare_path(src, case_insensitive)
        src_col = self.get_collection(prepared_src)
        idx = next((i for (i, x) in enumerate(src_col._parent.children) if x.label == prepared_src[-1]), None)

        src_col._parent.children.pop(idx)
        src_col._parent = None
        self._deleted_ids.append(src_col.id)

    def add_collection(self, path_to_new: str | list[str]):
        """
        Creates a new collection at the path_to_new path. The collection is not saved.
        Please reload the collection after saving it.

        :param path_to_new: is either a string based on a unix path or a list

        :return: new Collection (not saved)
        """

        prepared_src = self._prepare_path(path_to_new)
        src_col = self.get_collection(prepared_src[:-1])
        c = Collection()
        c.label = prepared_src[-1]
        src_col.children.append(c)
        self._update_relations()
        return c

    def to_json(self) -> dict[str, list]:
        """
        Generates a dict containing all list of all children collection

        :return: list of children as savable JSON
        """

        return {'collections': super().to_json()['children']}

    def _prepare_path(self, col_path: str | list[str], case_insensitive: bool = False) -> list[str]:
        if type(col_path) == str:
            if not col_path.startswith('/'): col_path = '/' + col_path
            col_path = [x for x in col_path.strip('/').split('/') if x != '']
            if case_insensitive:
                col_path = [x.lower() for x in col_path]

        return col_path

    def _load_all_collection(self):
        collection_url = '/api/v1/collections/all'

        res = self._session.get(collection_url)

        if res.status_code != 200:
            raise ConnectionError('{} -> {}'.format(res.status_code, res.text))
        return json.loads(res.content)
