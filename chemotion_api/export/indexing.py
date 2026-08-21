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
    element id.
    """

    col_paths: dict[Any, str] = field(default_factory=dict)
    collections_by_id: dict[Any, Any] = field(default_factory=dict)
    elem_paths: dict[ElementKey, str] = field(default_factory=dict)
    elements_by_id: dict[ElementKey, Any] = field(default_factory=dict)
    elem_to_col: dict[ElementKey, Any] = field(default_factory=dict)


def build_element_index(root_collection: Any, sanitize_filename: Callable[[str], str],
                         skipped: list[dict]) -> ElementIndex:
    """Walk ``root_collection`` and every descendant collection, indexing each element found.

    Each element is registered under a composite ``(kind, id)`` key. Failures retrieving a
    kind's elements for a collection, or loading a single element, are appended to ``skipped``
    (mutated in place) instead of raising or silently dropping the item.

    :param root_collection: the collection to export (an
        :class:`~chemotion_api.collection.AbstractCollection` or an offline/mocked stand-in
        exposing the same ``get_samples``/``get_reactions``/.../``children`` surface).
    :param sanitize_filename: turns a free-form name into a filesystem/crate-safe token.
    :param skipped: export manifest list; entries are appended for retrieve/load failures.
    :return: the populated :class:`ElementIndex`.
    """
    index = ElementIndex()

    def _index(col_id: Any, parent_path: str, getter: Callable[[], Any], plural: str,
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
            name_part = sanitize_filename(it.properties.get('short_label') or it.name or default_name)
            index.elem_paths[key] = f"{parent_path}{plural}/{name_part}_{it.id}/"
            index.elements_by_id[key] = it
            index.elem_to_col[key] = col_id

    def traverse(col: Any, parent_path: str) -> None:
        col_id = col.id or id(col)
        index.col_paths[col_id] = parent_path
        index.collections_by_id[col_id] = col

        _index(col_id, parent_path, lambda: col.get_samples(per_page=100), "samples", "sample", "sample")
        _index(col_id, parent_path, lambda: col.get_reactions(per_page=100), "reactions", "reaction", "reaction")
        _index(col_id, parent_path, lambda: col.get_wellplates(per_page=100), "wellplates", "wellplate", "wellplate")
        _index(col_id, parent_path, lambda: col.get_research_plans(per_page=100), "research_plans",
               "research_plan", "research_plan")

        root_col = col.get_root()
        if hasattr(root_col, "_element_manager") and root_col._element_manager:
            for type_name in root_col._element_manager.all_classes.keys():
                if type_name not in ('sample', 'reaction', 'wellplate', 'research_plan'):
                    def _generic_getter(tn: str = type_name) -> Any:
                        return col.get_generics_by_name(tn, per_page=100)
                    _index(col_id, parent_path, _generic_getter, "generics", "generic", type_name)

        for child in col.children:
            child_name = sanitize_filename(child.label or "subcollection")
            traverse(child, f"{parent_path}{child_name}_{child.id}/")

    traverse(root_collection, "./")
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
