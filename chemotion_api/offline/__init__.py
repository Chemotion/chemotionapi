"""Offline ingestion of a Chemotion *export collection* ZIP.

Chemotion's "export collection" feature produces a ZIP holding a relational dump
(``export.json`` keyed by Rails model: ``Sample`` / ``Molecule`` / ``Reaction`` /
``Container`` / ``Attachment`` plus join tables), a ``schema.json``, a
``description.txt`` manifest, and ``attachments/`` + ``images/`` payload folders.

This package reconstructs that dump into the **same per-element ``json_data`` shape
the live REST API returns**, instantiates the regular :class:`~chemotion_api.elements.sample.Sample`
/ :class:`~chemotion_api.elements.reaction.Reaction` objects from it, and exposes an
:class:`~chemotion_api.offline.offline_collection.OfflineCollection` so the existing
:meth:`~chemotion_api.collection.Collection.export_eln` runs with **no live server**.

Entry point: :func:`chemotion_api.offline.import_export_zip`.

The reverse direction — reading an existing ``.eln`` RO-Crate back into navigable Python
objects — lives in :mod:`chemotion_api.offline.eln_reader`; entry point
:func:`chemotion_api.offline.import_eln`.
"""
from __future__ import annotations

from chemotion_api.offline.export_reader import ExportArchive, ExportAdapter, uuid_to_id
from chemotion_api.offline.offline_collection import (
    OfflineCollection,
    OfflineConnection,
    import_export_zip,
)
from chemotion_api.offline.eln_reader import (
    ElnCrate,
    ElnDataset,
    ElnFile,
    import_eln,
)

__all__ = [
    "ExportArchive",
    "ExportAdapter",
    "uuid_to_id",
    "OfflineCollection",
    "OfflineConnection",
    "import_export_zip",
    "ElnCrate",
    "ElnDataset",
    "ElnFile",
    "import_eln",
]
