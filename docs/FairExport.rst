FAIR Export (RO-Crate ``.eln``)
===============================

A collection can be exported as a standards-compliant **RO-Crate 1.2** ``.eln`` archive whose metadata
is mapped to the **NFDI chem-dcat-ap** RDF model. The entry point is
:meth:`chemotion_api.collection.Collection.export_eln` (documented under :doc:`Collection`).

Conformance is verified, not claimed: every change is checked in CI against
`TheELNConsortium's <https://github.com/TheELNConsortium/TheELNFileFormat>`_ own validation suite —
``py-rocrate`` must parse the archive and ``rocrate-validator`` must report no REQUIRED issues for
the ``ro-crate-1.2`` profile. Run it locally with ``just conformance``.

The gate runs **two** validator versions. ``0.11.3`` is what TheELNFileFormat's own CI pins, and on
one axis it is the stricter of the two: it rejects a compact IRI whose *prefix* alone is declared,
where ``0.13.0`` accepts it. Checking only the newer one let a crate pass here that their CI
rejects, so both run.

What the crate declares
-----------------------

Every crate states the two profiles it conforms to, on the **root Dataset**::

    "conformsTo": [
      {"@id": "https://w3id.org/ro/crate/1.2"},
      {"@id": "https://purl.archive.org/purl/elnconsortium/eln-spec/1.2+20260923"}
    ]

Both also appear in the graph as ``Profile`` entities. The ELN version is read from the **root**,
not from the metadata descriptor — a crate that declares it only on the descriptor is treated by
TheELNFileFormat's checker as plain RO-Crate with no ELN version at all.

.. note::
   The ``.eln`` profile IRI uses ``purl.archive.org``, not ``purl.org``. TheELNFileFormat's
   ``SPECIFICATION.md`` currently shows ``purl.org`` while its checker matches only
   ``purl.archive.org``; a crate following the specification document verbatim is read as
   declaring no ELN version. Reported upstream.

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
* **A partial crate says so.** If anything was left out, the crate carries an ``#export-manifest``
  ``CreativeWork`` — referenced from the root's ``mentions`` — whose ``description`` names what was
  omitted, with one ``PropertyValue`` per kind under ``variableMeasured`` giving a count and a
  reason. Otherwise a crate missing four wellplates would read exactly like a complete one.

  Counts and stable reasons only: raw exception text is deliberately excluded, because it varies
  between runs and a failed download embeds the server's hostname, which would defeat
  ``disclose_host=False``. The full detail stays in the export log. Pass ``declare_skipped=False``
  for a crate without it; nothing is declared when nothing was omitted.
* **A licence is always present.** RO-Crate makes ``license`` mandatory on the root, so a
  collection without one is exported under CC-BY-4.0. Set your own if that is wrong for the data.
* **``@context`` is a list, and it is generated.** It is the canonical RO-Crate 1.2 context plus
  namespace prefixes (``qudt``, ``sio``, ``obo``, ``adms``, ``skos``) *and an explicit definition
  for every key in the graph the base context does not already define*. The definitions are
  derived from the finished document rather than a hand-kept list, so a newly mapped chem-dcat-ap
  predicate cannot silently produce an invalid crate. ``sha256`` needs no local definition any
  more — RO-Crate 1.2's context carries it, where 1.1's did not.

Collections, and where elements live
------------------------------------

Chemotion collections are **contextual entities**, not crate folders::

    {"@id": "#collection-11", "@type": "Collection", "name": "Project A",
     "hasPart": [{"@id": "./samples/Water_42/"}]}

The root ``Dataset`` (``./``) ``mentions`` every collection; a sub-collection points at its parent
with ``isPartOf``. Elements sit at **collection-independent** paths —
``./<plural>/<name>_<id>/`` — and each one names the collections it belongs to::

    {"@id": "./samples/Water_42/", "@type": ["Dataset", …],
     "isPartOf": [{"@id": "#collection-11"}, {"@id": "#collection-12"}]}

``isPartOf`` is a single object when the element is in one collection and a list when it is in
several. It and the collections' ``hasPart`` are exact inverses, built from one index, so the two
directions cannot disagree.

This is not cosmetic. An element can belong to several collections at once, and a folder cannot
say that: while the element's crate path was derived from the collection it was reached through,
the second collection simply overwrote the first and one membership was lost with no warning.
Typing collections as ``Dataset`` would not have fixed it — RO-Crate treats a ``Dataset`` as a
Data Entity Directory, which must have a path-shaped ``@id`` ending in ``/`` and be reachable from
a ``hasPart``, i.e. it would put the element back inside exactly one folder.

