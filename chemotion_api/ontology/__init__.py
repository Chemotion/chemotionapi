"""Ontology-term resolution for the FAIR export.

The semantic core is chem-dcat-ap (rich typed mapping for chemical entities). For
free-text technique/method/analysis labels that chem-dcat-ap does not cover, this
package resolves an ontology IRI using, in order:

1. the chem-dcat-ap typed mapping (handled upstream by ``to_dcat_ap``),
2. an ontology code **already embedded** in the Chemotion data (analyses carry
   ``extended_metadata.kind`` like ``"CHMO:0000595 | …"``),
3. an **OLS** lookup (EBI OLS4, cached, offline-safe), then
4. ``None`` (the caller falls back to the existing ontology placeholder).
"""
from __future__ import annotations

from chemotion_api.ontology.ols_lookup import (
    OntologyTerm,
    OlsCache,
    obo_code_to_iri,
    parse_embedded_kind,
    query_ols,
    resolve_ontology_term,
)

__all__ = [
    "OntologyTerm",
    "OlsCache",
    "obo_code_to_iri",
    "parse_embedded_kind",
    "query_ols",
    "resolve_ontology_term",
]
