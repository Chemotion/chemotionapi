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
