"""Heavy offline test: full export_eln emits the ontology placeholder for non-dcat elements.

This builds a real RO-Crate via export_eln (rdflib JSON-LD serialization against the 2627-term
context), so it is memory-heavy and marked `heavy`. The pure ontology_map/ontology_patch logic is
covered cheaply in tests/unit/test_ontology.py.
"""
import json
import zipfile
from unittest.mock import MagicMock

import pytest

from chemotion_api import Author, AuthorAffiliation
from chemotion_api.ontology_map import ELEMENT_TYPE_PROPERTY_ID

pytestmark = pytest.mark.heavy


def _authors():
    return [Author(name="Test Author", orcid="0000-0002-1825-0097",
                   affiliations=[AuthorAffiliation(name="Org", ror="https://ror.org/04t3en479")])]


def test_export_emits_placeholder_offline(tmp_path, monkeypatch):
    """Exporting an element without a chem-dcat-ap mapping produces a Dataset node carrying the
    ontology placeholder. Stubs the network-dependent SchemaView / RDFLibDumper."""
    import linkml_runtime.utils.schemaview as sv_mod
    import linkml_runtime.dumpers as dmp_mod

    monkeypatch.setattr(sv_mod, "SchemaView", lambda *a, **k: MagicMock())

    class _NoopDumper:
        def inject_triples(self, *a, **k):
            return None
    monkeypatch.setattr(dmp_mod, "RDFLibDumper", _NoopDumper)

    root_col = MagicMock()
    root_col._element_manager.all_classes = {"wellplate": {"label": "Wellplate"}}

    col = MagicMock()
    col.id = 123
    col.label = "Onto Col"
    col.get_root.return_value = root_col
    col._parent = None
    col.collection_json = None
    col.children = []

    wp = MagicMock()
    wp.id = 2001
    wp.name = "WP-1"
    wp._data_loaded = True
    wp.properties = {}
    wp.attachments = []
    wp.element_type = "wellplate"
    wp.to_dcat_ap.side_effect = Exception("no dcat")
    wp.eln_node_content.return_value = {}  # real dict, not a Mock (Mock would break json serialization)
    del wp.analyses

    col.get_samples.return_value = []
    col.get_reactions.return_value = []
    col.get_wellplates.return_value = [wp]
    col.get_research_plans.return_value = []
    col.get_generics_by_name.return_value = []

    out = tmp_path / "onto.eln"
    from chemotion_api.collection import Collection
    try:
        Collection.export_eln(col, str(out), authors=_authors())
    except Exception as e:  # export_eln may fetch the remote RO-Crate @context if not vendored
        if "URLError" in type(e).__name__ or "Network is unreachable" in str(e) or "urlopen" in str(e):
            pytest.skip("export_eln requires network for the RO-Crate @context; unreachable here")
        raise

    with zipfile.ZipFile(out, "r") as z:
        meta_name = next(n for n in z.namelist() if n.endswith("ro-crate-metadata.json"))
        meta = json.loads(z.read(meta_name))

    # variableMeasured holds references, not inline objects: RO-Crate requires a flattened graph,
    # so every entity is hoisted to top level. Resolve through @id to read the values.
    by_id = {n["@id"]: n for n in meta["@graph"] if isinstance(n.get("@id"), str)}

    def _resolve(values):
        return [by_id.get(v["@id"], v) if isinstance(v, dict) and "@id" in v else v
                for v in values]

    wp_nodes = [n for n in meta["@graph"]
                if isinstance(n.get("variableMeasured"), list)
                and any(pv.get("propertyID") == ELEMENT_TYPE_PROPERTY_ID
                        for pv in _resolve(n["variableMeasured"]))]
    assert len(wp_nodes) == 1
    node = wp_nodes[0]
    assert node["@type"] == "Dataset"  # structural type only, no bogus "Wellplate" type
    pv = _resolve(node["variableMeasured"])[0]
    assert pv["value"] == "wellplate"
    # The placeholder's identifier is omitted rather than written as "": an empty key says no more
    # than an absent one, and the conformance suite flags empty values. ontology_patch assigns the
    # key when the term is decided, so it does not need to pre-exist.
    assert "identifier" not in pv

    # --- ontology_patch must work on the crate as actually exported ------------------------------
    # Regression: the placeholder lives in `variableMeasured`, which RO-Crate requires to hold
    # {"@id": ...} references rather than inline objects. patch_metadata_dict originally read the
    # entries inline, so against a real crate it matched nothing and silently patched zero nodes.
    # The unit test for it used hand-built inline data and could not catch that.
    from chemotion_api.ontology_patch import patch_eln_ontology

    iri = "http://purl.obolibrary.org/obo/OBI_0400081"
    assert patch_eln_ontology(str(out), {"wellplate": iri}) == 1, "patched no nodes"

    with zipfile.ZipFile(out, "r") as z:
        patched = json.loads(z.read(next(n for n in z.namelist()
                                         if n.endswith("ro-crate-metadata.json"))))
    by_id = {n["@id"]: n for n in patched["@graph"] if isinstance(n.get("@id"), str)}
    pvs = [by_id.get(v["@id"], v) if isinstance(v, dict) and "@id" in v else v
           for n in patched["@graph"] if isinstance(n.get("variableMeasured"), list)
           for v in n["variableMeasured"]]
    assert any(pv.get("identifier") == iri for pv in pvs), "identifier not filled in"
    typed = [n for n in patched["@graph"]
             if iri in (n["@type"] if isinstance(n.get("@type"), list) else [n.get("@type")])]
    assert typed, "the ontology IRI was not added as an additional @type"
