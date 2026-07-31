"""chem-dcat-ap SHACL conformance tracking for the to_dcat_ap export graph.

Scope decision (see FIX_PLAN.md, Tier 1.1): SHACL conformance is a *tracked baseline
with documented known gaps*, NOT a hard release gate. The exported graph carries correct
ontology classes/values; the residual violations stem from chem-dcat-ap schema-profile
strictness (AP wrapper classes on attribute nodes, DefinedTerm/Identifier wrapping,
single-datatype prov:value shapes, max-1 rdf:type) in the sibling chem-dcat-ap project,
which this work leaves unchanged.

These tests therefore guard against *regressions* (more violations than the recorded
baseline), not absolute conformance.
"""
import os

import pytest

pyshacl = pytest.importorskip("pyshacl")
from rdflib import Graph  # noqa: E402

pytestmark = pytest.mark.heavy  # pyshacl validation over the 262 KB shapes is memory-heavy

HERE = os.path.dirname(__file__)
BASELINE_TTL = os.path.join(HERE, "data", "dcat_baseline.ttl")
# Vendored copy of the chem-dcat-ap SHACL shapes (kept in-repo so the test is self-contained and the
# package does not depend on any sibling project folder).
SHACL_PATH = os.path.join(HERE, "data", "chem_dcat_ap.shacl.ttl")

# Recorded baseline (2026-07-06, chem_dcat_ap 0.1.0rc3.post9.dev0): a SubstanceSample +
# its ChemicalEntity + a ChemicalReaction produce this many SHACL validation results.
# Re-baselined from 103 after deliberately adding reaction rdf_type (RXNO) + RInChI
# qualitative attributes and the short-label identifier — the added nodes hit the same
# known profile-strictness shapes (language-tagged literals, SIO_000008 attribute classes,
# max-1 rdf:type, closed nodes) already documented for the sample mapping.
BASELINE_VIOLATIONS = 180

# Parse the 262 KB SHACL shapes ONCE and reuse the graph across validate() calls. Passing the file
# path to pyshacl.validate re-parses + reprocesses the shapes on every call, and that memory is
# retained per call — which makes RSS climb ~8 MB per validation and can OOM a run that executes
# several SHACL tests in one process. Reusing a pre-parsed graph keeps peak memory flat.
_SHAPES_GRAPH = None


def _shapes_graph():
    global _SHAPES_GRAPH
    if _SHAPES_GRAPH is None:
        _SHAPES_GRAPH = Graph().parse(SHACL_PATH, format="turtle")
    return _SHAPES_GRAPH


def _count_violations(data_graph):
    from rdflib import Namespace
    SH = Namespace("http://www.w3.org/ns/shacl#")
    conforms, results_graph, _ = pyshacl.validate(
        data_graph, shacl_graph=_shapes_graph(), inference="none", advanced=True
    )
    return conforms, len(list(results_graph.subjects(SH.resultMessage, None)))


@pytest.mark.skipif(not os.path.exists(SHACL_PATH), reason="chem-dcat-ap SHACL shapes not present")
def test_shacl_baseline_fixture_offline():
    """Offline, deterministic: the committed baseline graph still has exactly the
    documented number of violations. Catches schema/SHACL/pyshacl drift."""
    g = Graph()
    g.parse(BASELINE_TTL, format="turtle")
    conforms, n = _count_violations(g)
    assert not conforms  # documented: not fully conformant yet
    assert n == BASELINE_VIOLATIONS, (
        f"Baseline fixture drifted: {n} violations vs recorded {BASELINE_VIOLATIONS}. "
        "Re-triage and update BASELINE_VIOLATIONS if intentional."
    )


@pytest.mark.skipif(not os.path.exists(SHACL_PATH), reason="chem-dcat-ap SHACL shapes not present")
def test_shacl_no_regression_live(instance_with_collection):
    """Live: a freshly exported sample+reaction must not produce MORE violations than
    the recorded baseline (regression guard on the actual to_dcat_ap mapping)."""
    from linkml_runtime.utils.schemaview import SchemaView
    from linkml_runtime.dumpers import RDFLibDumper
    import chem_dcat_ap.datamodel as dm
    from chem_dcat_ap.datamodel import MAIN_SCHEMA_PATH

    col = instance_with_collection["main_collection"]
    sample = col.new_sample_smiles("CCO")
    sample.name = "SHACL ethanol"
    sample.save()
    rxn = col.new_reaction()
    rxn.save()

    import os as _os
    import dcat_ap_plus
    importmap = {"dcatapplus:latest/schema/dcat_ap_plus":
                 _os.path.join(_os.path.dirname(dcat_ap_plus.__file__), "schema", "dcat_ap_plus")}
    schemaview = SchemaView(str(MAIN_SCHEMA_PATH), merge_imports=True, importmap=importmap)
    dumper = RDFLibDumper()
    graph = Graph()
    for elem in (sample, rxn):
        dcat_obj = elem.to_dcat_ap()
        linkml_cls = getattr(dm, dcat_obj.__class__.__name__)
        l_obj = linkml_cls(**dcat_obj.model_dump(exclude_none=True))
        dumper.inject_triples(l_obj, schemaview, graph)

    _, n = _count_violations(graph)
    assert n <= BASELINE_VIOLATIONS, (
        f"SHACL regression: {n} violations > baseline {BASELINE_VIOLATIONS}"
    )
