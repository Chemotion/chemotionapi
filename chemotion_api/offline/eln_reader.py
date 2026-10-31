"""Read a ``.eln`` RO-Crate archive back into navigable Python objects.

A ``.eln`` file (see `TheELNFileFormat <https://github.com/TheELNConsortium/TheELNFileFormat>`_)
is a ZIP whose single root folder contains an RO-Crate 1.1 ``ro-crate-metadata.json`` plus the
crate's payload files. This module parses that JSON-LD graph and exposes it as
:class:`ElnCrate` / :class:`ElnDataset` / :class:`ElnFile` objects with zip-slip-safe payload
access.

Supported input is what this library's own
:meth:`~chemotion_api.collection.AbstractCollection.export_eln` writes — identified by the
``chemotion-api`` producer marker (see :mod:`chemotion_api.eln_producer`). Crates from other
ELNs are rejected by default (importing them is a deferred feature); ``allow_foreign=True``
opens them anyway with best-effort generic RO-Crate parsing.

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
import re
import zipfile
from pathlib import Path
from typing import Any

from chemotion_api.authors import (
    Author, AuthorAffiliation, _normalize_orcid, _normalize_ror)
from chemotion_api.eln_producer import PRODUCER_NAME
from chemotion_api.offline.export_reader import (
    MAX_COMPRESSION_RATIO, MAX_ZIP_MEMBER_SIZE)
from chemotion_api.utils import safe_join
from chemotion_api.ontology_map import ELEMENT_TYPE_PROPERTY_ID

logger = logging.getLogger(__name__)

_METADATA_NAME = "ro-crate-metadata.json"

#: @id of the CreateAction recording the export itself (see Collection.export_eln).
_CREATE_ACTION_ID = "#ro-crate_created"

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


def _claimed_identifier(stated: Any, node_id: str, normalise) -> str:
    """Return a validated identifier from a crate, or ``""`` when neither candidate is one.

    Reading is lenient about *missing* identifiers but must not be lenient about *false* ones:
    a crate is an untrusted document, and reporting an attacker-chosen URI as somebody's ORCID
    would launder it into the next export.
    """
    for candidate in (stated, node_id):
        if isinstance(candidate, str) and candidate.strip():
            try:
                return normalise(candidate)
            except ValueError:
                continue
    return ""


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
        """Write the payload inside ``dest_dir`` and return the written path.

        ``name`` comes from the crate's metadata, which is untrusted — a crate can ask for
        ``/home/you/.ssh/authorized_keys`` or ``../../.bashrc``. :func:`safe_join` reduces it to a
        basename inside ``dest_dir``. ``read()`` was already traversal-checked via ``_member_for``;
        this is the half that actually touches the filesystem.

        :raises ValueError: if the crate's name would escape ``dest_dir``.
        """
        dest = safe_join(dest_dir, self.name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(self.read())
        return dest

    def __repr__(self) -> str:
        return f"<ElnFile {self.id!r}>"


class ElnDataset:
    """A ``Dataset`` node of the crate: the root, or an element.

    Collections are *not* Datasets -- they are contextual :class:`ElnCollection` entities, so an
    element can belong to several of them without being stored more than once."""

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
        # Generic elements are written as `./generics/<element_type>/<name>_<id>/`: the type
        # segment keeps two generic types with the same id apart, so "generics" is one level up.
        if len(parts) >= 3 and parts[-3] == "generics":
            return _PATH_KINDS["generics"]
        return None

    @property
    def source_id(self) -> int | None:
        """The originating element's numeric id, parsed from the ``…_<id>/`` path suffix
        ``export_eln`` writes (``None`` when the ``@id`` does not follow that convention)."""
        last = self.id.rstrip("/").rsplit("/", 1)[-1]
        _, _, tail = last.rpartition("_")
        # `[0-9]+`, not `isdigit()`/`isdecimal()`/`\d`: all three are Unicode-aware, so "²" raises
        # in int() and "٩" parses to a *wrong* id of 9. Only ASCII digits are an element id.
        return int(tail) if re.fullmatch(r"[0-9]+", tail) else None

    @property
    def files(self) -> list[ElnFile]:
        """The ``File`` nodes referenced by this dataset's ``hasPart``."""
        return [ElnFile(self._crate, n) for n in self._parts() if self._crate._is_type(n, "File")]

    @property
    def datasets(self) -> list[ElnDataset]:
        """The ``Dataset`` nodes referenced by this dataset's ``hasPart`` (sub-datasets)."""
        return [ElnDataset(self._crate, n)
                for n in self._parts() if self._crate._is_type(n, "Dataset")]

    @property
    def collections(self) -> list[ElnCollection]:
        """The ELN collections this element belongs to, from its ``isPartOf`` references.

        An element in several collections is stored in the crate once and names every collection
        here; the crate path says nothing about membership. Empty for the crate root and for
        crates whose producer does not record collections.
        """
        out = []
        for ref_id in _ref_ids(self.node.get("isPartOf")):
            node = self._crate._nodes.get(ref_id)
            if node is not None and self._crate._is_type(node, "Collection"):
                out.append(ElnCollection(self._crate, node))
        return out

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


