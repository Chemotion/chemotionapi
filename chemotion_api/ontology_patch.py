"""Patch ontology annotations into an already-exported `.eln` file.

When the ontology term for an element kind (Wellplate, ResearchPlan, GenericElement, ...) is
decided later, this helper rewrites the ontology placeholders that ``export_eln`` left in the
crate's ``ro-crate-metadata.json`` — no re-export needed.

It locates Dataset nodes whose ``variableMeasured`` contains the ontology placeholder
(``propertyID == ELEMENT_TYPE_PROPERTY_ID``), fills the placeholder's ``identifier`` with the
IRI, and adds the IRI as an additional ``@type`` on the node so consumers get real semantic
typing.
"""
import json
import os
import logging
import posixpath
import shutil
import tempfile
import zipfile
from typing import Optional

from chemotion_api.ontology_map import ELEMENT_TYPE_PROPERTY_ID
from chemotion_api.offline.export_reader import (
    MAX_COMPRESSION_RATIO, MAX_ZIP_MEMBER_SIZE)

logger = logging.getLogger(__name__)

_METADATA_NAME = "ro-crate-metadata.json"


def _check_zip_member(archive: zipfile.ZipFile, member: str) -> None:
    """Raise ``ValueError`` if ``member`` is oversized or looks like a decompression bomb.

    A size cap alone is not a bomb defence — 400 MB out of a 400 KB archive passes a 500 MiB
    limit comfortably — so the compression ratio is checked too.
    """
    info = archive.getinfo(member)
    if info.file_size > MAX_ZIP_MEMBER_SIZE:
        raise ValueError(
            f"{member} is {info.file_size} bytes, exceeding the "
            f"{MAX_ZIP_MEMBER_SIZE}-byte member size limit")
    if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
        raise ValueError(
            f"{member} expands {info.file_size // max(info.compress_size, 1)}x "
            f"({info.compress_size} -> {info.file_size} bytes), above the "
            f"{MAX_COMPRESSION_RATIO}x limit; refusing to read it")


def _metadata_member(names: list[str]) -> str | None:
    """Return the archive member named ``ro-crate-metadata.json``, or ``None`` if absent.

    Matches on the exact basename (not a suffix, which would also match a hostile
    "evil-ro-crate-metadata.json") and, when several members match, prefers the shallowest one
    -- independent of the ZIP's ``namelist()`` order.
    """
    candidates = sorted(
        (n for n in names if posixpath.basename(n) == _METADATA_NAME),
        key=lambda n: n.count("/"),
    )
    return candidates[0] if candidates else None


def patch_metadata_dict(metadata: dict, mapping: dict[str, str]) -> int:
    """Inject ontology IRIs into a parsed ro-crate-metadata dict in place.

    :param mapping: ``{element_kind: ontology_IRI}``.
    :return: number of nodes patched.
    """
    patched = 0
    graph = metadata.get("@graph", [])
    if not isinstance(graph, list):
        logger.warning("@graph is a %s, not a list; nothing to patch", type(graph).__name__)
        return 0
    # RO-Crate requires a flattened graph, so `variableMeasured` holds {"@id": …} references
    # rather than inline PropertyValue objects. Resolve them, otherwise there is nothing with a
    # `propertyID` to match and this silently patches nothing.
    by_id = {n["@id"]: n for n in graph
             if isinstance(n, dict) and isinstance(n.get("@id"), str)}

    def _deref(value):
        if isinstance(value, dict) and set(value) == {"@id"}:
            return by_id.get(value["@id"], value)
        return value

    for node in graph:
        # An @graph member need not be an object; `by_id` above already guards exactly this.
        if not isinstance(node, dict):
            continue
        var = node.get("variableMeasured")
        if not isinstance(var, list):
            continue
        for entry in var:
            pv = _deref(entry)
            if not isinstance(pv, dict) or pv.get("propertyID") != ELEMENT_TYPE_PROPERTY_ID:
                continue
            kind = pv.get("value")
            if not isinstance(kind, str):
                continue
            iri = mapping.get(kind)
            if not iri:
                continue
            pv["identifier"] = iri
            # add the IRI as an additional @type for real semantic typing
            t = node.get("@type", "Dataset")
            types = [t] if isinstance(t, str) else list(t)
            if iri not in types:
                types.append(iri)
            node["@type"] = types
            patched += 1
    return patched


def patch_eln_ontology(eln_path: str, mapping: dict[str, str], output_path: str | None = None) -> int:
    """Patch ontology IRIs into an `.eln` archive.

    :param eln_path: path to the existing `.eln` (RO-Crate ZIP).
    :param mapping: ``{element_kind: ontology_IRI}`` (e.g. ``{"wellplate": "http://purl.obolibrary.org/obo/OBI_0400081"}``).
    :param output_path: where to write the patched archive; defaults to overwriting ``eln_path``.
    :return: number of nodes patched.
    :raises ValueError: if the archive has no ro-crate-metadata.json.
    """
    in_place = output_path is None
    with zipfile.ZipFile(eln_path, "r") as zin:
        names = zin.namelist()
        meta_name = _metadata_member(names)
        if meta_name is None:
            raise ValueError(f"No ro-crate-metadata.json found in {eln_path}")
        # The third ZIP reader in this package, and the only one that was unguarded: a 400 KB
        # `.eln` whose metadata inflates to 400 MB was read whole, before any validation. Same
        # limits as eln_reader._read_member and export_reader._check_member_size.
        _check_zip_member(zin, meta_name)
        metadata = json.loads(zin.read(meta_name))
        if not isinstance(metadata, dict):
            raise ValueError(
                f"{meta_name} in {eln_path} is a JSON {type(metadata).__name__}, not an object")
        patched = patch_metadata_dict(metadata, mapping)

        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".eln")
        os.close(tmp_fd)
        try:
            with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    if item.filename == meta_name:
                        zout.writestr(item, json.dumps(metadata, indent=2))
                    else:
                        # Streamed, so memory is bounded — but the bytes still land in a temp
                        # file, so a bomb member would fill TMPDIR. Checked before copying.
                        _check_zip_member(zin, item.filename)
                        with zin.open(item) as src, zout.open(item, "w") as dst:
                            shutil.copyfileobj(src, dst)
        except BaseException:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    # The move happens only after ``zin`` is closed: with no output_path the target *is*
    # ``eln_path``, and replacing a file that is still open for reading fails on Windows. It is
    # still wrapped so a failing move (cross-filesystem, permissions, disk full) cannot leak
    # tmp_path behind.
    target: str = output_path or eln_path  # no output_path -> patch in place (overwrite eln_path)
    try:
        shutil.move(tmp_path, target)
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    return patched
