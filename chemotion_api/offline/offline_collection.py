"""Offline stand-ins so ``Collection.export_eln`` runs against an export ZIP.

`OfflineCollection` mimics the small slice of the `Collection` surface that
`export_eln`'s traversal touches (``get_samples`` / ``get_reactions`` / …, ``label``,
``children``, ``get_root``, ``_session``) and yields the regular ``Sample`` /
``Reaction`` objects built from reshaped ``json_data``. `OfflineConnection` supplies
``_host_url`` and serves attachment bytes from the archive so the unchanged streaming
exporter works without a server.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from collections.abc import Iterator

from chemotion_api.eln_producer import OFFLINE_HOST
from chemotion_api.offline.export_reader import ExportArchive, ExportAdapter, uuid_to_id

logger = logging.getLogger(__name__)


class _OfflineResponse:
    """Minimal ``requests.Response`` stand-in backed by archive bytes."""

    def __init__(self, archive: ExportArchive | None, identifier: str | None) -> None:
        self._archive = archive
        self._identifier = identifier
        self._found = bool(archive and identifier and archive.has_attachment(identifier))
        self.status_code = 200 if self._found else 404

    @property
    def content(self) -> bytes:
        """The attachment's full bytes, or ``b""`` if it is not in the archive."""
        if self._found:
            return self._archive.read_attachment(self._identifier)  # type: ignore[union-attr,arg-type]
        return b""

    def iter_content(self, chunk_size: int = 1 << 20) -> Iterator[bytes]:
        """Yield the attachment's bytes in chunks (nothing if it is not in the archive)."""
        if self._found:
            yield from self._archive.iter_attachment(self._identifier, chunk_size)  # type: ignore[union-attr,arg-type]

    @property
    def text(self) -> str:
        """Why the request failed, for the error messages callers build from it.

        ``Attachment.load_file``/``iter_file`` raise ``ConnectionError(f"{status} -> {res.text}")``
        on a non-200. Without this, a missing offline attachment surfaced as
        ``AttributeError: '_OfflineResponse' object has no attribute 'text'`` — which says nothing
        about the actual problem and, under ``strict=True``, aborted the export with that instead
        of naming the attachment.
        """
        if self._found:
            return ""
        return (f"offline attachment {self._identifier!r} is not in the export archive "
                "(the dump does not contain its bytes)")

    def raise_for_status(self) -> None:
        """Raise ``FileNotFoundError`` if the requested attachment is not in the archive."""
        if not self._found:
            raise FileNotFoundError(f"offline attachment {self._identifier} not in archive")

    def close(self) -> None:
        """No-op: Attachment.iter_file closes its response after streaming."""




class _OfflineSchemaManager:
    """Stand-in for ``Connection.schema_manager`` used when setting an element's ``@type``."""

    #: There is no ``/about`` to read offline, so the source ELN's version is genuinely unknown.
    #: ``None`` rather than a placeholder: the exporter omits what it does not know instead of
    #: inventing it, exactly as it does for element timestamps.
    version_string = None
    version = None
    revision = None

    @staticmethod
    def generate_model_type(element_type: str | None, schema_version: Any = None) -> str:
        """Return a placeholder ``@type`` URL for an element type in offline mode."""
        return f"{OFFLINE_HOST}/type/{element_type or 'element'}"


class OfflineConnection:
    """Connection shim: a host URL for ``@id`` formatting + offline attachment serving."""

    def __init__(self, archive: ExportArchive | None = None,
                 host_url: str = OFFLINE_HOST) -> None:
        self._archive = archive
        # Normalised the way Connection.__init__ does, so a caller-supplied host with a trailing
        # slash does not produce double-slashed ids on the offline path only.
        host_url = host_url.strip('/')
        self._host_url = host_url
        self.host_url = host_url
        self.schema_manager = _OfflineSchemaManager()
        #: No server to ask for the label vocabulary, so an offline element's label ids cannot be
        #: resolved to titles. An empty list, not a missing attribute: without this
        #: ``AbstractElement.user_labels_resolved`` raised AttributeError on every offline element
        #: carrying labels, and the caller's ``getattr(..., [])`` swallowed it — so the labels
        #: vanished from the crate with no error and no warning.
        self.user_labels: list[dict] = []

    def reset_user_labels(self) -> None:
        """No-op: there is no cached label list to drop when there is no server."""

    def get(self, url: str, stream: bool = False, **kwargs: Any) -> _OfflineResponse:
        """Serve attachment GETs from the archive; any other GET degrades to a 404 stand-in."""
        prefix = "/api/v1/attachments/"
        if prefix in url:
            identifier = url.split(prefix, 1)[1].split("/", 1)[0].split("?", 1)[0]
            return _OfflineResponse(self._archive, identifier)
        # Any other server call has no offline backing; degrade gracefully.
        logger.debug("OfflineConnection ignoring non-attachment GET %s", url)
        return _OfflineResponse(None, None)

    # Mutating verbs must never be reached during export; fail loudly if they are.
    def _refuse(self, verb: str, *a: Any, **k: Any):  # pragma: no cover - defensive
        """Always raise: mutating verbs must never be reached during offline export."""
        raise RuntimeError(f"OfflineConnection is read-only; {verb} attempted during offline export")

    def post(self, *a: Any, **k: Any):  # pragma: no cover - defensive
        return self._refuse("POST", *a, **k)

    def put(self, *a: Any, **k: Any):  # pragma: no cover - defensive
        return self._refuse("PUT", *a, **k)

    def patch(self, *a: Any, **k: Any):  # pragma: no cover - defensive
        return self._refuse("PATCH", *a, **k)

    def delete(self, *a: Any, **k: Any):  # pragma: no cover - defensive
        return self._refuse("DELETE", *a, **k)


