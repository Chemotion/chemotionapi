"""Ontology-term resolution for the FAIR export.

The semantic core is chem-dcat-ap (rich typed mapping for chemical entities). For
free-text technique/method/analysis labels that chem-dcat-ap does not cover, this
package resolves an ontology IRI using, in order:

1. the chem-dcat-ap typed mapping (handled upstream by ``to_dcat_ap``),
2. an ontology code **already embedded** in the Chemotion data (analyses carry
   ``extended_metadata.kind`` like ``"CHMO:0000595 | …"``),
3. the **instance's own** OLS term trees, which an admin can edit and extend
   (:mod:`~chemotion_api.ontology.instance_terms`),
4. an **OLS** lookup (EBI OLS4, cached, offline-safe), then
5. ``None`` (the caller falls back to the existing ontology placeholder).

Steps 2 and 3 are the ELN's own answer and come first by design: a crate should record the
term the instance shows its users, not a public-ontology near-match for the same words.
"""
from __future__ import annotations

from chemotion_api.ontology.instance_terms import (
    InstanceVocabulary,
    index_instance_terms,
    index_terms_by_iri,
)
from chemotion_api.ontology.ols_lookup import (
    OntologyTerm,
    OlsCache,
    obo_code_to_iri,
    parse_embedded_kind,
    query_ols,
    query_ols_label,
    resolve_ontology_term,
    resolve_term_label,
)

__all__ = [
    "InstanceVocabulary",
    "OntologyTerm",
    "OlsCache",
    "index_instance_terms",
    "index_terms_by_iri",
    "obo_code_to_iri",
    "parse_embedded_kind",
    "query_ols",
    "query_ols_label",
    "resolve_ontology_term",
    "resolve_term_label",
]
