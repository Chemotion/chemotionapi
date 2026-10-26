"""Collection objects: the hierarchy, navigation, element creation and sharing.

A *collection* is the unit Chemotion uses to organise elements (samples, reactions, well plates,
research plans and generic elements). This module provides the collection hierarchy
(:class:`AbstractCollection` and its editable/root subclasses), navigation by path, creation of new
elements, and sharing/syncing.
"""

import json
import os
import typing
import logging
from datetime import datetime
from urllib.parse import urlparse
from enum import Enum
from random import random
from typing import TypeVar, Self, Any
from collections.abc import Generator

logger = logging.getLogger(__name__)

from chemotion_api.elements import Wellplate, Sample, Reaction, GenericElement, ResearchPlan
from chemotion_api.user import Person, Group

from chemotion_api.elements.sample import MoleculeManager
from chemotion_api.connection import Connection

from chemotion_api.element_manager import ElementManager

from chemotion_api.utils import break_parent_cycles
from chemotion_api.elements import ElementSet, AbstractElement

TAbstractCollection = TypeVar("TAbstractCollection", bound="AbstractCollection")
TRootCollection = TypeVar("TRootCollection", bound="RootCollection")


def _col_path_join(path_part: str, *path_parts: str) -> str:
    """Join unix-style collection path segments, collapsing duplicate slashes (helper)."""
    # An absolute segment (starting with '/') resets the path to that segment onward.
    for i, x in enumerate(path_parts):
        if x.startswith('/'):
            if i == 0:
                return _col_path_join(x)
            return _col_path_join(x, *path_parts[-i:])
    joined = '/'.join([path_part, *path_parts])
    while '//' in joined:
        joined = joined.replace('//', '/')
    return joined


def _share_target_ids(users) -> list[int]:
    """Return the ids to share with, refusing anything that is neither a person nor a group.

    Filtering silently turned a mistake — passing a Device, say — into a share that quietly
    reached fewer people than asked for, or nobody at all.
    """
    ids, rejected = [], []
    for user in users:
        if user.is_group() or user.is_person():
            ids.append(user.id)
        else:
            rejected.append(f"{type(user).__name__}(id={getattr(user, 'id', '?')})")
    if rejected:
        raise ValueError(
            "share() takes people and groups; cannot share with " + ", ".join(rejected))
    if not ids:
        raise ValueError("share() needs at least one person or group to share with")
    return ids


def nest_by_ancestry(flat: list[dict]) -> list[dict]:
    """Rebuild a nested ``children`` tree from ELN v4's flat collection list.

    Up to ELN 3.x the server returned collections already nested. v4 returns a flat list where
    each entry carries an ``ancestry`` materialized path instead; this restores the nested shape
    the rest of this module (``_set_children`` / ``Collection.set_json``) expects.

    ``ancestry`` is a slash-delimited list of ancestor ids with leading and trailing slashes —
    ``'/'`` at the top level, ``'/9/'`` for a child of 9, ``'/9/12/'`` for its grandchild. (Not
    guesswork: the server's own migrations build it as ``'/' || c.id || '/'``.)

    Entries are attached to their **nearest ancestor present in** ``flat``, not strictly to their
    immediate parent, so a collection whose parent is filtered out (the 'All' collection) or simply
    not visible to this user still surfaces rather than vanishing. Anything with no visible ancestor
    becomes a top-level entry.

    :param flat: collection dicts as returned by ``GET /api/v1/collections/``.
    :return: top-level dicts, each with a ``children`` list (recursively).
    """
    nodes: dict[int, dict] = {}
    for col in flat:
        node = dict(col)
        node['children'] = []
        nodes[col['id']] = node

    # Sort by depth first so a parent is always processed before its descendants, then by the
    # server's own ordering, so sibling order is stable across reloads.
    def _sort_key(col: dict) -> tuple:
        ancestry = col.get('ancestry') or '/'
        depth = len([p for p in ancestry.split('/') if p])
        return depth, col.get('position') or 0, col['id']

    def _nearest_visible_ancestor(col: dict) -> int | None:
        for raw_id in reversed([p for p in (col.get('ancestry') or '').split('/') if p]):
            try:
                candidate = int(raw_id)
            except ValueError:
                continue
            if candidate in nodes and candidate != col['id']:
                return candidate
        return None

    parent_of = {col['id']: _nearest_visible_ancestor(col) for col in flat}

    # A cycle would give every entry a parent, leaving `roots` empty and the whole tree silently
    # gone — and `_update_relations`/`to_json` would then recurse forever over it. The server's
    # `ancestry` should never produce one, which is exactly why it must fail loudly if it does.
    cyclic = break_parent_cycles(parent_of)
    if cyclic:
        logger.warning(
            "Collection ancestry from the server forms a cycle involving %d collection(s); "
            "treating them as top-level so the tree is still usable: %s",
            len(cyclic), ", ".join(str(c) for c in sorted(cyclic)[:5]))

    roots: list[dict] = []
    for col in sorted(flat, key=_sort_key):
        node = nodes[col['id']]
        parent_id = None if col['id'] in cyclic else parent_of[col['id']]
        if parent_id is None:
            roots.append(node)
        else:
            nodes[parent_id]['children'].append(node)
    return roots


