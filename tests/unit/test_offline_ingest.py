"""Offline ingestion of a Chemotion export-collection dump (no live server).

All tests use a small self-contained fixture (tests/fixtures/mini_export.json); the full
chem-dcat-ap export tests are marked ``heavy``.
"""
import json
import os
import zipfile

import pytest

HERE = os.path.dirname(__file__)
FIXTURES = os.path.join(HERE, "..", "fixtures")
MINI = os.path.join(FIXTURES, "mini_export.json")
LIVE_SAMPLE = os.path.join(FIXTURES, "live_sample.json")


def _mini_dir(tmp_path):
    """Lay the mini fixture out as an export directory."""
    d = tmp_path / "export"
    d.mkdir()
    (d / "export.json").write_text(open(MINI).read(), encoding="utf-8")
    return d


def _authors():
    """A minimal valid author list (every .eln export now requires authors)."""
    from chemotion_api import Author, AuthorAffiliation
    return [Author(name="Test Author", orcid="0000-0002-1825-0097",
                   affiliations=[AuthorAffiliation(name="KIT", ror="https://ror.org/04t3en479")])]


def test_accepts_bare_export_json_file(tmp_path):
    """ExportArchive also accepts a single relational dump file (any name), not just dir/zip."""
    from chemotion_api.offline import import_export_zip
    f = tmp_path / "chemotion_export_collection.json"
    f.write_text(open(MINI).read(), encoding="utf-8")
    col = import_export_zip(f)
    assert len(col.get_reactions()) == 1


def test_reconstructs_reaction_and_materials(tmp_path):
    from chemotion_api.offline import import_export_zip
    col = import_export_zip(_mini_dir(tmp_path))
    assert col.label == "Mini Test Collection"
    reactions = col.get_reactions()
    assert len(reactions) == 1
    rxn = reactions[0]
    assert rxn.name == "Oxidation of ethanol"
    assert len(rxn.starting_materials) == 1
    assert len(rxn.products) == 1
    # all samples belong to the reaction → none standalone
    assert col.get_samples() == []


def test_material_properties_and_join_fields(tmp_path):
    from chemotion_api.offline import import_export_zip
    rxn = import_export_zip(_mini_dir(tmp_path)).get_reactions()[0]
    sm = rxn.starting_materials[0]
    # amounts reshaped from the relational *_amount_* columns
    assert sm.properties["target_amount"].value == 0.1
    assert sm.properties["target_amount"].unit == "mol"
    assert sm.properties["density"] == 0.789
    # equivalent comes from the join record (not the Sample table)
    assert rxn.products[0].properties["equivalent"] == 0.85
    # molecule embedded from the Molecule table
    assert sm.molecule.get("inchikey") == "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"
    assert sm.molecule.get("cano_smiles") == "CCO"


def test_analyses_and_attachments_reconstructed(tmp_path):
    from chemotion_api.offline import import_export_zip
    rxn = import_export_zip(_mini_dir(tmp_path)).get_reactions()[0]
    analyses = list(rxn.analyses)
    assert len(analyses) == 1
    ana = analyses[0]
    # the CHMO kind survives for WS3 ontology annotation
    assert "CHMO:0000595" in ana.get("kind", "")
    ds = ana.datasets
    assert len(ds) == 1
    atts = list(ds[0].attachments)
    assert atts and atts[0]["filename"] == "product_1H.jdx"


def test_reconstructed_json_data_covers_live_shape(tmp_path):
    """The reshaped sample json_data carries the keys the live parser reads."""
    from chemotion_api.offline.export_reader import ExportArchive, ExportAdapter
    ad = ExportAdapter(ExportArchive(_mini_dir(tmp_path)).export_data)
    uuid = next(iter(ad.samples))
    jd = ad.to_sample_json(uuid)
    parser_keys = {
        "name", "short_label", "external_label", "target_amount_unit", "target_amount_value",
        "real_amount_unit", "real_amount_value", "molarity_unit", "molarity_value",
        "melting_point", "boiling_point", "stereo", "density", "purity", "sum_formula",
        "molecular_mass", "molecule", "type", "id",
    }
    missing = parser_keys - set(jd)
    assert not missing, f"reshaped json_data missing parser keys: {missing}"
    # if the live golden fixture is present, the embedded molecule sub-shape should line up
    # (top-level amount columns vary by listing context, but the molecule block is stable).
    if os.path.exists(LIVE_SAMPLE):
        live = json.load(open(LIVE_SAMPLE))
        if isinstance(live.get("molecule"), dict):
            live_mol = set(live["molecule"].keys())
            for k in ("cano_smiles", "inchikey", "inchistring", "iupac_name", "sum_formular"):
                assert k in live_mol and k in jd["molecule"]


