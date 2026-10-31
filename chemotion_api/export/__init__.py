"""Standalone, independently-testable building blocks for :meth:`chemotion_api.collection.AbstractCollection.export_eln`.

Currently holds the element-indexing and URI-mapping pieces of the exporter (see
:mod:`chemotion_api.export.indexing`). The rest of ``export_eln`` (graph assembly, author
nodes, ZIP writing) still lives in :mod:`chemotion_api.collection`.
"""