class ElnCollection:
    """A ``Collection`` contextual entity: one ELN collection the crate was exported from.

    Collections are not crate folders. They are contextual entities the root ``mentions``, and
    membership runs both ways -- :attr:`elements` is the exact inverse of
    :attr:`ElnDataset.collections` -- so one element can belong to several collections without
    being stored twice.
    """

    def __init__(self, crate: ElnCrate, node: dict) -> None:
        self._crate = crate
        self.node = node

    @property
    def id(self) -> str:
        """The collection's ``@id`` (a ``#collection-…`` fragment as ``export_eln`` writes it)."""
        return self.node["@id"]

    @property
    def name(self) -> str | None:
        """The collection's label."""
        return self.node.get("name")

    @property
    def description(self) -> str | None:
        """The collection's description, if any."""
        return self.node.get("description")

    @property
    def parent(self) -> ElnCollection | None:
        """The parent collection, or ``None`` for a top-level one."""
        for ref_id in _ref_ids(self.node.get("isPartOf")):
            node = self._crate._nodes.get(ref_id)
            if node is not None and self._crate._is_type(node, "Collection"):
                return ElnCollection(self._crate, node)
        return None

    @property
    def elements(self) -> list[ElnDataset]:
        """The element datasets in this collection, from its ``hasPart`` references."""
        out = []
        for ref_id in _ref_ids(self.node.get("hasPart")):
            node = self._crate._nodes.get(ref_id)
            if node is not None and self._crate._is_type(node, "Dataset"):
                out.append(ElnDataset(self._crate, node))
        return out

    def __repr__(self) -> str:
        return f"<ElnCollection {self.id!r} name={self.name!r}>"


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
            # `rglob` descends through symlinked directories on CPython < 3.13, so an extracted
            # crate containing `payload -> /home/you` would enumerate files outside the crate into
            # `_members` — and `read_file()` would then hand their bytes to a caller that trusts
            # the crate's `@id`s. Every member is resolved and required to stay inside the root.
            # (The ZIP path is immune: zipfile never recreates symlinks on extract.)
            root = self.path.resolve()
            members = []
            for candidate in self.path.rglob("*"):
                if candidate.is_symlink() or not candidate.is_file():
                    continue
                try:
                    if not candidate.resolve().is_relative_to(root):
                        continue
                except OSError:                      # broken link, unreadable parent
                    continue
                members.append(str(candidate.relative_to(self.path)).replace("\\", "/"))
        elif zipfile.is_zipfile(self.path):
            try:
                self._zip = zipfile.ZipFile(self.path)
                members = self._zip.namelist()
            except zipfile.BadZipFile as exc:
                # is_zipfile() only sniffs for an end-of-central-directory record; opening can
                # still fail on a damaged one.
                raise ValueError(f"{self.path} is a damaged ZIP archive: {exc}") from exc
        else:
            # Reporting a truncated download as "neither a ZIP nor a crate directory" sends people
            # looking for the wrong problem. A local ZIP header with no central directory is the
            # signature of a partial file.
            if self.path.is_file() and self.path.open("rb").read(4) == b"PK\x03\x04":
                raise ValueError(
                    f"{self.path} starts like a ZIP archive but has no readable central "
                    "directory — it is most likely truncated or still downloading.")
            raise ValueError(f"{self.path} is neither a .eln ZIP archive nor a crate directory")

        # Match on the exact member basename, not a suffix -- `m.endswith(_METADATA_NAME)` would
        # also match a hostile/incidental "evil-ro-crate-metadata.json". When more than one member
        # matches (nested archive, decoy file), prefer the shallowest one: the crate root's own
        # descriptor, not one buried in a subfolder, and independent of zip namelist() order.
        _candidates = sorted(
            (m for m in members if posixpath.basename(m) == _METADATA_NAME),
            key=lambda m: m.count("/"),
        )
        meta_member = _candidates[0] if _candidates else None
        if meta_member is None:
            self.close()
            raise ValueError(f"No {_METADATA_NAME} found in {self.path}")
        # Crate-relative @ids resolve against the metadata file's folder (the crate root).
        self._root_prefix = meta_member[: -len(_METADATA_NAME)]
        self._members = set(members)
        self.metadata = json.loads(self._read_member(meta_member))
        if not isinstance(self.metadata, dict):
            self.close()
            raise ValueError(
                f"{meta_member} in {self.path} is a JSON {type(self.metadata).__name__}, not an "
                "object — an RO-Crate descriptor must be a JSON object with an @graph.")
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
    def source_eln(self) -> dict | None:
        """The ELN instance this crate's data came from, if the crate records one.

        Resolved from the root dataset's ``isBasedOn``. The node carries the instance URL as its
        ``@id`` and, when the exporter could read it, the server's ``version``. A crate exported
        offline — or one whose hostname was deliberately withheld — names
        :data:`~chemotion_api.eln_producer.OFFLINE_HOST` instead of a real host.

        :return: the source ELN node, or ``None`` when the crate does not say.
        """
        try:
            root_node = self.root.node
        except ValueError:      # a crate with no root Dataset simply does not say
            return None
        for ref_id in _ref_ids(root_node.get("isBasedOn")):
            node = self._nodes.get(ref_id)
            if node is not None:
                return node
        return None

    @property
    def producer(self) -> dict | None:
        """The graph node of the software that wrote the crate, if declared.

        Read from the ``instrument`` of the crate's ``CreateAction``, which is where the writing
        software is recorded. (The descriptor's ``sdPublisher`` names the publishing
        *organization*, not the software.)

        :return: the producer node, or ``None`` when the crate declares none.
        """
        # Match the action that created *this crate*, not merely the first CreateAction in the
        # graph. Ours is appended after every element and file node, so a scan that takes the
        # first match would deterministically lose to any other CreateAction — element
        # provenance, an instrument run, or one carried in from a re-exported foreign crate.
        for candidate in self._nodes.values():
            types = candidate.get("@type")
            types = types if isinstance(types, list) else [types]
            if "CreateAction" not in types:
                continue
            if candidate.get("@id") != _CREATE_ACTION_ID and \
                    _ref_ids(candidate.get("object")) != ["./"]:
                continue
            for ref_id in _ref_ids(candidate.get("instrument")):
                instrument = self._nodes.get(ref_id)
                if instrument is not None:
                    return instrument
        return None

    @property
    def is_chemotion_api(self) -> bool:
        """Whether this crate was written by this library (``export_eln``).

        Keys on the producer marker every chemotion-api export embeds: a
        ``SoftwareApplication`` node named ``"chemotion-api"``, referenced as the ``instrument``
        of the crate's ``CreateAction`` — see :attr:`producer`.
        """
        producer = self.producer
        return producer is not None and producer.get("name") == PRODUCER_NAME

    @property
    def datasets(self) -> list[ElnDataset]:
        """All ``Dataset`` nodes of the crate except the root itself."""
        root_id = self.root.id
        return [ElnDataset(self, n) for i, n in self._nodes.items()
                if i != root_id and self._is_type(n, "Dataset")]

    @property
    def elements(self) -> list[ElnDataset]:
        """The datasets recognizable as ELN elements (those with a resolvable :attr:`ElnDataset.kind`).

        Datasets from producers without kind information are excluded; use :attr:`datasets` for
        the full list. Collections never appear here -- see :attr:`collections`.
        """
        return [ds for ds in self.datasets if ds.kind is not None]

    @property
    def collections(self) -> list[ElnCollection]:
        """Every ELN collection the crate records, in graph order.

        Empty for crates from producers that do not describe collections.
        """
        return [ElnCollection(self, n) for n in self._nodes.values()
                if self._is_type(n, "Collection")]

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
                    ror=_claimed_identifier(org.get("identifier"), org_id, _normalize_ror),
                ))
            # A *substring* test accepted `https://evil.com/orcid.org/fake` as this person's
            # ORCID. Crates come from anywhere, so a claimed identifier is only reported when it
            # really is one — otherwise the field stays empty rather than carrying a lie.
            orcid = _claimed_identifier(person.get("identifier"), person_id, _normalize_orcid)
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
        """Raw bytes of an archive member (ZIP entry or file under the crate directory).

        Size- and ratio-capped like the export reader. This reader had no cap at all, so a 408 KB
        ``.eln`` whose metadata inflates to 400 MB was read in full — before any validation — and
        exhausted memory. One PR shipped two ZIP readers; only one of them guarded this.

        :raises ValueError: if the member is oversized or compresses too improbably.
        """
        if self._zip is not None:
            info = self._zip.getinfo(member)
            if info.file_size > MAX_ZIP_MEMBER_SIZE:
                raise ValueError(
                    f"{member} is {info.file_size} bytes, exceeding the "
                    f"{MAX_ZIP_MEMBER_SIZE}-byte member size limit")
            if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
                raise ValueError(
                    f"{member} expands {info.file_size // max(info.compress_size, 1)}x "
                    f"({info.compress_size} -> {info.file_size} bytes), above the "
                    f"{MAX_COMPRESSION_RATIO}x limit; refusing to read it")
            return self._zip.read(member)
        # The directory branch was uncapped, although an extracted crate directory is a documented,
        # equally untrusted input. There is no compression ratio to check on disk, so only the size
        # limit applies.
        on_disk = self.path / member
        size = on_disk.stat().st_size
        if size > MAX_ZIP_MEMBER_SIZE:
            raise ValueError(
                f"{member} is {size} bytes, exceeding the "
                f"{MAX_ZIP_MEMBER_SIZE}-byte member size limit")
        return on_disk.read_bytes()

    def __repr__(self) -> str:
        return f"<ElnCrate {str(self.path)!r} root={self.root.name!r}>"