class _OfflineGenericSegments:
    """Stand-in for ElementManager's generic-segment registry (no custom segments offline)."""

    all_classes: list[dict] = []


class OfflineCollection:
    """A collection backed by an export-collection archive (no live server).

    When the export carries collection-membership join tables (``CollectionsSample`` /
    ``CollectionsReaction``), :func:`import_export_zip` builds one ``OfflineCollection``
    per exported collection, wired into the original tree, each scoped to its own
    elements. Older dumps without membership data yield a single flat collection.
    """

    def __init__(self, archive: ExportArchive, label: str | None = None,
                 adapter: ExportAdapter | None = None,
                 collection_uuid: str | None = None,
                 wrapper: bool = False) -> None:
        """:param collection_uuid: scope element getters to this exported collection
            (``None`` = the whole archive).
        :param wrapper: a synthetic root grouping several top-level collections; holds
            no elements of its own."""
        self._archive = archive
        self._adapter = adapter if adapter is not None else ExportAdapter(archive.export_data)
        self._session = OfflineConnection(archive)
        self._generic_segments = _OfflineGenericSegments()
        self._collection_uuid = collection_uuid
        self._wrapper = wrapper
        if label is None and collection_uuid is not None:
            label = self._adapter.collections.get(collection_uuid, {}).get("label")
        self.label = label or self._adapter.collection_label()
        self.children: list[OfflineCollection] = []
        self.collection_json: dict = {"label": self.label}
        self._parent: OfflineCollection | None = None
        self._export_authors: list = []
        self._id = uuid_to_id(collection_uuid) if collection_uuid else 1

    def set_authors(self, authors: list) -> None:
        """Set the author(s) used by :meth:`export_eln` (see ``chemotion_api.authors.Author``)."""
        self._export_authors = list(authors)

    @property
    def authors(self) -> list:
        """The author(s) used by :meth:`export_eln` (see :meth:`set_authors`)."""
        return self._export_authors

    @property
    def id(self) -> int:
        """This offline collection's id (derived from the exported collection's UUID;
        ``1`` for a flat/wrapper root)."""
        return self._id

    def get_root(self) -> OfflineCollection:
        """Return the root of the offline collection tree.

        Guarded against a parent chain that loops: without the visited set a self-parent spins
        here forever rather than failing.
        """
        node = self
        seen = {id(node)}
        while node._parent is not None:
            node = node._parent
            if id(node) in seen:
                logger.warning("Collection parent chain loops at %r; treating it as the root.",
                               getattr(node, "label", "?"))
                break
            seen.add(id(node))
        return node

    # -- element getters consumed by export_eln's traversal ----------------
    def _finalize(self, element: Any) -> Any:
        """Mark an element as already loaded so the exporter does not attempt a network ``load()``."""
        # Mark loaded so the exporter does not attempt a network ``load()``.
        element._data_loaded = True
        return element

    def get_samples(self, per_page: int = 100) -> list[Any]:
        """Return this collection's standalone samples (not part of any reaction) as
        :class:`Sample` objects."""
        from chemotion_api.elements.sample import Sample
        if self._wrapper:
            return []
        out = []
        for uuid in self._adapter.standalone_sample_uuids(self._collection_uuid):
            jd = self._adapter.to_sample_json(uuid)
            out.append(self._finalize(Sample(self._generic_segments, self._session, jd)))
        return out

    def get_reactions(self, per_page: int = 100) -> list[Any]:
        """Return this collection's reactions as :class:`Reaction` objects."""
        from chemotion_api.elements.reaction import Reaction
        if self._wrapper:
            return []
        out = []
        for uuid in self._adapter.reaction_uuids(self._collection_uuid):
            jd = self._adapter.to_reaction_json(uuid)
            out.append(self._finalize(Reaction(self._generic_segments, self._session, jd)))
        return out

    def get_wellplates(self, per_page: int = 100) -> list[Any]:
        """Return wellplates (always empty: offline reconstruction not yet supported)."""
        return []  # export-collection wellplate reconstruction not yet supported

    def get_research_plans(self, per_page: int = 100) -> list[Any]:
        """Return research plans (always empty: offline reconstruction not yet supported)."""
        return []  # export-collection research-plan reconstruction not yet supported

    def get_generics_by_name(self, type_name: str, per_page: int = 100) -> list[Any]:
        """Return generic elements of a type (always empty: not reconstructed offline)."""
        return []  # generic elements not reconstructed offline

    # Rails model tables that may appear in an export dump but that offline ingestion does not
    # reconstruct (the getters above return [] for them).
    _UNRECONSTRUCTED_TABLES = {
        "Wellplate": "wellplate",
        "Screen": "screen",
        "ResearchPlan": "research_plan",
        "Labimotion::Element": "generic_element",
    }

    def unreconstructed_counts(self) -> dict[str, int]:
        """Count entities present in the archive that offline ingestion cannot reconstruct.

        The counts are archive-wide (not scoped to this collection): they feed the export's
        skipped manifest, which describes what the source archive held.

        :return: mapping of element kind (e.g. ``"wellplate"``) to how many the archive holds.
            :meth:`export_eln` records these in its skipped manifest so the resulting crate never
            silently omits them.
        """
        counts: dict[str, int] = {}
        for table, kind in self._UNRECONSTRUCTED_TABLES.items():
            n = len(self._archive.export_data.get(table) or {})
            if n:
                counts[kind] = n
        return counts

    def export_eln(self, file_path: str, strict: bool = False,
                   ontology_lookup: bool = True, ols_cache: str | None = None,
                   authors: list | None = None, progress_callback=None,
                   interactive: bool = False, disclose_host: bool = True,
                   declare_skipped: bool = True) -> str:
        """Export this offline collection to a ``.eln`` crate via the standard exporter.

        Every keyword is forwarded verbatim, so an offline export behaves exactly like a live one
        — including ``disclose_host``, which is a no-op here only because the offline host is
        already the sentinel.
        """
        from chemotion_api.collection import Collection
        return Collection.export_eln(
            self, file_path, strict=strict,  # type: ignore[arg-type]
            ontology_lookup=ontology_lookup, ols_cache=ols_cache, authors=authors,
            progress_callback=progress_callback, interactive=interactive,
            disclose_host=disclose_host, declare_skipped=declare_skipped,
        )