def test_dcat_ap_types_offline(tmp_path):
    from chemotion_api.offline import import_export_zip
    rxn = import_export_zip(_mini_dir(tmp_path)).get_reactions()[0]
    assert type(rxn.to_dcat_ap()).__name__ == "ChemicalReaction"
    assert type(rxn.starting_materials[0].to_dcat_ap()).__name__ == "StartingMaterial"
    assert type(rxn.products[0].to_dcat_ap()).__name__ == "ChemicalProduct"


@pytest.mark.heavy
def test_offline_export_eln_full(tmp_path):
    """Full chem-dcat-ap export from the mini fixture → valid RO-Crate .eln."""
    from chemotion_api.offline import import_export_zip
    out = str(tmp_path / "offline.eln")
    import_export_zip(_mini_dir(tmp_path)).export_eln(out, authors=_authors())
    with zipfile.ZipFile(out) as z:
        meta = next(n for n in z.namelist() if n.endswith("ro-crate-metadata.json"))
        crate = json.loads(z.read(meta))
    assert crate["@context"] == "https://w3id.org/ro/crate/1.1/context"
    graph = crate["@graph"]
    # rich chem-dcat-ap graph, not a bare Dataset
    assert len(graph) > 30
    blob = json.dumps(graph)
    assert "ChemicalEntity" in blob or "CHEBI" in blob


@pytest.mark.heavy
def test_analysis_annotation_uses_embedded_chmo_without_network(tmp_path):
    """The analysis CHMO kind becomes a measurementTechnique DefinedTerm — no OLS call."""
    from unittest.mock import patch
    from chemotion_api.offline import import_export_zip
    out = str(tmp_path / "ann.eln")
    with patch("requests.get") as m:
        import_export_zip(_mini_dir(tmp_path)).export_eln(out, ontology_lookup=True, authors=_authors())
        assert not m.called  # embedded CHMO:0000595 ⇒ no network
    with zipfile.ZipFile(out) as z:
        graph = json.loads(z.read(next(n for n in z.namelist()
                                       if n.endswith("ro-crate-metadata.json"))))["@graph"]
    iris = {n["@id"] for n in graph if n.get("@type") == "DefinedTerm"}
    assert "http://purl.obolibrary.org/obo/CHMO_0000595" in iris
    assert any(n.get("measurementTechnique") for n in graph)


@pytest.mark.heavy
def test_analysis_annotation_falls_back_to_ols(tmp_path):
    """When an analysis kind has no embedded code, the exporter queries OLS (mocked)."""
    from unittest.mock import patch
    from chemotion_api.offline import import_export_zip

    # strip the embedded CHMO code so resolution must fall back to OLS
    data = json.load(open(MINI))
    data["Container"]["cont-analysis"]["extended_metadata"]["kind"] = "1H NMR"
    d = tmp_path / "export"; d.mkdir()
    (d / "export.json").write_text(json.dumps(data), encoding="utf-8")

    class _R:
        def raise_for_status(self): ...
        def json(self):
            return {"response": {"docs": [
                {"iri": "http://purl.obolibrary.org/obo/CHMO_0000595", "label": "1H NMR"}]}}

    out = str(tmp_path / "ols.eln")
    with patch("requests.get", return_value=_R()) as m:
        import_export_zip(d).export_eln(out, ontology_lookup=True, authors=_authors())
        assert m.called  # no embedded code ⇒ OLS consulted
    with zipfile.ZipFile(out) as z:
        graph = json.loads(z.read(next(n for n in z.namelist()
                                       if n.endswith("ro-crate-metadata.json"))))["@graph"]
    assert any(n.get("@type") == "DefinedTerm" and n["@id"].endswith("CHMO_0000595")
               for n in graph)


def test_unreconstructed_elements_are_reported_not_silently_dropped(tmp_path, caplog):
    """An archive holding element kinds ingestion can't rebuild (wellplates, research plans, …)
    must surface them in the skipped manifest instead of silently exporting a thinner crate."""
    import logging
    from chemotion_api.offline import import_export_zip

    data = json.loads(open(MINI).read())
    data["Wellplate"] = {"11111111-1111-1111-1111-111111111111": {"name": "WP1"}}
    data["ResearchPlan"] = {"22222222-2222-2222-2222-222222222222": {"name": "RP1"},
                            "33333333-3333-3333-3333-333333333333": {"name": "RP2"}}
    f = tmp_path / "export.json"
    f.write_text(json.dumps(data), encoding="utf-8")

    col = import_export_zip(f)
    assert col.unreconstructed_counts() == {"wellplate": 1, "research_plan": 2}

    out = tmp_path / "out.eln"
    with caplog.at_level(logging.WARNING, logger="chemotion_api.collection"):
        col.export_eln(str(out), ontology_lookup=False, authors=_authors())
    assert out.exists()
    warnings = [r.message for r in caplog.records if "does not reconstruct" in r.message]
    assert len(warnings) == 2

    # strict mode must refuse to produce a silently-thinned crate
    with pytest.raises(RuntimeError, match="offline_reconstruction"):
        col.export_eln(str(tmp_path / "strict.eln"), ontology_lookup=False,
                       authors=_authors(), strict=True)


@pytest.mark.heavy
def test_present_attachment_payload_lands_in_crate(tmp_path):
    """Regression: streaming an archived attachment into the crate must succeed (the offline
    response shim needs the full requests.Response streaming surface, incl. close())."""
    from chemotion_api.offline import import_export_zip

    d = _mini_dir(tmp_path)
    (d / "attachments").mkdir()
    (d / "attachments" / "att-1-uuid.jdx").write_bytes(b"##TITLE=1H\n##END=\n")
    out = str(tmp_path / "with_payload.eln")
    import_export_zip(d).export_eln(out, ontology_lookup=False, authors=_authors())
    with zipfile.ZipFile(out) as z:
        member = next(n for n in z.namelist() if n.endswith("product_1H.jdx"))
        assert z.read(member) == b"##TITLE=1H\n##END=\n"


# --- collection trees (bundles of collections in one export) ------------------------------------

def _bundle_data(second_root=False):
    """Mini fixture extended with membership joins, a child collection holding an extra
    standalone sample, and (optionally) a second top-level collection."""
    data = json.loads(open(MINI).read())
    data["Collection"]["col-2"] = {"label": "Child Col", "ancestry": "col-1"}
    data["Sample"]["smp-extra"] = dict(data["Sample"]["smp-sm"], name="Extra")
    data["CollectionsSample"] = {
        "cs-1": {"collection_id": "col-1", "sample_id": "smp-sm"},
        "cs-2": {"collection_id": "col-1", "sample_id": "smp-prod"},
        "cs-3": {"collection_id": "col-2", "sample_id": "smp-extra"},
    }
    data["CollectionsReaction"] = {
        "cr-1": {"collection_id": "col-1", "reaction_id": "rxn-1"},
    }
    if second_root:
        data["Collection"]["col-3"] = {"label": "Other Root", "ancestry": ""}
        data["CollectionsSample"]["cs-4"] = {"collection_id": "col-3", "sample_id": "smp-extra"}
    return data


def _import(tmp_path, data):
    from chemotion_api.offline import import_export_zip
    f = tmp_path / "export.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    return import_export_zip(f)


def test_collection_tree_is_rebuilt_with_scoped_elements(tmp_path):
    root = _import(tmp_path, _bundle_data())
    assert root.label == "Mini Test Collection"
    (child,) = root.children
    assert child.label == "Child Col"
    assert child._parent is root and child.get_root() is root
    assert root.id != child.id
    # elements are scoped per collection
    assert len(root.get_reactions()) == 1 and len(child.get_reactions()) == 0
    assert [s.name for s in child.get_samples()] == ["Extra"]
    # smp-sm / smp-prod are reaction materials, not standalone samples of col-1
    assert root.get_samples() == []


def test_bundle_of_top_level_collections_gets_wrapper_root(tmp_path):
    root = _import(tmp_path, _bundle_data(second_root=True))
    assert root.label == "Exported Collections"
    assert sorted(c.label for c in root.children) == ["Mini Test Collection", "Other Root"]
    # the wrapper holds no elements of its own
    assert root.get_samples() == [] and root.get_reactions() == []
    other = next(c for c in root.children if c.label == "Other Root")
    assert [s.name for s in other.get_samples()] == ["Extra"]   # shared sample appears there too


def test_dump_without_membership_tables_falls_back_flat(tmp_path, caplog):
    import logging

    data = json.loads(open(MINI).read())
    data["Collection"]["col-2"] = {"label": "Child Col", "ancestry": "col-1"}
    with caplog.at_level(logging.WARNING, logger="chemotion_api.offline.offline_collection"):
        root = _import(tmp_path, data)
    assert root.children == []
    assert len(root.get_reactions()) == 1                        # everything in one collection
    assert any("no membership join tables" in r.message for r in caplog.records)