class CollectionSharePermission(Enum):
    """Permission granted when sharing a collection (see :meth:`Collection.share`).

    These are ELN v4's levels, mirroring ``CollectionShare::PERMISSION_LEVELS`` server-side. Each
    level includes the ones below it.

    .. warning::
       This replaces the pre-v4 ``SyncPermission``, and **the same integer now grants a different
       permission**. The ladder still runs 0-5; what changed is which capability sits on which
       rung. Share administration moved *up*, from 2 to 4, and adding/importing elements moved
       *down*, from 4 to 2:

       ===== ==================== ====================
       Level Pre-v4               v4
       ===== ==================== ====================
       0     ``Read``             :attr:`ReadElements`
       1     ``Write``            :attr:`EditElements`
       2     ``Share``            :attr:`AddElements`
       3     ``Delete``           :attr:`RemoveElements`
       4     ``ImportElements``   :attr:`ManageShares`
       5     ``PassOwnerShip``    :attr:`PassOwnership`
       ===== ==================== ====================

       So a hardcoded ``2`` that used to delegate share administration now merely lets the
       recipient add elements, and a hardcoded ``4`` that used to permit importing now hands over
       share administration. Port call sites by name, not by number.
    """

    ReadElements = 0
    EditElements = 1
    AddElements = 2
    RemoveElements = 3
    ManageShares = 4
    PassOwnership = 5


#: Every per-element-type detail level ELN v4 accepts on a collection share. Note the spellings:
#: ``researchplan`` and ``celllinesample`` are single words server-side, and the list grew from the
#: five types the pre-v4 API took.
SHARE_DETAIL_LEVEL_TYPES = (
    'celllinesample',
    'devicedescription',
    'element',
    'reaction',
    'researchplan',
    'sample',
    'screen',
    'sequencebasedmacromoleculesample',
    'wellplate',
)


