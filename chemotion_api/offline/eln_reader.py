"""Read a ``.eln`` RO-Crate archive back into navigable Python objects.

A ``.eln`` file (see `TheELNFileFormat <https://github.com/TheELNConsortium/TheELNFileFormat>`_)
is a ZIP whose single root folder contains an RO-Crate 1.1 ``ro-crate-metadata.json`` plus the
crate's payload files. This module parses that JSON-LD graph — regardless of which application
produced it (this library's :meth:`~chemotion_api.collection.Collection.export_eln`, a Chemotion
server, eLabFTW, …) — and exposes it as :class:`ElnCrate` / :class:`ElnDataset` /
:class:`ElnFile` objects with zip-slip-safe payload access.

Entry point: :func:`import_eln`::

    from chemotion_api.offline import import_eln

    with import_eln("my_project.eln") as crate:
        print(crate.root.name, [a.name for a in crate.authors])
        for ds in crate.elements:
            print(ds.kind, ds.name, [f.name for f in ds.files])
            for f in ds.files:
                data = f.read()
"""
from __future__ import annotations

import json
import logging
import posixpath
import zipfile
from pathlib import Path
from typing import Any

from chemotion_api.authors import Author, AuthorAffiliation
from chemotion_api.ontology_map import ELEMENT_TYPE_PROPERTY_ID

logger = logging.getLogger(__name__)

_METADATA_NAME = "ro-crate-metadata.json"

# Crate folder segment (as written by export_eln) -> element kind.
_PATH_KINDS = {
    "samples": "sample",
    "reactions": "reaction",
    "wellplates": "wellplate",
    "research_plans": "research_plan",
    "generics": "generic",
}


