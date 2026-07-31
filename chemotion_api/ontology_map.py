"""Central registry mapping Chemotion element kinds to ontology class IRIs for `.eln` export.

Single source of truth for both the exporter (``collection.export_eln``) and the post-export
patch helper (``chemotion_api.ontology_patch``).

`sample` and `reaction` are annotated richly via ``Element.to_dcat_ap`` (chem-dcat-ap) and are
NOT listed here. The kinds below do not yet have an agreed ontology term. They are exported as
spec-conformant RO-Crate ``Dataset`` nodes carrying a forward-compatible ontology *placeholder*
(a ``PropertyValue`` in ``variableMeasured``); when a term is decided, fill its IRI in here — a
one-line edit — and re-export, or patch existing ``.eln`` files with ``ontology_patch``.
"""

#: ``propertyID`` used to tag the ontology placeholder PropertyValue so it can be located later.
ELEMENT_TYPE_PROPERTY_ID = "chemotion:elementType"

#: element_type -> ontology class IRI (or None = "to be defined later").
ELEMENT_TYPE_IRI: dict[str, str | None] = {
    "wellplate": None,
    "research_plan": None,
    # Generic LabIMotion element types share a single placeholder until typed individually.
    "generic": None,
}


def iri_for(element_kind: str) -> str | None:
    """Return the ontology IRI for an element kind, or None if not yet defined."""
    if element_kind in ELEMENT_TYPE_IRI:
        return ELEMENT_TYPE_IRI[element_kind]
    # Unknown/custom generic types fall back to the generic placeholder.
    return ELEMENT_TYPE_IRI.get("generic")


def ontology_placeholder(element_kind: str) -> dict:
    """Build a spec-conformant ontology placeholder PropertyValue for an element kind.

    Per TheELNFileFormat spec, ``variableMeasured`` entries are ``PropertyValue`` nodes whose
    ``identifier`` MAY be an ontology IRI. We emit the IRI now if known, else an empty string
    that ``ontology_patch`` can fill in once the term is defined.
    """
    iri = iri_for(element_kind)
    return {
        "@type": "PropertyValue",
        "propertyID": ELEMENT_TYPE_PROPERTY_ID,
        "name": "chemotion element type",
        "value": element_kind,
        "identifier": iri or "",
    }
