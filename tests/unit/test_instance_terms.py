"""The instance's own OLS terms outrank EBI (offline; both sources mocked)."""
from unittest.mock import patch

from chemotion_api.eln_producer import OFFLINE_HOST
from chemotion_api.ontology import (
    InstanceVocabulary,
    index_instance_terms,
    index_terms_by_iri,
    resolve_ontology_term,
)

# Copied from what a live instance actually serves for public/ontologies/chmo.json, not from the
# entity source: `term_id` and `synonyms` serialise as null throughout (the tree is built from
# string-keyed hashes while the entity exposes those two as attributes), the id lives only in
# `value`, which may carry a leading space, and the first root is a group header naming no term.
PAYLOAD = {
    "ols_terms": [
        {"title": "-- Recently selected --", "value": "-- Recently selected --",
         "selectable": False, "children": []},
        {
            "term_id": None,
            "value": "CHMO:0000228 | spectroscopy",
            "title": "spectroscopy",
            "synonym": None,
            "synonyms": None,
            "children": [
                {
                    "term_id": None,
                    "value": " CHMO:0000595 | house 1H NMR (1H NMR)",
                    "title": "house 1H NMR (1H NMR)",
                    "synonym": "1H NMR",
                    "synonyms": ["proton NMR"],
                    "children": [],
                },
                "not a term object",
            ],
        },
        {"term_id": None, "value": "no-such-code | junk", "children": []},
    ]
}


def _response(payload):
    class _R:
        def raise_for_status(self):
            pass

        def json(self):
            return payload
    return _R()


class _Session:
    """Minimal stand-in for Connection: records calls, serves one payload."""

    host_url = "https://eln.example.org"

    def __init__(self, payload=PAYLOAD):
        self._payload = payload
        self.calls = []

    def get(self, path, **kwargs):
        self.calls.append((path, kwargs.get("params")))
        return _response(self._payload)


def test_index_reads_the_code_from_value_not_term_id():
    """Regression: every node carries `term_id: null`, so indexing on it found nothing at all.

    Unit tests built from the entity source passed while the live instance yielded 0 terms.
    """
    index = index_instance_terms(PAYLOAD)
    assert index, "term_id is null on every node; the code must come from `value`"
    assert all(t.iri.startswith("http://purl.obolibrary.org/obo/") for t in index.values())


def test_index_skips_the_group_header_naming_no_term():
    assert "-- recently selected --" not in index_instance_terms(PAYLOAD)


def test_index_tolerates_an_ontology_the_instance_does_not_publish():
    # Measured: `bao` comes back as {"ols_terms": null} on an instance with no bao file.
    assert index_instance_terms({"ols_terms": None}) == {}
    assert index_instance_terms(None) == {}


def test_index_flattens_tree_and_skips_unusable_nodes():
    index = index_instance_terms(PAYLOAD)
    assert index["spectroscopy"].iri.endswith("CHMO_0000228")
    # The bare label, the displayed "label (synonym)" title, the synonym and each entry of
    # `synonyms` all resolve to the same term.
    for key in ("house 1h nmr", "house 1h nmr (1h nmr)", "1h nmr", "proton nmr"):
        assert index[key].iri.endswith("CHMO_0000595"), key
    # The DefinedTerm name is the instance's label without the displayed "(synonym)" suffix.
    assert index["1h nmr"].label == "house 1H NMR"
    # A term_id that is not PREFIX:NUMBER has no IRI to give, so it is dropped rather than
    # indexed with a broken @id.
    assert "junk" not in index


def test_lookup_is_case_and_whitespace_insensitive():
    vocab = InstanceVocabulary(_Session())
    assert vocab.lookup("  SPECTROSCOPY  ").iri.endswith("CHMO_0000228")
    assert vocab.lookup("Proton   NMR").iri.endswith("CHMO_0000595")
    assert vocab.lookup("nothing like this") is None
    assert vocab.lookup(None) is None


def test_each_ontology_is_fetched_once():
    session = _Session()
    vocab = InstanceVocabulary(session)
    vocab.lookup("spectroscopy")
    vocab.lookup("1H NMR")
    vocab.lookup("missing")
    assert session.calls == [("/api/v1/ols_terms/list", {"name": "chmo", "edited": "false"})]


def test_unsupported_ontology_is_never_requested():
    session = _Session()
    assert InstanceVocabulary(session).lookup("spectroscopy", ontology="chebi") is None
    assert session.calls == []


