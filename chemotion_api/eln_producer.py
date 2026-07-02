"""The producer marker identifying a chemotion-api-generated ``.eln``.

``export_eln`` writes a ``SoftwareApplication`` contextual entity into the crate graph and
references it from the metadata descriptor's ``sdPublisher`` (TheELNFileFormat's convention
for "the software that wrote this crate"). Its ``name`` — :data:`PRODUCER_NAME` — is the
stable, grep-able string that uniquely identifies our crates::

    grep '"name": "chemotion-api"' ro-crate-metadata.json

:func:`chemotion_api.offline.import_eln` keys its own-crate check on the same marker.
"""
from __future__ import annotations

from importlib import metadata

#: ``name`` of the SoftwareApplication node — THE identifying string of our crates.
PRODUCER_NAME = "chemotion-api"

#: crate-local ``@id`` of the SoftwareApplication node.
PRODUCER_ID = "#chemotion-api"


def producer_version() -> str:
    """The installed chemotion-api package version (``"unknown"`` outside an installation)."""
    try:
        return metadata.version("chemotion-api")
    except metadata.PackageNotFoundError:
        return "unknown"


def producer_node() -> dict:
    """The SoftwareApplication graph node ``export_eln`` embeds in every crate."""
    return {
        "@id": PRODUCER_ID,
        "@type": "SoftwareApplication",
        "name": PRODUCER_NAME,
        "version": producer_version(),
    }