def _as_list(value: Any) -> list:
    """Normalize a JSON-LD value that may be a single object or a list into a list."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _ref_ids(value: Any) -> list[str]:
    """Extract the ``@id`` strings from a JSON-LD reference value (single ref, list, or bare id)."""
    ids = []
    for ref in _as_list(value):
        if isinstance(ref, dict) and isinstance(ref.get("@id"), str):
            ids.append(ref["@id"])
        elif isinstance(ref, str):
            ids.append(ref)
    return ids


class ElnFile:
    """A ``File`` node of the crate, with access to its payload bytes."""

    def __init__(self, crate: ElnCrate, node: dict) -> None:
        self._crate = crate
        self.node = node

    @property
    def id(self) -> str:
        """The file's crate-relative ``@id`` (its path inside the crate)."""
        return self.node["@id"]

    @property
    def name(self) -> str:
        """The file's name (falls back to the last path segment of its ``@id``)."""
        return self.node.get("name") or posixpath.basename(self.id.rstrip("/"))

    @property
    def encoding_format(self) -> str | None:
        """The file's MIME type, if recorded."""
        return self.node.get("encodingFormat")

    @property
    def content_size(self) -> int | None:
        """The file's size in bytes as recorded in the metadata (``None`` if absent/unparsable)."""
        raw = self.node.get("contentSize")
        try:
            return int(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None

    def read(self) -> bytes:
        """Return the file's payload bytes from the archive.

        :raises FileNotFoundError: if the metadata references a file the archive does not contain.
        """
        return self._crate.read_file(self.id)

    def extract(self, dest_dir: str | Path) -> Path:
        """Write the payload to ``dest_dir/<name>`` and return the written path."""
        dest = Path(dest_dir) / self.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(self.read())
        return dest

    def __repr__(self) -> str:
        return f"<ElnFile {self.id!r}>"


class ElnDataset:
    """A ``Dataset`` node of the crate (the root, a collection folder, or an element)."""

    def __init__(self, crate: ElnCrate, node: dict) -> None:
        self._crate = crate
        self.node = node

    @property
    def id(self) -> str:
        """The dataset's crate-relative ``@id``."""
        return self.node["@id"]

    @property
    def name(self) -> str | None:
        """The dataset's human-readable name."""
        return self.node.get("name")

    @property
    def description(self) -> str | None:
        """The dataset's description, if any."""
        return self.node.get("description")

    @property
    def types(self) -> list[str]:
        """The node's ``@type`` value(s), always as a list."""
        return [t for t in _as_list(self.node.get("@type")) if isinstance(t, str)]

    @property
    def kind(self) -> str | None:
        """The element kind (``"sample"``, ``"reaction"``, …) if it can be determined.

        Resolution order: the ontology placeholder written by ``export_eln``
        (``variableMeasured`` entry with ``propertyID == ELEMENT_TYPE_PROPERTY_ID``) → the
        crate folder the dataset lives in (``samples/``, ``reactions/``, …). ``None`` for
        crates from other producers that carry neither.
        """
        for pv in _as_list(self.node.get("variableMeasured")):
            if isinstance(pv, dict) and pv.get("propertyID") == ELEMENT_TYPE_PROPERTY_ID:
                value = pv.get("value")
                if isinstance(value, str):
                    return value
        parts = [p for p in self.id.split("/") if p and p != "."]
        if len(parts) >= 2 and parts[-2] in _PATH_KINDS:
            return _PATH_KINDS[parts[-2]]
        return None

    @property
    def source_id(self) -> int | None:
        """The originating element's numeric id, parsed from the ``…_<id>/`` path suffix
        ``export_eln`` writes (``None`` when the ``@id`` does not follow that convention)."""
        last = self.id.rstrip("/").rsplit("/", 1)[-1]
        _, _, tail = last.rpartition("_")
        return int(tail) if tail.isdigit() else None

    @property
    def files(self) -> list[ElnFile]:
        """The ``File`` nodes referenced by this dataset's ``hasPart``."""
        return [ElnFile(self._crate, n) for n in self._parts() if self._crate._is_type(n, "File")]

    @property
    def datasets(self) -> list[ElnDataset]:
        """The ``Dataset`` nodes referenced by this dataset's ``hasPart`` (sub-datasets)."""
        return [ElnDataset(self._crate, n)
                for n in self._parts() if self._crate._is_type(n, "Dataset")]

    def _parts(self) -> list[dict]:
        """The resolved graph nodes of this dataset's ``hasPart`` references."""
        out = []
        for ref_id in _ref_ids(self.node.get("hasPart")):
            node = self._crate._nodes.get(ref_id)
            if node is not None:
                out.append(node)
        return out

    def __repr__(self) -> str:
        return f"<ElnDataset {self.id!r} name={self.name!r} kind={self.kind!r}>"


class ElnCrate:
    """An opened ``.eln`` RO-Crate archive (ZIP or already-extracted directory).

    Usable as a context manager; :meth:`close` releases the underlying ZIP handle.
    """

    def __init__(self, path: str | Path) -> None:
        """Open ``path`` as a ``.eln`` ZIP or an extracted crate directory.

        :raises ValueError: if ``path`` is neither, or contains no ``ro-crate-metadata.json``.
        """
        self.path = Path(path)
        self._zip: zipfile.ZipFile | None = None
        if self.path.is_dir():
            members = [str(p.relative_to(self.path)).replace("\\", "/")
                       for p in self.path.rglob("*") if p.is_file()]
        elif zipfile.is_zipfile(self.path):
            self._zip = zipfile.ZipFile(self.path)
            members = self._zip.namelist()
        else:
            raise ValueError(f"{self.path} is neither a .eln ZIP archive nor a crate directory")

        meta_member = next((m for m in members if m.endswith(_METADATA_NAME)), None)
        if meta_member is None:
            self.close()
            raise ValueError(f"No {_METADATA_NAME} found in {self.path}")
        # Crate-relative @ids resolve against the metadata file's folder (the crate root).
        self._root_prefix = meta_member[: -len(_METADATA_NAME)]
        self._members = set(members)
        self.metadata: dict = json.loads(self._read_member(meta_member))
        self._nodes: dict[str, dict] = {
            n["@id"]: n for n in self.metadata.get("@graph", [])
            if isinstance(n, dict) and isinstance(n.get("@id"), str)
        }

    # -- context manager ----------------------------------------------------
    def close(self) -> None:
        """Release the underlying ZIP handle (no-op for directory crates)."""
        if self._zip is not None:
            self._zip.close()
            self._zip = None

    def __enter__(self) -> ElnCrate:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- graph access ---------------------------------------------------------
    @staticmethod
    def _is_type(node: dict, type_name: str) -> bool:
        """Whether ``type_name`` appears in the node's ``@type`` (string or list)."""
        return type_name in _as_list(node.get("@type"))

    @property
    def descriptor(self) -> dict:
        """The crate's metadata descriptor node (``@id == "ro-crate-metadata.json"``).

        :raises ValueError: if the graph has no descriptor (not a valid RO-Crate).
        """
        node = self._nodes.get(_METADATA_NAME)
        if node is None:
            raise ValueError(f"{self.path} has no RO-Crate metadata descriptor node")
        return node

    @property
    def root(self) -> ElnDataset:
        """The crate's root Dataset (the descriptor's ``about`` target, conventionally ``"./"``).

        :raises ValueError: if the root dataset cannot be located.
        """
        for root_id in _ref_ids(self.descriptor.get("about")) + ["./"]:
            node = self._nodes.get(root_id)
            if node is not None:
                return ElnDataset(self, node)
        raise ValueError(f"{self.path} has no root Dataset node")

    @property
    def date_created(self) -> str | None:
        """The crate's creation timestamp from the descriptor, if recorded (ISO string)."""
        return self.descriptor.get("dateCreated")

    @property
    def datasets(self) -> list[ElnDataset]:
        """All ``Dataset`` nodes of the crate except the root itself."""
        root_id = self.root.id
        return [ElnDataset(self, n) for i, n in self._nodes.items()
                if i != root_id and self._is_type(n, "Dataset")]

    @property
    def elements(self) -> list[ElnDataset]:
        """The datasets recognizable as ELN elements (those with a resolvable :attr:`ElnDataset.kind`).

        Collection-folder datasets and datasets from producers without kind information are
        excluded; use :attr:`datasets` for the full list.
        """
        return [ds for ds in self.datasets if ds.kind is not None]

    @property
    def files(self) -> list[ElnFile]:
        """All ``File`` nodes of the crate."""
        return [ElnFile(self, n) for n in self._nodes.values() if self._is_type(n, "File")]

    def get_dataset(self, dataset_id: str) -> ElnDataset | None:
        """Return the dataset with this ``@id``, or ``None`` if the graph has no such node."""
        node = self._nodes.get(dataset_id)
        return ElnDataset(self, node) if node is not None and self._is_type(node, "Dataset") else None

    @property
    def authors(self) -> list[Author]:
        """The crate's authors as :class:`~chemotion_api.authors.Author` objects.

        Reconstructed from the root dataset's ``author`` references and their ``Person`` /
        ``Organization`` contextual entities (ORCID as the Person ``@id``/``identifier``, ROR as
        the Organization's). Persons without ORCID/affiliations still come back, just with
        empty fields — reading is lenient where exporting is strict.
        """
        authors = []
        for person_id in _ref_ids(self.root.node.get("author")):
            person = self._nodes.get(person_id, {"@id": person_id})
            affiliations = []
            for org_id in _ref_ids(person.get("affiliation")):
                org = self._nodes.get(org_id, {})
                affiliations.append(AuthorAffiliation(
                    name=org.get("name") or "",
                    ror=org.get("identifier") or org_id,
                ))
            orcid = person.get("identifier") or (person_id if "orcid.org" in person_id else "")
            authors.append(Author(name=person.get("name") or "", orcid=orcid,
                                  affiliations=affiliations, email=person.get("email")))
        return authors

    # -- payload access -------------------------------------------------------
    def _member_for(self, crate_relative_id: str) -> str:
        """Resolve a crate-relative ``@id`` to an archive member path, zip-slip safe.

        :raises ValueError: if the id escapes the crate root (``..``) or is absolute.
        """
        rel = posixpath.normpath(crate_relative_id.removeprefix("./"))
        if rel.startswith(("..", "/")) or (len(rel) > 1 and rel[1] == ":"):
            raise ValueError(f"unsafe crate path {crate_relative_id!r}")
        return self._root_prefix + rel

    def has_file(self, crate_relative_id: str) -> bool:
        """Whether the archive actually contains a payload for this crate-relative ``@id``."""
        try:
            return self._member_for(crate_relative_id) in self._members
        except ValueError:
            return False

    def read_file(self, crate_relative_id: str) -> bytes:
        """Return the payload bytes for a crate-relative ``@id``.

        :raises FileNotFoundError: if the archive contains no such member.
        :raises ValueError: if the id is unsafe (path traversal).
        """
        member = self._member_for(crate_relative_id)
        if member not in self._members:
            raise FileNotFoundError(f"{crate_relative_id} not present in {self.path}")
        return self._read_member(member)

    def _read_member(self, member: str) -> bytes:
        """Raw bytes of an archive member (ZIP entry or file under the crate directory)."""
        if self._zip is not None:
            return self._zip.read(member)
        return (self.path / member).read_bytes()

    def __repr__(self) -> str:
        return f"<ElnCrate {str(self.path)!r} root={self.root.name!r}>"


def import_eln(path: str | Path) -> ElnCrate:
    """Open a ``.eln`` RO-Crate archive (ZIP or extracted directory) for reading.

    Example::

        from chemotion_api.offline import import_eln

        with import_eln("my_project.eln") as crate:
            for ds in crate.elements:
                print(ds.kind, ds.name)
    """
    return ElnCrate(path)