def test_fetch_failure_is_tolerated_and_not_retried():
    class _Broken(_Session):
        def get(self, path, **kwargs):
            self.calls.append((path, kwargs.get("params")))
            raise ConnectionError("instance down")

    session = _Broken()
    vocab = InstanceVocabulary(session)
    assert vocab.lookup("spectroscopy") is None  # warns, never raises
    assert vocab.lookup("1H NMR") is None
    assert len(session.calls) == 1  # the miss is remembered


def test_from_session_returns_none_without_an_instance():
    assert InstanceVocabulary.from_session(None) is None
    assert InstanceVocabulary.from_session(object()) is None  # no .get
    offline = _Session()
    offline.host_url = OFFLINE_HOST
    assert InstanceVocabulary.from_session(offline) is None
    assert InstanceVocabulary.from_session(_Session()) is not None


def test_resolve_prefers_the_instance_over_ebi():
    vocab = InstanceVocabulary(_Session())
    with patch("requests.get") as ebi:
        term = resolve_ontology_term("1H NMR", vocabulary=vocab)
        ebi.assert_not_called()
    assert term.iri.endswith("CHMO_0000595")
    assert term.label == "house 1H NMR"  # the instance's label, not EBI's


def test_resolve_falls_through_to_ebi_when_the_instance_lacks_the_term():
    class _R:
        def raise_for_status(self):
            pass

        def json(self):
            return {"response": {"docs": [
                {"iri": "http://purl.obolibrary.org/obo/CHMO_0000470",
                 "label": "mass spectrometry"},
            ]}}

    vocab = InstanceVocabulary(_Session())
    with patch("requests.get", return_value=_R()) as ebi:
        term = resolve_ontology_term("mass spectrometry", vocabulary=vocab)
        ebi.assert_called_once()
    assert term.iri.endswith("CHMO_0000470")


def test_embedded_code_still_wins_over_the_instance_vocabulary():
    vocab = InstanceVocabulary(_Session())
    term = resolve_ontology_term("1H NMR", embedded_kind="CHMO:0000228 | spectroscopy",
                                 vocabulary=vocab)
    assert term.iri.endswith("CHMO_0000228")


def test_reverse_index_names_a_term_from_its_iri():
    index = index_terms_by_iri(PAYLOAD)
    assert index["http://purl.obolibrary.org/obo/CHMO_0000595"].label == "house 1H NMR"
    assert index_terms_by_iri({"ols_terms": None}) == {}


def test_label_for_iri_searches_every_published_tree():
    """The trees are not confined to their own ontology, so the IRI prefix is no guide."""
    session = _Session()
    vocab = InstanceVocabulary(session)
    assert vocab.label_for_iri("http://purl.obolibrary.org/obo/CHMO_0000228") == "spectroscopy"
    assert vocab.label_for_iri("http://purl.obolibrary.org/obo/NOPE_9999999") is None
    assert vocab.label_for_iri(None) is None
    # chmo answered first, so rxno/bao were still fetched for the miss — but only once each.
    assert len(session.calls) <= len(("chmo", "rxno", "bao"))


def test_unsupported_ontology_is_reported_not_silently_empty(caplog):
    """A silent empty index is indistinguishable from 'the instance has no such term'."""
    import logging
    session = _Session()
    with caplog.at_level(logging.INFO, logger="chemotion_api.ontology.instance_terms"):
        assert InstanceVocabulary(session).lookup("spectroscopy", ontology="mop") is None
    assert session.calls == []
    assert any("mop" in r.getMessage() for r in caplog.records), \
        "an unknown ontology must say so"


def test_resolve_term_label_prefers_the_instance_over_ebi():
    from chemotion_api.ontology import resolve_term_label
    vocab = InstanceVocabulary(_Session())
    with patch("requests.get") as ebi:
        label = resolve_term_label("http://purl.obolibrary.org/obo/CHMO_0000228",
                                   vocabulary=vocab)
        ebi.assert_not_called()
    assert label == "spectroscopy"


def test_resolve_term_label_makes_no_request_when_lookups_are_off():
    from chemotion_api.ontology import resolve_term_label
    with patch("requests.get") as ebi:
        assert resolve_term_label("http://purl.obolibrary.org/obo/BFO_0000051",
                                  enable_ols=False) is None
        ebi.assert_not_called()
