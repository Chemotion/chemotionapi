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
        authors=[Author(name="Josiah Carberry", orcid="0000-0002-1825-0097",
                        affiliations=[AuthorAffiliation(name="Brown University",
                                                        ror="https://ror.org/05gq02987")])],
    )

.. note::
   Offline reconstruction currently covers **samples and reactions**; wellplates, research plans and
   generic elements reconstruct only from the live API.

.. autofunction:: chemotion_api.offline.import_export_zip

.. autoclass:: chemotion_api.offline.OfflineCollection
    :members:
