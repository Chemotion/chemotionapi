"""Richer RO-Crate content for un-typed elements (Wellplate / ResearchPlan / GenericElement).

Method-level tests call ``eln_node_content`` against lightweight stubs (the methods only read
``wells`` / ``body`` / ``properties``). A heavy test drives the real exporter to confirm the
``else``-branch merge produces an enriched ``Dataset`` node that still keeps the ontology placeholder.
"""
import json
import os
import zipfile
from types import SimpleNamespace

import pytest

from chemotion_api.elements.wellplate import Wellplate
from chemotion_api.elements.research_plan import ResearchPlan
from chemotion_api.elements.generic_element import GenericElement


def test_generic_element_emits_property_values():
    stub = SimpleNamespace(properties={
        "temperature": {"value": 25, "unit": "°C"},
        "note": "stir well",
        "empty": "",
    })
    content = GenericElement.eln_node_content(stub)
    pvs = content["variableMeasured"]
    by_name = {p["name"]: p for p in pvs}
    assert by_name["temperature"]["value"] == 25
    assert by_name["temperature"]["unitText"] == "°C"
    assert by_name["note"]["value"] == "stir well"
    assert "empty" not in by_name  # blank values skipped


def test_wellplate_emits_well_property_values():
    sample = SimpleNamespace(
        properties={"short_label": "MT-1"}, name="Ethanol",
        molecule={"cano_smiles": "CCO"},
    )
    stub = SimpleNamespace(wells=[{"A": sample, "B": None}], properties={"description": "my plate"},
                           _properties={})
    content = Wellplate.eln_node_content(stub)
    pvs = content["variableMeasured"]
    assert len(pvs) == 1  # only the occupied well
    assert pvs[0]["name"] == "well A1"
    assert pvs[0]["value"] == "MT-1"
    assert content["description"] == "my plate"


def test_research_plan_emits_description_from_richtext():
    rt1 = SimpleNamespace(value=[{"insert": "Hypothesis: "}, {"insert": "X reacts with Y."}])
    rt2 = SimpleNamespace(value=[{"insert": "Observation: clean."}])
    stub = SimpleNamespace(body=[rt1, rt2])
    content = ResearchPlan.eln_node_content(stub)
    assert content["description"] == "Hypothesis: X reacts with Y.\nObservation: clean."


def test_default_eln_node_content_is_empty():
    from chemotion_api.elements.abstract_element import AbstractElement
    assert AbstractElement.eln_node_content(SimpleNamespace()) == {}


@pytest.mark.heavy
def test_untyped_element_node_enriched_in_export(tmp_path):
    """An un-typed element flows through export → Dataset node with placeholder + content."""
    from chemotion_api.offline import import_export_zip
    from chemotion_api.offline.offline_collection import OfflineCollection

    fixtures = os.path.join(os.path.dirname(__file__), "..", "fixtures")
    d = tmp_path / "export"; d.mkdir()
    (d / "export.json").write_text(open(os.path.join(fixtures, "mini_export.json")).read())

    # A minimal un-typed element (no to_dcat_ap) that the exporter routes to the else branch.
    stub = SimpleNamespace(
        _data_loaded=True, id=9001, name="My Plan", element_type="research_plan",
        properties={"short_label": "RP-1", "description": "fallback"}, analyses=[], attachments=[],
        eln_node_content=lambda: {
            "description": "Rich plan body.",
            "variableMeasured": [{"@type": "PropertyValue", "name": "goal", "value": "test"}],
        },
    )

    from chemotion_api import Author, AuthorAffiliation
    col = import_export_zip(d)
    col.get_research_plans = lambda per_page=100: [stub]  # type: ignore[assignment]

    out = str(tmp_path / "rt.eln")
    col.export_eln(out, authors=[Author(
        name="Test Author", orcid="0000-0002-1825-0097",
        affiliations=[AuthorAffiliation(name="KIT", ror="https://ror.org/04t3en479")])])
    with zipfile.ZipFile(out) as z:
        graph = json.loads(z.read(next(n for n in z.namelist()
                                       if n.endswith("ro-crate-metadata.json"))))["@graph"]
    plan_nodes = [n for n in graph if str(n.get("@id", "")).endswith("RP-1_9001/")]
    assert plan_nodes, "research-plan Dataset node missing"
    node = plan_nodes[0]
    assert node["description"] == "Rich plan body."
    names = [pv.get("name") for pv in node.get("variableMeasured", [])]
    assert "goal" in names                       # our structured content
    assert "chemotion element type" in names     # ontology placeholder preserved