def import_export_zip(path: str | Path, label: str | None = None) -> OfflineCollection:
    """Open a Chemotion export-collection ZIP (or extracted dir) as an OfflineCollection.

    The archive may hold a single collection or a bundle: when the dump carries
    collection-membership join tables, the original collection tree is rebuilt — one
    :class:`OfflineCollection` per exported collection, each scoped to its own elements.
    A bundle of several top-level collections is grouped under a synthetic root (labeled
    ``label`` or ``"Exported Collections"``). Dumps without membership data (older
    Chemotion versions) fall back to a single flat collection holding everything.

    Example::

        from chemotion_api.offline import import_export_zip
        import_export_zip("my_export.zip").export_eln("out.eln")

    :param path: the export ZIP, its extracted directory, or a bare ``export.json``.
    :param label: optional label override for the returned root collection.
    """
    archive = ExportArchive(path)
    adapter = ExportAdapter(archive.export_data)
    tree = adapter.collection_tree()
    if not adapter.has_membership_data or not tree:
        # No way (or no need) to scope elements per collection: single flat collection.
        if len(tree) > 1:
            logger.warning(
                "Export dump lists %d collections but has no membership join tables; "
                "importing everything as one flat collection.", len(tree))
        return OfflineCollection(archive, label=label, adapter=adapter)

    nodes: dict[str, OfflineCollection] = {
        rec["uuid"]: OfflineCollection(archive, adapter=adapter, collection_uuid=rec["uuid"])
        for rec in tree
    }
    roots: list[OfflineCollection] = []
    for rec in tree:
        node = nodes[rec["uuid"]]
        parent = nodes.get(rec["parent"]) if rec["parent"] else None
        if parent is not None:
            node._parent = parent
            parent.children.append(node)
        else:
            roots.append(node)

    if len(roots) == 1:
        root = roots[0]
        if label:
            root.label = label
        return root
    root = OfflineCollection(archive, label=label or "Exported Collections",
                             adapter=adapter, wrapper=True)
    for top in roots:
        top._parent = root
    root.children = roots
    return root
