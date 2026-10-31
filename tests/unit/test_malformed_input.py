"""Slice 6: the server and a Rails dump send shapes the parsers did not expect.

Every case here aborted an import (or produced a *wrong* value) before the fix. The distinction
that matters throughout: a structurally wrong document is refused, a single bad row is dropped
with a warning, and nothing is ever invented to paper over a gap.
"""
import json
import zipfile

import pytest

from chemotion_api.offline.export_reader import ExportAdapter, _table


# --- export.json shapes ---------------------------------------------------

def test_table_that_is_not_an_object_is_refused():
    with pytest.raises(ValueError, match="expected an object"):
        _table({"Sample": [1, 2, 3]}, "Sample")


def test_malformed_rows_are_dropped_not_fatal(caplog):
    """`"Sample": {"s1": null}` used to reach `.get()` on None -> TypeError mid-import."""
    with caplog.at_level("WARNING"):
        rows = _table({"Sample": {"good": {"name": "x"}, "bad": None, "worse": [1]}}, "Sample")
    assert rows == {"good": {"name": "x"}}
    assert "2 malformed row(s)" in caplog.text


def test_missing_table_is_empty_not_an_error():
    assert _table({}, "Sample") == {}


def test_null_position_does_not_abort_the_import():
    """`"position": null` is routine in a Rails dump; `.get("position", 0)` did not cover it."""
    dump = {
        "Reaction": {"r1": {"name": "R"}},
        "Sample": {"s1": {"name": "A"}, "s2": {"name": "B"}, "s3": {"name": "C"}},
        "ReactionsStartingMaterialSample": {
            "j1": {"reaction_id": "r1", "sample_id": "s1", "position": 2},
            "j2": {"reaction_id": "r1", "sample_id": "s2", "position": None},
            "j3": {"reaction_id": "r1", "sample_id": "s3"},
        },
    }
    rxn = ExportAdapter(dump).to_reaction_json("r1")
    # null and missing both sort as 0, ahead of the explicit position 2
    assert [s["name"] for s in rxn["starting_materials"]] == ["B", "C", "A"]


def test_molecule_absent_from_the_dump_gets_no_fabricated_id(caplog):
    """A dangling reference must not mint `chemotion://molecule/<id>` for a molecule that is not there."""
    dump = {"Sample": {"s1": {"name": "A", "molecule_id": "m-does-not-exist"}}, "Molecule": {}}
    with caplog.at_level("WARNING"):
        sample = ExportAdapter(dump).to_sample_json("s1")
    assert sample["molecule"]["id"] is None
    assert "absent from the export dump" in caplog.text


def test_molecule_present_still_gets_its_id():
    dump = {"Sample": {"s1": {"molecule_id": "m1"}},
            "Molecule": {"m1": {"cano_smiles": "O", "inchistring": "InChI=1S/H2O/h1H2"}}}
    mol = ExportAdapter(dump).to_sample_json("s1")["molecule"]
    assert isinstance(mol["id"], int) and mol["cano_smiles"] == "O"


# --- crate shapes ---------------------------------------------------------

def _write_crate(tmp_path, metadata, name="mini.eln"):
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mini.eln/ro-crate-metadata.json", json.dumps(metadata))
    return path


def test_metadata_that_is_a_list_is_refused_clearly(tmp_path):
    """`metadata` of `[]` reached `.get("@graph")` -> AttributeError with no explanation."""
    from chemotion_api.offline import import_eln

    with pytest.raises(ValueError, match="not an object"):
        import_eln(_write_crate(tmp_path, []))


