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
import re
import os
import typing
import logging
from datetime import datetime, UTC
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

from chemotion_api.eln_producer import OFFLINE_HOST
from chemotion_api.utils import break_parent_cycles, normalise_range_value, quill_to_text
from chemotion_api.elements import ElementSet, AbstractElement
from collections.abc import Mapping

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


#: ``@id`` of the node declaring what the export left out.
_MANIFEST_ID = "#export-manifest"

#: The RO-Crate metadata descriptor's fixed @id.
_METADATA_ID = "ro-crate-metadata.json"

#: Human wording for each ``skipped`` kind/stage, so the crate explains the omission in stable
#: terms rather than echoing a raw exception (which is both unstable and, for a download failure,
#: carries the server's hostname).
_OMISSION_REASONS = {
    "download": "its file could not be retrieved from the server",
    "offline_reconstruction": "offline ingestion does not reconstruct this element type",
    "to_dcat_ap": "it could not be mapped to chem-dcat-ap, so it is described generically",
    "retrieve": "it could not be retrieved from the server",
    "load": "it could not be loaded",
    "metadata": "the source did not provide this metadata",
}


def build_skipped_manifest(skipped: list[dict]) -> list[dict]:
    """Describe what the export left out, as ordinary RO-Crate entities.

    Without this a partial crate is indistinguishable from a complete one: the root description
    reads the same either way, and a reader has no way to learn that four wellplates never made
    it in.

    Deliberately plain: a ``CreativeWork`` carrying prose, plus one ``PropertyValue`` per kind of
    omission under ``variableMeasured`` — which is the format's own mechanism for structured
    extras. No new vocabulary, and nothing a consumer needs to special-case.

    Raw exception text is **not** included. It is unstable across runs and, for a failed
    download, embeds the server's hostname — which would defeat ``disclose_host=False``.

    :param skipped: the export's omission records.
    :return: the nodes to add to ``@graph``; empty when nothing was omitted.
    """
    if not skipped:
        return []

    counts: dict[tuple[str, str], int] = {}
    for entry in skipped:
        key = (str(entry.get("kind", "item")), str(entry.get("stage", "")))
        counts[key] = counts.get(key, 0) + int(entry.get("count", 1) or 1)

    measured, lines = [], []
    for index, ((kind, stage), count) in enumerate(sorted(counts.items()), start=1):
        reason = _OMISSION_REASONS.get(stage, "it could not be included")
        lines.append(f"{count} \u00d7 {kind}: {reason}")
        measured.append({
            "@id": f"{_MANIFEST_ID}-{index}",
            "@type": "PropertyValue",
            "propertyID": f"chemotion:omitted/{kind}",
            "name": f"{kind} omitted",
            "value": str(count),
            "description": reason,
        })

    manifest = {
        "@id": _MANIFEST_ID,
        "@type": "CreativeWork",
        "name": "Export manifest",
        "description": ("This crate is incomplete. The following were omitted: "
                        + "; ".join(lines) + "."),
        "variableMeasured": [{"@id": node["@id"]} for node in measured],
    }
    return [manifest, *measured]


def _write_crate_zip(file_path: str, root_folder: str, metadata_dict: dict, elem_files: dict,
                     elem_paths: dict,
                     skipped: list[dict],
                     progress: Callable[[str], None] | None = None,
                     strict: bool = False, declare_skipped: bool = True,
                     mask_host: str | None = None) -> None:
    """Write the RO-Crate ZIP: ro-crate-metadata.json + each element's attachment files.

    ``elem_files`` maps each element key to a list of ``(attachment, safe_filename)`` pairs —
    the sanitized/disambiguated filename is precomputed once by the caller and reused verbatim
    here (see the exporter's file-collision fix), rather than recomputed from the original name.

    Attachment download failures are logged and recorded in ``skipped`` (not fatal), unless
    ``strict`` is True, in which case the failure is raised immediately: writing happens into a
    temp file that is discarded (not renamed to ``file_path``) whenever this function raises, so
    a strict-mode failure never leaves a partial/complete crate at ``file_path``.
    ``progress`` (if given) is called with the filename after each attachment is written."""

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

    # Write to a temp file next to the target and rename at the end, so a failure
    # mid-export cannot leave a truncated zip clobbering a previous good export.
    tmp_path = f"{file_path}.part"
    if os.path.exists(tmp_path):
        # Overwriting this silently would destroy an unrelated file that happens to sit here, or a
        # concurrent export's scratch file. The user picked `file_path`, not `file_path.part`.
        raise FileExistsError(
            f"{tmp_path} already exists. export_eln writes there before renaming to {file_path}; "
            "remove it, or export to a different path.")
    try:
        _write_crate_zip_inner(tmp_path, root_folder, metadata_dict, elem_files, elem_paths,
                               skipped, progress, _json_default, strict,
                               declare_skipped, mask_host)
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
    os.replace(tmp_path, file_path)


