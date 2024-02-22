import json
import os
from enum import Enum
from random import random
from typing import TypeVar

from chemotion_api.user import Person, Group

from chemotion_api.elements.sample import MoleculeManager
from chemotion_api.connection import Connection

from chemotion_api.element_manager import ElementManager
from chemotion_api.elements import ElementSet, AbstractElement

TAbstractCollection = TypeVar("TAbstractCollection", bound="AbstractCollection")
TRootCollection = TypeVar("TRootCollection", bound="RootCollection")


class SyncPremission(Enum):
    Read = 0
    Write = 1
    Share = 2
    Delete = 3
    ImportElements = 4
    PassOwnership = 5


class AbstractCollection:
    children: list[TAbstractCollection]
    label: str = None
    _parent: TAbstractCollection = None
    id: int = None

    @classmethod
    def prepare_label(cls, label: str, case_insensitive):
        if case_insensitive:
            return label.lower()
        return label

    def __init__(self):
        self.children = []
        self.is_sync = False

    def __str__(self) -> str:
        return self.get_path()

    def __iter__(self):
        yield ('collections', self.children)

    def _set_children(self, new_children: list[dict]):
        if new_children is None:
            self.children = []
            return
        ids = []
        for child in new_children:
            ids.append(child['id'])
            child_obj: TAbstractCollection | None = next((x for x in self.children if x.id == child['id']), None)
            if child_obj is None:
                self.children.append(Collection(child))
            else:
                child_obj.set_json(child)
        self.children = [child_obj for child_obj in self.children if child_obj.id in ids]
        self._update_relations()

    def _update_relations(self):
        for child in self.children:
            child._parent = self
            child.is_sync = self.is_sync
            child._update_relations()

    def to_json(self) -> dict:
        return {'children': [x.to_json() for x in self.children]}

    def find(self, label: str = None, **kwargs) -> list[TAbstractCollection]:
        results: list[AbstractCollection] = []
        if label is not None: kwargs['label'] = label
        hit = True
        for (key, val) in kwargs.items():
            if getattr(self, key) != val:
                hit = False
                break
        if hit:
            results.append(self)
        for x in self.children:
            results += x.find(**kwargs)
        return results

    def get_path(self) -> str:
        abs_path = []
        col = self
        while col._parent is not None:
            abs_path.append(col.label)
            col = col._parent
        abs_path.append('')
        abs_path.reverse()
        return '/'.join(abs_path)

    def get_root(self) -> TRootCollection:
        col = self
        while col._parent is not None:
            col = col._parent
        return col

    def get_collection(self, col_path: str | list[str], case_insensitive: bool = False) -> TAbstractCollection | None:
        abs_path = self.get_path()
        if col_path.__class__ is not str:
            col_path = '/'.join(col_path)
        return self.get_root().get_collection(os.path.join(abs_path, col_path), case_insensitive)

    def get_or_create_collection(self, col_path: str | list[str],
                                 case_insensitive: bool = False) -> TAbstractCollection:
        try:
            return self.get_collection(col_path, case_insensitive)
        except:
            new_col = self.add_collection(col_path)
            root = self.get_root()
            new_path = new_col.get_path()
            root.save()
            return root.get_collection(new_path)

    def add_collection(self, col_path: str | list[str]):
        if self.is_sync:
            raise Exception("You cannot add a collection to a synced collection!")
        raise NotImplementedError('This collection cannot add a collection')

    def get_samples(self, per_page=10) -> ElementSet:
        root = self.get_root()
        e = ElementSet(root._session, root._element_manager.all_classes.get('sample'), self.id,
                       self.is_sync)
        e.load_elements(per_page)
        return e

    def get_reactions(self, per_page=10) -> ElementSet:
        root = self.get_root()
        e = ElementSet(root._session, root._element_manager.all_classes.get('reaction'), self.id,
                       self.is_sync)
        e.load_elements(per_page)
        return e

    def get_research_plans(self, per_page=10) -> ElementSet:
        root = self.get_root()
        e = ElementSet(root._session, root._element_manager.all_classes.get('research_plan'), self.id,
                       self.is_sync)
        e.load_elements(per_page)
        return e

    def get_wellplates(self, per_page=10) -> ElementSet:
        root = self.get_root()
        e = ElementSet(root._session, root._element_manager.all_classes.get('wellplate'), self.id,
                       self.is_sync)
        e.load_elements(per_page)
        return e

    def get_generics_by_name(self, name, per_page=10):
        root = self.get_root()
        elem = root._element_manager.all_classes.get(name)
        if elem is None:
            raise ValueError(f'Could not find a generic element under the name: "{name}"')

        e = ElementSet(root._session, elem, self.id, self.is_sync)
        e.load_elements(per_page)
        return e

    def get_generics_by_label(self, label, id):
        root = self.get_root()
        for (elem_name, elem) in root._element_manager.all_classes.items():
            if elem['label'] == label:
                return self.get_generics_by_label(elem_name, id)
        raise ValueError(f'Could not find a generic element with the label: "{label}"')