An element in two collections is therefore stored **once**, and its attachments with it. Reading it
back::

    with import_eln("project.eln") as crate:
        for element in crate.elements:
            print(element.name, [c.name for c in element.collections])
        for collection in crate.collections:
            print(collection.name, collection.parent, len(collection.elements))

What the crate records besides the chemistry
--------------------------------------------

A crate can be valid and still be hard to use. Alongside the chem-dcat-ap graph, each export
carries the descriptive metadata a reader needs to make sense of it:

.. list-table::
   :header-rows: 1
   :widths: 22 78

   * - Property
     - Where it comes from
   * - ``identifier``
     - The element's short label (``S-42``), falling back to its database id. On the root, the
       collection id — so a re-export is recognisably the same collection.
   * - ``genre``
     - Which kind of ELN record this is (``Sample``, ``Reaction``, …), so a consumer can tell them
       apart without interpreting the ontology types.
   * - ``keywords``
     - The element's user labels and tag, as a **single comma-separated string** (an array is
       invalid here).
   * - ``text``
     - The element's narrative content — a reaction's observation or description.
   * - ``dateCreated`` / ``dateModified``
     - The element's own timestamps. See the note below on offline exports.
   * - ``variableMeasured``
     - ELN fields that chem-dcat-ap has no home for (location, melting/boiling point, TLC details,
       vessel size, …) as ``PropertyValue`` entries, so they are carried rather than lost.
   * - ``sha256`` on files
     - Computed from the bytes as they stream into the archive, so it always matches what was
       actually stored. A file whose download failed gets no checksum rather than a wrong one.

Provenance of the export itself is recorded as a ``CreateAction`` (``#ro-crate_created``) whose
``instrument`` is the ``SoftwareApplication`` node for this library, including its version and —
in ``softwareRequirements`` — the versions of the metadata models the chemistry is expressed in
(chem-dcat-ap over dcat-ap-plus, both pre-1.0 and still moving). The descriptor's ``sdPublisher``
names the **publishing organization**, taken from the first author's affiliation; one line is
logged at export time saying which organization was used, so you can set a different first
affiliation if another one should be credited.

Which ELN the data came from
----------------------------

The root dataset's ``isBasedOn`` points at a ``SoftwareApplication`` node describing the source
notebook: its URL as ``@id`` and ``url``, its ``version`` exactly as ``/about`` reports it
(``v4.0.0-rc-20260902`` — the build suffix, not just ``4.0.0``, because v4 ships under a moving
tag and the dotted version alone cannot tell two builds months apart), and the build ``identifier``
when the server reports a revision.

So a crate states four versions in total: the RO-Crate spec, the ``.eln`` spec, this client (plus
its metadata models), and the ELN that produced the data.

Two cases where the host is not a real one:

* **Offline exports.** There is no server to ask, so the node is identified by
  ``https://offline.chemotion.invalid`` — the RFC 2606 reserved TLD, which can never resolve — and
  carries **no** ``version``. An unknown version is left out rather than guessed.
* **Withholding the hostname.** Pass ``disclose_host=False`` to :meth:`~chemotion_api.collection.Collection.export_eln`
  for an archive leaving the institution: the source is recorded as the same sentinel, while the
  ELN **version is still recorded**. The crate then says what produced it without disclosing where
  it runs, and one line is logged noting the omission.

.. warning::
   **Ontology lookup contacts EBI, and is on by default.** ``export_eln(ontology_lookup=True)``
   is the default, so every analysis whose ``kind`` carries no embedded ``CHMO:…`` code has its
   **name sent to EBI's OLS service** at ``www.ebi.ac.uk`` to resolve a ``measurementTechnique``
   term.

   This is independent of ``disclose_host``: withholding the hostname does **not** withhold the
   analysis names, and the lookup still happens when exporting an offline dump. If analysis names
   are sensitive in your setting, or the export must make no outbound connection at all, pass
   ``ontology_lookup=False`` — embedded CHMO codes are still used, so crates keep the annotations
   they can derive locally. Passing ``ols_cache=<path>`` resolves each distinct term once and
   reuses it on later exports.

   Lookups are cached and never fatal: a failure downgrades the annotation rather than failing
   the export.

.. note::
   **Offline exports have no timestamps.** A Chemotion *export collection* dump does not record
   ``created_at``/``updated_at``, so :func:`~chemotion_api.offline.import_export_zip` crates omit
   ``dateCreated`` and ``dateModified`` entirely rather than inventing them. This is stated
   explicitly in the export log and recorded in the manifest, so an absent date is never ambiguous
   between "the source had none" and "this element genuinely has none". Export from a live server
   if you need them.

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
            name="Josiah Carberry",
            orcid="0000-0002-1825-0097",  # bare id or full https://orcid.org/... URL
            affiliations=[AuthorAffiliation(name="Brown University",
                                            ror="https://ror.org/05gq02987")],
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