def test_truncated_zip_is_not_reported_as_not_an_archive(tmp_path):
    """A partial download said "neither a ZIP nor a crate directory", sending people the wrong way."""
    from chemotion_api.offline import import_eln

    whole = _write_crate(tmp_path, {"@graph": []}).read_bytes()
    truncated = tmp_path / "partial.eln"
    truncated.write_bytes(whole[: len(whole) // 2])

    with pytest.raises(ValueError, match="truncated or still downloading"):
        import_eln(truncated)


def test_not_an_archive_at_all_keeps_its_own_message(tmp_path):
    from chemotion_api.offline import import_eln

    plain = tmp_path / "notes.txt"
    plain.write_text("hello")
    with pytest.raises(ValueError, match="neither a .eln ZIP archive"):
        import_eln(plain)


@pytest.mark.parametrize("suffix, expected", [
    ("Water_42", 42),
    ("Water_007", 7),
    ("Water_²", None),      # superscript two: isdigit() True, int() raises
    ("Water_٩", None),      # arabic-indic nine: isdecimal() True, int() returns a WRONG 9
    ("Water", None),
    ("Water_", None),
])
def test_source_id_accepts_only_ascii_digits(suffix, expected):
    from chemotion_api.offline.eln_reader import ElnDataset

    ds = ElnDataset.__new__(ElnDataset)
    ds.node = {"@id": f"./samples/{suffix}/"}
    assert ds.source_id == expected


# --- ontology helpers -----------------------------------------------------

def test_ontology_patch_tolerates_a_non_object_graph_member():
    from chemotion_api.ontology_patch import patch_metadata_dict

    metadata = {"@graph": ["a bare string", None,
                           {"@id": "./s/", "variableMeasured": [
                               {"@type": "PropertyValue",
                                "propertyID": "chemotion:elementType", "value": "sample"}]}]}
    assert patch_metadata_dict(metadata, {"sample": "http://purl.obolibrary.org/obo/CHMO_0002773"}) == 1


def test_ontology_patch_tolerates_a_non_list_graph(caplog):
    from chemotion_api.ontology_patch import patch_metadata_dict

    with caplog.at_level("WARNING"):
        assert patch_metadata_dict({"@graph": "nonsense"}, {"sample": "x"}) == 0
    assert "not a list" in caplog.text


@pytest.mark.parametrize("entry", [
    {"iri": "http://x/1"},                      # no label
    {"label": "melting point"},                 # no iri
    {"iri": 7, "label": "melting point"},       # wrong type
    "not a dict",
])
def test_malformed_ols_cache_entry_is_a_miss_not_a_crash(tmp_path, entry, caplog):
    """A hand-edited cache file must degrade to a re-lookup, not raise inside an export."""
    from chemotion_api.ontology.ols_lookup import OlsCache

    path = tmp_path / "ols.json"
    path.write_text(json.dumps({"chmo": {"melting point": entry}}))
    with caplog.at_level("WARNING"):
        hit, term = OlsCache(path).get("chmo", "melting point")
    assert (hit, term) == (False, None)
    assert "malformed OLS cache entry" in caplog.text


def test_ols_cache_that_is_not_an_object_starts_empty(tmp_path):
    from chemotion_api.ontology.ols_lookup import OlsCache

    path = tmp_path / "ols.json"
    path.write_text("[1, 2, 3]")
    assert OlsCache(path).get("chmo", "anything") == (False, None)


def test_ols_cache_negative_entry_is_still_a_hit(tmp_path):
    """`null` is a deliberate negative-cache record and must not be confused with a bad entry."""
    from chemotion_api.ontology.ols_lookup import OlsCache

    path = tmp_path / "ols.json"
    path.write_text(json.dumps({"chmo": {"nope": None}}))
    assert OlsCache(path).get("chmo", "nope") == (True, None)


# --- serialisation --------------------------------------------------------

def test_segment_with_no_json_data_entry_raises_instead_of_indexerror():
    """`list_idx = len(res_list)` then indexed one past the end -> bare IndexError on save.

    Appending a blank entry instead would be worse: ``clean_generic_object_json`` reads
    ``properties.layers.<key>.fields``, which only the server's klass template provides, so a
    fabricated skeleton would silently drop the segment's values.
    """
    from chemotion_api.elements.abstract_element import AbstractElement

    class _Stub:
        element_type, id = "Sample", 42
        json_data = {"segments": [{"id": 1}]}
        segments = {"Stress": {"layer": {"f": 1}}}
        _segments_mapping = {"Stress": {"__id": 999}}   # __id 999 is not in json_data['segments']

    with pytest.raises(RuntimeError, match="has no entry in the element's json_data"):
        AbstractElement._clean_segments_data(_Stub())


def test_segment_list_tolerates_a_non_dict_member():
    """`x.get('id')` assumed every member of json_data['segments'] is a dict."""
    from chemotion_api.elements.abstract_element import AbstractElement

    class _Stub:
        element_type, id = "Sample", 42
        json_data = {"segments": ["junk", None, {"id": 7, "properties": {"layers": {}}}]}
        segments = {"Stress": {}}                       # no layers to walk -> no-op clean
        _segments_mapping = {"Stress": {"__id": 7}}

    assert AbstractElement._clean_segments_data(_Stub())["segments"][2]["id"] == 7
