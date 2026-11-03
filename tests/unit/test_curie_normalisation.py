"""Compact IRIs in a crate are spelled the way the accession's own registry spells them.

rdflib's JSON-LD serializer builds a CURIE by splitting an IRI at its last ``/`` or ``#``, so an
OBO-style accession can only ever match the host-level ``obo:`` prefix and comes out as
``obo:CHMO_0000595`` — the ontology name repeated, which is not what CHMO publishes and not what
a consumer keying on Bioregistry prefixes will match. ``_normalise_curies`` rewrites those onto
the per-ontology prefixes chem-dcat-ap declares.

The rewrite is *spelling only*, so the central guarantee tested here is that it changes no
triples: every CURIE must expand to exactly the IRI it expanded to before.
"""
import json
import os
import re
import zipfile
from types import SimpleNamespace

import pytest

from chemotion_api.collection import (
    _COARSE_PREFIXES,
    _context_namespaces,
    _crate_namespaces,
    _expand_iri,
    _normalise_curies,
    _recurie,
)

#: A CURIE whose local part repeats the ontology name: `obo:CHMO_0000595`, `sio:SIO_010345`.
STUTTER_RE = re.compile(rf"^({'|'.join(_COARSE_PREFIXES)}):[A-Za-z]+_")

NAMESPACES = {
    "obo": "http://purl.obolibrary.org/obo/",
    "sio": "http://semanticscience.org/resource/",
    "qudt": "http://qudt.org/schema/qudt/",
    "CHMO": "http://purl.obolibrary.org/obo/CHMO_",
    "CHEBI": "http://purl.obolibrary.org/obo/CHEBI_",
    "RO": "http://purl.obolibrary.org/obo/RO_",
    "SIO": "http://semanticscience.org/resource/SIO_",
    "CHEMINF": "http://semanticscience.org/resource/CHEMINF_",
    "AFR": "http://purl.allotrope.org/ontologies/result#AFR_",
    "doi": "https://doi.org/",
}
CANDIDATES = sorted(((p, i) for p, i in NAMESPACES.items() if p not in _COARSE_PREFIXES),
                    key=lambda kv: len(kv[1]), reverse=True)


def recurie(term):
    return _recurie(term, NAMESPACES, CANDIDATES)


@pytest.mark.parametrize("term, expected", [
    # the host-level prefix gives way to the ontology's own
    ("obo:CHMO_0000595", "CHMO:0000595"),
    ("obo:CHEBI_59999", "CHEBI:59999"),
    ("obo:RO_0004008", "RO:0004008"),
    ("sio:SIO_010345", "SIO:010345"),
    # CHEMINF lives on semanticscience.org but is not SIO, and must not be labelled as it
    ("sio:CHEMINF_000113", "CHEMINF:000113"),
    # an absolute IRI rdflib could not compact at all (the namespace ends in `#AFR_`)
    ("http://purl.allotrope.org/ontologies/result#AFR_0002409", "AFR:0002409"),
    ("http://purl.obolibrary.org/obo/CHMO_0000595", "CHMO:0000595"),
])
def test_recurie_rewrites_onto_the_registered_prefix(term, expected):
    assert recurie(term) == expected


@pytest.mark.parametrize("term", [
    "./",                                       # the crate root
    "./reactions/Oxidation_8011/",              # a relative data-entity path
    "#collection-1",                            # a local contextual entity
    "name",                                     # a bare schema.org term
    "qudt:unit",                                # already abbreviated, nothing more specific
    "https://orcid.org/0000-0002-1825-0097",    # no declared prefix covers it
    "https://doi.org/10.5281/zenodo.1",         # `doi:` matches, but the local part has a `/`
    "https://qudt.org/vocab/unit/MOL-PER-L",    # likewise: cutting here would be wrong
])
def test_recurie_leaves_everything_else_alone(term):
    assert recurie(term) == term


def test_recurie_is_idempotent():
    once = recurie("obo:CHMO_0000595")
    assert recurie(once) == once


def _triples(doc, namespaces):
    """The doc's triples, as a comparable set. Parsed offline, through the real ``@context``
    rendering — a prefix declared the wrong way does not expand, and that must show up here."""
    from rdflib import Graph
    payload = dict(doc)
    payload["@context"] = _context_namespaces(namespaces)
    g = Graph()
    g.parse(data=json.dumps(payload), format="json-ld")
    return set(g)


