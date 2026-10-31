"""Ontology resolution + OLS fallback (offline; OLS network mocked)."""
import json
from unittest.mock import patch

import pytest

from chemotion_api.ontology import (
    OlsCache,
    OntologyTerm,
    obo_code_to_iri,
    parse_embedded_kind,
    query_ols,
    resolve_ontology_term,
)


def test_obo_code_to_iri():
    assert obo_code_to_iri("CHMO:0000595") == "http://purl.obolibrary.org/obo/CHMO_0000595"
    assert obo_code_to_iri("chebi:1234") == "http://purl.obolibrary.org/obo/CHEBI_1234"
    assert obo_code_to_iri("not a code") is None


def test_parse_embedded_kind():
    t = parse_embedded_kind("CHMO:0000595 | proton NMR (1H NMR)")
    assert t == OntologyTerm("http://purl.obolibrary.org/obo/CHMO_0000595", "proton NMR (1H NMR)")
    assert parse_embedded_kind("1H NMR") is None
    assert parse_embedded_kind("") is None


def _fake_response(docs):
    class _R:
        def raise_for_status(self):
            pass

        def json(self):
            return {"response": {"docs": docs}}
    return _R()


def test_query_ols_hit_and_caches(tmp_path):
    cache = OlsCache(tmp_path / "ols.json")
    docs = [{"iri": "http://purl.obolibrary.org/obo/CHMO_0000470", "label": "mass spectrometry"}]
    with patch("requests.get", return_value=_fake_response(docs)) as m:
        term = query_ols("mass spec", ontology="chmo", cache=cache)
    assert term and term.iri.endswith("CHMO_0000470")
    # second call served from cache → no new HTTP
    with patch("requests.get") as m2:
        again = query_ols("mass spec", ontology="chmo", cache=cache)
        m2.assert_not_called()
    assert again == term


def test_query_ols_negative_cache(tmp_path):
    cache = OlsCache(tmp_path / "ols.json")
    with patch("requests.get", return_value=_fake_response([])):
        assert query_ols("nonsense", cache=cache) is None
    # recorded as a miss → not re-queried
    with patch("requests.get") as m2:
        assert query_ols("nonsense", cache=cache) is None
        m2.assert_not_called()
    hit, term = cache.get("chmo", "nonsense")
    assert hit and term is None


def test_query_ols_network_error_is_tolerated():
    with patch("requests.get", side_effect=ConnectionError("no net")):
        assert query_ols("anything") is None  # warns + returns None, never raises


def test_cache_round_trips_to_disk(tmp_path):
    p = tmp_path / "ols.json"
    c = OlsCache(p)
    c.put("chmo", "x", OntologyTerm("http://e/IRI_1", "x"))
    c.save()
    assert json.loads(p.read_text())["chmo"]["x"]["iri"] == "http://e/IRI_1"
    c2 = OlsCache(p)  # reload
    hit, term = c2.get("chmo", "x")
    assert hit and term.iri == "http://e/IRI_1"


def test_resolve_prefers_embedded_kind_without_ols():
    with patch("requests.get") as m:
        term = resolve_ontology_term("1H NMR", embedded_kind="CHMO:0000595 | 1H NMR")
        m.assert_not_called()  # embedded code wins; no network
    assert term.iri.endswith("CHMO_0000595")


def test_resolve_falls_back_to_ols_when_no_embedded_code():
    docs = [{"iri": "http://purl.obolibrary.org/obo/CHMO_0000470", "label": "mass spectrometry"}]
    with patch("requests.get", return_value=_fake_response(docs)) as m:
        term = resolve_ontology_term("mass spectrometry", embedded_kind=None)
        m.assert_called_once()
    assert term.iri.endswith("CHMO_0000470")


def test_resolve_disabled_ols_returns_none():
    with patch("requests.get") as m:
        assert resolve_ontology_term("mass spec", enable_ols=False) is None
        m.assert_not_called()
