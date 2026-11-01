"""Every ontology-bearing field in the ELN reaches the crate (offline; no network).

The ELN stores ontology terms in four places. Three of them belong on an element's crate
node, and two were being dropped:

* an analysis ``extended_metadata.kind`` — always mapped;
* a reaction's ``rxno`` — picked from the same tree widget, in the same
  ``"PREFIX:id | label"`` form, but carried only as a plain string;
* a generic dataset's LabIMotion klass, whose ``ols_term_id`` is ``NOT NULL`` by schema, so
  the dataset's *type* is an ontology term — and it never reached the crate at all.

(The fourth, ``device_descriptions.ontologies``, belongs to an element type this client does
not export; see AI/ONTOLOGY_AUDIT.md.)

These run against ``Collection.export_eln`` with the graph machinery stubbed, so they assert
the annotation logic rather than re-serialising a crate.
"""
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.heavy


def _nodes_for(elem, **export_kwargs):
    """Export a one-element collection and return its @graph."""
    import json
    import zipfile
    import tempfile
    import os
    import linkml_runtime.utils.schemaview as sv_mod
    import linkml_runtime.dumpers as dmp_mod
    from chemotion_api import Author, AuthorAffiliation
    from chemotion_api.collection import Collection

    authors = [Author(name="T", orcid="0000-0002-1825-0097",
                      affiliations=[AuthorAffiliation(name="O", ror="https://ror.org/04t3en479")])]

    root_col = MagicMock()
    root_col._element_manager.all_classes = {"reaction": {"label": "Reaction"}}
    root_col._session = None

    col = MagicMock()
    col.id = 7
    col.label = "Onto"
    col.get_root.return_value = root_col
    col._parent = None
    col.collection_json = None
    col.children = []
    col._session = None
    col.get_samples.return_value = []
    col.get_reactions.return_value = [elem]
    col.get_wellplates.return_value = []
    col.get_research_plans.return_value = []
    col.get_generics_by_name.return_value = []

    with patch.object(sv_mod, "SchemaView", lambda *a, **k: MagicMock()):
        class _NoopDumper:
            def inject_triples(self, *a, **k):
                return None
        with patch.object(dmp_mod, "RDFLibDumper", _NoopDumper):
            with tempfile.TemporaryDirectory() as d:
                out = os.path.join(d, "o.eln")
                try:
                    Collection.export_eln(col, out, authors=authors, **export_kwargs)
                except Exception as e:  # the RO-Crate @context may need the network
                    if any(s in str(e) or s in type(e).__name__
                           for s in ("URLError", "urlopen", "Network is unreachable")):
                        pytest.skip("export_eln needs the RO-Crate @context; unreachable here")
                    raise
                with zipfile.ZipFile(out) as z:
                    name = next(n for n in z.namelist()
                                if n.endswith("ro-crate-metadata.json"))
                    return json.loads(z.read(name))["@graph"]


def _reaction(rxno=None, analyses=None):
    r = MagicMock()
    r.id = 11
    r.name = "RX"
    r.element_type = "reaction"
    r._data_loaded = True
    r.attachments = []
    r.properties = {"rxno": rxno} if rxno is not None else {}
    r.to_dcat_ap.side_effect = Exception("no dcat")  # exercise the generic Dataset path
    r.eln_node_content.return_value = {}
    if analyses is None:
        del r.analyses
    else:
        r.analyses = analyses
    return r


class _FakeDataset(dict):
    """Mirrors chemotion_api.elements.abstract_element.Dataset: a dict that also has files."""

    attachments: list = []


def _defined_terms(graph):
    return {n["@id"]: n.get("name") for n in graph if n.get("@type") == "DefinedTerm"}


def test_reaction_rxno_becomes_a_typed_term_not_a_bare_string():
    """Regression: the one ontology term a chemist picks for a reaction was left unresolved."""
    with patch("requests.get") as net:
        graph = _nodes_for(_reaction(rxno="RXNO:0000087 | aldol condensation"))
        net.assert_not_called()  # the code is embedded; nothing to look up
    iri = "http://purl.obolibrary.org/obo/RXNO_0000087"
    assert _defined_terms(graph).get(iri) == "aldol condensation"
    typed = [n for n in graph
             if iri in (n["@type"] if isinstance(n.get("@type"), list) else [n.get("@type")])]
    assert typed, "the RXNO term should also type the reaction node"


def test_rxno_without_a_code_is_left_alone():
    """Free text that names no term must not invent one, and must not crash the export."""
    with patch("requests.get") as net:
        graph = _nodes_for(_reaction(rxno="something typed by hand"),
                           ontology_lookup=False)
        net.assert_not_called()
    assert not any("RXNO" in i for i in _defined_terms(graph))


def test_generic_dataset_klass_term_reaches_the_crate():
    """``klass_ols``/``klass_label`` ship in the payload, so this needs no lookup at all."""
    ana = MagicMock()
    ana.get.return_value = None          # no kind/name on the analysis itself
    ana.datasets = [_FakeDataset({"dataset": {"klass_ols": "CHMO:0000595",
                                              "klass_label": "13C NMR (house)"}})]
    with patch("requests.get") as net:
        graph = _nodes_for(_reaction(analyses=[ana]), ontology_lookup=False)
        net.assert_not_called()  # the payload already carries code *and* label
    iri = "http://purl.obolibrary.org/obo/CHMO_0000595"
    assert _defined_terms(graph).get(iri) == "13C NMR (house)"
    assert any({"@id": iri} in (n.get("measurementTechnique") or []) for n in graph)


def test_a_dataset_without_a_klass_term_is_skipped_quietly():
    ana = MagicMock()
    ana.get.return_value = None
    # A dataset with no klass, and one with no `dataset` block at all — both real shapes for a
    # non-generic analysis. (The annotation itself also tolerates non-dict entries, but the
    # surrounding attachment walk does not, so this stays to what the API actually returns.)
    ana.datasets = [_FakeDataset({"dataset": {"klass_ols": None, "klass_label": None}}),
                    _FakeDataset()]
    graph = _nodes_for(_reaction(analyses=[ana]), ontology_lookup=False)
    assert graph  # exported fine, simply unannotated