def _declared_prefixes(metadata):
    """The crate's prefix map, flattened from ``@context`` and the vendored RO-Crate context.

    The RO-Crate context is referenced by URL, so its prefixes (``dct:`` among them) are not in
    the inline object; read them from the vendored copy rather than going to the network.
    """
    import chemotion_api
    vendored = os.path.join(os.path.dirname(chemotion_api.__file__),
                            "data", "ro-crate-context.jsonld")
    declared = dict(json.load(open(vendored))["@context"])
    for entry in metadata["@context"]:
        if isinstance(entry, dict):
            declared.update(entry)
    # `{"@id": …, "@prefix": true}` declares the same namespace as a bare string would.
    return {prefix: (iri["@id"] if isinstance(iri, dict) and "@id" in iri else iri)
            for prefix, iri in declared.items()}


def test_normalise_curies_preserves_every_triple():
    """The point of the whole pass: spelling changes, the graph does not."""
    doc = {"@graph": [{
        "@id": "#sample-1",
        "@type": ["Thing", "obo:CHEBI_59999", "sio:CHEMINF_000113"],
        "name": "Ethanol",
        "obo:RO_0004008": {"@id": "sio:SIO_010345"},
        "http://purl.allotrope.org/ontologies/result#AFR_0002409": {"@id": "obo:CHMO_0000595"},
        "qudt:unit": {"@id": "https://qudt.org/vocab/unit/MOL-PER-L"},
    }]}
    before = _triples(doc, NAMESPACES)
    _normalise_curies(doc, NAMESPACES)
    assert _triples(doc, NAMESPACES) == before


def test_normalise_curies_rewrites_keys_types_and_ids():
    doc = {"@graph": [{
        "@id": "#sample-1",
        "@type": ["Thing", "obo:CHEBI_59999"],
        "obo:RO_0004008": {"@id": "sio:CHEMINF_000113"},
        "name": "obo:CHEBI_59999",  # a *value*, not an IRI — must survive untouched
    }]}
    _normalise_curies(doc, NAMESPACES)
    node = doc["@graph"][0]
    assert node["@type"] == ["Thing", "CHEBI:59999"]
    assert node["RO:0004008"] == {"@id": "CHEMINF:000113"}
    assert node["name"] == "obo:CHEBI_59999"


def _export_fixture_crate(tmp_path):
    """Drive the real exporter over the offline fixture and return the crate's metadata."""
    from chemotion_api import Author, AuthorAffiliation
    from chemotion_api.offline import import_export_zip

    fixtures = os.path.join(os.path.dirname(__file__), "..", "fixtures")
    d = tmp_path / "export"
    d.mkdir()
    (d / "export.json").write_text(open(os.path.join(fixtures, "mini_export.json")).read())

    col = import_export_zip(d)
    out = str(tmp_path / "curies.eln")
    col.export_eln(out, authors=[Author(
        name="Test Author", orcid="0000-0002-1825-0097",
        affiliations=[AuthorAffiliation(name="KIT", ror="https://ror.org/04t3en479")])])
    with zipfile.ZipFile(out) as z:
        name = next(n for n in z.namelist() if n.endswith("ro-crate-metadata.json"))
        return json.loads(z.read(name))


def _crate_terms(metadata):
    """Every string in the crate that is meant to be an IRI: keys, ``@id`` and ``@type``."""
    terms = set()
    for node in metadata.get("@graph", []):
        if not isinstance(node, dict):
            continue
        terms.update(k for k in node if not k.startswith("@"))
        for field in ("@id", "@type"):
            value = node.get(field)
            terms.update(v for v in (value if isinstance(value, list) else [value])
                         if isinstance(v, str))
    return terms


@pytest.mark.heavy
def test_exported_crate_has_no_stuttering_curies(tmp_path):
    offenders = sorted(t for t in _crate_terms(_export_fixture_crate(tmp_path))
                       if STUTTER_RE.match(t))
    assert not offenders, f"compact IRIs still repeat their ontology name: {offenders}"


@pytest.mark.heavy
def test_every_curie_in_the_crate_resolves_through_the_declared_context(tmp_path):
    """A rewritten prefix that the ``@context`` does not declare is a REQUIRED violation."""
    metadata = _export_fixture_crate(tmp_path)
    declared = _declared_prefixes(metadata)

    unresolved = []
    for term in _crate_terms(metadata):
        prefix, sep, _ = term.partition(":")
        if not sep or term.startswith(("http://", "https://", "./", "#", "_:")):
            continue
        if prefix not in declared:
            unresolved.append(term)
        elif not _expand_iri(term, declared).startswith(("http://", "https://")):
            unresolved.append(term)
    assert not unresolved, f"compact IRIs with no declared prefix: {sorted(unresolved)}"


