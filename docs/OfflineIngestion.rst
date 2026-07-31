Offline Ingestion
=================

A Chemotion *export collection* ZIP (produced by the ELN's "export collection" feature) can be turned
into a ``.eln`` archive **without a live server**. The reader reshapes the relational ``export.json``
dump into the same per-element ``json_data`` the REST API returns, instantiates the regular
:class:`~chemotion_api.elements.sample.Sample` / :class:`~chemotion_api.elements.reaction.Reaction`
objects, and exposes an :class:`~chemotion_api.offline.offline_collection.OfflineCollection` so the
existing :meth:`~chemotion_api.collection.Collection.export_eln` runs offline.

.. code-block:: python

    from chemotion_api import Author, AuthorAffiliation
    from chemotion_api.offline import import_export_zip

    col = import_export_zip("my_export_collection.zip", label="My Project")
    col.export_eln(
        "my_project.eln",
        authors=[Author(name="Ada Lovelace", orcid="0000-0002-1825-0097",
                        affiliations=[AuthorAffiliation(name="Example University",
                                                        ror="https://ror.org/05dxps055")])],
    )

The ZIP may hold a single collection or a bundle of collections: the exported collection tree is
rebuilt (elements scoped per collection via the dump's membership join tables), and several
top-level collections are grouped under a synthetic root. Import only — writing Chemotion's
native export format remains the ELN GUI's domain.

.. note::
   Offline reconstruction currently covers **samples and reactions**; wellplates, research plans and
   generic elements reconstruct only from the live API.

.. autofunction:: chemotion_api.offline.import_export_zip

.. autoclass:: chemotion_api.offline.OfflineCollection
    :members:

Reading a ``.eln`` back in
--------------------------

An exported ``.eln`` can be opened again — its RO-Crate metadata graph and payload files become
navigable Python objects. Supported input is what this library's own
:meth:`~chemotion_api.collection.AbstractCollection.export_eln` writes, identified by the
``chemotion-api`` producer marker (a ``SoftwareApplication`` node referenced by the metadata
descriptor's ``sdPublisher``). Crates from other ELNs are rejected by default;
``allow_foreign=True`` opens them with best-effort generic parsing.

.. code-block:: python

    from chemotion_api.offline import import_eln

    with import_eln("my_project.eln") as crate:
        print(crate.root.name, [a.name for a in crate.authors])
        for ds in crate.elements:
            print(ds.kind, ds.name)
            for f in ds.files:
                f.extract("downloads/")

.. autofunction:: chemotion_api.offline.import_eln

.. autoclass:: chemotion_api.offline.ElnCrate
    :members:

.. autoclass:: chemotion_api.offline.ElnDataset
    :members:

.. autoclass:: chemotion_api.offline.ElnFile
    :members:
