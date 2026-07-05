"""Collection objects and the offline-capable ``.eln`` (RO-Crate) exporter.

A *collection* is the unit Chemotion uses to organise elements (samples, reactions, well plates,
research plans and generic elements). This module provides the collection hierarchy
(:class:`AbstractCollection` and its editable/root subclasses), navigation by path, creation of new
elements, sharing/syncing, and :meth:`AbstractCollection.export_eln` which serialises a collection
and all its elements/attachments into a `TheELNFileFormat <https://github.com/TheELNConsortium/TheELNFileFormat>`_
RO-Crate ZIP using chem-dcat-ap. The export is offline-friendly: vendored schemas/contexts are used
where available so it does not depend on remote schema fetches.
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
from collections.abc import Generator, Callable

logger = logging.getLogger(__name__)

from chemotion_api.elements import Wellplate, Sample, Reaction, GenericElement, ResearchPlan
from chemotion_api.user import Person, Group

from chemotion_api.elements.sample import MoleculeManager
from chemotion_api.connection import Connection

from chemotion_api.element_manager import ElementManager
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


_SCHEMAVIEW_CACHE: dict[tuple, object] = {}


def _get_export_schemaview(schema_path: Any, importmap: dict[str, str]):
    """Build (once) and cache the merged chem-dcat-ap SchemaView used for RDF export.
    Parsing + merging the schema is expensive; it is constant per process, so reuse it across
    export_eln calls. Keyed by schema path + importmap so a different config gets its own entry."""
    key = (str(schema_path), tuple(sorted(importmap.items())))
    sv = _SCHEMAVIEW_CACHE.get(key)
    if sv is None:
        from linkml_runtime.utils.schemaview import SchemaView
        sv = SchemaView(str(schema_path), merge_imports=True, importmap=importmap)
        _SCHEMAVIEW_CACHE[key] = sv
    return sv


def _make_progress_bar(total: int, desc: str, unit: str):
    """Best-effort tqdm progress bar; returns None if tqdm is unavailable.

    Uses ``tqdm.auto`` (widget in Jupyter/IPython, text bar in a terminal). tqdm.auto emits a
    TqdmWarning ("IProgress not found …") in kernels whose ipywidgets isn't a working widget
    frontend; that warning is silenced so tqdm falls back to a text bar, which renders everywhere.
    """
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from tqdm.auto import tqdm
            return tqdm(total=total, desc=desc, unit=unit)
    except Exception as e:
        logger.debug("interactive progress bar unavailable (%s); continuing without it", e)
        return None


def _write_crate_zip(file_path: str, root_folder: str, metadata_dict: dict, elem_files: dict,
                     elem_paths: dict, sanitize_filename: Callable[[str], str],
                     skipped: list[dict],
                     progress: Callable[[str], None] | None = None) -> None:
    """Write the RO-Crate ZIP: ro-crate-metadata.json + each element's attachment files.
    Attachment download failures are logged and recorded in ``skipped`` (not fatal).
    ``progress`` (if given) is called with the filename after each attachment is written."""
    import json, os, zipfile

    def _json_default(o):
        # PropertyDict/UnitDict and similar wrappers expose .to_dict(); fall back to str.
        # Only trust a to_dict() that yields JSON-native data — otherwise json would call this
        # handler again on the result, and an object whose to_dict() returns another such object
        # (e.g. a unittest.mock.Mock) would recurse forever and exhaust memory. Guard against that.
        if hasattr(o, "to_dict"):
            d = o.to_dict()
            if d is None or isinstance(d, (dict, list, str, int, float, bool)):
                return d
        return str(o)

    with zipfile.ZipFile(file_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        metadata_json = json.dumps(metadata_dict, indent=2, ensure_ascii=False, default=_json_default)
        zip_file.writestr(f"{root_folder}/ro-crate-metadata.json", metadata_json)

        for elem_id, files in elem_files.items():
            rel_path = elem_paths[elem_id]
            for att in files:
                orig_filename = att['filename']
                name_part, ext_part = os.path.splitext(os.path.basename(orig_filename))
                safe_filename = sanitize_filename(name_part) + ext_part
                zip_entry_path = f"{root_folder}/{rel_path.lstrip('./')}{safe_filename}"
                try:
                    if hasattr(att, "iter_file"):
                        # Stream the download chunk-by-chunk straight into the zip entry so large
                        # attachments never sit fully in memory. force_zip64 allows >2 GiB entries.
                        with zip_file.open(zip_entry_path, "w", force_zip64=True) as dest:
                            for chunk in att.iter_file():
                                dest.write(chunk)
                    else:  # fallback for objects exposing only load_file()
                        zip_file.writestr(zip_entry_path, att.load_file())
                except Exception as e:
                    logger.warning("Failed to download attachment %s: %s", orig_filename, e)
                    skipped.append({"kind": "attachment", "stage": "download",
                                    "filename": orig_filename, "error": str(e)})
                if progress is not None:
                    progress(orig_filename)


def _build_author_nodes(metadata_dict: dict, graph_nodes: dict,
                        authors: list) -> tuple[list[dict], dict | None]:
    """Add Person (ORCID-identified) and Organization (ROR-identified) contextual entities for the
    manually-provided authors. Returns ``(author_refs, publisher_ref)`` where author_refs is a list
    of ``{"@id": <orcid url>}`` dicts and publisher_ref is the first organization (or None). Authors
    are pre-validated by ``chemotion_api.authors.validate_authors``."""
    author_refs: list[dict] = []
    publisher_ref: dict | None = None

    for author in authors:
        person_id = author.orcid_url
        person_node = {
            "@id": person_id,
            "@type": "Person",
            "name": author.name,
            "identifier": author.orcid_url,
        }
        if author.email:
            person_node["email"] = author.email

        org_refs = []
        for aff in author.affiliations:
            org_id = aff.ror_url
            if org_id not in graph_nodes:
                org_node = {
                    "@id": org_id,
                    "@type": "Organization",
                    "name": aff.name,
                    "identifier": aff.ror_url,
                }
                metadata_dict["@graph"].append(org_node)
                graph_nodes[org_id] = org_node
            org_refs.append({"@id": org_id})
            if publisher_ref is None:
                publisher_ref = {"@id": org_id}

        if org_refs:
            person_node["affiliation"] = org_refs if len(org_refs) > 1 else org_refs[0]

        if person_id not in graph_nodes:
            metadata_dict["@graph"].append(person_node)
            graph_nodes[person_id] = person_node
        author_refs.append({"@id": person_id})

    return author_refs, publisher_ref


class SyncPermission(Enum):
    """Permission levels granted when sharing/syncing a collection (see :meth:`Collection.share`)."""
    Read = 0
    Write = 1
    Share = 2
    Delete = 3
    ImportElements = 4
    PassOwnership = 5


class AbstractCollection:
    """Base class for all collection objects.

    Holds the shared tree state (children, parent, label, id) and the read-only behaviour:
    navigation by path, finding sub-collections, listing elements (samples, reactions, well plates,
    research plans, generics) and exporting to ``.eln``. Concrete subclasses add editing
    (:class:`AbstractEditableCollection`) and root behaviour (:class:`RootCollection`,
    :class:`RootSyncCollection`).
    """

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

    def prepare_label(self, case_insensitive: bool) -> str:
        """
        Prepares the label of a collection

        :param case_insensitive: If true it returns teh lower case label

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
        Finds a collection by its label or other properties. Path is not needed.

        :param label: String or None.
        :param kwargs: Other properties used to search Collections

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

    def get_path(self) -> str:
        """
        Generates the absolut path of collection

        :return: Absolut path of a collection
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
        Gets a collection a path points to.

        :param col_path: is either a string based on a unix path or a list
        :param case_insensitive: If true the cases of path are taken into account

        :return: Collection the path points to
        """

        abs_path = self.get_path()
        if col_path.__class__ is not str:
            col_path = '/'.join(col_path)
        return self.get_root().get_collection(_col_path_join(abs_path, col_path), case_insensitive)

    def get_or_create_collection(self, col_path: str | list[str],
                                 case_insensitive: bool = False) -> AbstractCollection:
        """
        Gets or creates a collection the col_path path points to. If the collection needs to be created
        the collection is saved right away.

        :param col_path: is either a string based on a unix path or a list
        :param case_insensitive: If true the cases of path are taken into account

        :return: Collection the path points to
        """

        try:
            return self.get_collection(col_path, case_insensitive)
        except (IndexError, KeyError, ValueError, ModuleNotFoundError):
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

    def get_elements_of_iri(self, element_type: str, per_page: int | None = 10, updated_to_date: datetime | None = None,
                      updated_from_date: datetime | None = None) -> ElementSet:
        """
        Gets all elements of given IRI type.

        :param element_type: IRI string chemotion:xxx/xxx/xxx
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
                           typing.cast(int, self.id),
                           self.is_sync)
            e.load_elements(per_page, updated_to_date, updated_from_date)
            e.set_iri_filter(element_type)
            return e
        raise ValueError(f'Could not find a element with the IRI: "{element_type}"')

    def get_samples(self, per_page: int | None = 10, updated_to_date: datetime | None = None,
                      updated_from_date: datetime | None = None, product_only: bool = False) -> ElementSet:
        """
        List of all samples.

        :param per_page: How many Elements per page
        :param updated_to_date: Set date time to fetch only elements which are updated before 'updated_to_date'
        :param updated_from_date: Set date time to fetch only elements which are updated after 'updated_from_date'
        :param product_only: If True only samples which are products in a reaction are returned

        :return: ElementSet of samples
        """

        root = self.get_root()
        e = ElementSet(root._session, typing.cast(dict, root._element_manager.all_classes.get('sample')),
                       typing.cast(int, self.id),
                       self.is_sync)
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
                       typing.cast(int, self.id),
                       self.is_sync)
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
                       typing.cast(int, self.id),
                       self.is_sync)
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
                       typing.cast(int, self.id),
                       self.is_sync)
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

        e = ElementSet(root._session, elem, typing.cast(int, self.id), self.is_sync)
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

    def export_eln(self, file_path: str, strict: bool = False,
                   ontology_lookup: bool = True, ols_cache: str | None = None,
                   authors: list | None = None,
                   progress_callback: Callable[[int, int, str | None], None] | None = None,
                   interactive: bool = False) -> str:
        """
        Exports the collection and all its elements to a .eln ZIP file.

        :param file_path: destination ``.eln`` path.
        :param strict: if True, raise ``RuntimeError`` when any element/category could not be
            retrieved, loaded, or mapped (i.e. would be silently omitted from the crate). When
            False (default) such items are skipped, logged as a warning summary, and recorded.
        :param progress_callback: optional callable invoked once per element during the mapping
            phase as ``progress_callback(processed_count, total_count, current_item_name)`` (1-based
            ``processed_count``). Useful for progress bars in notebooks/GUIs. Exceptions raised by
            the callback are caught and logged so a faulty callback never aborts the export.
        :param authors: the export's author(s) as a list of :class:`chemotion_api.authors.Author`,
            each with an ORCID iD and ROR-identified affiliation(s). **Required**: every ``.eln``
            must declare its authors. If omitted here, the authors set via :meth:`set_authors` are
            used; if neither is provided a ``ValueError`` explains how to set them. Authorship is no
            longer taken from the logged-in user.
        :param ontology_lookup: annotate each analysis with a ``measurementTechnique`` ontology
            term. Resolution order: the ``CHMO:…`` code embedded in the analysis ``kind`` →
            (when no code) an EBI OLS lookup. OLS access is cached and never fatal; set this
            ``False`` to use only embedded codes and skip all network calls.
        :param ols_cache: optional path to a JSON OLS cache (read + updated) for deterministic
            and offline-friendly lookups.
        :param interactive: if True, show progress bars during the export when possible (uses
            ``tqdm.auto``, which renders a widget in Jupyter/IPython and a text bar in a terminal):
            one for the element→DCAT mapping, then one for attachment download/ZIP writing (the
            slow phase). Best-effort: if ``tqdm`` is not installed it degrades silently to no bar.
            Composes with ``progress_callback`` (both are invoked; the callback's index/total
            continue across the two phases).
        :return: the written ``file_path``.
        """
        import re
        import json
        import os
        from datetime import datetime
        from rdflib import Graph, URIRef
        from linkml_runtime.dumpers import RDFLibDumper
        import chem_dcat_ap.datamodel as dm
        from chem_dcat_ap.datamodel import MAIN_SCHEMA_PATH
        from chemotion_api.authors import validate_authors

        # Authorship is explicit: use the authors passed here, else those set via set_authors().
        # validate_authors() raises a helpful ValueError (with examples) if none/invalid — fail fast
        # before doing any export work.
        export_authors = validate_authors(
            authors if authors is not None else getattr(self, "_export_authors", None)
        )

        def sanitize_filename(name: str) -> str:
            if not name:
                return "unnamed"
            return re.sub(r'[^a-zA-Z0-9_\-]', '_', name)

        col_paths = {}
        elem_paths = {}
        collections_by_id = {}
        elements_by_id = {}
        elem_to_col = {}
        # Manifest of items omitted from the crate so export never silently loses data.
        skipped: list[dict] = []

        # Ontology resolution for analysis measurement techniques (embedded CHMO code → OLS).
        from chemotion_api.ontology import OlsCache, resolve_ontology_term
        _ols_cache = OlsCache(ols_cache)
        _defined_terms_seen: set[str] = set()

        def _annotate_analyses(elem, node):
            """Attach measurementTechnique DefinedTerm refs for each analysis (best-effort)."""
            analyses = getattr(elem, "analyses", None)
            if not analyses:
                return
            for ana in analyses:
                try:
                    kind = ana.get("kind") if hasattr(ana, "get") else None
                    name = ana.get("name") if hasattr(ana, "get") else None
                    term = resolve_ontology_term(name, embedded_kind=kind,
                                                 cache=_ols_cache, enable_ols=ontology_lookup)
                except Exception as e:  # never break export on annotation
                    logger.debug("Analysis ontology annotation failed: %s", e)
                    continue
                if term is None:
                    continue
                node.setdefault("measurementTechnique", [])
                if {"@id": term.iri} not in node["measurementTechnique"]:
                    node["measurementTechnique"].append({"@id": term.iri})
                if term.iri not in _defined_terms_seen:
                    _defined_terms_seen.add(term.iri)
                    metadata_dict["@graph"].append({
                        "@id": term.iri, "@type": "DefinedTerm", "name": term.label,
                    })

        def _index(col_id, parent_path, getter, plural, default_name, kind):
            """List one element kind for a collection, load each, and register its crate path.
            Failures are recorded in ``skipped`` instead of being silently dropped."""
            try:
                items = list(getter())
            except Exception as e:
                logger.warning("Could not retrieve %s for collection %s: %s", kind, col_id, e)
                skipped.append({"kind": kind, "stage": "retrieve", "collection": col_id, "error": str(e)})
                return
            for it in items:
                if not it._data_loaded:
                    try:
                        it.load()
                    except Exception as e:
                        logger.warning("Could not load %s %s: %s", kind, getattr(it, "id", "?"), e)
                        skipped.append({"kind": kind, "stage": "load", "id": getattr(it, "id", None), "error": str(e)})
                        continue
                name_part = sanitize_filename(it.properties.get('short_label') or it.name or default_name)
                elem_paths[it.id] = f"{parent_path}{plural}/{name_part}_{it.id}/"
                elements_by_id[it.id] = it
                elem_to_col[it.id] = col_id

        def traverse(col, parent_path):
            col_id = col.id or id(col)
            col_paths[col_id] = parent_path
            collections_by_id[col_id] = col

            _index(col_id, parent_path, lambda: col.get_samples(per_page=100), "samples", "sample", "sample")
            _index(col_id, parent_path, lambda: col.get_reactions(per_page=100), "reactions", "reaction", "reaction")
            _index(col_id, parent_path, lambda: col.get_wellplates(per_page=100), "wellplates", "wellplate", "wellplate")
            _index(col_id, parent_path, lambda: col.get_research_plans(per_page=100), "research_plans", "research_plan", "research_plan")

            root_col = col.get_root()
            if hasattr(root_col, "_element_manager") and root_col._element_manager:
                for type_name in root_col._element_manager.all_classes.keys():
                    if type_name not in ('sample', 'reaction', 'wellplate', 'research_plan'):
                        _index(col_id, parent_path,
                               lambda tn=type_name: col.get_generics_by_name(tn, per_page=100),
                               "generics", "generic", type_name)

            for child in col.children:
                child_name = sanitize_filename(child.label or "subcollection")
                traverse(child, f"{parent_path}{child_name}_{child.id}/")

        traverse(self, "./")

        # Offline collections may hold entity kinds their ingestion cannot reconstruct yet
        # (wellplates, screens, research plans, generic elements). Record them in the skipped
        # manifest so the crate never silently comes out thinner than the archive.
        _unrec = getattr(self, "unreconstructed_counts", None)
        if callable(_unrec):
            for _kind, _count in _unrec().items():
                logger.warning("Offline ingestion does not reconstruct %s elements; "
                               "%d omitted from the crate.", _kind, _count)
                skipped.append({"kind": _kind, "stage": "offline_reconstruction", "count": _count,
                                "error": "offline ingestion does not reconstruct this element type"})

        uri_mapping = {}
        for elem_id, relative_path in elem_paths.items():
            elem = elements_by_id[elem_id]
            if hasattr(elem, "to_dcat_ap"):
                try:
                    dcat_obj = elem.to_dcat_ap()
                    abs_url = str(dcat_obj.id)
                    uri_mapping[abs_url] = relative_path
                except Exception as e:
                    logger.debug("Failed to map URI for element %s to DCAT-AP: %s", elem_id, e)

        def map_term(term):
            if isinstance(term, URIRef):
                val = str(term)
                if val.startswith("chemotion://molecule/"):
                    mol_db_id = val[len("chemotion://molecule/"):]
                    return URIRef(f"#molecule_{mol_db_id}")
                for abs_url, relative_path in uri_mapping.items():
                    if val == abs_url:
                        return URIRef(relative_path)
                    elif val.startswith(abs_url + "#"):
                        return URIRef(relative_path + val[len(abs_url):])
            return term

        graph = Graph()
        # Resolve the dcat_ap_plus import from the locally installed package instead of fetching
        # it from w3id.org, so export works offline. Falls back to remote if the package is absent.
        importmap = {}
        try:
            import dcat_ap_plus
            importmap["dcatapplus:latest/schema/dcat_ap_plus"] = os.path.join(
                os.path.dirname(dcat_ap_plus.__file__), "schema", "dcat_ap_plus")
        except Exception as e:
            logger.warning("dcat_ap_plus not installed locally; SchemaView will fetch it remotely: %s", e)
        schemaview = _get_export_schemaview(MAIN_SCHEMA_PATH, importmap)
        rdf_dumper = RDFLibDumper()

        _total = len(elements_by_id)
        # Phase 1 of the interactive progress display: the (fast) element→DCAT mapping. The slow
        # phase — downloading attachments into the ZIP — gets its own bar further down, so the
        # display doesn't sit at 100 % while multi-MB attachments stream.
        _bar = _make_progress_bar(_total, "Mapping elements", "element") if interactive else None

        def _report(i, total, name):
            if _bar is not None:
                if name:
                    _bar.set_postfix_str(str(name)[:40], refresh=False)
                _bar.update(1)
            if progress_callback is not None:
                progress_callback(i, total, name)

        try:
            for _i, elem in enumerate(elements_by_id.values(), start=1):
                try:
                    _report(_i, _total, getattr(elem, "name", None) or getattr(elem, "id", None))
                except Exception as e:  # a faulty callback/bar must never abort the export
                    logger.debug("progress reporting raised: %s", e)
                if hasattr(elem, "to_dcat_ap"):
                    try:
                        dcat_obj = elem.to_dcat_ap()
                        class_name = dcat_obj.__class__.__name__
                        linkml_cls = getattr(dm, class_name)
                        l_obj = linkml_cls(**dcat_obj.model_dump(exclude_none=True))
                        rdf_dumper.inject_triples(l_obj, schemaview, graph)
                    except Exception as e:
                        logger.warning("Could not map element %s to DCAT-AP (exported as generic Dataset): %s", elem.id, e)
                        skipped.append({"kind": "dcat_mapping", "stage": "to_dcat_ap", "id": getattr(elem, "id", None), "error": str(e)})
        finally:
            if _bar is not None:
                _bar.close()

        mapped_graph = Graph()
        for prefix, ns in graph.namespaces():
            mapped_graph.bind(prefix, ns)

        for s, p, o in graph:
            mapped_graph.add((map_term(s), map_term(p), map_term(o)))

        # Use the vendored RO-Crate JSON-LD context for compaction so serialization does not
        # fetch https://w3id.org/ro/crate/1.1/context at runtime (offline-capable). The output's
        # @context is still set to the canonical URL below.
        ctx = "https://w3id.org/ro/crate/1.1/context"
        try:
            _ctx_path = os.path.join(os.path.dirname(__file__), "data", "ro-crate-context.jsonld")
            with open(_ctx_path) as _f:
                ctx = json.load(_f).get("@context", ctx)
        except Exception as e:
            logger.warning("Vendored RO-Crate context unavailable; serialization may fetch it remotely: %s", e)
        serialized = mapped_graph.serialize(format="json-ld", context=ctx)
        metadata_dict = json.loads(serialized)
        
        metadata_dict["@context"] = "https://w3id.org/ro/crate/1.1/context"

        if "@graph" not in metadata_dict:
            node = {k: v for k, v in metadata_dict.items() if k != "@context"}
            metadata_dict = {
                "@context": "https://w3id.org/ro/crate/1.1/context",
                "@graph": [node]
            }

        elem_files = {}
        for elem_id in elem_paths:
            elem = elements_by_id[elem_id]
            files_list = []
            seen_filenames = set()
            if elem.attachments:
                for att in elem.attachments:
                    filename = att['filename']
                    if filename not in seen_filenames:
                        seen_filenames.add(filename)
                        files_list.append(att)
            if hasattr(elem, "analyses") and elem.analyses:
                for ana in elem.analyses:
                    if hasattr(ana, "datasets") and ana.datasets:
                        for ds in ana.datasets:
                            if ds.attachments:
                                for att in ds.attachments:
                                    filename = att['filename']
                                    if filename not in seen_filenames:
                                        seen_filenames.add(filename)
                                        files_list.append(att)
            elem_files[elem_id] = files_list

        file_nodes = []
        for elem_id, files in elem_files.items():
            rel_path = elem_paths[elem_id]
            for att in files:
                orig_filename = att['filename']
                safe_filename = os.path.basename(orig_filename)
                name_part, ext_part = os.path.splitext(safe_filename)
                safe_filename = sanitize_filename(name_part) + ext_part
                
                file_id = f"{rel_path}{safe_filename}"
                size = str(att.get('filesize') or att.get('contentSize') or "")
                mime = att.get('mime_type') or att.get('content_type') or "application/octet-stream"
                file_node = {
                    "@id": file_id,
                    "@type": "File",
                    "name": safe_filename,
                    "encodingFormat": mime,
                }
                if size:
                    file_node["contentSize"] = size
                file_nodes.append(file_node)

        for fn in file_nodes:
            metadata_dict["@graph"].append(fn)

        graph_nodes = {node["@id"]: node for node in metadata_dict["@graph"] if "@id" in node}

        for elem_id, rel_path in elem_paths.items():
            elem = elements_by_id[elem_id]
            node_id = rel_path
            if node_id in graph_nodes:
                node = graph_nodes[node_id]
                current_type = node.get("@type", [])
                if isinstance(current_type, str):
                    if current_type != "Dataset":
                        node["@type"] = ["Dataset", current_type]
                elif isinstance(current_type, list):
                    if "Dataset" not in current_type:
                        node["@type"] = ["Dataset"] + current_type
            else:
                # Elements without a chem-dcat-ap mapping (Wellplate, ResearchPlan, GenericElement):
                # keep the spec-required structural @type "Dataset" (a bare Python class name like
                # "Wellplate" is not an ontology term) and attach a forward-compatible ontology
                # placeholder so the term can be patched in later. See chemotion_api.ontology_map.
                from chemotion_api.ontology_map import ontology_placeholder
                kind = elem.element_type if hasattr(elem, "element_type") else "dataset"
                node = {
                    "@id": node_id,
                    "@type": "Dataset",
                    "name": elem.name or elem.properties.get("short_label") or kind,
                    "variableMeasured": [ontology_placeholder(kind)],
                }
                if hasattr(elem, "properties") and elem.properties.get("description"):
                    node["description"] = elem.properties.get("description")
                # Richer structured content for un-typed elements (Wellplate / ResearchPlan /
                # GenericElement): a real description + schema.org PropertyValue entries instead of
                # an empty Dataset. The ontology *type* placeholder above is preserved.
                try:
                    extra = elem.eln_node_content() if hasattr(elem, "eln_node_content") else {}
                except Exception as e:
                    logger.debug("eln_node_content failed for %s: %s", elem_id, e)
                    extra = {}
                if extra.get("description"):
                    node["description"] = extra["description"]
                if extra.get("variableMeasured"):
                    node["variableMeasured"] = node.get("variableMeasured", []) + extra["variableMeasured"]
                metadata_dict["@graph"].append(node)
                graph_nodes[node_id] = node

            _annotate_analyses(elem, node)

            from chemotion_api.elements import Sample, Reaction
            from chemotion_api.utils import PropertyDict

            def clean_json_value(val):
                if isinstance(val, PropertyDict):
                    return {k: clean_json_value(v) for k, v in val.to_dict().items()}
                elif isinstance(val, dict):
                    return {k: clean_json_value(v) for k, v in val.items()}
                elif isinstance(val, list):
                    return [clean_json_value(x) for x in val]
                return val

            if isinstance(elem, Sample) and hasattr(elem, "properties") and elem.properties:
                if elem.properties.get('dry_solvent') is not None:
                    node['dry_solvent'] = clean_json_value(elem.properties.get('dry_solvent'))
                if elem.properties.get('impurities') is not None:
                    node['impurities'] = clean_json_value(elem.properties.get('impurities'))
                if elem.properties.get('xref') is not None:
                    node['xref'] = clean_json_value(elem.properties.get('xref'))
            elif isinstance(elem, Reaction) and hasattr(elem, "properties") and elem.properties:
                for prop_name in ['rxno', 'conditions', 'purification', 'tlc_solvents', 'rf_value', 'volume', 'use_reaction_volume', 'weight_percentage', 'rinchi_string', 'rinchi_web_key', 'variations']:
                    if elem.properties.get(prop_name) is not None:
                        node[prop_name] = clean_json_value(elem.properties.get(prop_name))

            files = elem_files[elem_id]
            if files:
                has_parts_list = []
                for att in files:
                    orig_filename = att['filename']
                    safe_filename = os.path.basename(orig_filename)
                    name_part, ext_part = os.path.splitext(safe_filename)
                    safe_filename = sanitize_filename(name_part) + ext_part
                    has_parts_list.append({"@id": f"{rel_path}{safe_filename}"})
                node["hasPart"] = has_parts_list

        for node in metadata_dict.get("@graph", []):
            node_id = node.get("@id", "")
            if isinstance(node_id, str) and node_id.startswith("#molecule_"):
                try:
                    mol_db_id = int(node_id[len("#molecule_"):])
                    for elem in elements_by_id.values():
                        from chemotion_api.elements import Sample
                        if isinstance(elem, Sample) and elem.molecule:
                            curr_id = elem.molecule.id or elem.molecule.get('id')
                            if curr_id == mol_db_id:
                                if elem.molecule.get('cas') is not None:
                                    node['cas'] = elem.molecule.get('cas')
                                if elem.molecule.get('names') is not None:
                                    node['names'] = elem.molecule.get('names')
                                break
                except Exception as e:
                    logger.debug("Failed to enrich molecule node %s: %s", node_id, e)

        for col_id, col_path in col_paths.items():
            col = collections_by_id[col_id]
            col_node = {
                "@id": col_path,
                "@type": "Dataset",
                "name": col.label or "Collection",
            }
            if col.collection_json and col.collection_json.get("description"):
                col_node["description"] = col.collection_json.get("description")
            if col._parent and (col._parent.id or id(col._parent)) in col_paths:
                col_node["isPartOf"] = {"@id": col_paths[col._parent.id or id(col._parent)]}
            metadata_dict["@graph"].append(col_node)
            graph_nodes[col_path] = col_node

        root_node = graph_nodes.get("./")
        if root_node:
            root_node["name"] = self.label or "Collection"
            root_node["@type"] = "Dataset"
        else:
            root_node = {
                "@id": "./",
                "@type": "Dataset",
                "name": self.label or "Collection"
            }
            metadata_dict["@graph"].append(root_node)
            graph_nodes["./"] = root_node

        root_has_part = []
        for other_id, node in graph_nodes.items():
            if other_id != "./" and other_id != "ro-crate-metadata.json":
                node_type = node.get("@type", [])
                is_dataset = False
                if isinstance(node_type, str):
                    is_dataset = (node_type == "Dataset")
                elif isinstance(node_type, list):
                    is_dataset = ("Dataset" in node_type)
                if is_dataset:
                    root_has_part.append({"@id": other_id})
        root_node["hasPart"] = root_has_part

        # Author + affiliation: the manually-provided authors (validated above) become Person
        # contextual entities (ORCID iD as @id) with ROR-identified Organization affiliations, per
        # TheELNFileFormat / RO-Crate. Every Dataset node references the author(s) via ``author``;
        # the root dataset's ``publisher`` references the first author's first organization.
        author_refs, publisher_ref = _build_author_nodes(
            metadata_dict, graph_nodes, export_authors)
        if author_refs:
            author_value = author_refs if len(author_refs) > 1 else author_refs[0]
            for other_id, node in graph_nodes.items():
                if other_id == "ro-crate-metadata.json":
                    continue
                node_type = node.get("@type", [])
                is_dataset = node_type == "Dataset" or (isinstance(node_type, list) and "Dataset" in node_type)
                if is_dataset and "author" not in node:
                    node["author"] = author_value
        if publisher_ref is not None:
            root_node.setdefault("publisher", publisher_ref)

        # Producer marker (TheELNFileFormat convention): the descriptor's ``sdPublisher`` names
        # the software that wrote the crate. This is the stable, grep-able identifier of a
        # chemotion-api-generated .eln — import_eln keys its "own crate" check on it.
        from chemotion_api.eln_producer import producer_node
        software_node = producer_node()
        metadata_dict["@graph"].append(software_node)
        graph_nodes[software_node["@id"]] = software_node

        meta_descriptor = {
            "@id": "ro-crate-metadata.json",
            "@type": "CreativeWork",
            "about": {"@id": "./"},
            "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
            "dateCreated": datetime.now().isoformat(),
            "sdPublisher": {"@id": software_node["@id"]},
        }
        metadata_dict["@graph"].append(meta_descriptor)

        base_name = os.path.basename(file_path)
        if base_name.lower().endswith(".eln"):
            base_name = base_name[:-4]
        root_folder = sanitize_filename(base_name)
        if not root_folder:
            root_folder = "export"
        root_folder = root_folder + ".eln"

        # Phase 2 of the progress display: attachment download/ZIP writing — the slow part of a
        # real export. progress_callback continues counting past phase 1 (elements, then files).
        _n_att = sum(len(files) for files in elem_files.values())
        _bar2 = _make_progress_bar(_n_att, "Writing attachments", "file") if interactive and _n_att else None
        _att_done = 0

        def _tick_file(filename):
            nonlocal _att_done
            _att_done += 1
            try:  # a faulty callback/bar must never abort the export
                if _bar2 is not None:
                    if filename:
                        _bar2.set_postfix_str(str(filename)[:40], refresh=False)
                    _bar2.update(1)
                if progress_callback is not None:
                    progress_callback(_total + _att_done, _total + _n_att, filename)
            except Exception as e:
                logger.debug("progress reporting raised: %s", e)

        try:
            _write_crate_zip(file_path, root_folder, metadata_dict, elem_files, elem_paths,
                             sanitize_filename, skipped, progress=_tick_file)
        finally:
            if _bar2 is not None:
                _bar2.close()
        _ols_cache.save()

        logger.info("Exported %d element(s) and %d collection(s) to %s",
                    len(elem_paths), len(col_paths), file_path)
        if skipped:
            # Note: dcat_mapping entries are still exported as generic Dataset nodes (not lost);
            # retrieve/load entries ARE omitted from the crate.
            omitted = [s for s in skipped if s["stage"] != "to_dcat_ap"]
            logger.warning("export_eln: %d issue(s) during export (%d element(s) omitted, %d mapped generically). "
                           "See export manifest.", len(skipped), len(omitted), len(skipped) - len(omitted))
            if strict:
                raise RuntimeError(f"export_eln strict mode: {len(skipped)} issue(s) during export: {skipped}")
        return file_path

    def set_authors(self, authors: list) -> None:
        """Set the author(s) used by :meth:`export_eln`.

        :param authors: list of :class:`chemotion_api.authors.Author`, each with an ORCID iD and
            ROR-identified affiliation(s). Validated at export time.
        """
        self._export_authors = list(authors)

    @property
    def authors(self) -> list:
        """The author(s) currently set for export (see :meth:`set_authors`)."""
        return getattr(self, "_export_authors", []) or []



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

        :return: New (unsaved) Sample
        """
        sample = typing.cast(Sample, self._create_new_element('sample'))
        mol = MoleculeManager(self.get_root()._session).create_molecule_by_smiles(smiles_code)
        sample.molecule = mol
        return typing.cast(Sample, sample)

    def new_solvent(self, name) -> Sample:
        """
        Creates a new solvent in this collection.

        :return: New (unsaved) solvent as Sample
        """
        root = self.get_root()
        new_json = root._element_manager.build_solvent_sample(name, self.id)
        e = ElementSet(root._session, typing.cast(dict, root._element_manager.all_classes.get('sample')),
                       typing.cast(int, self.id),
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
        Creates a new element of given IRI type. However, if the type is generic the generated element is of the newest type.

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
        new_json = root._element_manager.build_new(type_name, self.id)

        e = ElementSet(root._session, typing.cast(dict, root._element_manager.all_classes.get(type_name)),
                       typing.cast(int, self.id),
                       self.is_sync)
        return e.new_element(new_json)


class Collection(AbstractEditableCollection):
    """
    The collection object represents the standard collection owned by the current user
    """

    def __init__(self, collection_json: dict | None = None):
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
        Moves this collection to a dest path.

        :param dest: is either a string based on a unix path or a list
        :param case_insensitive: If true the cases of path are taken into account

        :return: Collection the path points to
        """

        abs_path = self.get_path()
        dest = _col_path_join(os.path.dirname(abs_path), typing.cast(str, dest))
        self.get_root().move(abs_path, dest, case_insensitive)

    def delete(self):
        """
        Deletes this collection.
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

    def share(self, permission_level: SyncPermission, *users: Person | Group):
        """
        To synchronize a collection with a set of users or groups

        :param permission_level: Element from SyncPermission
        :param users: a list of users or groups
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
    This can be used amost like the root collection object.
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
    >>> # Create collection 'P 123' in '/Project/Team One'
    >>> col.get_or_create_collection('./P 123')
    >>> # Move collection P 122 into collection '/Done Projects'
    >>> col.get_collection('./P 122').move('/Done Projects')
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
        self._deleted_ids: list = []
        self._id = None

    @property
    def id(self) -> int:
        """
        The 'All' collection ID

        :return: Ihe ID of the 'All' collection
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

    def load_collection(self) -> dict[str,dict]:
        """
        Load collection information

        :return: A collection off all collection information
        """

        collection_url = '/api/v1/collections/roots.json'

        res = self._session.get(collection_url)

        if res.status_code != 200:
            raise ConnectionError(f'{res.status_code} -> {res.text}')

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
            raise ConnectionError(f'{res.status_code} -> {res.text}')
        collections = json.loads(res.content)
        self._sync_root = RootSyncCollection(self._session, self._element_manager)
        self._sync_root._set_children(collections['syncCollections'])
        return self._sync_root

    def save(self):
        """
        Saves ALL updates of done to owned (not synced) collection.
        """

        collection_url = '/api/v1/collections'
        payload = self.to_json()
        payload['deleted_ids'] = self._deleted_ids
        res = self._session.patch(collection_url,
                                  data=payload)
        if res.status_code != 200:
            raise ConnectionError(f'{res.status_code} -> {res.text}')
        self.load_collection()

    def get_collection(self, col_path: str | list[str], case_insensitive: bool = False) -> AbstractCollection:
        """
        Gets a collection a path points to.

        :param col_path: is either a string based on a unix path or a list
        :param case_insensitive: If true the cases of path are taken into account

        :return: Collection the path points to
        """

        col_path = self._prepare_path(col_path)
        current_pos: AbstractCollection = self
        for col_label in self._prepare_path(col_path):
            current_pos = typing.cast(AbstractCollection, next((x for x in current_pos.children if
                                x.prepare_label(case_insensitive) == col_label), None))
            if current_pos is None:
                raise ModuleNotFoundError("'{}' Collection Not Found".format('/'.join(col_path)))
        return current_pos

    def move(self, src: str | list[str], dest: str | list[str], case_insensitive: bool = False):  # type: ignore[override]
        """
        Moves a collection from a src path to a dest path.

        :param src: is either a string based on a unix path or a list
        :param dest: is either a string based on a unix path or a list
        :param case_insensitive: If true the cases of path are taken into account

        :return: Collection the path points to
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
        Deletes a collection at the src path.

        :param src: is either a string based on a unix path or a list
        :param case_insensitive: If true the cases of path are taken into account
        """

        prepared_src = self._prepare_path(src, case_insensitive)
        src_col = self.get_collection(prepared_src)
        idx = next((i for (i, x) in enumerate(typing.cast(AbstractCollection, src_col._parent).children) if x.label == prepared_src[-1]), None)

        typing.cast(AbstractCollection, src_col._parent).children.pop(typing.cast(int, idx))
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
