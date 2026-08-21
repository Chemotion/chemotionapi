FAIR Export (RO-Crate ``.eln``)
===============================

A collection can be exported as a standards-compliant **RO-Crate 1.1** ``.eln`` archive whose metadata
is mapped to the **NFDI chem-dcat-ap** RDF model. The entry point is
:meth:`chemotion_api.collection.Collection.export_eln` (documented under :doc:`Collection`).

Conformance is verified, not claimed: every change is checked in CI against
`TheELNConsortium's <https://github.com/TheELNConsortium/TheELNFileFormat>`_ own validation suite —
``py-rocrate`` must parse the archive and ``rocrate-validator`` must report no REQUIRED issues for
the ``ro-crate-1.1`` profile. Run it locally with ``just conformance``.

Reading a crate this exporter writes
------------------------------------

Four consequences of that conformance are worth knowing before you parse a crate:

* **The graph is flattened.** RO-Crate requires every entity to be a top-level member of
  ``@graph``, with properties referencing them as ``{"@id": …}``. So ``variableMeasured`` and
  similar hold *references*, not inline objects — resolve them against ``@graph`` by ``@id``.
* **Opaque Chemotion payloads are JSON strings.** ``variations`` is arbitrary nested JSON keyed on
  plain ``id`` (not ``@id``); embedded as an object it makes the archive unparseable, so it is
  carried as a string. ``json.loads`` it. Flat lists of literals (``purification``, for instance)
  are unaffected — those are ordinary multi-valued properties.
* **Empty fields are omitted.** Chemotion stores unset optional fields as empty strings; a key with
  no value says nothing an absent key does not, so it is dropped. One summary line is logged per
  export saying how many, and which.
* **A licence is always present.** RO-Crate makes ``license`` mandatory on the root, so a
  collection without one is exported under CC-BY-4.0. Set your own if that is wrong for the data.

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