class AbstractEditableCollection(AbstractCollection):

    def new_sample(self) -> AbstractElement:
        return self._create_new_element('sample')

    def new_sample_smiles(self, smiles_code: str) -> AbstractElement:
        sample = self._create_new_element('sample')
        mol = MoleculeManager(self.get_root()._session).create_molecule_by_smiles(smiles_code)
        sample.molecule = mol
        return sample

    def new_solvent(self, name) -> AbstractElement:
        root = self.get_root()
        new_json = root._element_manager.build_solvent_sample(name, self.id)
        e = ElementSet(root._session, root._element_manager.all_classes.get('sample'), self.id,
                       self.is_sync)
        return e.new_element(new_json)

    def new_reaction(self) -> AbstractElement:
        return self._create_new_element('reaction')

    def new_research_plan(self) -> AbstractElement:
        return self._create_new_element('research_plan')

    def new_wellplate(self) -> AbstractElement:
        return self._create_new_element('wellplate')

    def new_generic(self, type_name) -> AbstractElement:
        return self._create_new_element(type_name)

    def new_generic_by_label(self, label) -> AbstractElement:
        for (elem_name, elem) in self.get_root()._element_manager.all_classes.items():
            if elem['label'] == label:
                return self._create_new_element(elem_name)
        raise ValueError(f'Could not find a generic element with the label: "{label}"')

    def _create_new_element(self, type_name) -> AbstractElement:
        root = self.get_root()
        new_json = root._element_manager.build_new(type_name, self.id)

        e = ElementSet(root._session, root._element_manager.all_classes.get(type_name), self.id,
                       self.is_sync)
        return e.new_element(new_json)