def _write_crate_zip_inner(file_path: str, root_folder: str, metadata_dict: dict, elem_files: dict,
                           elem_paths: dict,
                           skipped: list[dict],
                           progress: Callable[[str], None] | None,
                           _json_default, strict: bool = False, declare_skipped: bool = True,
                           mask_host: str | None = None) -> None:
    import zipfile

    import hashlib

    #: crate-relative File @id -> sha256 hex digest, filled in as the bytes stream past.
    digests: dict[str, str] = {}
    #: File @ids whose bytes did not fully arrive, so their nodes must not stay in the crate.
    failed_ids: set[str] = set()
    #: crate-relative File @id -> bytes actually written, which is what contentSize must state.
    sizes: dict[str, int] = {}

    with zipfile.ZipFile(file_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Attachments are written BEFORE the metadata so their sha256 can be computed from the
        # bytes as they stream and still land in ro-crate-metadata.json. Hashing here costs one
        # pass over data we are already moving — no second download, nothing held in memory.
        for elem_id, files in elem_files.items():
            rel_path = elem_paths[elem_id]
            for att, safe_filename in files:
                orig_filename = att['filename']
                zip_entry_path = f"{root_folder}/{rel_path.lstrip('./')}{safe_filename}"
                digest = hashlib.sha256()
                written = 0
                try:
                    if hasattr(att, "iter_file"):
                        # Stream the download chunk-by-chunk straight into the zip entry so large
                        # attachments never sit fully in memory. force_zip64 allows >2 GiB entries.
                        with zip_file.open(zip_entry_path, "w", force_zip64=True) as dest:
                            for chunk in att.iter_file():
                                digest.update(chunk)
                                written += len(chunk)
                                dest.write(chunk)
                    else:  # fallback for objects exposing only load_file()
                        payload = att.load_file()
                        digest.update(payload)
                        written = len(payload)
                        zip_file.writestr(zip_entry_path, payload)
                    digests[f"{rel_path}{safe_filename}"] = digest.hexdigest()
                    sizes[f"{rel_path}{safe_filename}"] = written
                    if progress is not None:
                        progress(orig_filename)
                except Exception as e:
                    logger.warning("Failed to download attachment %s: %s", orig_filename, e)
                    skipped.append({"kind": "attachment", "stage": "download",
                                    "filename": orig_filename, "error": str(e)})
                    # A failure partway through streaming leaves a TRUNCATED member in the archive
                    # (the entry is already open, and closing it commits what was written). Left
                    # alone, the crate would keep a File node advertising the server's contentSize
                    # with no checksum — a consumer would read silently corrupt bytes and have
                    # nothing to detect it with. Record it so the node is withdrawn below: the
                    # crate then makes no claim about a file it does not really contain.
                    failed_ids.add(f"{rel_path}{safe_filename}")
                    if strict:
                        raise RuntimeError(
                            f"export_eln strict mode: failed to download attachment "
                            f"{orig_filename}: {e}") from e

        # Every element is a Dataset *data entity*, and RO-Crate 1.2 requires a data entity to be
        # present in the payload (`ro-crate-1.2_18.1`) — a directory that exists only in the
        # metadata is a REQUIRED violation. An element with no attachments writes no ZIP member at
        # all, so its directory has to be created explicitly. Under 1.1 this passed, which is why
        # it only surfaced on the two-collection fixture, whose shared sample carries no files.
        _written_dirs = {f"{root_folder}/{path.lstrip('./')}"
                         for path, files in ((elem_paths[k], v) for k, v in elem_files.items())
                         if files}
        for _key, _rel in elem_paths.items():
            _dir_entry = f"{root_folder}/{_rel.lstrip('./')}"
            if _dir_entry in _written_dirs:
                continue
            # A trailing slash with no content is how ZIP records a directory.
            zip_file.writestr(zipfile.ZipInfo(_dir_entry), b"")

        # A File node only gets a digest if its bytes actually made it into the archive, so a
        # skipped attachment never ends up advertising a checksum for content that is not there.
        for node in metadata_dict.get("@graph", []):
            # Guarded like the withdrawal loop below: a @graph member can be collapsed to a bare
            # scalar by _collapse_value_objects, and .get() on a str raises AttributeError here —
            # after every attachment has already been downloaded. @type is matched as
            # string-or-list because that is how it is handled everywhere else in this file.
            if not isinstance(node, dict):
                continue
            node_type = node.get("@type")
            is_file = node_type == "File" or (isinstance(node_type, list) and "File" in node_type)
            if is_file and node.get("@id") in digests:
                node["sha256"] = digests[node["@id"]]
                # contentSize came from the server's recorded filesize, which can be stale — the
                # example fixture declared 1234 bytes for a 206-byte file. Now that the bytes have
                # actually gone past, describe those: a size that disagrees with the checksum
                # beside it is worse than no size.
                node["contentSize"] = str(sizes[node["@id"]])

        if failed_ids:
            # Withdraw the nodes for files whose bytes did not fully arrive, and any hasPart
            # reference to them. Whatever partial bytes are in the archive are then unreferenced —
            # inert — instead of being described as a complete file.
            graph = metadata_dict.get("@graph", [])
            metadata_dict["@graph"] = [n for n in graph
                                       if not (isinstance(n, dict) and n.get("@id") in failed_ids)]
            for node in metadata_dict["@graph"]:
                parts = node.get("hasPart") if isinstance(node, dict) else None
                if isinstance(parts, list):
                    node["hasPart"] = [r for r in parts
                                       if not (isinstance(r, dict) and r.get("@id") in failed_ids)]
            logger.warning(
                "export_eln: withdrew %d File node(s) whose bytes did not fully arrive, so the "
                "crate does not describe content it lacks: %s",
                len(failed_ids), ", ".join(sorted(failed_ids)[:5]))

        # Built here, not in export_eln: attachment download failures are only known once the
        # bytes have been streamed, and the metadata is written last precisely so late findings
        # like these can still reach it.
        if declare_skipped:
            manifest_nodes = build_skipped_manifest(skipped)
            if manifest_nodes:
                metadata_dict.setdefault("@graph", []).extend(manifest_nodes)
                for node in metadata_dict["@graph"]:
                    if isinstance(node, dict) and node.get("@id") == "./":
                        # `mentions` is the format's own way for a dataset to point at something
                        # it refers to — and one of the properties the .eln checker suggests.
                        mentions = node.setdefault("mentions", [])
                        if isinstance(mentions, list):
                            mentions.append({"@id": _MANIFEST_ID})
                        break
                if mask_host:
                    # The manifest is assembled after export_eln's scrub ran, so it needs its own.
                    _replace_host(metadata_dict, mask_host, OFFLINE_HOST)

        metadata_json = json.dumps(metadata_dict, indent=2, ensure_ascii=False, default=_json_default)
        zip_file.writestr(f"{root_folder}/ro-crate-metadata.json", metadata_json)


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


#: Licence assigned to an exported crate when the collection does not specify one. RO-Crate 1.1
#: §8.3 makes `license` mandatory on the Root Data Entity, so something has to be stated.
#: ELN fields carried as ``variableMeasured`` PropertyValue entries because chem-dcat-ap has no
#: home for them. Without this they are simply absent from the crate. Deliberately a curated list
#: rather than "everything left over": a crate padded with dozens of empty administrative flags is
#: harder to read, not richer.
_ELN_EXTRA_FIELDS = (
    "external_label", "location", "melting_point", "boiling_point",
    "tlc_description", "tlc_solvents", "rf_value", "rxno", "role",
)
# Deliberately NOT here — each arrives as a list or mapping, so the container guard skips it and
# listing it would be dead code pretending to be a curated choice:
#   solvent, purification - always lists;  vessel_size - always a mapping
#   stereo, xref  - jsonb on the server, so they arrive as mappings and are skipped anyway.
#                   xref is an internal bag (it holds inventory_label), not descriptive metadata.
#   temperature_display - not exposed by the reaction API at all; it is computed in the frontend.
#                   The real temperature is mapped properly as a QUDT quantity.
# Administrative flags (is_top_secret, decoupled, can_update, children_count, ancestor_ids, ...)
# are left out on purpose: a crate padded with booleans is harder to read, not richer.


def sanitize_filename(name: str) -> str:
    """Reduce a name to the characters that are safe in a ZIP entry path and a crate ``@id``."""
    if not name:
        return "unnamed"
    return re.sub(r'[^a-zA-Z0-9_\-]', '_', name)


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


def _attachment_key(att):
    """A stable identity for an attachment record, for cross-referencing within one export.

    The server-assigned ``identifier`` (a UUID) or ``id``; ``id(att)`` only as a last resort for a
    record carrying neither. Object identity alone was the original key, which held only as long
    as every accessor handed back the same wrapper object.
    """
    try:
        return att.get('identifier') or att.get('id') or id(att)
    except AttributeError:                      # not a mapping; fall back to object identity
        return id(att)


class _CrateFileNamer:
    """Assigns each of an element's attachments a unique name inside the crate.

    The name is computed once here and reused verbatim by every downstream consumer (ZIP entry
    path, File ``@id``, ``hasPart`` refs), instead of each redoing the splitext+sanitize dance —
    which is what let the ZIP entry path and the File ``@id`` disagree whenever two different
    original names sanitized to the same string.

    Attachments are deduplicated by **record identity**, not by filename. An element's own
    attachments plus every dataset of every analysis are walked together, and those are distinct
    records: two analyses each holding ``spectrum.jdx`` are two different files. Keying on the
    filename dropped the second one's bytes and its ``File`` node entirely, and appended nothing
    to ``skipped`` — so the crate did not even declare the omission.
    """

    def __init__(self) -> None:
        #: (attachment, name-inside-the-crate) pairs, in insertion order.
        self.files: list = []
        #: crate name -> the original filename that first claimed it.
        self._claimed: dict[str, str] = {}
        #: identities of the records already taken.
        self._seen: set = set()

    def add(self, att) -> None:
        """Include ``att``, unless this exact record was already included."""
        orig_filename = att['filename']
        record_id = att.get('identifier') or att.get('id')
        if record_id is not None:
            if record_id in self._seen:
                return                      # the same attachment record, already included
            self._seen.add(record_id)
        # (no identifier and no id: nothing stable to dedupe on — fall through to the name rules)

        name_part, ext_part = os.path.splitext(os.path.basename(orig_filename))
        safe_name = sanitize_filename(name_part) + ext_part
        if safe_name not in self._claimed:
            self._claimed[safe_name] = orig_filename
            self.files.append((att, safe_name))
            return
        if record_id is None and self._claimed.get(safe_name) == orig_filename:
            # No identity to go on and the same original filename: treat it as a duplicate.
            return
        # A name already taken by a different record -> disambiguate with a numeric suffix
        # instead of silently colliding on one ZIP entry / @id.
        base_name, ext = os.path.splitext(safe_name)
        n = 2
        while True:
            candidate = f"{base_name}_{n}{ext}"
            if candidate not in self._claimed:
                self._claimed[candidate] = orig_filename
                self.files.append((att, candidate))
                return
            n += 1


def _extra_field_value(elem, props, field):
    """Resolve one :data:`_ELN_EXTRA_FIELDS` entry, which is not always a plain ``props`` key.

    Four of the nine never resolved through ``props.get(field)`` on a real element, so they were
    silently absent from every crate — and the ``normalise_range_value`` branch written for two of
    them was unreachable:

    * ``melting_point`` / ``boiling_point`` — ``Sample._parse_properties`` splits each Ruby range
      into ``*_lowerbound`` / ``*_upperbound``, so the un-suffixed key is not in a parsed sample's
      properties at all. Both shapes are accepted: the raw range string where a payload carries
      one, otherwise the parsed bounds, otherwise the raw ``json_data`` range.
    * ``role`` — a sample's role is the ``role_in_reaction`` attribute, not a property.
    * ``tlc_description`` — validated by ``Reaction._parse_properties`` but left out of the dict it
      returns, so it survives only on the raw payload.
    """
    raw_json = getattr(elem, "json_data", None)
    if not isinstance(raw_json, Mapping):
        raw_json = {}

    if field in ("melting_point", "boiling_point"):
        value = props.get(field)
        if value is not None:
            return normalise_range_value(str(value))
        low, high = props.get(f"{field}_lowerbound"), props.get(f"{field}_upperbound")
        if low is not None or high is not None:
            if high is None or low == high:
                return low if low is not None else high
            return f"{low}-{high}" if low is not None else high
        raw = raw_json.get(field)
        return normalise_range_value(str(raw)) if raw is not None else None

    if field == "role":
        role = getattr(elem, "role_in_reaction", None)
        return role if isinstance(role, str) else None

    value = props.get(field)
    if value is None and field == "tlc_description":
        value = raw_json.get(field)
    return value


def _replace_host(metadata_dict: dict, real_host: str, replacement: str) -> int:
    """Replace every occurrence of ``real_host`` in the graph's strings, returning how many.

    Walks values as well as ``@id``s: the hostname does not only appear as an identifier. A
    molecule node, for instance, records ``compound assigned to <host>/api/v1/...`` in prose, and an
    element referenced but not itself exported keeps its absolute URI. Missing those is the
    difference between withholding the host and merely claiming to.

    :param metadata_dict: the crate metadata, modified in place.
    :param real_host: the hostname to remove (with and without its scheme).
    :param replacement: what to put in its place.
    :return: the number of strings changed.
    """
    bare_host = real_host.split("://", 1)[-1]
    bare_replacement = replacement.split("://", 1)[-1]
    changed = 0

    def scrubbed(text: str) -> str:
        return text.replace(real_host, replacement).replace(bare_host, bare_replacement)

    # Mutates in place rather than rebuilding. The caller still holds references into this graph
    # (root_node, graph_nodes) and keeps editing them afterwards; returning fresh dicts would
    # detach those, and their later edits would silently never reach the crate.
    def walk(container):
        nonlocal changed
        items = container.items() if isinstance(container, dict) else enumerate(container)
        for key, value in list(items):
            if isinstance(value, str):
                if real_host in value or bare_host in value:
                    container[key] = scrubbed(value)
                    changed += 1
            elif isinstance(value, dict | list):
                walk(value)

    walk(metadata_dict.get("@graph", []))
    return changed


def annotate_element_metadata(elem, node, undated: list | None = None):
    """Attach the descriptive metadata every ELN exporter is expected to emit.

    ``TheELNFileFormat``'s own checker keeps a DATASET_SUGGESTED list — ``author``,
    ``mentions``, ``dateCreated``, ``dateModified``, ``identifier``, ``text``, ``keywords``
    — none of which the spec requires, but all of which is what makes an archive worth
    reading rather than merely valid.
    """
    created = getattr(elem, "created_at", None)
    updated = getattr(elem, "last_update", None)
    if created is not None:
        node["dateCreated"] = created.isoformat()
    if updated is not None:
        node["dateModified"] = updated.isoformat()
    if created is None and updated is None:
        (undated if undated is not None else []).append(str(getattr(elem, "id", "?")))

    props = getattr(elem, "properties", None) or {}
    # identifier: the ELN's human-facing short label ("SSH-156"), else the database id.
    identifier = getattr(elem, "short_label", None) or props.get("short_label")
    if not identifier and getattr(elem, "id", None) is not None:
        identifier = str(elem.id)
    if identifier:
        node["identifier"] = str(identifier)

    # genre: which kind of ELN record this is, so a consumer can tell a sample from a
    # reaction without having to parse the ontology types.
    kind = getattr(elem, "element_type", None)
    if kind:
        node["genre"] = str(kind)

    # keywords MUST be a delimited string: an array is a hard failure in both
    # TheELNFileFormat's tests/schema.json and its checks.py.
    keywords: list[str] = []
    try:
        # Accessed directly, NOT via getattr(..., []): a default silently swallows an
        # AttributeError raised *inside* the property, which is how an offline connection missing
        # `user_labels` made labels disappear from crates with no error at all.
        for label in elem.user_labels_resolved or []:
            title = getattr(label, "title", None)
            if title:
                keywords.append(str(title))
    except Exception as e:
        # Never fail an export over labels — but say so at warning level. At debug this was
        # indistinguishable from "this element has no labels".
        logger.warning("Could not resolve user labels for element %s, so none are recorded: %s",
                       getattr(elem, "id", "?"), e)
    tag = props.get("tag")
    if isinstance(tag, str) and tag.strip():
        keywords.append(tag.strip())
    if keywords:
        node["keywords"] = ", ".join(dict.fromkeys(keywords))

    # text: the element's narrative content. Chemotion stores these as Quill deltas, so an
    # isinstance(str) guard silently skipped exactly the elements whose narrative matters —
    # reaction observations and descriptions are never plain strings.
    for field in ("observation", "description"):
        text_value = quill_to_text(props.get(field))
        if text_value and "text" not in node:
            node["text"] = text_value

    # ELN fields with no chem-dcat-ap home would otherwise be dropped on the floor. The
    # spec's own mechanism for structured extras is variableMeasured -> PropertyValue, so
    # carry them there rather than losing them or inventing predicates.
    extras = []
    for field in _ELN_EXTRA_FIELDS:
        value = _extra_field_value(elem, props, field)
        # Containers are skipped, not stringified. `isinstance(value, dict)` is not enough:
        # Chemotion's PropertyDict is a MutableMapping but NOT a dict subclass, so a dict check
        # misses it and str() then writes `<PropertyDict object at 0x...>` — a memory address —
        # into the crate. Test the ABCs instead.
        if value is None or isinstance(value, Mapping | list | tuple | set):
            continue
        text_value = str(value).strip()
        if not text_value or text_value.lower() in ("none", "false"):
            continue
        extras.append({
            "@type": "PropertyValue",
            "propertyID": f"chemotion:{field}",
            "name": field.replace("_", " "),
            "value": text_value,
        })
    if extras:
        node["variableMeasured"] = node.get("variableMeasured", []) + extras


#: Matches the default ``object.__repr__`` shape (``<module.Class object at 0x7f…>``) and the
#: bare ``<Class …>`` reprs objects commonly define. Used as a final guard: no such string is ever
#: legitimate crate content.
_REPR_LEAK_RE = re.compile(r'<[A-Za-z_][\w.]* object at 0x[0-9a-fA-F]+>|<[a-z_]+\.[\w.]+ object')

_CRATE_DEFAULT_LICENSE = "https://creativecommons.org/licenses/by/4.0/"

#: The crate's ``@context``: the canonical RO-Crate 1.1 context plus a definition for ``sha256``.
#: ``sha256`` is not a schema.org term, so it has to be defined here — left undefined it is
#: invisible to any consumer that expands the JSON-LD properly.
#: Namespace prefixes for the vocabularies chem-dcat-ap uses as JSON-LD *keys*. RO-Crate 1.2's
#: own context does not define them, and an absolute IRI used as a key that the document context
#: does not map is a REQUIRED violation (`ro-crate-1.2_3.1`) — the crate is rejected outright.
#: Declaring the prefixes lets those predicates compact to `qudt:unit`, `sio:SIO_000008` and so
#: on, which the rule accepts as "a term or compact IRI".
_CRATE_NAMESPACES: dict = {
    "qudt": "http://qudt.org/schema/qudt/",
    "sio": "http://semanticscience.org/resource/",
    "obo": "http://purl.obolibrary.org/obo/",
    "adms": "http://www.w3.org/ns/adms#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
}

#: RO-Crate 1.2. `sha256` needs no local definition any more — 1.2's context defines it, where
#: 1.1's did not (which is why every 1.1-era `.eln` carrying checksums fails validation today).
_CRATE_CONTEXT: list = [
    "https://w3id.org/ro/crate/1.2/context",
    dict(_CRATE_NAMESPACES),
]

#: The `.eln` profile this exporter targets. Both IRIs are emitted as `conformsTo` on the root
#: Dataset and as `Profile` entities in the graph, per TheELNFileFormat's migration guide.
_RO_CRATE_PROFILE = "https://w3id.org/ro/crate/1.2"
#: Note `purl.archive.org`, not `purl.org`: TheELNFileFormat's SPECIFICATION.md says the latter,
#: but its checker (`tests/checks/versions.py`) matches only the former, and a crate using
#: `purl.org` is read as declaring no ELN version at all. Reported upstream.
_ELN_SPEC_PROFILE = "https://purl.archive.org/purl/elnconsortium/eln-spec/1.2+20260923"


#: Types that make a node a *data* entity rather than a contextual one.
_DATA_ENTITY_TYPES = {"Dataset", "File"}


def _is_schema_org_type(type_name: str) -> bool:
    """Whether a ``@type`` value is a schema.org term.

    The RO-Crate context is schema.org-based, so a bare term (``Dataset``, ``PropertyValue``) is
    one; a compact IRI (``qudt:Quantity``) or an absolute IRI is not.
    """
    return bool(type_name) and ":" not in type_name and not type_name.startswith("http")


def _readable_name(node: dict) -> str:
    """A human-readable ``name`` for a contextual entity that has none.

    RO-Crate asks every contextual entity to carry one (`ro-crate-1.2_75.1`), and a crate full of
    `#qudt_quantity-2` with no label is unreadable by a person even though it validates. The
    chem-dcat-ap mapping already puts a label on most nodes, so prefer the real thing and fall
    back to the type only when there is nothing better.
    """
    for key in ("dct:title", "dct:description", "skos:notation", "prov:value"):
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            text = value.strip()
            return text if len(text) <= 120 else text[:117] + "..."
    types = node.get("@type", [])
    types = types if isinstance(types, list) else [types]
    for type_name in types:
        if not isinstance(type_name, str):
            continue
        local = type_name.rsplit("/", 1)[-1].rsplit("#", 1)[-1].rsplit(":", 1)[-1]
        if local:
            return local.replace("_", " ")
    return str(node.get("@id", "entity")).lstrip("#")


def _expand_iri(term: str, prefixes: dict) -> str:
    """Expand a compact IRI (``qudt:Quantity``) to its absolute form using ``prefixes``.

    Needed because the same concept can appear both compacted (as a ``@type``) and absolute (as a
    node ``@id``). Comparing the two spellings literally produced duplicate ``@id`` nodes, which merge
    silently once the JSON-LD is expanded.
    """
    if not isinstance(term, str) or term.startswith(("http://", "https://", "_:", "@")):
        return term
    prefix, sep, local = term.partition(":")
    base = prefixes.get(prefix)
    if sep and isinstance(base, str) and base.endswith(("/", "#", ":")):
        return f"{base}{local}"
    return term


def _term_label(iri: str) -> str:
    """A readable label for a vocabulary IRI we reference but do not otherwise describe."""
    local = iri.rstrip("/").rsplit("/", 1)[-1].rsplit("#", 1)[-1]
    return local.replace("-", " ").replace("_", " ") or iri


def _polish_contextual_entities(metadata_dict: dict, root_node: dict,
                                base_context: dict) -> None:
    """Satisfy RO-Crate's RECOMMENDED rules about contextual entities, in place.

    Three rules, all of which make a crate more readable rather than merely more compliant:

    * every contextual entity carries a ``name`` and at least one schema.org ``@type``
      (`75.1`, `42.1`, `42.0`);
    * every IRI the crate *references* is also *described* in the graph (`76.1`) — a bare
      ``{"@id": "http://qudt.org/vocab/unit/MilliMOL"}`` tells a reader nothing on its own;
    * nothing sits in the graph unreachable from anything else (`77.0`).
    """
    graph = metadata_dict.get("@graph", [])

    # Re-resolve the root from the graph instead of trusting the reference handed in. The id
    # rewriting pass above rebuilds every node as a *new dict*, so any reference held across it
    # points at a discarded copy and mutations through it vanish without a trace. (That is a
    # hazard for every `graph_nodes` holder, not just this one — see AI/DEFERRED.md.)
    root_id = root_node.get("@id", "./")
    for node in graph:
        if isinstance(node, dict) and node.get("@id") == root_id:
            root_node = node
            break

    #: Everything that needs *describing*: entities, the ontology classes used as `@type`, and
    #: the predicate IRIs. Being a predicate is not the same as being referenced *by* an entity,
    #: though, so reachability is judged on ``linked`` alone — otherwise a described predicate
    #: looks reachable to us and stranded to the validator.
    referenced: set[str] = set()
    linked: set[str] = set()

    def _collect(value) -> None:
        if isinstance(value, dict):
            if set(value) == {"@id"} and isinstance(value["@id"], str):
                referenced.add(value["@id"])
                linked.add(value["@id"])
            for item in value.values():
                _collect(item)
        elif isinstance(value, list):
            for item in value:
                _collect(item)

    for node in graph:
        if isinstance(node, dict):
            _collect({k: v for k, v in node.items() if k not in ("@id", "@type")})

    # An entity's `@type` is an RDF reference too, and the ontology classes the chem-dcat-ap
    # mapping uses (`qudt:Quantity`, `sio:SIO_001406`, …) were referenced by every typed node and
    # described by none — which is most of what `76.1` was reporting. Counting only `{"@id": …}`
    # objects missed them entirely.
    for node in graph:
        if not isinstance(node, dict):
            continue
        node_types = node.get("@type", [])
        node_types = node_types if isinstance(node_types, list) else [node_types]
        for type_name in node_types:
            if isinstance(type_name, str) and not _is_schema_org_type(type_name):
                referenced.add(type_name)
        # So are the predicates: an object-valued property IRI such as `qudt:unit` is an entity
        # in the RDF graph, and the validator asks for it to be described like any other.
        for key in node:
            if not key.startswith("@") and not _is_schema_org_type(key):
                referenced.add(key)

    # -- names and schema.org types -------------------------------------------------------
    for node in graph:
        if not isinstance(node, dict) or node.get("@id") == _METADATA_ID:
            continue
        types = node.get("@type", [])
        types = types if isinstance(types, list) else [types]
        if _DATA_ENTITY_TYPES.intersection(types):
            continue
        if not node.get("name"):
            node["name"] = _readable_name(node)
        if not any(_is_schema_org_type(t) for t in types if isinstance(t, str)):
            # A measured value or an identifier is a PropertyValue; anything else gets the
            # schema.org root rather than a type we cannot justify.
            kind = "PropertyValue" if ("prov:value" in node or "skos:notation" in node) else "Thing"
            node["@type"] = [*types, kind] if types else kind

    # -- describe what we only referenced -------------------------------------------------
    # The set of ids present must come from the graph itself, not from ``graph_nodes``: nodes are
    # appended to the graph in several places without being registered there, and keying off the
    # stale map produced a *second* node with an @id that already existed — a duplicate @id, which
    # is its own violation (`ro-crate-1.2_2.8`) and silently merges two entities when the JSON-LD
    # is expanded.
    prefixes = {term: iri for term, iri in base_context.items()
                if isinstance(iri, str) and iri.endswith(("/", "#", ":"))}
    prefixes.update(_CRATE_NAMESPACES)
    present = {_expand_iri(node["@id"], prefixes) for node in graph
               if isinstance(node, dict) and isinstance(node.get("@id"), str)}
    for term in sorted(referenced):
        iri = _expand_iri(term, prefixes)
        if iri in present or not iri.startswith(("http://", "https://")):
            continue
        stub = {"@id": iri, "@type": "DefinedTerm", "name": _term_label(iri)}
        graph.append(stub)
        present.add(iri)

    # -- data entities carry a description --------------------------------------------------
    for node in graph:
        if not isinstance(node, dict):
            continue
        types = node.get("@type", [])
        types = types if isinstance(types, list) else [types]
        if "Dataset" not in types or node.get("description") or node.get("@id") == "./":
            continue
        label = node.get("name") or str(node.get("@id", "")).strip("./")
        genre = node.get("genre") or "Element"
        node["description"] = f"{genre} '{label}' as recorded in the Chemotion ELN."

    # -- organizations: a URL, and a reachable contact point ----------------------------------
    contact_points: dict[str, str] = {}
    for node in graph:
        if not isinstance(node, dict):
            continue
        types = node.get("@type", [])
        types = types if isinstance(types, list) else [types]
        node_id = node.get("@id", "")
        if "Person" in types and node.get("email") and "contactPoint" not in node:
            contact_id = f"#contact-{str(node_id).lstrip('#').rsplit('/', 1)[-1]}"
            contact_points[contact_id] = node["email"]
            node["contactPoint"] = {"@id": contact_id}
        if "Organization" in types and isinstance(node_id, str):
            # A ROR id is the organization's @id; schema.org still wants an explicit `url`.
            node.setdefault("url", node_id if node_id.startswith("http") else None)
            if node.get("url") is None:
                node.pop("url", None)
    # Give the organizations a contact point too, reusing the author's where there is one.
    if contact_points:
        first_contact = next(iter(contact_points))
        for node in graph:
            if not isinstance(node, dict):
                continue
            types = node.get("@type", [])
            types = types if isinstance(types, list) else [types]
            if "Organization" in types and "contactPoint" not in node:
                node["contactPoint"] = {"@id": first_contact}
    for contact_id, email in contact_points.items():
        if contact_id in {n.get("@id") for n in graph if isinstance(n, dict)}:
            continue
        contact_node = {"@id": contact_id, "@type": "ContactPoint", "email": email,
                        "name": f"Contact for {email}", "contactType": "author"}
        graph.append(contact_node)

    # -- and make sure nothing is stranded ------------------------------------------------
    mentions = root_node.setdefault("mentions", [])
    if isinstance(mentions, dict):
        mentions = [mentions]
        root_node["mentions"] = mentions
    mentioned = {ref["@id"] for ref in mentions if isinstance(ref, dict) and "@id" in ref}
    for node in graph:
        if not isinstance(node, dict):
            continue
        node_id = node.get("@id")
        if not isinstance(node_id, str) or node_id in mentioned:
            continue
        if _expand_iri(node_id, prefixes) in {_expand_iri(r, prefixes) for r in linked}:
            continue
        if node_id in (_METADATA_ID, root_node.get("@id")):
            continue
        types = node.get("@type", [])
        types = types if isinstance(types, list) else [types]
        if _DATA_ENTITY_TYPES.intersection(types):
            continue
        mentions.append({"@id": node_id})
        mentioned.add(node_id)


def _declare_unmapped_terms(metadata_dict: dict, base_context: dict) -> dict:
    """Return explicit term definitions for every graph key the base context does not define.

    Declaring namespace *prefixes* is not enough. `roc-validator` 0.11.3 — the version
    TheELNFileFormat's CI pins — requires each key to be **present in the @context** verbatim and
    rejects a compact IRI whose prefix alone is declared; 0.13.0 relaxed that to "a term or
    compact IRI". Emitting the full key as its own term satisfies both, and costs one line of
    @context per predicate actually used.

    The definitions are derived from the serialized document rather than from a hand-kept list, so
    a new chem-dcat-ap predicate cannot silently reintroduce the failure.

    :param metadata_dict: the serialized crate, already compacted.
    :param base_context: the RO-Crate context object used for compaction.
    :return: ``{key: absolute_iri}`` for the keys needing a definition, sorted for a stable diff.
    """
    prefixes = {term: iri for term, iri in base_context.items()
                if isinstance(iri, str) and iri.endswith(("/", "#", ":"))}
    extra: dict[str, str] = {}
    for node in metadata_dict.get("@graph", []):
        if not isinstance(node, dict):
            continue
        for key in node:
            if key.startswith("@") or key in base_context or key in extra:
                continue
            if key.startswith(("http://", "https://")):
                extra[key] = key
                continue
            prefix, sep, local = key.partition(":")
            if sep and prefix in prefixes:
                extra[key] = f"{prefixes[prefix]}{local}"
            else:
                logger.debug("Crate key %r has no resolvable namespace; leaving it undeclared.", key)
    return dict(sorted(extra.items()))


def _is_opaque_payload(value) -> bool:
    """Whether a property value is a nested structure RO-Crate cannot represent as-is.

    RO-Crate allows literals, `{"@id": …}` references, and arrays of those. What it cannot hold is
    an arbitrary **nested object** — so a dict, or a list containing one, has to be carried as a
    JSON string instead. A flat list of scalars is a normal multi-valued property and must be left
    alone.

    :param value: a candidate property value.
    :return: True if it must be serialised to a string.
    """
    if isinstance(value, dict):
        return True
    if isinstance(value, list):
        return any(isinstance(item, (dict, list)) for item in value)
    return False


def flatten_crate_graph(metadata_dict: dict) -> int:
    """Make an RO-Crate metadata graph spec-conformant in place.

    Two fixes, both required by RO-Crate 1.1 and both flagged by TheELNConsortium's conformance
    suite on crates this exporter used to produce:

    * **No blank nodes** (§2.2, "fully flattened"). chem-dcat-ap emits nested value objects — the
      CHEMINF identifier entities for InChI, SMILES, IUPAC name and so on — and serialising that
      RDF to JSON-LD turns them into blank nodes (``_:Nabc…``). Each one is given a stable
      fragment id instead, and every reference to it is rewritten.
    * **Datasets need `name`** (schema.org). chem-dcat-ap titles land in ``dct:title``, which
      RO-Crate consumers do not read; mirror it into ``name`` where absent.

    :param metadata_dict: the parsed ``ro-crate-metadata.json``, modified in place.
    :return: the number of blank nodes renamed.
    """
    graph = metadata_dict.get("@graph")
    if not isinstance(graph, list):
        return 0

    # Blank-node labels are only unique within one document, so a positional counter is a stable
    # enough basis for the replacement id; the type suffix keeps it readable.
    renames: dict[str, str] = {}
    for node in graph:
        if not isinstance(node, dict):
            continue
        node_id = node.get("@id")
        if isinstance(node_id, str) and node_id.startswith("_:"):
            node_type = node.get("@type") or "entity"
            if isinstance(node_type, list):
                node_type = node_type[0] if node_type else "entity"
            slug = re.sub(r"[^A-Za-z0-9]+", "_", str(node_type).rsplit("/", 1)[-1]).strip("_")
            renames[node_id] = f"#{slug.lower() or 'entity'}-{len(renames) + 1}"

    def _rewrite(obj):
        if isinstance(obj, dict):
            return {k: (renames.get(v, v) if k == "@id" and isinstance(v, str) else _rewrite(v))
                    for k, v in obj.items()}
        if isinstance(obj, list):
            return [_rewrite(v) for v in obj]
        return obj

    if renames:
        metadata_dict["@graph"] = _rewrite(graph)
        graph = metadata_dict["@graph"]

    # RO-Crate JSON-LD is a *restricted* profile of JSON-LD, not the full language: every property
    # value must be a literal or a {"@id": …} reference, and every entity must be a top-level
    # member of @graph. Two shapes that are perfectly legal JSON-LD violate it, and both appear in
    # what chem-dcat-ap's RDF serialises to:
    #
    #   1. typed literals — {"@type": "xsd:float", "@value": "0.0"}
    #   2. anonymous entities — a nested object with no @id at all (an implicit blank node),
    #      e.g. the PropertyValue entries this exporter puts in `variableMeasured`
    #
    # Collapse the first to a plain literal (the xsd datatype is dropped; RO-Crate has nowhere to
    # put it), and give the second a minted @id so it can be hoisted like any other entity.
    def _collapse_value_objects(obj):
        if isinstance(obj, dict):
            if "@value" in obj and set(obj) <= {"@value", "@type", "@language"}:
                return obj["@value"]
            return {k: _collapse_value_objects(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_collapse_value_objects(v) for v in obj]
        return obj

    graph = [_collapse_value_objects(node) for node in graph]
    metadata_dict["@graph"] = graph

    # "Fully flattened" means every entity is a *top-level* member of @graph: giving a nested
    # object an @id is not enough, it has to be hoisted out and replaced by a reference. Repeat
    # until nothing moves, since hoisted entities can themselves contain nested entities.
    minted = 0

    def _mint_id(entity: dict) -> str:
        nonlocal minted
        minted += 1
        for key in ("propertyID", "name", "@type"):
            raw = entity.get(key)
            if isinstance(raw, list):
                raw = raw[0] if raw else None
            if isinstance(raw, str) and raw:
                slug = re.sub(r"[^A-Za-z0-9]+", "-", raw.rsplit("/", 1)[-1]).strip("-").lower()
                if slug:
                    return f"#{slug}-{minted}"
        return f"#entity-{minted}"

    while True:
        hoisted: list[dict] = []

        def _hoist(obj, top=False):
            if isinstance(obj, list):
                return [_hoist(v) for v in obj]
            if not isinstance(obj, dict):
                return obj
            inner = {k: _hoist(v) for k, v in obj.items()}
            # A bare {"@id": ...} is already a reference; anything richer is an entity definition.
            if not top and len(inner) > 1:
                if not isinstance(inner.get("@id"), str):
                    inner["@id"] = _mint_id(inner)
                hoisted.append(inner)
                return {"@id": inner["@id"]}
            return inner

        graph = [_hoist(node, top=True) for node in graph]
        # Always publish the rebuilt list: _hoist returns new dicts every pass, so leaving the old
        # generation in metadata_dict would silently discard this pass's work (including anything
        # a later step mutates on these nodes).
        metadata_dict["@graph"] = graph
        if not hoisted:
            break
        by_id = {n["@id"]: n for n in graph if isinstance(n, dict) and isinstance(n.get("@id"), str)}
        for entity in hoisted:
            existing = by_id.get(entity["@id"])
            if existing is None:
                graph.append(entity)
                by_id[entity["@id"]] = entity
            else:
                # Same entity nested in two places: merge rather than duplicate the @id, which
                # would itself be a spec violation.
                for key, value in entity.items():
                    existing.setdefault(key, value)
        metadata_dict["@graph"] = graph

    for node in graph:
        if not isinstance(node, dict) or "name" in node:
            continue
        node_type = node.get("@type")
        types = node_type if isinstance(node_type, list) else [node_type]
        if "Dataset" not in types:
            continue
        title = node.get("dct:title") or node.get("title")
        if isinstance(title, list):
            title = title[0] if title else None
        if isinstance(title, dict):
            title = title.get("@value")
        if isinstance(title, str) and title:
            node["name"] = title
            # Having mirrored it into schema.org `name`, drop the chem-dcat-ap spelling: two keys
            # carrying the identical string is noise for a reader, and `name` is the one the .eln
            # checker requires on every Dataset.
            if node.get("dct:title") == title:
                node.pop("dct:title", None)
            if node.get("title") == title:
                node.pop("title", None)

    # Drop properties whose value is empty or whitespace-only. A key with no content says nothing
    # a missing key does not, and the .eln conformance suite reports such nodes as
    # "contains empty values in the key-value pairs".
    dropped: dict[str, int] = {}
    for node in graph:
        if not isinstance(node, dict):
            continue
        for key in [k for k, v in node.items()
                    if k not in ("@id", "@type") and not isinstance(v, (dict, list))
                    and not str(v).strip()]:
            del node[key]
            dropped[key] = dropped.get(key, 0) + 1
    # Last line of defence against a whole family of bug this exporter has now produced three
    # times: a value arriving from the server is written out with str() without anyone checking
    # its shape, and a Python repr ends up in the crate. The worst was
    # `<chemotion_api.utils.PropertyDict object at 0x74e3...>` — a live memory address — reaching a
    # real export, because PropertyDict is a MutableMapping and not a dict subclass, so the guard
    # meant to skip containers missed it.
    #
    # A repr is never valid crate content, so drop it rather than publish it, and say so loudly:
    # it means some upstream guard is wrong and should be fixed at the source.
    leaked_reprs: list[str] = []
    for node in graph:
        if not isinstance(node, dict):
            continue
        for key, value in list(node.items()):
            if isinstance(value, str) and _REPR_LEAK_RE.search(value):
                leaked_reprs.append(f"{node.get('@id', '?')}.{key}")
                del node[key]
    if leaked_reprs:
        logger.error(
            "export_eln: dropped %d propert(y/ies) whose value was a Python repr, not data: %s. "
            "This is a bug in the exporter — some value reached the crate via str() without its "
            "shape being checked. The crate is still valid; the affected values are absent.",
            len(leaked_reprs), ", ".join(leaked_reprs[:10]))

    if dropped:
        # One summary line per export, not one per field: this is routine (Chemotion stores unset
        # optional fields as empty strings), so it should inform without becoming noise.
        summary = ", ".join(f"{key} ({count})" for key, count in sorted(dropped.items()))
        logger.warning(
            "export_eln: omitted %d empty field(s) from the crate metadata — a key with no value "
            "carries no more meaning than an absent one: %s",
            sum(dropped.values()), summary,
        )

    return len(renames)


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
    research plans, generics) and exporting to ``.eln``. Concrete subclasses add editing
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

    def export_eln(self, file_path: str, strict: bool = False,
                   ontology_lookup: bool = True, ols_cache: str | None = None,
                   authors: list | None = None,
                   progress_callback: Callable[[int, int, str | None], None] | None = None,
                   interactive: bool = False, disclose_host: bool = True,
                   declare_skipped: bool = True) -> str:
        """
        Exports the collection and all its elements to a .eln ZIP file.

        :param file_path: destination ``.eln`` path.
        :param disclose_host: record the ELN's URL in the crate (default). Set ``False`` for an
            archive leaving the institution: the source notebook is then identified by the
            ``.invalid`` sentinel instead of its real hostname, while its **version is still
            recorded** — so the crate says what produced it without disclosing where it runs.
        :param declare_skipped: record what the export left out in the crate itself (default), as
            a ``CreativeWork`` the root ``mentions``. Without it a partial crate reads exactly like
            a complete one. Counts and stable reasons only — never raw error text, which is
            unstable and can carry the server's hostname.
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
            (when no code) an EBI OLS lookup.

            .. warning::
               **This makes outbound requests to a third party, and defaults to on.** Every
               analysis name that carries no embedded CHMO code is sent to EBI's OLS service at
               ``www.ebi.ac.uk``. Analysis names can themselves be sensitive, and this happens
               independently of ``disclose_host`` — withholding the hostname does not
               withhold the analysis names. It also happens during an otherwise offline export
               of a dump.

               Pass ``ontology_lookup=False`` to use only embedded codes and make **no** network
               call, or ``ols_cache=<path>`` to look each term up once and reuse it thereafter.
               Lookups are cached and never fatal: a failure downgrades the annotation, it does
               not fail the export.
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

        # Elements whose timestamps were unavailable, so the manifest can say so once rather than
        # leaving a reader to wonder whether the data or the source was missing them.
        _undated_elements: list[str] = []

        from chemotion_api.export.indexing import build_element_index, build_uri_mapping

        index = build_element_index(self, sanitize_filename, skipped)
        col_node_ids = index.col_node_ids
        collections_by_id = index.collections_by_id
        elem_paths = index.elem_paths
        elements_by_id = index.elements_by_id
        elem_to_cols = index.elem_to_cols

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

        # uri_mapping powers map_term() below; dcat_cache lets the main mapping loop further down
        # reuse each element's to_dcat_ap() result instead of calling it a second time.
        uri_mapping, dcat_cache = build_uri_mapping(elements_by_id, elem_paths)

        def map_term(term):
            if isinstance(term, URIRef):
                val = str(term)
                if val.startswith("chemotion://molecule/"):
                    mol_db_id = val[len("chemotion://molecule/"):]
                    return URIRef(f"#molecule_{mol_db_id}")
                relative_path = uri_mapping.get(val)
                if relative_path is not None:
                    return URIRef(relative_path)
                base, sep, fragment = val.partition("#")
                if sep:
                    relative_path = uri_mapping.get(base)
                    if relative_path is not None:
                        return URIRef(f"{relative_path}#{fragment}")
                # Embedded sub-entities (e.g. reaction materials that are not exported as
                # standalone elements) still carry absolute API URLs; rewrite them to crate
                # fragments so the crate-relative identifier policy holds for every record.
                api_match = re.match(r'https?://[^/]+/api/v1/(.+)$', val)
                if api_match:
                    frag = re.sub(r'[^A-Za-z0-9_-]+', '_',
                                   api_match.group(1).replace('.json', '')).strip('_')
                    return URIRef(f"#{frag}")
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
            for _i, (elem_key, elem) in enumerate(elements_by_id.items(), start=1):
                try:
                    _report(_i, _total, getattr(elem, "name", None) or getattr(elem, "id", None))
                except Exception as e:  # a faulty callback/bar must never abort the export
                    logger.debug("progress reporting raised: %s", e)
                if hasattr(elem, "to_dcat_ap"):
                    try:
                        # Reuse the to_dcat_ap() call already made while building uri_mapping
                        # (build_uri_mapping) instead of calling it again for every element.
                        # Elements absent from the cache (that first call failed) get one more
                        # attempt here so the failure is still recorded below, unchanged.
                        dcat_obj = dcat_cache[elem_key] if elem_key in dcat_cache else elem.to_dcat_ap()
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
        # fetch https://w3id.org/ro/crate/1.2/context at runtime (offline-capable). The output's
        # @context is still set to the canonical URL below.
        ctx = "https://w3id.org/ro/crate/1.2/context"
        try:
            _ctx_path = os.path.join(os.path.dirname(__file__), "data", "ro-crate-context.jsonld")
            with open(_ctx_path) as _f:
                ctx = json.load(_f).get("@context", ctx)
        except Exception as e:
            logger.warning("Vendored RO-Crate context unavailable; serialization may fetch it remotely: %s", e)
        if isinstance(ctx, dict):
            # Compact against the namespaces too, or rdflib emits chem-dcat-ap predicates as bare
            # absolute IRIs — which is the REQUIRED violation the prefixes exist to prevent. The
            # emitted `@context` below declares the same prefixes, so document and payload agree.
            ctx = {**ctx, **_CRATE_NAMESPACES}
        serialized = mapped_graph.serialize(format="json-ld", context=ctx)
        metadata_dict = json.loads(serialized)
        
        metadata_dict["@context"] = list(_CRATE_CONTEXT)

        if "@graph" not in metadata_dict:
            node = {k: v for k, v in metadata_dict.items() if k != "@context"}
            metadata_dict = {
                "@context": metadata_dict["@context"],
                "@graph": [node]
            }

        # elem_files[elem_id] is a list of (attachment, safe_filename) pairs. The sanitized (and,
        # on collision, disambiguated) filename is computed exactly once here and reused verbatim
        # by every downstream consumer (ZIP entry path, File @id, hasPart refs) instead of each
        # one redoing the splitext+sanitize dance independently (which is what let the ZIP entry
        # path and the File @id disagree whenever two different original names sanitized to the
        # same string, producing duplicate ZIP entries / duplicate @ids for what looked like two
        # distinct files).
        elem_files: dict = {}
        for elem_id in elem_paths:
            elem = elements_by_id[elem_id]
            namer = _CrateFileNamer()
            if elem.attachments:
                for att in elem.attachments:
                    namer.add(att)
            if hasattr(elem, "analyses") and elem.analyses:
                for ana in elem.analyses:
                    if hasattr(ana, "datasets") and ana.datasets:
                        for ds in ana.datasets:
                            if ds.attachments:
                                for att in ds.attachments:
                                    namer.add(att)
            elem_files[elem_id] = namer.files

        file_nodes = []
        for elem_id, files in elem_files.items():
            rel_path = elem_paths[elem_id]
            for att, safe_filename in files:
                file_id = f"{rel_path}{safe_filename}"
                size = str(att.get('filesize') or att.get('contentSize') or "")
                mime = att.get('mime_type') or att.get('content_type') or "application/octet-stream"
                file_node = {
                    "@id": file_id,
                    "@type": "File",
                    "name": safe_filename,
                    "encodingFormat": mime,
                }
                # FILE_SUGGESTED in TheELNFileFormat's checker is
                # [sha256, encodingFormat, contentSize, description]; sha256 is filled in below,
                # once the bytes have actually been streamed. identifier is the ELN's attachment
                # uuid, which survives re-export and so is a stabler handle than the filename.
                identifier = att.get('identifier')
                if identifier:
                    file_node["identifier"] = str(identifier)
                description = att.get('description')
                if isinstance(description, str) and description.strip():
                    file_node["description"] = description.strip()
                for prop, key in (("dateCreated", "created_at"), ("dateModified", "updated_at")):
                    stamp = AbstractElement._parse_timestamp(att.get(key))
                    if stamp is not None:
                        file_node[prop] = stamp.isoformat()
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
            annotate_element_metadata(elem, node, _undated_elements)

            # Which collections this element belongs to. An element in two collections used to be
            # unrepresentable: its crate path was derived from the collection it was reached
            # through, so the second traversal overwrote the first and one membership was lost
            # silently. Membership is now a reference, and an element sits at one
            # collection-independent path however many collections hold it.
            _member_of = [{"@id": col_node_ids[c]}
                          for c in elem_to_cols.get(elem_id, []) if c in col_node_ids]
            if _member_of:
                node["isPartOf"] = _member_of if len(_member_of) > 1 else _member_of[0]

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
                    prop_val = elem.properties.get(prop_name)
                    # skip empty values ('' / [] / {}) — they add noise keys to the crate node
                    if prop_val not in (None, '', [], {}):
                        value = clean_json_value(prop_val)
                        # Raw Chemotion payloads (notably `variations`) are arbitrary nested JSON
                        # keyed on plain `id`. Embedding them as objects makes the crate
                        # unparseable — py-rocrate rejects it with "ValueError: no @id in {...}" —
                        # so opaque structures are carried as a JSON string. The data is preserved;
                        # it just stops pretending to be linked data.
                        #
                        # Only *nested* values qualify. A flat list of literals (e.g.
                        # purification == ["Extraction", "Filtration"]) is a perfectly good
                        # multi-valued property in RO-Crate, and stringifying it would destroy a
                        # legitimate value to solve a problem it does not have.
                        if _is_opaque_payload(value):
                            value = json.dumps(value, ensure_ascii=False, default=lambda o: str(o))
                        node[prop_name] = value

            files = elem_files[elem_id]
            # Keyed on the attachment record's own identity, matching _CrateFileNamer, so every
            # reference below reuses the exact name that went into the ZIP entry path and the File
            # node's @id. This used to key on `id(att)` — Python object identity — which held only
            # while `elem.attachments` / `Analysis.datasets` / `Dataset.attachments` handed back
            # the *same* wrapper objects within one export. A miss did not fail loudly: it fell
            # through to recomputing the name *without* the collision-disambiguation suffix,
            # producing an @id pointing at a ZIP entry that does not exist.
            _safe_name_by_attachment = {_attachment_key(att): safe_name for att, safe_name in files}

            def _safe_file_id(att, _rel_path=rel_path, _table=_safe_name_by_attachment):
                safe_name = _table.get(_attachment_key(att))
                if safe_name is None:
                    # Not part of this element's deduped file list (e.g. a genuine duplicate that
                    # was dropped) -- recompute so a reference still resolves to a stable id.
                    name_part, ext_part = os.path.splitext(os.path.basename(att['filename']))
                    safe_name = sanitize_filename(name_part) + ext_part
                return f"{_rel_path}{safe_name}"

            if files:
                node["hasPart"] = [{"@id": _safe_file_id(att)} for att, _safe_name in files]

            # Link each analysis' data files to its AnalysisSourceData node, so the
            # provenance chain reaches the actual spectra:
            # AnalysisDataset → DataAnalysis → AnalysisSourceData → files.
            if hasattr(elem, "analyses") and elem.analyses:
                for _ana_idx, ana in enumerate(elem.analyses):
                    _ana_get = ana.get if hasattr(ana, "get") else (lambda _k, _d=None: _d)
                    src_node = graph_nodes.get(
                        f"{rel_path}#analysis_{_ana_get('id') or _ana_idx}_source_data")
                    if src_node is None:
                        continue
                    parts = []
                    if hasattr(ana, "datasets") and ana.datasets:
                        for ds in ana.datasets:
                            for att in (ds.attachments or []):
                                parts.append({"@id": _safe_file_id(att)})
                    if parts:
                        src_node["hasPart"] = parts

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
                                # `cas` and `names` are Chemotion column names, not vocabulary
                                # terms: as JSON-LD keys the @context does not map them, which
                                # RO-Crate 1.2 rejects outright (`ro-crate-1.2_4.1`). schema.org
                                # already has both concepts, and the RO-Crate context defines
                                # them, so the data is kept and the crate stays valid.
                                if elem.molecule.get('cas') is not None:
                                    node['identifier'] = elem.molecule.get('cas')
                                if elem.molecule.get('names'):
                                    node['alternateName'] = elem.molecule.get('names')
                                break
                except Exception as e:
                    logger.debug("Failed to enrich molecule node %s: %s", node_id, e)

        # Collections are *contextual* entities (`schema:Collection`), not directories. Typing them
        # `Dataset` would make each one a Data Entity Directory, which RO-Crate 1.1 requires to
        # have a path-shaped `@id` ending in `/` and to be reachable from a `hasPart` -- i.e. it
        # would force the element back inside exactly one collection folder. A Chemotion collection
        # is an organisational grouping, so it says so and refers to its members instead.
        for col_id, col_node_id in col_node_ids.items():
            col = collections_by_id[col_id]
            col_node = {
                "@id": col_node_id,
                "@type": "Collection",
                "name": col.label or "Collection",
            }
            if col.collection_json and col.collection_json.get("description"):
                col_node["description"] = col.collection_json.get("description")
            parent_key = (col._parent.id or id(col._parent)) if col._parent else None
            if parent_key is not None and parent_key in col_node_ids:
                col_node["isPartOf"] = {"@id": col_node_ids[parent_key]}
            # The exact inverse of the elements' `isPartOf`, built from the same index so the two
            # directions cannot drift apart. Omitted rather than empty for a collection with no
            # elements of its own.
            members = [{"@id": elem_paths[key]}
                       for key, cols in elem_to_cols.items()
                       if col_id in cols and key in elem_paths]
            if members:
                col_node["hasPart"] = members
            metadata_dict["@graph"].append(col_node)
            graph_nodes[col_node_id] = col_node

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

        # RO-Crate 1.1 §8.2/§8.3: the Root Data Entity MUST carry `description` and `license`.
        # (Both are flagged as REQUIRED failures by the TheELNConsortium conformance suite.)
        root_node.setdefault(
            "description",
            (self.collection_json or {}).get("description")
            or f"Chemotion ELN collection '{self.label or 'Collection'}' "
               "exported as an RO-Crate by chemotion-api.",
        )
        # §8.4: `datePublished` MUST be a valid ISO 8601 date.
        root_node.setdefault("datePublished", datetime.now(UTC).date().isoformat())
        # The collection's own id, so a re-export is recognisably the same collection.
        if self.id is not None:
            root_node.setdefault("identifier", str(self.id))
        # The root Dataset is what declares the profiles: RO-Crate 1.2 *and* the `.eln` version.
        # `tests/checks/versions.py` reads the ELN version from here and nowhere else — a crate
        # that declares it only on the descriptor is treated as plain RO-Crate.
        root_node["conformsTo"] = [{"@id": _RO_CRATE_PROFILE}, {"@id": _ELN_SPEC_PROFILE}]
        for _profile_id, _profile_name in (
                (_RO_CRATE_PROFILE, "RO-Crate 1.2 Specification"),
                (_ELN_SPEC_PROFILE, "ELN-File Format 1.2+20260923 Specification")):
            if _profile_id not in graph_nodes:
                _profile_node = {
                    "@id": _profile_id,
                    "@type": ["CreativeWork", "Profile"],
                    "name": _profile_name,
                }
                metadata_dict["@graph"].append(_profile_node)
                graph_nodes[_profile_id] = _profile_node

        root_node.setdefault("license", {"@id": _CRATE_DEFAULT_LICENSE})
        if not any(n.get("@id") == _CRATE_DEFAULT_LICENSE
                   for n in metadata_dict["@graph"] if isinstance(n, dict)):
            license_node = {
                "@id": _CRATE_DEFAULT_LICENSE,
                "@type": "CreativeWork",
                "name": "Creative Commons Attribution 4.0 International",
                "description": "Default export licence. Set a different one on the crate if the "
                               "data is under other terms.",
            }
            metadata_dict["@graph"].append(license_node)
            graph_nodes[_CRATE_DEFAULT_LICENSE] = license_node

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
        # `hasPart` carries data entities only. The collection entities are contextual, so the
        # root reaches them through `mentions` -- otherwise nothing in the crate would point at
        # them and a reader walking from the root would never see the collection structure.
        if col_node_ids:
            root_node["mentions"] = [{"@id": node_id} for node_id in col_node_ids.values()]

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

        # Producer marker: a SoftwareApplication node naming the library that wrote the crate.
        # It hangs off the CreateAction's ``instrument`` below, which is the conventional place
        # for the writing software. import_eln keys its "own crate" check on it; see
        # ElnCrate.producer for the compatibility path.
        from chemotion_api.eln_producer import producer_node
        software_node = producer_node()
        metadata_dict["@graph"].append(software_node)
        graph_nodes[software_node["@id"]] = software_node

        # Export provenance: what wrote this crate, and when.
        export_time = datetime.now(UTC).isoformat()
        create_action = {
            "@id": "#ro-crate_created",
            "@type": "CreateAction",
            "name": "RO-Crate created",
            "object": {"@id": "./"},
            "endTime": export_time,
            "instrument": {"@id": software_node["@id"]},
            "actionStatus": {"@id": "http://schema.org/CompletedActionStatus"},
        }
        metadata_dict["@graph"].append(create_action)
        graph_nodes[create_action["@id"]] = create_action

        # Which notebook this data came from, and at what version. Without it a crate cannot say
        # whether it was produced by a v3-era ELN or a v4 one — the client version alone does not
        # answer that. The host comes from the session: live gives the real URL, the offline shim
        # gives the RFC 2606 `.invalid` sentinel, so "unknown origin" is stated rather than faked.
        # A plain Collection has no _session of its own; the root holds it (as new_sample_smiles
        # and share already do). OfflineCollection carries one directly, hence the fallback order.
        session = getattr(self, "_session", None)
        if session is None:
            session = getattr(self.get_root(), "_session", None)
        source_manager = getattr(session, "schema_manager", None)
        source_version = getattr(source_manager, "version_string", None)
        real_host = (getattr(session, "host_url", "") or "").strip("/")
        if disclose_host:
            source_host = real_host or OFFLINE_HOST
        else:
            source_host = OFFLINE_HOST
            # Naming the sentinel on one node is NOT enough: the hostname also reaches the crate
            # through prose built elsewhere (a molecule's dct:description carries the API URL it
            # was assigned from) and through any element URI that was never remapped. Withholding
            # has to mean withholding everywhere, or the promise is false.
            if real_host:
                replaced = _replace_host(metadata_dict, real_host, OFFLINE_HOST)
                logger.info(
                    "export_eln: withholding the ELN hostname (%s); recorded as %s and replaced in "
                    "%d further value(s). The ELN version is still recorded.",
                    real_host, OFFLINE_HOST, replaced)
            else:
                logger.info("export_eln: no ELN hostname to record; using %s.", OFFLINE_HOST)
        # RO-Crate 1.2 makes `version` REQUIRED on a SoftwareApplication (`ro-crate-1.2_32.3`).
        # Offline there is no `/about` to read, and the standing rule is that a crate states what
        # it does not know rather than inventing it — so the node is only *typed* as a software
        # application when we can actually name its version. Without one it stays a CreativeWork:
        # still the thing the data came from, still reachable via `isBasedOn`, but not pretending
        # to identify a build. `ElnCrate.source_eln` resolves it by reference, not by type.
        source_node = {
            "@id": source_host,
            "@type": "SoftwareApplication" if source_version else "CreativeWork",
            "name": "Chemotion ELN",
            "url": source_host,
        }
        if source_version:
            # The full string, not the dotted numbers: v4 ships under a moving `next-release` tag,
            # so `4.0.0` cannot tell two builds months apart from one another.
            source_node["version"] = source_version
        else:
            logger.info(
                "export_eln: the source ELN's version is unknown (no /about to read offline), so "
                "the crate records it as a CreativeWork rather than claiming a software version.")
        revision = getattr(source_manager, "revision", None)
        if revision:
            source_node["identifier"] = revision
        if source_host not in graph_nodes:
            metadata_dict["@graph"].append(source_node)
            graph_nodes[source_host] = source_node
        root_node.setdefault("isBasedOn", {"@id": source_host})

        # sdPublisher names the *organization* publishing the crate, as the .eln spec asks.
        # Rather than invent a vendor entity, reuse the first author's ROR-identified affiliation
        # — already in the graph as the root publisher.
        meta_descriptor = {
            "@id": "ro-crate-metadata.json",
            "@type": "CreativeWork",
            "name": "RO-Crate metadata descriptor",
            "about": {"@id": "./"},
            "conformsTo": {"@id": _RO_CRATE_PROFILE},
            "dateCreated": export_time,
            # TheELNFileFormat's metadata check still lists `version` as suggested on this node.
            "version": "1.0",
        }
        # Author validation (chemotion_api.authors) makes at least one ROR-identified affiliation
        # mandatory, so there is always an organization to name here.
        if publisher_ref is not None:
            meta_descriptor["sdPublisher"] = publisher_ref
            publisher_node = graph_nodes.get(publisher_ref.get("@id"), {})
            logger.info(
                "export_eln: publishing this crate as %r (%s) — taken from the first author's "
                "affiliation. Set a different first affiliation if another organization should be "
                "credited as publisher.",
                publisher_node.get("name") or publisher_ref.get("@id"), publisher_ref.get("@id"),
            )
        metadata_dict["@graph"].append(meta_descriptor)

        # Final spec pass: drop blank nodes (RO-Crate requires a fully flattened graph) and mirror
        # chem-dcat-ap's dct:title into schema.org name on Dataset nodes. Runs last so it sees
        # every node, including the ones added just above.
        renamed = flatten_crate_graph(metadata_dict)
        if renamed:
            logger.debug("Flattened %d blank node(s) into addressable crate entities", renamed)

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

        # Strict mode must fail *before* any bytes are written to file_path (a previous version
        # wrote the crate first and raised afterwards, leaving a "failed" export sitting at the
        # requested path). Every skip stage except attachment "download" is already fully known
        # at this point (retrieve/load during indexing, dcat_mapping during the loop above,
        # offline_reconstruction before that); download failures can only happen during the write
        # itself, so _write_crate_zip is also told about ``strict`` and raises immediately on the
        # first one, before its temp file is renamed into place.
        if strict and skipped:
            logger.warning("export_eln: %d issue(s) during export (strict mode; aborting before writing %s). "
                           "See export manifest.", len(skipped), file_path)
            raise RuntimeError(f"export_eln strict mode: {len(skipped)} issue(s) during export: {skipped}")

        # Say plainly when timestamps could not be emitted. A Chemotion *export collection* dump
        # carries no created_at/updated_at at all, so an offline export has none to give.
        # Recording it lets a reader tell "the source had none" from "the elements genuinely have
        # none" instead of inferring from absence.
        #
        # Appended after the strict check but *before* the crate is written: a source that never
        # had timestamps is a limitation of that source, not a failed export — so it must not make
        # strict mode reject every offline export, but it does belong in the crate's manifest.
        if _undated_elements:
            logger.info(
                "export_eln: %d of %d element(s) carry no timestamps, so dateCreated/dateModified "
                "were omitted for them. An offline export (import_export_zip) never has them — the "
                "Chemotion export dump does not record timestamps; export from a live server if "
                "you need them.", len(_undated_elements), len(elem_paths))
            skipped.append({"kind": "timestamps", "stage": "metadata",
                            "count": len(_undated_elements), "ids": _undated_elements[:20],
                            "error": "source carried no created_at/updated_at; "
                                     "dateCreated/dateModified omitted"})

        _base_ctx = ctx if isinstance(ctx, dict) else {}

        # Names, schema.org types, descriptions for referenced vocabulary IRIs, and reachability.
        # Runs before the @context is declared because it adds nodes (but no new keys).
        _polish_contextual_entities(metadata_dict, root_node, _base_ctx)

        # Declare every key the RO-Crate context does not already define. This must run *last*:
        # element, file, collection, profile and provenance nodes are all appended above, so a
        # declaration made earlier would miss whatever came after it.
        _extra_terms = _declare_unmapped_terms(metadata_dict, _base_ctx)
        metadata_dict["@context"] = [_CRATE_CONTEXT[0], {**_CRATE_NAMESPACES, **_extra_terms}]
        logger.debug("export_eln: declared %d term(s) in the crate's @context.", len(_extra_terms))

        try:
            _write_crate_zip(file_path, root_folder, metadata_dict, elem_files, elem_paths,
                             skipped, progress=_tick_file, strict=strict,
                             declare_skipped=declare_skipped,
                             mask_host=None if disclose_host else real_host or None)
        finally:
            if _bar2 is not None:
                _bar2.close()
            # In the `finally`: a strict-mode failure raises out of _write_crate_zip, and
            # persisting here anyway means the (slow, network-bound) OLS lookups from this run are
            # not thrown away just because the export was refused afterwards.
            _ols_cache.save()

        logger.info("Exported %d element(s) and %d collection(s) to %s",
                    len(elem_paths), len(col_node_ids), file_path)

        if skipped:
            # Note: dcat_mapping entries are still exported as generic Dataset nodes (not lost);
            # retrieve/load entries ARE omitted from the crate; `metadata` entries are notes about
            # what the source could not supply. (strict mode already raised above if this branch is
            # reached with strict=True, so this is the non-strict summary log.)
            notes = [s for s in skipped if s["stage"] == "metadata"]
            mapped_generically = [s for s in skipped if s["stage"] == "to_dcat_ap"]
            omitted = [s for s in skipped if s not in notes and s not in mapped_generically]
            logger.warning("export_eln: %d issue(s) during export (%d element(s) omitted, %d mapped "
                           "generically, %d note(s)). See export manifest.",
                           len(skipped), len(omitted), len(mapped_generically), len(notes))
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
        # The cache exists to let get_root_collection() serve both halves from one request, so it
        # is consumed here rather than read: a standalone load_sync_collection() — the call you
        # make to see a share someone just granted — must not hand back the listing from whenever
        # load_collection() last ran, with nothing to indicate it is stale.
        payload = self._collections_payload or self._fetch_collections()
        self._collections_payload = None
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
