"""Element indexing and URI-mapping helpers extracted from ``export_eln``.

Pulled out of :meth:`chemotion_api.collection.AbstractCollection.export_eln` as standalone
functions so the id-collision fix (composite ``(kind, id)`` keys) and the URI-mapping
correctness/perf fix are independently unit-testable, without a large refactor of the rest
of the exporter (see PR review findings 1, 6, 11).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from collections.abc import Callable

logger = logging.getLogger(__name__)

#: Composite key for an indexed element: ``(kind, raw_element_id)``. Samples, reactions,
#: wellplates, research plans and generic elements each have independent DB id sequences, so
#: a same-numbered sample and reaction must not share a dict key -- doing so silently drops
#: one of them (PR review finding 1).
ElementKey = tuple[str, Any]


@dataclass
class ElementIndex:
    """Result of walking a collection tree for ``export_eln``: crate paths + collected elements.

    All element-keyed dicts are keyed by :data:`ElementKey` (``(kind, id)``), never by the bare
    element id. Element paths are collection-independent (``./samples/Water_42/``): an element
    is stored once no matter how many collections it belongs to, and membership is carried by
    :attr:`elem_to_cols` rather than by where the element sits.
    """

    col_node_ids: dict[Any, str] = field(default_factory=dict)
    collections_by_id: dict[Any, Any] = field(default_factory=dict)
    elem_paths: dict[ElementKey, str] = field(default_factory=dict)
    elements_by_id: dict[ElementKey, Any] = field(default_factory=dict)
    #: every collection an element belongs to, in traversal order. An element reachable through
    #: two collections is ONE element with two memberships, not two elements -- which is why this
    #: is a list. Keying a single collection here is what silently dropped the second membership.
    elem_to_cols: dict[ElementKey, list[Any]] = field(default_factory=dict)


def _collection_node_id(col: Any, sanitize_filename: Callable[[str], str],
                        taken: dict[Any, str]) -> str:
    """A stable, crate-safe ``#collection-…`` fragment identifier for one collection.

    Collections are contextual entities in the crate, not directories, so they need an ``@id``
    of their own. It must be *stable*: ``col.id or id(col)`` is fine as a dict key but its
    fallback is a Python object address, and writing that into ``ro-crate-metadata.json`` would
    make two exports of the same data differ. Collections without a server id (the synthetic
    wrapper root an offline bundle gets) fall back to their label plus an ordinal instead.
    """
    token = sanitize_filename(str(col.id)) if getattr(col, "id", None) else ""
    if not token:
        token = f"{sanitize_filename(getattr(col, 'label', None) or 'collection')}-{len(taken) + 1}"
    node_id = f"#collection-{token}"
    existing = set(taken.values())
    suffix = 2
    while node_id in existing:
        node_id = f"#collection-{token}-{suffix}"
        suffix += 1
    return node_id


def build_element_index(root_collection: Any, sanitize_filename: Callable[[str], str],
                         skipped: list[dict]) -> ElementIndex:
    """Walk ``root_collection`` and every descendant collection, indexing each element found.

    Each element is registered under a composite ``(kind, id)`` key. Failures retrieving a
    kind's elements for a collection, or loading a single element, are appended to ``skipped``
    (mutated in place) instead of raising or silently dropping the item.

    An element reachable through several collections is indexed once, at one path, with every
    collection recorded in ``elem_to_cols``. It is neither re-loaded nor re-pathed on the second
    sighting -- which is what previously overwrote the first path and lost the first membership.

    :param root_collection: the collection to export (an
        :class:`~chemotion_api.collection.AbstractCollection` or an offline/mocked stand-in
        exposing the same ``get_samples``/``get_reactions``/.../``children`` surface).
    :param sanitize_filename: turns a free-form name into a filesystem/crate-safe token.
    :param skipped: export manifest list; entries are appended for retrieve/load failures.
    :return: the populated :class:`ElementIndex`.
    """
    index = ElementIndex()

    def _index(col_id: Any, getter: Callable[[], Any], plural: str,
               default_name: str, kind: str) -> None:
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
            key: ElementKey = (kind, it.id)
            memberships = index.elem_to_cols.setdefault(key, [])
            if col_id not in memberships:
                memberships.append(col_id)
            if key in index.elem_paths:
                # Seen through another collection already. The element is the same element: keep
                # the first path and the first loaded object, and record only the extra
                # membership. Re-registering here is what used to overwrite the earlier path.
                continue
            name_part = sanitize_filename(it.properties.get('short_label') or it.name or default_name)
            # `it.id` is sanitized too: it is always an int from a genuine server, but a
            # compromised or hostile one could return `../..`, which would put traversal segments
            # into the crate's ZIP entry paths — making an archive we hand to a third party a
            # zip-slip against *their* extractor.
            path = f"./{plural}/{name_part}_{sanitize_filename(str(it.id))}/"
            if path in claimed_paths and claimed_paths[path] != key:
                # Two different elements resolving to one crate path would merge their
                # attachments into one folder and give two graph nodes the same @id. Disambiguate
                # deterministically rather than letting the later one win.
                suffix = 2
                while f"{path.rstrip('/')}~{suffix}/" in claimed_paths:
                    suffix += 1
                logger.warning("Crate path %s is already taken by %s; storing %s %s at a "
                               "disambiguated path instead.", path, claimed_paths[path], kind, it.id)
                skipped.append({"kind": kind, "stage": "path", "id": getattr(it, "id", None),
                                "error": f"crate path collision with {claimed_paths[path]}"})
                path = f"{path.rstrip('/')}~{suffix}/"
            claimed_paths[path] = key
            index.elem_paths[key] = path
            index.elements_by_id[key] = it

    def traverse(col: Any) -> None:
        col_id = col.id or id(col)
        index.col_node_ids[col_id] = _collection_node_id(col, sanitize_filename, index.col_node_ids)
        index.collections_by_id[col_id] = col

        _index(col_id, lambda: col.get_samples(per_page=100), "samples", "sample", "sample")
        _index(col_id, lambda: col.get_reactions(per_page=100), "reactions", "reaction", "reaction")
        _index(col_id, lambda: col.get_wellplates(per_page=100), "wellplates", "wellplate", "wellplate")
        _index(col_id, lambda: col.get_research_plans(per_page=100), "research_plans",
               "research_plan", "research_plan")

        root_col = col.get_root()
        if hasattr(root_col, "_element_manager") and root_col._element_manager:
            for type_name in root_col._element_manager.all_classes.keys():
                if type_name not in ('sample', 'reaction', 'wellplate', 'research_plan'):
                    def _generic_getter(tn: str = type_name) -> Any:
                        return col.get_generics_by_name(tn, per_page=100)
                    # Every generic element type shares the plural "generics", so two elements of
                    # different types with the same id and name would land on one path. The type
                    # segment keeps them apart without relying on traversal order.
                    _index(col_id, _generic_getter, f"generics/{sanitize_filename(type_name)}",
                           "generic", type_name)

        for child in col.children:
            child_id = child.id or id(child)
            if child_id in visited:
                # A loop in the collection tree would recurse until RecursionError, killing an
                # export that is otherwise fine. Skip the revisit and record it.
                logger.warning("Collection tree revisits %r; skipping to avoid looping.",
                               child.label)
                skipped.append({"kind": "collection", "stage": "index",
                                "id": child_id, "error": "collection tree contains a loop"})
                continue
            visited.add(child_id)
            traverse(child)

    claimed_paths: dict[str, ElementKey] = {}
    visited: set = {root_collection.id or id(root_collection)}
    traverse(root_collection)
    return index


def build_uri_mapping(elements_by_id: dict[ElementKey, Any],
                       elem_paths: dict[ElementKey, str]
                       ) -> tuple[dict[str, str], dict[ElementKey, Any]]:
    """Build the absolute-URL -> crate-relative-path map used by ``export_eln``'s ``map_term``.

    Also returns a ``{key: dcat_obj}`` cache of each element's ``to_dcat_ap()`` result, so the
    caller's main per-element mapping loop can reuse it instead of calling ``to_dcat_ap()`` a
    second time per element (PR review finding 6). Elements without a ``to_dcat_ap`` mapping,
    or for which the call fails, are simply absent from both return values -- failures here are
    not fatal and not recorded in the export manifest (a later, independent ``to_dcat_ap()``
    attempt in the main loop is what gets recorded, to keep existing manifest semantics).

    :param elements_by_id: ``{key: element}`` as produced by :func:`build_element_index`.
    :param elem_paths: ``{key: crate_relative_path}`` as produced by :func:`build_element_index`.
    :return: ``(uri_mapping, dcat_cache)``.
    """
    uri_mapping: dict[str, str] = {}
    dcat_cache: dict[ElementKey, Any] = {}
    for key, relative_path in elem_paths.items():
        elem = elements_by_id[key]
        if hasattr(elem, "to_dcat_ap"):
            try:
                dcat_obj = elem.to_dcat_ap()
                dcat_cache[key] = dcat_obj
                abs_url = str(dcat_obj.id)
                uri_mapping[abs_url] = relative_path
            except Exception as e:
                logger.debug("Failed to map URI for element %s to DCAT-AP: %s", key, e)
    return uri_mapping, dcat_cache