class AbstractCollection:
    """Base class for all collection objects.

    Holds the shared tree state (children, parent, label, id) and the read-only behaviour:
    navigation by path, finding sub-collections, listing elements (samples, reactions, well plates,
    research plans, generics). Concrete subclasses add editing
    (:class:`AbstractEditableCollection`) and root behaviour (:class:`RootCollection`,
    :class:`RootSyncCollection`).
    """

    def __init__(self):
        #: True for a collection someone else shared with you (reached via
        #: :attr:`RootCollection.sync_root`). It marks the tree read-only — adding, moving and
        #: deleting raise — and nothing more. It must never influence which collection is
        #: *queried*: v4 has no `sync_collection_id`, and using one silently returned the
        #: caller's own elements instead of the shared collection's.
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
            return typing.cast(str, self.label).lower()
        return typing.cast(str, self.label)

    def __str__(self) -> str:
        return self.get_path()

    def __repr__(self) -> str:
        return f"Collection(id={self.id}, path={self.get_path()!r})"

    def __iter__(self) -> Generator[tuple[str, list[Self]]]:
        """
        Iterate over all children

        :return: Iterator
        """
        yield 'collections', self._children

    def move(self, dest: str | list[str], case_insensitive: bool = False):
        """Move this collection to ``dest`` (overridden by movable subclasses).

        :param dest: destination path as a unix-style string or a list of segments.
        :param case_insensitive: if True, path matching ignores case.
        :raises NotImplementedError: this collection type cannot be moved.
        """
        raise NotImplementedError('Cannot not move this Collection')

    def _set_children(self, new_children: list[dict]):
        """Reconcile the children list against server JSON, reusing existing child objects (helper)."""
        if new_children is None:
            self._children = []
            return
        ids = []
        for child in new_children:
            ids.append(child['id'])
            child_obj: Self | None = next((x for x in self._children if x.id == child['id']), None)
            if child_obj is None:
                self._children.append(typing.cast(Self, Collection(child)))
            else:
                typing.cast("Collection", child_obj).set_json(child)
        self._children = [child_obj for child_obj in self._children if child_obj.id in ids]
        self._update_relations()

    def _update_relations(self):
        """Re-link every descendant's parent and sync flag after the tree changes (helper)."""
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

    def find(self, label: str | None = None, **kwargs) -> list[AbstractCollection | Collection]:
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

    def walk(self, include_self: bool = False, max_depth: int | None = None) -> Generator[Self]:
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
        return '/'.join(typing.cast(list[str], abs_path))

    def get_root(self) -> RootCollection:
        """
        Get root Collection

        :return: Instance of the RootCollection
        """

        col = self
        while col._parent is not None:
            col = col._parent
        return typing.cast("RootCollection", col)

    def get_collection(self, col_path: str | list[str], case_insensitive: bool = False) -> AbstractCollection:
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
                                 case_insensitive: bool = False) -> AbstractCollection:
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

    #: Element kinds this client will send to `collection_elements`. v4 declares
    #: sample/reaction/wellplate/screen/research_plan in `main_ui_state_params`, and the usecase
    #: resolves more besides — but a kind we have not exercised is untested, not supported.
    _COLLECTION_ELEMENT_KINDS = ('sample', 'reaction', 'research_plan')

    def assign_elements(self, dest: AbstractCollection, *elements) -> None:
        """Add elements of this collection to ``dest`` as well — they stay here too.

        ``POST /api/v1/collection_elements``. The element itself is not copied; only its
        membership is added, which is why an element can sit in several collections at once.

        :param dest: the collection to add them to.
        :param elements: saved elements of this collection.
        :raises ValueError: for an unsaved element, a collection that cannot hold elements, or an
            element kind this client does not send (see :attr:`_COLLECTION_ELEMENT_KINDS`).
        :raises PermissionError: if you may not add elements to ``dest`` (403).
        """
        self._send_collection_elements('post', elements, dest=dest)

    def remove_elements(self, *elements) -> list[int]:
        """Remove elements from this collection. They are **not** deleted — they remain in 'All'.

        ``DELETE /api/v1/collection_elements/:collection_id``.

        :return: the ids of samples the server **refused** to remove, empty when everything went.
            A sample belonging to a reaction or wellplate still in this collection cannot be
            removed on its own; v4 answers **200** with ``{"locked_sample_ids": [...]}`` instead
            of 204. That is a 2xx which is *not* success, so it is returned rather than
            swallowed — a caller that assumed 2xx meant done would report a removal that did not
            happen.
        """
        return self._send_collection_elements('delete', elements)

    def move_elements(self, dest: AbstractCollection, *elements) -> list[int]:
        """Move elements from this collection into ``dest``.

        .. warning::
           **Not atomic.** v4 has no move endpoint: this adds to ``dest`` and then removes from
           here, as two requests. If the removal fails or is refused, the elements are left in
           **both** collections — which is a valid state, not corruption, but it is not what was
           asked for. The refused ids are returned so the caller can tell.

        :return: the ids of samples that could not be removed from this collection, and therefore
            still sit in both. Empty when the move completed.
        """
        self._send_collection_elements('post', elements, dest=dest)
        try:
            locked = self._send_collection_elements('delete', elements)
        except Exception as e:
            # The addition already went through. Letting the removal's error propagate untouched
            # would tell the caller "move failed" while the elements sit in *both* collections —
            # the one outcome they cannot infer from the exception they were handed.
            raise type(e)(
                f"{e} — note the elements were already added to {dest.label!r}; they are now in "
                f"both collections. Retry the removal from {self.label!r} rather than the move."
            ) from e
        if locked:
            logger.warning(
                "move_elements: %d sample(s) were added to %r but could not be removed from %r, "
                "so they are now in both: %s", len(locked), dest.label, self.label, locked)
        return locked

    def _send_collection_elements(self, method: str, elements, dest=None) -> list[int]:
        """Build and send one `collection_elements` request. Returns any locked sample ids."""
        if self.id is None:
            raise ValueError(f'Collection "{self.label}" cannot hold elements')

        ui_state: dict[str, Any] = {'currentCollection': {'id': self.id}}
        for element in elements:
            if getattr(element, 'is_new', False) or element.id is None:
                raise ValueError('The element has not been saved yet. Save it first.')
            kind = element.element_type
            if kind not in self._COLLECTION_ELEMENT_KINDS:
                raise ValueError(
                    f"Moving {kind} elements between collections is not implemented. The server "
                    f"may well accept it — this client only sends kinds it has exercised "
                    f"({', '.join(self._COLLECTION_ELEMENT_KINDS)}); see AI/DEFERRED.md.")
            # `checkedAll` is deliberately never sent: the server reduces it to
            # `where.not(id: unchecked_ids)` over the *whole* element class, not this collection,
            # so one request could attach a user's entire sample library.
            ui_state.setdefault(kind, {'checkedAll': False, 'checkedIds': []})
            ui_state[kind]['checkedIds'].append(element.id)
        if len(ui_state) == 1:
            raise ValueError('No elements given.')

        session = self.get_root()._session
        if method == 'post':
            if dest is None or dest.id is None:
                raise ValueError('A destination collection with an id is required')
            res = session.post('/api/v1/collection_elements',
                               data={'collection_id': dest.id, 'ui_state': ui_state})
        else:
            # DELETE carries a body, which this session does not send as JSON by default.
            res = session.delete(f'/api/v1/collection_elements/{self.id}',
                                 data=json.dumps({'ui_state': ui_state}),
                                 headers=session.get_json_session_header())

        if res.status_code == 403:
            raise PermissionError(
                f'You may not change the elements of this collection: {res.text}')
        if res.status_code == 404:
            raise ValueError('Collection not found')
        if res.status_code not in (200, 201, 204):
            raise ConnectionError(f'{res.status_code} -> {res.text}')
        if res.status_code == 200 and res.content:
            try:
                return list((res.json() or {}).get('locked_sample_ids') or [])
            except ValueError:
                return []
        return []

    def get_elements_of_iri(self, element_type: str, per_page: int | None = 10, updated_to_date: datetime | None = None,
                      updated_from_date: datetime | None = None) -> ElementSet:
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
            e = ElementSet(root._session,
                           typing.cast(dict, root._element_manager.all_classes.get(o.path.split('/')[1])),
                           typing.cast(int, self.id))
            e.load_elements(per_page, updated_to_date, updated_from_date)
            e.set_iri_filter(element_type)
            return e
        raise ValueError(f'Could not find a element with the IRI: "{element_type}"')

    def get_samples(self, per_page: int | None = 10, updated_to_date: datetime | None = None,
                      updated_from_date: datetime | None = None, product_only: bool = False) -> ElementSet:
        """
        List of all samples.

        The server does not list samples that are only used as reactants or solvents of a reaction.
        Use ``reaction.reactants``, ``reaction.solvents`` etc. to access them.

        :param per_page: How many Elements per page (the server allows at most 100)
        :param updated_to_date: Set date time to fetch only elements which are updated before 'updated_to_date'
        :param updated_from_date: Set date time to fetch only elements which are updated after 'updated_from_date'
        :param product_only: If True only samples which are products in a reaction are returned

        :return: ElementSet of samples
        """

        root = self.get_root()
        e = ElementSet(root._session, typing.cast(dict, root._element_manager.all_classes.get('sample')),
                       typing.cast(int, self.id))
        e.load_elements(per_page, updated_to_date, updated_from_date, product_only)
        return e

    def get_reactions(self, per_page: int | None = 10, updated_to_date: datetime | None = None,
                      updated_from_date: datetime | None = None) -> ElementSet:
        """
        List of all reactions.

        :param per_page: How many Elements per page
        :param updated_to_date: Set date time to fetch only elements which are updated before 'updated_to_date'
        :param updated_from_date: Set date time to fetch only elements which are updated after 'updated_from_date'

        :return: ElementSet of reactions
        """

        root = self.get_root()
        e = ElementSet(root._session, typing.cast(dict, root._element_manager.all_classes.get('reaction')),
                       typing.cast(int, self.id))
        e.load_elements(per_page, updated_to_date, updated_from_date)
        return e

    def get_research_plans(self, per_page: int | None = 10, updated_to_date: datetime | None = None,
                      updated_from_date: datetime | None = None) -> ElementSet:
        """
        List of all research plans.

        :param per_page: How many Elements per page
        :param updated_to_date: Set date time to fetch only elements which are updated before 'updated_to_date'
        :param updated_from_date: Set date time to fetch only elements which are updated after 'updated_from_date'

        :return: ElementSet of research plans
        """

        root = self.get_root()
        e = ElementSet(root._session, typing.cast(dict, root._element_manager.all_classes.get('research_plan')),
                       typing.cast(int, self.id))
        e.load_elements(per_page, updated_to_date, updated_from_date)
        return e

    def get_wellplates(self, per_page: int | None = 10, updated_to_date: datetime | None = None,
                      updated_from_date: datetime | None = None) -> ElementSet:
        """
        List of all well plates.

        :param per_page: How many Elements per page
        :param updated_to_date: Set date time to fetch only elements which are updated before 'updated_to_date'
        :param updated_from_date: Set date time to fetch only elements which are updated after 'updated_from_date'

        :return: ElementSet of well plates
        """

        root = self.get_root()
        e = ElementSet(root._session, typing.cast(dict, root._element_manager.all_classes.get('wellplate')),
                       typing.cast(int, self.id))
        e.load_elements(per_page, updated_to_date, updated_from_date)
        return e

    def get_generics_by_name(self, name: str, per_page: int | None = 10, updated_to_date: datetime | None = None,
                      updated_from_date: datetime | None = None) -> ElementSet:
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

        e = ElementSet(root._session, elem, typing.cast(int, self.id))
        e.load_elements(per_page, updated_to_date, updated_from_date)
        return e

    def get_generics_by_label(self, label: str, per_page: int | None = 10, updated_to_date: datetime | None = None,
                      updated_from_date: datetime | None = None) -> ElementSet:
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
    """A collection into which new elements (samples, reactions, well plates, ...) can be created."""

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
        sample = typing.cast(Sample, self._create_new_element('sample'))
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
        e = ElementSet(root._session, typing.cast(dict, root._element_manager.all_classes.get('sample')),
                       typing.cast(int, self.id))
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

        element_manager: ElementManager = self.get_root()._element_manager
        for reload in (False, True):
            if reload:
                # The type may have been created, released or activated after the types were loaded
                element_manager.reload()
            for (elem_name, elem) in element_manager.all_classes.items():
                if elem['label'] == label:
                    return typing.cast(GenericElement, self._create_new_element(elem_name))
        raise ValueError(f'Could not find a generic element with the label: "{label}". Only released and '
                         f'active templates are available')

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
        """Build and return a new (unsaved) element of ``type_name`` in this collection (helper)."""
        root = self.get_root()
        if type_name not in root._element_manager.all_classes:
            root._element_manager.reload()
        new_json = root._element_manager.build_new(type_name, self.id)

        e = ElementSet(root._session, typing.cast(dict, root._element_manager.all_classes.get(type_name)),
                       typing.cast(int, self.id))
        return e.new_element(new_json)


class Collection(AbstractEditableCollection):
    """
    The collection object represents the standard collection owned by the current user.
    Changes to the collection tree (add, move, delete) are only sent to the server when
    :meth:`chemotion_api.collection.RootCollection.save` is called.
    """

    def __init__(self, collection_json: dict | None = None):
        super().__init__()
        # `set_json` assigns a server field only `if hasattr(self, key)`, so an attribute that is
        # not declared here silently discards data the server did send. These are the fields
        # `OwnCollectionEntity` and `SharedCollectionEntity` actually expose in v4.
        self.is_locked: bool | None = None
        self.ancestry: str | None = None
        self.position: int | None = None
        self.tabs_segment: dict | None = None
        self.inventory_id: int | None = None
        self.inventory_name: str | None = None
        self.inventory_prefix: str | None = None
        #: True when the collection has at least one share. Sent on your own collections; the
        #: server keeps it in step with the share table, so reading it costs no extra request
        #: (unlike :meth:`get_shares`, which also needs admin rights on the collection).
        self.shared: bool | None = None
        #: Set only on collections shared *with* you (SharedCollectionEntity).
        self.permission_level: int | None = None
        self.owner: str | None = None
        self.owner_name: str | None = None
        self.collection_share_id: int | None = None
        self.shared_via_group: bool | None = None
        # Removed: is_shared, is_synchronized, the five *_detail_level attributes and
        # sync_collections_users. Nothing ever assigned them — v4 has no sync_collections_users
        # table at all — so they read as None on every collection whether shared or not, which is
        # worse than absent. `shared` above is the real flag; `get_shares()` has the detail.
        self.set_json(collection_json)

    collection_json: dict | None = None

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
        """Return the default JSON payload for a brand-new, unsaved collection (helper)."""
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
        dest = _col_path_join(os.path.dirname(abs_path), typing.cast(str, dest))
        self.get_root().move(abs_path, dest, case_insensitive)

    def delete(self):
        """
        Deletes this collection. The deletion is not saved.
        """
        abs_path = self.get_path()
        self.get_root().delete(abs_path)

    def add_collection(self, name: str):  # type: ignore[override]
        """
        Creates a new child collection. The collection is not saved.
        Please reload the collection after saving it.

        :param name: new collection`s name

        :return: new Collection (not saved)
        """
        abs_path = _col_path_join(self.get_path(), name)
        return self.get_root().add_collection(abs_path)

    def share(self, permission_level: CollectionSharePermission, *users: Person | Group,
              detail_level: int, apply_to_subcollections: bool = False):
        """
        Shares this collection with a set of users or groups.

        :param permission_level: element of :class:`CollectionSharePermission`
        :param users: the users and/or groups to share with
        :param detail_level: how much of each element type the recipients may see (0-10), applied
            to all nine types. **Required** — there is no default, because the only defensible one
            would be ``10``, which discloses every field of every element and unlocks
            ``POST /collections/export`` for the recipient. Disclosure is the caller's decision to
            make explicitly. (The web client's share dialog does default to 10.)
        :param apply_to_subcollections: also share every descendant collection

        :raises ConnectionError: if the server rejects the share
        :raises ValueError: if ``detail_level`` is outside 0-10

        .. note::
           **This sends mail.** ELN v4.0.0 added a ``CollectionShareNotifier``, so every recipient
           is notified that you shared a collection with them. Earlier servers shared silently.
        """
        if not isinstance(detail_level, int) or isinstance(detail_level, bool) \
                or not 0 <= detail_level <= 10:
            raise ValueError(
                f"detail_level must be an integer from 0 (least disclosure) to 10 (every field, "
                f"and the recipient may export the collection); got {detail_level!r}")
        # ELN v4 replaced POST /syncCollections (a nested payload keyed on
        # `collection_attributes`, with user_ids as {label, name, value} objects) with
        # POST /collection_shares, which takes a flat body and plain integer user ids.
        data: dict[str, Any] = {
            'collection_id': self.id,
            'user_ids': _share_target_ids(users),
            'permission_level': permission_level.value,
            'apply_to_subcollections': apply_to_subcollections,
        }
        for element_type in SHARE_DETAIL_LEVEL_TYPES:
            data[f'{element_type}_detail_level'] = detail_level

        res = self.get_root()._session.post('/api/v1/collection_shares', data=data)
        if res.status_code not in (200, 201):
            raise ConnectionError(f"{res.status_code} -> {res.text}")

    def update_share(self, share_id: int,
                     permission_level: CollectionSharePermission | None = None,
                     detail_level: int | None = None,
                     apply_to_subcollections: bool = False,
                     include_new_subcollections: bool = False) -> dict:
        """Change an existing share (``PUT /api/v1/collection_shares/:id``).

        ``share()`` creates (and updates) shares in bulk; this edits one share that
        :meth:`get_shares` returned, and is the **only** route that accepts
        ``include_new_subcollections``.

        :param share_id: the ``id`` of a share from :meth:`get_shares`.
        :param permission_level: the new permission level, or ``None`` to leave it.
        :param detail_level: the new disclosure level (0-10) applied to all nine element types, or
            ``None`` to leave them. Omitted fields are genuinely left alone — the server declares
            params with ``include_missing: false``, so a field we do not send is not reset.
        :param apply_to_subcollections: cascade this edit to descendant collections that are
            **already shared** with this share's recipient.
        :param include_new_subcollections: widen the cascade to descendants **not yet shared**
            with them. This *grants access that did not exist before*, so it is off by default and
            has to be asked for: the plain cascade can only change the level of an existing share,
            while this one mints new ones. Only meaningful together with
            ``apply_to_subcollections``.

        :raises ValueError: if ``detail_level`` is out of range, or the server refuses the change.
        :raises PermissionError: if you may not administrate this share.
        :raises ConnectionError: on any other failure.
        """
        if detail_level is not None and (not isinstance(detail_level, int)
                                         or isinstance(detail_level, bool)
                                         or not 0 <= detail_level <= 10):
            raise ValueError(
                f"detail_level must be an integer from 0 (least disclosure) to 10 (every field, "
                f"and the recipient may export the collection); got {detail_level!r}")
        if include_new_subcollections and not apply_to_subcollections:
            # The server would silently ignore it, which is the kind of quiet no-op that makes a
            # caller believe access was widened when it was not.
            raise ValueError(
                "include_new_subcollections only applies while cascading; pass "
                "apply_to_subcollections=True as well, or drop it.")

        data: dict[str, Any] = {
            'id': share_id,
            'apply_to_subcollections': apply_to_subcollections,
            'include_new_subcollections': include_new_subcollections,
        }
        if permission_level is not None:
            data['permission_level'] = permission_level.value
        if detail_level is not None:
            for element_type in SHARE_DETAIL_LEVEL_TYPES:
                data[f'{element_type}_detail_level'] = detail_level
        if include_new_subcollections:
            logger.info(
                "update_share: cascading share %s into sub-collections that were NOT previously "
                "shared with this recipient — this grants new access.", share_id)

        res = self.get_root()._session.put(f'/api/v1/collection_shares/{share_id}', data=data)
        if res.status_code == 401:
            raise PermissionError(f'You may not administrate collection share {share_id}.')
        if res.status_code == 404:
            raise ValueError(f'Collection share {share_id} does not exist.')
        if res.status_code == 422:
            raise ValueError(f'The server refused the share change: {res.text}')
        if res.status_code not in (200, 201):
            raise ConnectionError(f"{res.status_code} -> {res.text}")
        return res.json() if res.content else {}

    def get_shares(self) -> list[dict]:
        """Return this collection's shares, as the server reports them.

        Each entry carries the share's ``id``, ``shared_with``/``shared_with_id``/
        ``shared_with_type``, its ``permission_level`` and the nine ``*_detail_level`` values.
        Only a user who administrates the collection may list them.

        :raises ConnectionError: if the server rejects the request
        """
        res = self.get_root()._session.get('/api/v1/collection_shares',
                                           params={'collection_id': self.id})
        if res.status_code != 200:
            raise ConnectionError(f"{res.status_code} -> {res.text}")
        return res.json().get('collection_shares', [])

    def unshare(self, *users: Person | Group, all: bool = False) -> int:
        """Revoke this collection's shares — the counterpart to :meth:`share`.

        :param users: the users and/or groups to revoke.
        :param all: revoke **every** share on this collection. Required when no users are given.
        :return: how many shares were removed.

        :raises ValueError: if called with no users and without ``all=True``.

        :raises ConnectionError: if listing or deleting fails.

        The v4 endpoint deletes by *share* id rather than by collection and user, so the shares are
        listed first and matched on ``shared_with_id``. A share that is already gone (404) counts
        as revoked.
        """
        if not users and not all:
            # `col.unshare(*to_remove)` with an empty list is an ordinary result of filtering, and
            # used to mean "revoke everything". `share()` already refuses an empty target list;
            # the destructive inverse should be at least as hard to trigger by accident.
            raise ValueError(
                'unshare() with no users does nothing by default. Pass the users to revoke, or '
                'unshare(all=True) to revoke every share on this collection.')
        if users and all:
            raise ValueError('Pass either users or all=True, not both.')
        wanted = {user.id for user in users}
        session = self.get_root()._session
        removed = 0
        for share in self.get_shares():
            if wanted and share.get('shared_with_id') not in wanted:
                continue
            res = session.delete(f"/api/v1/collection_shares/{share['id']}")
            if res.status_code not in (200, 204, 404):
                raise ConnectionError(f"{res.status_code} -> {res.text}")
            removed += 1
        return removed


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
        """
        Generates a dict containing all list of all children collection

        :return: list of children as savable JSON
        """
        as_dict = dict(self)
        return super().to_json() | as_dict

    def move(self, *args, **kwargs):
        """Synced collections cannot be moved.

        :raises Exception: always, because a synced collection cannot be moved.
        """
        raise Exception("You cannot move a synced collection collection!")

    def delete(self, *args, **kwargs):
        """Synced collections cannot be deleted.

        :raises Exception: always, because a synced collection cannot be deleted.
        """
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
        self._collections_payload: dict | None = None
        self._element_manager: ElementManager
        self._session = session
        self.label = 'root'
        self._deleted_ids: list = []
        self._id = None

    @property
    def id(self) -> int:
        """
        The 'All' collection ID

        :return: The ID of the 'All' collection
        """

        if self._id is None:
            self.load_collection()
        return typing.cast(int, self._id)

    @id.setter
    def id(self, id: int) -> None:
        """
        The 'All' collection ID
        """
        self._id = id

    @property
    def sync_root(self) -> RootSyncCollection:
        """
        The RootSyncCollection collection can be used to access all collection synced with you.

        :return: instance of RootSyncCollection
        """

        if self._sync_root is None:
            self.load_sync_collection()
        return typing.cast(RootSyncCollection, self._sync_root)

    @property
    def all(self) -> dict[str,dict]:
        """
        Returns all information of the 'All' collections

        :return: information of the 'All' collection
        """

        if self._all is None:
            self.load_collection()
        return typing.cast(dict[str, dict], self._all)

    def set_element_manager(self, element_manager: ElementManager):
        """
        Set the ElementManager class

        :param element_manager: instance of ElementManager
        """

        self._element_manager = element_manager

    def _fetch_collections(self) -> dict:
        """Fetch the v4 collection listing: ``{'own': [...], 'shared_with_me': [...]}``.

        ELN v4 replaced ``/collections/roots.json`` (a ready-made nested tree of owned
        collections) with this flat, two-part listing. The old path is not merely missing — v4
        routes it to ``/collections/:id``, whose id pattern (``All|all|\\d+``) rejects
        ``"roots.json"``, so it answers **400 'id is invalid'** rather than 404.

        The response is cached on the instance so ``load_collection`` and
        ``load_sync_collection`` share one request.
        """
        res = self._session.get('/api/v1/collections/')
        if res.status_code != 200:
            raise ConnectionError(f'{res.status_code} -> {res.text}')
        self._collections_payload = json.loads(res.content)
        return self._collections_payload

    def load_collection(self) -> dict[str,dict]:
        """
        Loads the collection tree from the server. Unsaved changes are lost.

        :return: information of the 'All' collection
        """

        collections = self._fetch_collections()
        self._all = self._load_all_collection().get('collection')
        if self._all is None:
            # Seen on a real 3.1.2 server with an Admin account that owns nothing: the endpoint
            # answers 200 with `{"collection": null}`. Subscripting that gave
            # "TypeError: 'NoneType' object is not subscriptable" from inside get_root_collection(),
            # which says nothing about the cause.
            raise ValueError(
                "This account has no 'All' collection, so its collection tree cannot be loaded. "
                "That normally means the account has never owned or been shared an element.")
        self._id = self._all['id']
        # 'All' is exposed as the root collection itself (its id is this object's id), so it must
        # not also appear as one of its own children — the pre-v4 tree endpoint likewise excluded it.
        owned = [col for col in (collections.get('own') or []) if col.get('id') != self._id]
        self._set_children(nest_by_ancestry(owned))
        return self._all

    def load_sync_collection(self) -> RootSyncCollection:
        """
        Loads the RootSyncCollection. The RootSyncCollection collection can be used to access all collection synced with you.

        :return: instance of RootSyncCollection
        """

        # ELN v4 deleted the whole /syncCollections namespace (that path is a genuine 404 now).
        # Collections other people share with you arrive in the `shared_with_me` half of the same
        # listing that load_collection() reads, so reuse that response instead of a second request.
        payload = self._collections_payload or self._fetch_collections()
        self._sync_root = RootSyncCollection(self._session, self._element_manager)
        self._sync_root._set_children(nest_by_ancestry(payload.get('shared_with_me') or []))
        return self._sync_root

    @staticmethod
    def _is_unsaved(col: AbstractCollection) -> bool:
        """True for a collection created locally that the server has never seen.

        :meth:`Collection._get_new_json` marks these with ``isNew`` and a placeholder float id.
        """
        json_data = getattr(col, 'collection_json', None) or {}
        return bool(json_data.get('isNew')) or not isinstance(col.id, int)

    def _create_unsaved(self, node: AbstractCollection, parent_id: int | None) -> None:
        """Depth-first: create every locally-added collection under ``node``, parents first.

        Children are created only after their parent has a real server id, since v4 takes the
        parent by id rather than accepting a whole tree.
        """
        for child in node.children:
            if self._is_unsaved(child):
                # parent_id is `requires ... allow_blank: true` server-side; '' means top level.
                payload = {'parent_id': '' if parent_id is None else parent_id,
                           'label': child.label}
                res = self._session.post('/api/v1/collections/', data=payload)
                if res.status_code not in (200, 201):
                    raise ConnectionError(f'{res.status_code} -> {res.text}')
                created = json.loads(res.content)['collection']
                child.id = created['id']
                if isinstance(getattr(child, 'collection_json', None), dict):
                    child.collection_json.pop('isNew', None)
            self._create_unsaved(child, child.id)

    def _bulk_update_tree(self, node: AbstractCollection) -> list[dict]:
        """Build the ``{id, label, children}`` tree that v4's bulk tree update expects.

        Locked collections ('All', 'chemotion-repository.net') are skipped along with their
        subtrees: the server answers 403 for any attempt to modify one.
        """
        out: list[dict] = []
        for child in node.children:
            if self._is_unsaved(child) or getattr(child, 'is_locked', False):
                continue
            out.append({'id': child.id,
                        'label': child.label,
                        'children': self._bulk_update_tree(child)})
        return out

    def save(self):
        """
        Saves ALL updates done to owned (not synced) collections and reloads the collection tree.
        """

        # ELN v4 split the old single `PATCH /api/v1/collections` (whole tree + deleted_ids, which
        # now answers 405) into three separate operations, applied here in an order that keeps the
        # server consistent: remove first, then create, then re-describe what remains.
        # Each id is dropped from the queue as it is dealt with, not all of them after the loop.
        # Clearing at the end meant one failure left the earlier ids queued, so every later save()
        # re-deleted them, got 404 for something already gone, raised — and never reached the
        # create/bulk-update steps below. The object stayed permanently unusable.
        for collection_id in list(self._deleted_ids):
            res = self._session.delete(f'/api/v1/collections/{collection_id}')
            if res.status_code in (200, 204, 404):
                # 404 means the server no longer has it, which is what we wanted. Verified against
                # a live v4 instance: a missing id answers 404, and so does a non-integer id.
                self._deleted_ids.remove(collection_id)
                continue
            raise ConnectionError(f'{res.status_code} -> {res.text}')

        self._create_unsaved(self, None)

        tree = self._bulk_update_tree(self)
        if tree:
            res = self._session.put('/api/v1/collections/bulk_update_own_collections',
                                    data={'collections': tree})
            if res.status_code != 200:
                raise ConnectionError(f'{res.status_code} -> {res.text}')

        self.load_collection()

    def get_collection(self, col_path: str | list[str], case_insensitive: bool = False) -> AbstractCollection:
        """
        Gets a collection a path points to.

        :param col_path: is either a string based on a unix path or a list
        :param case_insensitive: If true, the path is matched ignoring upper and lower case

        :return: Collection the path points to
        """

        col_path = self._prepare_path(col_path)
        current_pos: AbstractCollection = self
        # case_insensitive must reach _prepare_path as well: prepare_label() lowercases the
        # candidate, so the path segments have to be lowercased to match it.
        for col_label in self._prepare_path(col_path, case_insensitive):
            current_pos = typing.cast(AbstractCollection, next((x for x in current_pos.children if
                                x.prepare_label(case_insensitive) == col_label), None))
            if current_pos is None:
                raise ModuleNotFoundError("'{}' Collection Not Found".format('/'.join(col_path)))
        return current_pos

    def move(self, src: str | list[str], dest: str | list[str], case_insensitive: bool = False):  # type: ignore[override]
        """
        Moves a collection from a src path into the collection at the dest path. The move is not saved.

        :param src: is either a string based on a unix path or a list
        :param dest: is either a string based on a unix path or a list
        :param case_insensitive: If true, the path is matched ignoring upper and lower case
        """

        prepared_src = self._prepare_path(src, case_insensitive)
        src_col = self.get_collection(prepared_src, case_insensitive)

        idx = next((i for (i, x) in enumerate(typing.cast(AbstractCollection, src_col._parent).children) if
                    x.prepare_label(case_insensitive) == prepared_src[-1]), None)
        dest_col = self.get_collection(dest, case_insensitive)

        typing.cast(AbstractCollection, src_col._parent).children.pop(typing.cast(int, idx))
        dest_col.children.append(src_col)
        self._update_relations()

    def delete(self, src: str | list[str], case_insensitive: bool = False):
        """
        Deletes a collection at the src path. The deletion is not saved.

        :param src: is either a string based on a unix path or a list
        :param case_insensitive: If true, the path is matched ignoring upper and lower case
        """

        prepared_src = self._prepare_path(src, case_insensitive)
        # The flag has to reach the lookup too: _prepare_path lowercases the path, so a
        # case-sensitive get_collection could never match it and the delete failed before it
        # began.
        src_col = self.get_collection(prepared_src, case_insensitive)
        parent = typing.cast(AbstractCollection, src_col._parent)
        # Compare the way the lookup did. Matching `x.label` raw against an already-lowercased
        # path meant case_insensitive=True found nothing, so `idx` was None and pop(None) raised
        # TypeError instead of deleting anything.
        idx = next((i for (i, x) in enumerate(parent.children)
                    if x.prepare_label(case_insensitive) == prepared_src[-1]), None)
        if idx is None:
            raise ModuleNotFoundError(f"'{'/'.join(prepared_src)}' Collection Not Found")

        parent.children.pop(idx)
        src_col._parent = None
        # Only queue a server-side delete for something the server actually has. An unsaved
        # collection's id is a random() float, and DELETE /collections/0.81… answers 404 — which
        # used to poison the queue for every later save().
        if self._is_unsaved(src_col):
            logger.debug("Dropped unsaved collection %r locally; nothing to delete server-side.",
                         src_col.label)
        else:
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
        """Normalise a string/list path into a list of segments, optionally lower-cased (helper)."""
        if type(col_path) == str:
            if not col_path.startswith('/'): col_path = '/' + col_path
            col_path = [x for x in col_path.strip('/').split('/') if x != '']
        if case_insensitive:
            col_path = [x.lower() for x in col_path]

        return typing.cast(list[str], col_path)

    def _load_all_collection(self):
        """Fetch the server's 'All' collection JSON (helper)."""
        collection_url = '/api/v1/collections/all'

        res = self._session.get(collection_url)

        if res.status_code != 200:
            raise ConnectionError(f'{res.status_code} -> {res.text}')
        return json.loads(res.content)