class Collection(AbstractEditableCollection):
    permission_level: int = None
    reaction_detail_level: int = None
    sample_detail_level: int = None
    screen_detail_level: int = None
    wellplate_detail_level: int = None
    element_detail_level: int = None
    sync_collections_users: dict = None
    is_locked: bool = None
    is_shared: bool = None
    is_synchronized: bool = None

    collection_json: dict = None

    def __init__(self, collection_json: dict = None):
        super().__init__()
        self.set_json(collection_json)

    def set_json(self, collection_json):
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
        as_dict = dict(self)
        return super().to_json() | as_dict

    def move(self, dest):
        abs_path = self.get_path()
        dest = os.path.abspath(os.path.join(os.path.dirname(abs_path), dest))
        self.get_root().move(abs_path, dest)

    def delete(self):
        abs_path = self.get_path()
        self.get_root().delete(abs_path)

    def add_collection(self, name):
        abs_path = os.path.join(self.get_path(), name)
        return self.get_root().add_collection(abs_path)

    def share(self, premission_level: SyncPremission, *users: Person | Group):
        data = {
            "collection_attributes": {
                "permission_level": premission_level.value,
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
    sync_root: RootSyncCollection = None
    all: dict = None
    _element_manager: ElementManager

    def __init__(self, session: Connection):
        super().__init__()
        self._session = session
        self.label = 'root'
        self._deleted_ids = []

    def set_element_manager(self, element_manager: ElementManager):
        self._element_manager = element_manager

    def load_collection(self):
        collection_url = '/api/v1/collections/roots.json'

        res = self._session.get(collection_url)

        if res.status_code != 200:
            raise ConnectionError('{} -> {}'.format(res.status_code, res.text))

        collections = json.loads(res.content)
        self.all = self._load_all_collection()['collection']
        self.id = self.all['id']
        self._set_children(collections['collections'])

    def _load_all_collection(self):
        collection_url = '/api/v1/collections/all'

        res = self._session.get(collection_url)

        if res.status_code != 200:
            raise ConnectionError('{} -> {}'.format(res.status_code, res.text))
        return json.loads(res.content)

    def load_sync_collection(self):
        collection_url = '/api/v1/syncCollections/sync_remote_roots'

        res = self._session.get(collection_url)

        if res.status_code != 200:
            raise ConnectionError('{} -> {}'.format(res.status_code, res.text))
        collections = json.loads(res.content)
        self.sync_root = RootSyncCollection(self._session, self._element_manager)
        self.sync_root._set_children(collections['syncCollections'])

    def save(self):
        collection_url = '/api/v1/collections'
        payload = self.to_json()
        payload['deleted_ids'] = self._deleted_ids
        res = self._session.patch(collection_url,
                                  data=payload)
        if res.status_code != 200:
            raise ConnectionError('{} -> {}'.format(res.status_code, res.text))
        self.load_collection()

    def get_collection(self, col_path: str | list[str], case_insensitive: bool = False) -> TAbstractCollection | None:
        col_path = self._prepare_path(col_path)
        current_pos = self
        for col_label in self._prepare_path(col_path):
            current_pos = next((x for x in current_pos.children if
                                AbstractCollection.prepare_label(x.label, case_insensitive) == col_label), None)
            if current_pos is None:
                raise ModuleNotFoundError("'{}' Collection Not Found".format('/'.join(col_path)))
        return current_pos

    def move(self, src: str | list[str], dest: str | list[str], case_insensitive: bool = False):
        prepared_src = self._prepare_path(src, case_insensitive)
        src_col = self.get_collection(prepared_src, case_insensitive)

        idx = next((i for (i, x) in enumerate(src_col._parent.children) if
                    AbstractCollection.prepare_label(x.label, case_insensitive) == prepared_src[-1]), None)
        dest_col = self.get_collection(dest, case_insensitive)

        src_col._parent.children.pop(idx)
        dest_col.children.append(src_col)
        self._update_relations()

    def delete(self, src: str | list[str]):
        prepared_src = self._prepare_path(src)
        src_col = self.get_collection(prepared_src)
        idx = next((i for (i, x) in enumerate(src_col._parent.children) if x.label == prepared_src[-1]), None)

        src_col._parent.children.pop(idx)
        src_col._parent = None
        self._deleted_ids.append(src_col.id)

    def add_collection(self, path_to_new: str | list[str]):
        prepared_src = self._prepare_path(path_to_new)
        src_col = self.get_collection(prepared_src[:-1])
        c = Collection()
        c.label = prepared_src[-1]
        src_col.children.append(c)
        self._update_relations()
        return c

    def to_json(self) -> dict:
        return {'collections': super().to_json()['children']}

    def _prepare_path(self, col_path: str | list[str], case_insensitive: bool = False) -> list[str]:
        if type(col_path) == str:
            if not col_path.startswith('/'): col_path = '/' + col_path
            col_path = [x for x in os.path.abspath(col_path).strip('/').split('/') if x != '']
            if case_insensitive:
                col_path = [x.lower() for x in col_path]

        return col_path
