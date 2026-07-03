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
import shutil
import tempfile
import zipfile

from chemotion_api.ontology_map import ELEMENT_TYPE_PROPERTY_ID


def _metadata_member(names: list[str]) -> str | None:
    """Return the archive member ending in ``ro-crate-metadata.json``, or ``None`` if absent."""
    for n in names:
        if n.endswith("ro-crate-metadata.json"):
            return n
    return None


def patch_metadata_dict(metadata: dict, mapping: dict[str, str]) -> int:
    """Inject ontology IRIs into a parsed ro-crate-metadata dict in place.

    :param mapping: ``{element_kind: ontology_IRI}``.
    :return: number of nodes patched.
    """
    patched = 0
    for node in metadata.get("@graph", []):
        var = node.get("variableMeasured")
        if not isinstance(var, list):
            continue
        for pv in var:
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
    with zipfile.ZipFile(eln_path, "r") as zin:
        names = zin.namelist()
        meta_name = _metadata_member(names)
        if meta_name is None:
            raise ValueError(f"No ro-crate-metadata.json found in {eln_path}")
        metadata = json.loads(zin.read(meta_name))
        patched = patch_metadata_dict(metadata, mapping)

        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".eln")
        os.close(tmp_fd)
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename == meta_name:
                    zout.writestr(item, json.dumps(metadata, indent=2))
                else:
                    zout.writestr(item, zin.read(item.filename))

    target: str = output_path or eln_path  # no output_path -> patch in place (overwrite eln_path)
    shutil.move(tmp_path, target)
    return patched