def import_eln(path: str | Path, allow_foreign: bool = False) -> ElnCrate:
    """Open a ``.eln`` RO-Crate archive (ZIP or extracted directory) for reading.

    Only crates exported by this library (identified by the ``chemotion-api``
    ``SoftwareApplication`` producer marker in the metadata descriptor's ``sdPublisher``)
    are accepted; importing ``.eln`` files from other ELNs is not supported yet.

    :param allow_foreign: open crates from other producers anyway (best-effort parsing —
        the generic RO-Crate structure is read, but element kinds and authors may be absent).
    :raises ValueError: if the crate declares a different (or no) producer and
        ``allow_foreign`` is not set.

    Example::

        from chemotion_api.offline import import_eln

        with import_eln("my_project.eln") as crate:
            for ds in crate.elements:
                print(ds.kind, ds.name)
    """
    crate = ElnCrate(path)
    if not allow_foreign and not crate.is_chemotion_api:
        producer = crate.producer or {}
        described = producer.get("name") or "an unknown producer"
        crate.close()
        raise ValueError(
            f"{path} was written by {described}, not by {PRODUCER_NAME} — importing .eln "
            "files from other ELNs is not supported yet. Pass allow_foreign=True to open "
            "it anyway (best-effort, generic RO-Crate parsing)."
        )
    return crate
