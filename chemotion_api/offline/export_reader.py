"""Read a Chemotion export-collection dump and reshape it into API ``json_data``.

The export ``export.json`` is a relational dump keyed by Rails model name, with
UUID-keyed entity tables and join tables (``ReactionsProductSample`` …). This module
indexes those tables and
emits, per Sample/Reaction, a dict matching the **live REST API element JSON** so the
unmodified :class:`~chemotion_api.elements.sample.Sample` /
:class:`~chemotion_api.elements.reaction.Reaction` parsers and ``to_dcat_ap`` can consume it.

Design note: the relational ``Sample``/``Molecule``/``Reaction`` columns are the same
Rails columns the API serializes, so most fields pass through unchanged. Range strings
(``melting_point`` = ``"100...150"``) are left as-is — ``Sample._parse_properties`` parses
them itself.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import posixpath
import zipfile
from pathlib import Path
from typing import Any, Optional
from collections.abc import Iterable, Iterator

from chemotion_api.utils import break_parent_cycles

logger = logging.getLogger(__name__)

# Export archives are untrusted input (the maintainer's own PR review flagged this): a member
# claiming an implausibly large uncompressed size (a corrupt file, or a deliberately crafted
# "zip bomb" style entry) must not be read fully into memory. Chosen generously above any
# legitimate single attachment/relational dump this library expects to handle.
MAX_ZIP_MEMBER_SIZE = 500 * 1024 * 1024  # 500 MiB

#: Highest uncompressed:compressed ratio a member may have before it is refused. Ordinary JSON and
#: text compress well but not absurdly; a zip bomb is orders of magnitude beyond this.
MAX_COMPRESSION_RATIO = 200

# The five reaction-material join tables, in canonical order, mapped to the
# json_data list keys the Reaction parser expects.
_MATERIAL_JOINS: dict[str, str] = {
    "ReactionsStartingMaterialSample": "starting_materials",
    "ReactionsReactantSample": "reactants",
    "ReactionsProductSample": "products",
    "ReactionsSolventSample": "solvents",
    "ReactionsPurificationSolventSample": "purification_solvents",
}

# Collection-membership join tables (present when the export was made by a Chemotion
# version that scopes elements per collection) -> the entity foreign-key column.
_MEMBERSHIP_JOINS: dict[str, str] = {
    "CollectionsSample": "sample_id",
    "CollectionsReaction": "reaction_id",
}


def uuid_to_id(uuid: str) -> int:
    """Deterministic positive integer ID derived from a UUID string.

    The export keys entities by UUID, but the API/elements use integer ``id`` values.
    Uses the first 15 hex digits (60 bits) of the MD5 of the UUID — wide enough that a
    birthday collision within one archive is negligible (~5e-10 at 100k entities), yet
    still within a signed 64-bit integer for any downstream consumer.
    """
    return int(hashlib.md5(uuid.encode()).hexdigest()[:15], 16)


class ExportArchive:
    """Opens an export-collection ZIP (or already-extracted directory).

    Exposes the parsed ``export.json`` and resolves attachment payload bytes by the
    attachment identifier (the ``attachments/<identifier>.<ext>`` files).
    """

    def __init__(self, path: str | Path) -> None:
        """Open ``path`` as an extracted directory, a ZIP archive, or a bare ``export.json``.

        :param path: the export collection (directory, ``.zip``, or ``.json`` file).
        :raises ValueError: if ``path`` is none of those.
        """
        self.path = Path(path)
        self._zip: zipfile.ZipFile | None = None
        self._members: list[str] = []
        #: Path prefix of the folder holding export.json ('' when it sits at the archive root).
        #: Attachments are resolved relative to this, so a nested decoy cannot shadow a real one.
        self._root_prefix: str = ""
        if self.path.is_dir():
            self.export_data = self._read_json_dir("export.json")
        elif zipfile.is_zipfile(self.path):
            self._zip = zipfile.ZipFile(self.path)
            self._members = self._zip.namelist()
            self.export_data = self._read_json_zip("export.json")
        elif self.path.is_file() and self.path.suffix == ".json":
            # A bare relational dump (export.json under any name); attachments, if any, live in a
            # sibling ``attachments/`` directory next to it.
            self.export_data = json.loads(self.path.read_text(encoding="utf-8"))
            self.path = self.path.parent
        else:
            raise ValueError(
                f"{self.path} is neither an export JSON file, a directory, nor a ZIP export archive"
            )
        # identifier (without extension) -> archive member path for attachments
        self._attachment_members: dict[str, str] = {}
        # `attachments/` must be the one beside export.json — `parts[-2] == "attachments"` matched
        # it at ANY depth, so `docs/attachments/abc.png` still shadowed the genuine
        # `attachments/abc.png`, and which one won was decided by central-directory order, which
        # whoever wrote the archive controls. The decoy's bytes would then be exported under the
        # real attachment's filename with a correct sha256 computed over them, so the crate's own
        # integrity data would certify the swap and nothing downstream could detect it.
        # `export_collections.rb` writes `attachments/<identifier><ext>` beside `export.json`.
        prefix = self._root_prefix
        for member in (self._members or self._list_dir_members()):
            normalised = member.replace(os.sep, "/")
            if prefix and not normalised.startswith(prefix):
                continue
            parts = [p for p in normalised[len(prefix):].split("/") if p]
            if len(parts) != 2 or parts[0] != "attachments":
                continue
            stem, _ext = os.path.splitext(parts[-1])
            if stem in self._attachment_members:
                logger.warning(
                    "Archive contains two attachment payloads for %r (%s and %s); keeping the "
                    "first and ignoring the duplicate.", stem, self._attachment_members[stem], member)
                continue
            self._attachment_members[stem] = member

    # -- internal readers ---------------------------------------------------
    def _check_member_size(self, member: str) -> None:
        """Raise ``ValueError`` if ``member``'s (uncompressed) size exceeds :data:`MAX_ZIP_MEMBER_SIZE`.

        Guards against fully reading an oversized member from an untrusted archive into memory.
        """
        if self._zip is None:                   # `assert` here is stripped under `python -O`,
            raise RuntimeError(                 # which would silence the guard entirely
                "_check_member_size called on a directory archive; use _check_file_size")
        info = self._zip.getinfo(member)
        size = info.file_size
        if size > MAX_ZIP_MEMBER_SIZE:
            raise ValueError(
                f"{member} is {size} bytes, exceeding the {MAX_ZIP_MEMBER_SIZE}-byte member size limit")
        # A size cap alone is not a zip-bomb defence: 400 MB from a 400 KB archive passes a
        # 500 MiB limit comfortably. Compression ratio is what distinguishes a bomb from a big file.
        if info.compress_size and size / info.compress_size > MAX_COMPRESSION_RATIO:
            raise ValueError(
                f"{member} expands {size // max(info.compress_size, 1)}x "
                f"({info.compress_size} -> {size} bytes), above the {MAX_COMPRESSION_RATIO}x limit; "
                "refusing to read it")

    def _locate(self, name: str) -> str | None:
        """Return the shallowest ZIP member whose basename is exactly ``name``.

        Exact basename, not ``endswith``: ``endswith("export.json")`` also matches a hostile or
        incidental ``evil-export.json``. Shallowest-wins, not ``namelist()`` order: the order of
        the central directory is chosen by whoever wrote the archive, so a nested decoy could
        otherwise be placed ahead of the genuine root file and win. Matches the tiebreak in
        ``eln_reader._locate_metadata`` and ``ontology_patch``.
        """
        candidates = sorted(
            (m for m in self._members if posixpath.basename(m.replace(os.sep, "/")) == name),
            key=lambda m: m.replace(os.sep, "/").count("/"),
        )
        return candidates[0] if candidates else None

    def _read_json_zip(self, name: str) -> dict:
        """Load and parse the shallowest ZIP member named ``name``."""
        member = self._locate(name)
        if member is None:
            raise FileNotFoundError(f"{name} not found in {self.path}")
        self._root_prefix = member[: -len(name)]
        self._check_member_size(member)
        with self._zip.open(member) as fh:  # type: ignore[union-attr]
            return json.load(fh)

    def _read_json_dir(self, name: str) -> dict:
        """Load and parse ``name`` from the extracted directory, searching recursively if needed."""
        candidate = self.path / name
        if not candidate.is_file():
            # Shallowest-wins here too, and rglob's order is filesystem-dependent.
            matches = sorted((m for m in self.path.rglob(name) if m.is_file()),
                             key=lambda m: len(m.relative_to(self.path).parts))
            if not matches:
                raise FileNotFoundError(f"{name} not found under {self.path}")
            candidate = matches[0]
        rel = candidate.relative_to(self.path).as_posix()
        self._root_prefix = rel[: -len(name)]
        # 5: a directory crate gets no zip metadata, so cap on the real file size instead.
        self._check_file_size(candidate)
        return json.loads(candidate.read_text(encoding="utf-8"))

    def _check_file_size(self, candidate: Path) -> None:
        """Raise ``ValueError`` if an on-disk member exceeds :data:`MAX_ZIP_MEMBER_SIZE`.

        The ZIP branch was capped but the extracted-directory branch was not, although a crate
        directory is an equally supported and equally untrusted input.
        """
        size = candidate.stat().st_size
        if size > MAX_ZIP_MEMBER_SIZE:
            raise ValueError(
                f"{candidate} is {size} bytes, exceeding the {MAX_ZIP_MEMBER_SIZE}-byte limit")

    def _list_dir_members(self) -> list[str]:
        """Return all file paths under the directory, relative to it (empty if not a directory)."""
        if self.path.is_dir():
            return [str(p.relative_to(self.path)) for p in self.path.rglob("*") if p.is_file()]
        return []

    # -- attachment bytes ---------------------------------------------------
    def has_attachment(self, identifier: str) -> bool:
        """Return ``True`` if an attachment payload with this identifier is present in the archive."""
        return identifier in self._attachment_members

    def read_attachment(self, identifier: str) -> bytes:
        """Return the payload bytes for an attachment identifier, or ``b""`` if absent.

        :raises ValueError: if the member exceeds :data:`MAX_ZIP_MEMBER_SIZE` or
            :data:`MAX_COMPRESSION_RATIO`. :meth:`iter_attachment` streams rather than buffering,
            but enforces the same limits — it is not a way around them.
        """
        member = self._attachment_members.get(identifier)
        if member is None:
            logger.warning("Attachment payload %s not present in archive", identifier)
            return b""
        if self._zip is not None:
            self._check_member_size(member)
            return self._zip.read(member)
        self._check_file_size(self.path / member)
        return (self.path / member).read_bytes()

    def iter_attachment(self, identifier: str, chunk_size: int = 1 << 20) -> Iterator[bytes]:
        """Yield an attachment's payload in chunks; yields nothing if the identifier is absent.

        :raises ValueError: if the member exceeds the size or compression-ratio limits.

        Streaming caps the memory used at ``chunk_size``, but not the bytes written: this is the
        path ``export_eln`` takes for every offline attachment (``_write_crate_zip_inner`` prefers
        ``iter_file()``), so an uncapped member could be streamed straight into the output crate
        until the disk filled. The same limits as :meth:`read_attachment` apply.
        """
        member = self._attachment_members.get(identifier)
        if member is None:
            logger.warning("Attachment payload %s not present in archive", identifier)
            return
        if self._zip is not None:
            self._check_member_size(member)
        else:
            self._check_file_size(self.path / member)
        if self._zip is not None:
            with self._zip.open(member) as fh:
                while True:
                    chunk = fh.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk
        else:
            with open(self.path / member, "rb") as fh:
                while True:
                    chunk = fh.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk

    def close(self) -> None:
        """Close the underlying ZIP file handle, if one is open."""
        if self._zip is not None:
            self._zip.close()
            self._zip = None


def _table(export_data: dict[str, Any], name: str) -> dict[str, dict]:
    """Return the ``name`` table of a dump as ``{uuid: record}``, dropping malformed rows.

    A Rails dump is an untrusted document. The two failure shapes are treated differently on
    purpose: a table that is not an object at all is a *structurally* wrong dump and is worth
    refusing, whereas one bad row among thousands should not abort an import somebody is running
    precisely to salvage the rest.
    """
    table = export_data.get(name)
    if table is None:
        return {}
    if not isinstance(table, dict):
        raise ValueError(
            f"export.json table {name!r} is a {type(table).__name__}, expected an object of "
            "{uuid: record}. This does not look like a Chemotion export dump.")
    rows = {k: v for k, v in table.items() if isinstance(v, dict)}
    if len(rows) != len(table):
        logger.warning("Ignoring %d malformed row(s) in export.json table %r (not objects)",
                       len(table) - len(rows), name)
    return rows


class ExportAdapter:
    """Indexes an export dump and emits API-shaped ``json_data`` per element."""

    def __init__(self, export_data: dict[str, Any]) -> None:
        """Index the relational dump (material joins, container hierarchy, attachments) for fast lookup.

        :param export_data: the parsed ``export.json`` relational dump.
        """
        self._export = export_data
        self.reactions: dict[str, dict] = _table(export_data, "Reaction")
        self.samples: dict[str, dict] = _table(export_data, "Sample")
        self.molecules: dict[str, dict] = _table(export_data, "Molecule")
        self.containers: dict[str, dict] = _table(export_data, "Container")
        self.attachments: dict[str, dict] = _table(export_data, "Attachment")
        self.collections: dict[str, dict] = _table(export_data, "Collection")

        # reaction_uuid -> {role_key: [join_record, ...]}
        self._material_links: dict[str, dict[str, list[dict]]] = {}
        for table, role_key in _MATERIAL_JOINS.items():
            for record in _table(export_data, table).values():
                rxn_id = record.get("reaction_id")
                if rxn_id:
                    self._material_links.setdefault(rxn_id, {}).setdefault(role_key, []).append(record)

        # Container hierarchy: parent_uuid -> [child_uuid, ...]
        self._children_index: dict[str, list[str]] = {}
        for cid, cdata in self.containers.items():
            parent = cdata.get("parent_id")
            if parent:
                self._children_index.setdefault(parent, []).append(cid)

        # containable_id -> root container uuid
        self._root_by_containable: dict[str, str] = {}
        for cid, cdata in self.containers.items():
            if cdata.get("container_type") == "root" and cdata.get("containable_id"):
                self._root_by_containable[cdata["containable_id"]] = cid

        # attachable_id (container uuid) -> [attachment_record, ...]
        self._attachments_by_attachable: dict[str, list[dict]] = {}
        for adata in self.attachments.values():
            aid = adata.get("attachable_id")
            if aid:
                self._attachments_by_attachable.setdefault(aid, []).append(adata)

        # sample_uuids referenced by any reaction (to find standalone samples)
        self._samples_in_reactions: set[str] = set()
        for roles in self._material_links.values():
            for records in roles.values():
                for rec in records:
                    if rec.get("sample_id"):
                        self._samples_in_reactions.add(rec["sample_id"])

        # Collection membership: collection_uuid -> {fk_column: {entity_uuid, ...}}.
        # Exports from current Chemotion versions carry CollectionsSample/CollectionsReaction
        # join tables; without them elements cannot be scoped per collection (flat fallback).
        self._membership: dict[str, dict[str, set[str]]] = {}
        self.has_membership_data = False
        for table, fk in _MEMBERSHIP_JOINS.items():
            join_table: dict[str, dict] | None = export_data.get(table)
            if join_table is None:
                continue
            self.has_membership_data = True
            for record in join_table.values():
                col_uuid, entity_uuid = record.get("collection_id"), record.get(fk)
                if col_uuid and entity_uuid:
                    self._membership.setdefault(col_uuid, {}).setdefault(fk, set()).add(entity_uuid)

    # -- molecules ----------------------------------------------------------
    def to_molecule_json(self, mol_uuid: str | None) -> dict:
        """Return the molecule's Rails columns plus a derived integer ``id`` (empty dict if absent)."""
        if not mol_uuid:
            return {"id": None}
        mol = self.molecules.get(mol_uuid)
        if mol is None:
            # A dangling reference: the sample names a molecule the dump does not contain. Deriving
            # an id from the uuid anyway would publish an identifier with nothing behind it —
            # `to_dcat_ap()` would mint `chemotion://molecule/<id>` for a molecule that does not
            # exist. Both consumers handle a null id (the IRI falls back to #EvaluatedCompound).
            logger.warning("Sample references molecule %s, which is absent from the export dump; "
                           "emitting no molecule id", mol_uuid)
            return {"id": None}
        out = dict(mol)  # pass through the Rails columns the Molecule wrapper reads
        out["id"] = uuid_to_id(mol_uuid)
        return out

    # -- attachments / analyses --------------------------------------------
    def _attachment_json(self, record: dict) -> dict:
        """Reshape an export attachment record into the API attachment JSON shape."""
        identifier = record.get("identifier") or record.get("key") or ""
        return {
            "id": identifier,
            "identifier": identifier,
            "filename": record.get("filename") or identifier,
            "filesize": record.get("filesize"),
            "content_type": record.get("content_type"),
        }

    def _datasets_json(self, analysis_uuid: str) -> list[dict]:
        """Return the API-shaped dataset nodes (with attachments) under an analysis container."""
        datasets: list[dict] = []
        for ds_uuid in self._children_index.get(analysis_uuid, []):
            ds = self.containers.get(ds_uuid, {})
            if ds.get("container_type") != "dataset":
                continue
            atts = [self._attachment_json(a) for a in self._attachments_by_attachable.get(ds_uuid, [])]
            datasets.append({
                "id": uuid_to_id(ds_uuid),
                "name": ds.get("name") or "",
                "description": ds.get("description") or "",
                "dataset": None,
                "attachments": atts,
            })
        return datasets

    def build_container_json(self, entity_uuid: str) -> dict | None:
        """Reconstruct the live ``container`` tree: root -> [analyses] -> [analysis] -> [dataset]."""
        root_uuid = self._root_by_containable.get(entity_uuid)
        if not root_uuid:
            return None
        analysis_nodes: list[dict] = []
        for analyses_uuid in self._children_index.get(root_uuid, []):
            if self.containers.get(analyses_uuid, {}).get("container_type") != "analyses":
                continue
            for ac_uuid in self._children_index.get(analyses_uuid, []):
                ac = self.containers.get(ac_uuid, {})
                if ac.get("container_type") != "analysis":
                    continue
                em = ac.get("extended_metadata") or {}
                analysis_nodes.append({
                    "id": uuid_to_id(ac_uuid),
                    "name": ac.get("name") or "",
                    "description": ac.get("description") or em.get("content") or "",
                    "container_type": "analysis",
                    "extended_metadata": em,
                    "children": self._datasets_json(ac_uuid),
                })
        return {"children": [{"container_type": "analyses", "children": analysis_nodes}]}

    # -- samples ------------------------------------------------------------
    def to_sample_json(self, sample_uuid: str, join_record: dict | None = None) -> dict:
        """Reshape a sample (and its molecule/container) into the live API element JSON.

        :param sample_uuid: UUID of the sample in the export dump.
        :param join_record: optional reaction-material join record whose role fields
            (equivalent, coefficient, reference, ...) override the sample's own.
        :return: an API-shaped sample ``json_data`` dict.
        """
        sample = self.samples.get(sample_uuid, {})
        out = dict(sample)  # Rails columns line up with what _parse_properties reads
        out["id"] = uuid_to_id(sample_uuid)
        out["molecule"] = self.to_molecule_json(sample.get("molecule_id"))
        # join-table fields take precedence (equivalent/coefficient/reference/role data)
        if join_record:
            for key in ("equivalent", "coefficient", "reference", "position",
                        "gas_type", "gas_phase_data", "show_label", "waste"):
                if join_record.get(key) is not None:
                    out[key] = join_record[key]
        out.setdefault("sample_type", sample.get("sample_type") or "Micromolecule")
        out["type"] = "Sample"
        container = self.build_container_json(sample_uuid)
        if container is not None:
            out["container"] = container
        out.setdefault("attachments", [])
        return out

    # -- reactions ----------------------------------------------------------
    def to_reaction_json(self, rxn_uuid: str) -> dict:
        """Reshape a reaction (with its material roles and container) into the live API element JSON.

        :param rxn_uuid: UUID of the reaction in the export dump.
        :return: an API-shaped reaction ``json_data`` dict.
        """
        rxn = self.reactions.get(rxn_uuid, {})
        out = dict(rxn)
        out["id"] = uuid_to_id(rxn_uuid)
        roles = self._material_links.get(rxn_uuid, {})
        for role_key in _MATERIAL_JOINS.values():
            # `.get("position", 0)` covers a *missing* key but not `"position": null`, which a
            # Rails dump emits routinely -> TypeError, aborting the whole import. Same
            # null-vs-missing idiom as the join-record loop above.
            records = sorted(
                roles.get(role_key, []),
                key=lambda r: r["position"] if r.get("position") is not None else 0)
            out[role_key] = [
                self.to_sample_json(rec["sample_id"], rec)
                for rec in records if rec.get("sample_id") in self.samples
            ]
        rxn_long = rxn.get("rinchi_long_key") or rxn.get("rinchi_string")
        if rxn_long:
            out["rinchi_long_key"] = rxn_long
        container = self.build_container_json(rxn_uuid)
        if container is not None:
            out["container"] = container
        out.setdefault("attachments", [])
        out.setdefault("segments", rxn.get("segments", []) or [])
        out["type"] = "Reaction"
        return out

    # -- collection membership ---------------------------------------------
    def _scope(self, uuids: Iterable[str], collection_uuid: str | None,
               fk: str) -> list[str]:
        """Filter entity UUIDs to those joined to ``collection_uuid`` (no-op without a scope)."""
        if collection_uuid is None:
            return list(uuids)
        member = self._membership.get(collection_uuid, {}).get(fk, set())
        return [u for u in uuids if u in member]

    def reaction_uuids(self, collection_uuid: str | None = None) -> list[str]:
        """Return the UUIDs of the reactions in the dump (scoped to one collection if given)."""
        return self._scope(self.reactions.keys(), collection_uuid, "reaction_id")

    def standalone_sample_uuids(self, collection_uuid: str | None = None) -> list[str]:
        """Return the UUIDs of samples not exported as part of a reaction, within this scope.

        "Part of a reaction" is judged against the reactions **in the same scope**, not the whole
        dump. Using the dump-wide set meant a sample that belongs to the collection being exported
        but whose only reaction belongs to a *different* collection appeared in neither list: not
        as a reaction material (the reaction is out of scope) and not as a standalone sample (it
        is in some reaction somewhere). It vanished from the crate with no warning.
        """
        in_scope_reactions = set(self.reaction_uuids(collection_uuid))
        covered = {rec["sample_id"]
                   for rxn_uuid in in_scope_reactions
                   for records in self._material_links.get(rxn_uuid, {}).values()
                   for rec in records if rec.get("sample_id")}
        standalone = (u for u in self.samples if u not in covered)
        return self._scope(standalone, collection_uuid, "sample_id")

    def collection_label(self) -> str:
        """Return the first collection's label, or ``"Exported Collection"`` as a fallback."""
        first = next(iter(self.collections.values()), {})
        return first.get("label", "") or "Exported Collection"

    def collection_tree(self) -> list[dict]:
        """Return the dump's collections as ``{"uuid", "label", "parent"}`` records.

        ``parent`` is the UUID of the direct parent (the last segment of the exported
        ``ancestry`` field, which Chemotion remaps to UUIDs) — ``None`` for top-level
        collections or when the parent is not part of the dump. Dump order is preserved
        (Chemotion exports ancestors before their descendants).
        """
        parent_of = {}
        for uuid, record in self.collections.items():
            ancestry = [a for a in (record.get("ancestry") or "").split("/") if a]
            parent_of[uuid] = ancestry[-1] if ancestry and ancestry[-1] in self.collections else None

        # A cycle gives every node a parent, so nothing qualifies as a root and the caller's tree
        # comes out empty — which previously meant the export silently contained no elements at
        # all and still reported success. Promote the offenders to roots and say so.
        cyclic = break_parent_cycles(parent_of)
        if cyclic:
            logger.warning(
                "Collection ancestry in this dump forms a cycle involving %d collection(s); "
                "treating them as top-level so their contents are still exported: %s",
                len(cyclic), ", ".join(sorted(cyclic)[:5]))

        return [{"uuid": uuid,
                 "label": self.collections[uuid].get("label") or "Collection",
                 "parent": None if uuid in cyclic else parent}
                for uuid, parent in parent_of.items()]
