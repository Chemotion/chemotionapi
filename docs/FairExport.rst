FAIR Export (RO-Crate ``.eln``)
===============================

A collection can be exported as a standards-compliant **RO-Crate 1.1** ``.eln`` archive whose metadata
is mapped to the **NFDI chem-dcat-ap** RDF model. The entry point is
:meth:`chemotion_api.collection.Collection.export_eln` (documented under :doc:`Collection`).

Authors are mandatory
---------------------

Authorship is **not** taken from the logged-in user. Every ``.eln`` must declare its authors
explicitly, each with an ORCID iD and at least one ROR-identified affiliation. Set them via
:meth:`chemotion_api.collection.Collection.set_authors` or pass ``authors=[...]`` to ``export_eln``;
if neither is provided, ``export_eln`` raises a ``ValueError`` explaining how to set them.

.. code-block:: python

    from chemotion_api import Author, AuthorAffiliation

    collection.set_authors([
        Author(
            name="Ada Lovelace",
            orcid="0000-0002-1825-0097",  # bare id or full https://orcid.org/... URL
            affiliations=[AuthorAffiliation(name="Example University",
                                            ror="https://ror.org/05dxps055")],
        ),
    ])
    collection.export_eln("project.eln")

.. autoclass:: chemotion_api.authors.Author
    :members:

.. autoclass:: chemotion_api.authors.AuthorAffiliation
    :members:

Identifiers are crate-relative by design
----------------------------------------

Every IRI that names one of *our* records — samples, reactions, molecules, datasets, files —
is **crate-internal** (a crate-relative path or ``#fragment``), resolved against the crate root
as RO-Crate prescribes. The export deliberately mints **no external PIDs**: a repository PID or
DOI only comes into existence when the dataset is actually *published*, and inventing
plausible-looking URLs before that point would produce dead identifiers. When a PID is minted at
publication, it can be injected into the already-written ``.eln`` post-hoc (the same in-place
patching approach as :func:`chemotion_api.ontology_patch.patch_eln_ontology`) by the system that
assigned it — no re-export needed.

External IRIs still appear where they reference *shared, established* things rather than our
records: ontology terms (CHEBI, CHMO, QUDT, RXNO, …), ORCID iDs and ROR ids for authors, and
plain-string notations such as CAS registry numbers. Samples additionally carry their Chemotion
short label as a local identifier notation.

Ontology annotation and later patching
---------------------------------------

Samples and reactions are richly typed through chem-dcat-ap. Element kinds that do not yet have an
agreed ontology term (Wellplate, ResearchPlan, GenericElement) are exported as spec-conformant
``Dataset`` nodes carrying a forward-compatible *placeholder*. When a term is decided later, fill it in
:mod:`chemotion_api.ontology_map` (a one-line edit for new exports) or patch an already-written
``.eln`` in place with :func:`chemotion_api.ontology_patch.patch_eln_ontology` — no re-export needed.

.. autofunction:: chemotion_api.ontology_map.iri_for

.. autofunction:: chemotion_api.ontology_map.ontology_placeholder

.. autofunction:: chemotion_api.ontology_patch.patch_eln_ontology
