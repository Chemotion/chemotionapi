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

    def raise_for_status(self) -> None:
        """Raise ``FileNotFoundError`` if the requested attachment is not in the archive."""
        if not self._found:
            raise FileNotFoundError(f"offline attachment {self._identifier} not in archive")


class _OfflineSchemaManager:
    """Stand-in for ``Connection.schema_manager`` used when setting an element's ``@type``."""

    @staticmethod
    def generate_model_type(element_type: str | None, schema_version: Any = None) -> str:
        """Return a placeholder ``@type`` URL for an element type in offline mode."""
        return f"https://offline.chemotion.invalid/type/{element_type or 'element'}"


class OfflineConnection:
    """Connection shim: a host URL for ``@id`` formatting + offline attachment serving."""

    def __init__(self, archive: ExportArchive | None = None,
                 host_url: str = "https://offline.chemotion.invalid") -> None:
        self._archive = archive
        self._host_url = host_url
        self.host_url = host_url
        self.schema_manager = _OfflineSchemaManager()

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
    def post(self, *a: Any, **k: Any):  # pragma: no cover - defensive
        """Always raise: mutating verbs must never be reached during offline export."""
        raise RuntimeError("OfflineConnection is read-only; POST attempted during offline export")

    put = delete = post


class _OfflineGenericSegments:
    """Stand-in for ElementManager's generic-segment registry (no custom segments offline)."""

    all_classes: list[dict] = []


class OfflineCollection:
    """A collection backed by an export-collection archive (no live server)."""

    def __init__(self, archive: ExportArchive, label: str | None = None) -> None:
        self._archive = archive
        self._adapter = ExportAdapter(archive.export_data)
        self._session = OfflineConnection(archive)
        self._generic_segments = _OfflineGenericSegments()
        self.label = label or self._adapter.collection_label()
        self.children: list[OfflineCollection] = []
        self.collection_json: dict = {"label": self.label}
        self._parent = None
        self._export_authors: list = []
        self._id = 1

    def set_authors(self, authors: list) -> None:
        """Set the author(s) used by :meth:`export_eln` (see ``chemotion_api.authors.Author``)."""
        self._export_authors = list(authors)

    @property
    def authors(self) -> list:
        """The author(s) used by :meth:`export_eln` (see :meth:`set_authors`)."""
        return self._export_authors

    @property
    def id(self) -> int:
        """This offline collection's synthetic id (always ``1``)."""
        return self._id

    def get_root(self) -> OfflineCollection:
        """Return the root collection (always ``self`` for an offline collection)."""
        return self

    # -- element getters consumed by export_eln's traversal ----------------
    def _finalize(self, element: Any) -> Any:
        """Mark an element as already loaded so the exporter does not attempt a network ``load()``."""
        # Mark loaded so the exporter does not attempt a network ``load()``.
        element._data_loaded = True
        return element

    def get_samples(self, per_page: int = 100) -> list[Any]:
        """Return the standalone samples (not part of any reaction) as :class:`Sample` objects."""
        from chemotion_api.elements.sample import Sample
        out = []
        for uuid in self._adapter.standalone_sample_uuids():
            jd = self._adapter.to_sample_json(uuid)
            out.append(self._finalize(Sample(self._generic_segments, self._session, jd)))
        return out

    def get_reactions(self, per_page: int = 100) -> list[Any]:
        """Return all reactions in the archive as :class:`Reaction` objects."""
        from chemotion_api.elements.reaction import Reaction
        out = []
        for uuid in self._adapter.reaction_uuids():
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
                   interactive: bool = False) -> str:
        """Export this offline collection to a ``.eln`` crate via the standard exporter."""
        from chemotion_api.collection import Collection
        return Collection.export_eln(
            self, file_path, strict=strict,  # type: ignore[arg-type]
            ontology_lookup=ontology_lookup, ols_cache=ols_cache, authors=authors,
            progress_callback=progress_callback, interactive=interactive,
        )


def import_export_zip(path: str | Path, label: str | None = None) -> OfflineCollection:
    """Open a Chemotion export-collection ZIP (or extracted dir) as an OfflineCollection.

    Example::

        from chemotion_api.offline import import_export_zip
        import_export_zip("my_export.zip").export_eln("out.eln")
    """
    return OfflineCollection(ExportArchive(path), label=label)