@pytest.mark.heavy
def test_export_eln_preserves_collection_tree(tmp_path):
    """Exporting a rebuilt tree writes the child collection as a nested crate folder."""
    root = _import(tmp_path, _bundle_data())
    out = str(tmp_path / "tree.eln")
    root.export_eln(out, ontology_lookup=False, authors=_authors())
    with zipfile.ZipFile(out) as z:
        meta = next(n for n in z.namelist() if n.endswith("ro-crate-metadata.json"))
        graph = json.loads(z.read(meta))["@graph"]
    import re
    nodes = {n["@id"]: n for n in graph if "@id" in n}
    child_id = next(i for i in nodes if re.fullmatch(r"\./Child_Col_\d+/", i))
    assert nodes[child_id]["isPartOf"] == {"@id": "./"}
    # the child's standalone sample lives under the child's folder
    assert any(i.startswith(child_id + "samples/") for i in nodes)


def test_reaction_dcat_ap_rxno_and_rinchi(tmp_path):
    """Reactions carry an RXNO rdf_type and RInChI identifier attributes (chem-dcat-ap style)."""
    from chemotion_api.offline import import_export_zip
    rxn = import_export_zip(_mini_dir(tmp_path)).get_reactions()[0]
    dcat = json.loads(rxn.to_dcat_ap().model_dump_json(exclude_none=True))
    assert dcat["rdf_type"]["id"].startswith("RXNO:")
    quals = dcat.get("has_qualitative_attribute", [])
    rinchi = [q for q in quals if q.get("rdf_type", {}).get("id") == "IAO:0020000"]
    assert rinchi, "expected at least one RInChI identifier attribute"
    assert all(q.get("value") for q in rinchi)


@pytest.mark.heavy
def test_export_emits_analysis_dataset_chain(tmp_path):
    """Each analysis exports as an AnalysisDataset with the canonical was_generated_by chain."""
    from chemotion_api.offline import import_export_zip
    out = str(tmp_path / "ana.eln")
    import_export_zip(_mini_dir(tmp_path)).export_eln(out, authors=_authors(),
                                                      ontology_lookup=False)
    with zipfile.ZipFile(out) as z:
        meta = next(n for n in z.namelist() if n.endswith("ro-crate-metadata.json"))
        graph = json.loads(z.read(meta))["@graph"]
    by_id = {n.get("@id"): n for n in graph if isinstance(n, dict)}
    datasets = [n for n in graph if str(n.get("@id", "")).endswith("#analysis_0")]
    assert len(datasets) == 1
    ds = datasets[0]
    assert ds["@id"].startswith("./"), "analysis dataset id must be crate-relative"
    evaluation = by_id[ds["prov:wasGeneratedBy"]["@id"]]
    source = by_id[evaluation["prov:used"]["@id"]]
    measurement = by_id[source["prov:wasGeneratedBy"]["@id"]]
    types = measurement["@type"] if isinstance(measurement["@type"], list) else [measurement["@type"]]
    assert any("CHMO" in t for t in types), f"measurement not CHMO-typed: {types}"
    # the provenance chain must reach the actual data files
    src_parts = [p["@id"] for p in source.get("hasPart", [])]
    assert any(p.endswith(".jdx") for p in src_parts), f"source data not linked to files: {src_parts}"


@pytest.mark.heavy
def test_export_has_no_absolute_api_ids_and_no_duplicates(tmp_path):
    """Crate-relative policy holds for every record (incl. embedded reaction materials);
    the graph carries no duplicate @ids and no empty-value noise keys."""
    import re
    from collections import Counter
    from chemotion_api.offline import import_export_zip
    out = str(tmp_path / "rel.eln")
    import_export_zip(_mini_dir(tmp_path)).export_eln(out, authors=_authors(),
                                                      ontology_lookup=False)
    with zipfile.ZipFile(out) as z:
        meta = next(n for n in z.namelist() if n.endswith("ro-crate-metadata.json"))
        graph = json.loads(z.read(meta))["@graph"]
    ids = [n["@id"] for n in graph if isinstance(n, dict) and "@id" in n]
    api_ids = [i for i in ids if re.match(r"https?://[^/]+/api/v1/", str(i))]
    assert api_ids == [], f"absolute API URLs leaked into the crate: {api_ids}"
    dups = [k for k, v in Counter(ids).items() if v > 1]
    assert dups == [], f"duplicate @ids in graph: {dups}"
    rxn = next(n for n in graph if str(n.get("@id", "")).startswith("./reactions/")
               and str(n.get("@id", "")).endswith("/"))
    noise = {k: v for k, v in rxn.items() if v in ("", [], {})}
    assert noise == {}, f"empty-value noise keys on reaction node: {noise}"