@pytest.mark.heavy
def test_chemistry_accessions_keep_their_absolute_iris(tmp_path):
    """The rewrite must not change what a term *means*, only how it is written."""
    metadata = _export_fixture_crate(tmp_path)
    expanded = {_expand_iri(t, _declared_prefixes(metadata)) for t in _crate_terms(metadata)}

    for iri in (
        "http://purl.obolibrary.org/obo/",          # OBO accessions still point at OBO
        "http://semanticscience.org/resource/",     # CHEMINF/SIO still point at semanticscience
    ):
        assert any(e.startswith(iri) for e in expanded), f"nothing resolves under {iri}"
    # and nothing expanded to a malformed IRI with the prefix glued on twice
    assert not [e for e in expanded if "obo/CHMO_CHMO" in e or "resource/SIO_SIO" in e]


def test_underscore_namespaces_are_declared_as_explicit_prefixes():
    """The trap this pass has to step over.

    JSON-LD only treats a term as a CURIE prefix when its IRI ends in a gen-delim. OBO
    namespaces end in ``_``, so a plain string declaration leaves ``CHEBI:59999`` unexpanded —
    read as an absolute IRI with scheme ``CHEBI``. Declared properly it round-trips.
    """
    rendered = _context_namespaces({
        "CHEBI": "http://purl.obolibrary.org/obo/CHEBI_",
        "AFR": "http://purl.allotrope.org/ontologies/result#AFR_",
        "qudt": "http://qudt.org/schema/qudt/",      # already a gen-delim
        "adms": "http://www.w3.org/ns/adms#",        # likewise
    })
    assert rendered["CHEBI"] == {"@id": "http://purl.obolibrary.org/obo/CHEBI_", "@prefix": True}
    assert rendered["AFR"]["@prefix"] is True
    assert rendered["qudt"] == "http://qudt.org/schema/qudt/"   # plain string, stays readable
    assert rendered["adms"] == "http://www.w3.org/ns/adms#"


def test_plain_string_declaration_would_break_expansion():
    """Guards the reason for ``_context_namespaces``: shows the broken form actually breaks."""
    from rdflib import Graph
    doc = {"@graph": [{"@id": "http://example.org/s", "@type": ["CHEBI:59999"]}]}
    namespaces = {"CHEBI": "http://purl.obolibrary.org/obo/CHEBI_"}

    def types(context):
        g = Graph()
        g.parse(data=json.dumps({**doc, "@context": context}), format="json-ld")
        return {str(o) for _, _, o in g}

    assert types(dict(namespaces)) == {"CHEBI:59999"}                       # the trap
    assert types(_context_namespaces(namespaces)) == {
        "http://purl.obolibrary.org/obo/CHEBI_59999"}                       # what we emit


def test_crate_namespaces_prefers_chem_dcat_ap_over_the_fallback():
    """Without a SchemaView there is nothing authoritative to read, so the coarse map stands."""
    fallback = _crate_namespaces(None)
    assert fallback["obo"] == "http://purl.obolibrary.org/obo/"
    assert "CHMO" not in fallback

    schemaview = SimpleNamespace(namespaces=lambda: {
        "CHMO": "http://purl.obolibrary.org/obo/CHMO_",
        "schema": "http://schema.org/",        # shadows RO-Crate's own definitions
        "dcterms": "http://purl.org/dc/terms/",  # RO-Crate declares this as `dct:`
        "bogus": "not-an-iri",
    })
    derived = _crate_namespaces(schemaview)
    assert derived["CHMO"] == "http://purl.obolibrary.org/obo/CHMO_"
    assert derived["obo"] == "http://purl.obolibrary.org/obo/"  # fallback kept underneath
    for dropped in ("schema", "dcterms", "bogus"):
        assert dropped not in derived


def test_crate_namespaces_survives_an_unreadable_schemaview():
    """A prefix miss must never fail an export."""
    def boom():
        raise RuntimeError("schema unavailable")

    derived = _crate_namespaces(SimpleNamespace(namespaces=boom))
    assert derived == _crate_namespaces(None)
