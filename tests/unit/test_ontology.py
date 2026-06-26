"""Unit tests for the ontology registry + post-export patch helper. Offline/pure (no rdflib)."""
import json
import zipfile

from chemotion_api.ontology_map import (
    ontology_placeholder, iri_for, ELEMENT_TYPE_PROPERTY_ID, ELEMENT_TYPE_IRI,
)
from chemotion_api.ontology_patch import patch_metadata_dict, patch_eln_ontology


# --- registry / placeholder ------------------------------------------------------

def test_iri_for_known_undefined_kinds_returns_none():
    assert iri_for("wellplate") is None
    assert "wellplate" in ELEMENT_TYPE_IRI


def test_iri_for_unknown_kind_falls_back_to_generic():
    # unknown/custom generic types share the 'generic' placeholder (currently None)
    assert iri_for("some_custom_generic") == ELEMENT_TYPE_IRI.get("generic")


def test_placeholder_shape_for_undefined_kind():
    pv = ontology_placeholder("wellplate")
    assert pv["@type"] == "PropertyValue"
    assert pv["propertyID"] == ELEMENT_TYPE_PROPERTY_ID
    assert pv["value"] == "wellplate"
    assert pv["identifier"] == ""  # empty -> patch later


# --- patch_metadata_dict ---------------------------------------------------------

def test_patch_metadata_injects_iri_and_additional_type():
    iri = "http://purl.obolibrary.org/obo/OBI_0400081"
    meta = {"@graph": [
        {"@id": "./", "@type": "Dataset", "name": "root"},
        {"@id": "./wellplates/W_1/", "@type": "Dataset", "name": "W-1",
         "variableMeasured": [ontology_placeholder("wellplate")]},
    ]}
    assert patch_metadata_dict(meta, {"wellplate": iri}) == 1
    wp = meta["@graph"][1]
    assert wp["variableMeasured"][0]["identifier"] == iri
    assert wp["@type"] == ["Dataset", iri]  # structural type kept, ontology type added


def test_patch_metadata_skips_unmapped_kinds():
    meta = {"@graph": [{"@id": "./rp/1/", "@type": "Dataset",
                        "variableMeasured": [ontology_placeholder("research_plan")]}]}
    assert patch_metadata_dict(meta, {"wellplate": "http://x"}) == 0
    assert meta["@graph"][0]["@type"] == "Dataset"  # untouched


def test_patch_metadata_ignores_non_placeholder_nodes():
    meta = {"@graph": [{"@id": "./s/1/", "@type": "Dataset",
                        "variableMeasured": [{"@type": "PropertyValue", "propertyID": "other", "value": "x"}]}]}
    assert patch_metadata_dict(meta, {"x": "http://x"}) == 0


# --- patch_eln_ontology (zip round-trip) -----------------------------------------

def test_patch_eln_roundtrip_preserves_other_entries(tmp_path):
    eln = tmp_path / "demo.eln"
    meta = {"@context": "https://w3id.org/ro/crate/1.1/context", "@graph": [
        {"@id": "ro-crate-metadata.json", "@type": "CreativeWork", "about": {"@id": "./"}},
        {"@id": "./", "@type": "Dataset", "name": "root"},
        {"@id": "./wellplates/W_1/", "@type": "Dataset", "name": "W-1",
         "variableMeasured": [ontology_placeholder("wellplate")]},
    ]}
    with zipfile.ZipFile(eln, "w") as z:
        z.writestr("demo/ro-crate-metadata.json", json.dumps(meta))
        z.writestr("demo/wellplates/W_1/data.txt", b"hi")

    iri = "http://purl.obolibrary.org/obo/OBI_0400081"
    out = tmp_path / "patched.eln"
    assert patch_eln_ontology(str(eln), {"wellplate": iri}, output_path=str(out)) == 1

    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        patched = json.loads(z.read("demo/ro-crate-metadata.json"))
    wp = next(n for n in patched["@graph"] if n["@id"] == "./wellplates/W_1/")
    assert iri in wp["@type"] and wp["variableMeasured"][0]["identifier"] == iri
    assert "demo/wellplates/W_1/data.txt" in names


def test_patch_eln_raises_without_metadata(tmp_path):
    eln = tmp_path / "bad.eln"
    with zipfile.ZipFile(eln, "w") as z:
        z.writestr("demo/data.txt", b"x")
    import pytest
    with pytest.raises(ValueError, match="ro-crate-metadata.json"):
        patch_eln_ontology(str(eln), {"wellplate": "http://x"}, output_path=str(tmp_path / "o.eln"))
