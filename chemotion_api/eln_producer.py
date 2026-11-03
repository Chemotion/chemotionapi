"""The producer marker identifying a chemotion-api-generated ``.eln``.

``export_eln`` writes a ``SoftwareApplication`` contextual entity into the crate graph and
references it as the ``instrument`` of the crate's ``CreateAction`` — "the software that wrote
this crate". Its ``name`` — :data:`PRODUCER_NAME` — is the stable, grep-able string that
uniquely identifies our crates::

    grep '"name": "chemotion-api"' ro-crate-metadata.json

:func:`chemotion_api.offline.import_eln` keys its own-crate check on the same marker.
"""
from __future__ import annotations

from importlib import metadata

#: ``name`` of the SoftwareApplication node — THE identifying string of our crates.
PRODUCER_NAME = "chemotion-api"

#: crate-local ``@id`` of the SoftwareApplication node.
PRODUCER_ID = "#chemotion-api"

#: RO-Crate 1.2 makes `url` REQUIRED on a SoftwareApplication (`ro-crate-1.2_32.2`), so the
#: producer marker has to say where this client lives, not merely name itself.
PRODUCER_URL = "https://github.com/Chemotion/chemotionapi"

#: Host recorded for the source ELN when there is no server to name — an offline export, or a
#: crate whose hostname is deliberately withheld. ``.invalid`` is the RFC 2606 reserved TLD, so it
#: can never resolve to anything real: it states "no server" instead of pointing somewhere
#: misleading. Lives here rather than in ``offline/`` so the crate writer does not have to import
#: a feature module to name it.
OFFLINE_HOST = "https://offline.chemotion.invalid"


def producer_version() -> str:
    """The installed chemotion-api package version (``"unknown"`` outside an installation)."""
    try:
        return metadata.version("chemotion-api")
    except metadata.PackageNotFoundError:
        return "unknown"


#: Packages whose versions decide how the chemistry in a crate is expressed. Both are pre-1.0 and
#: still moving, so a crate read a year from now needs to say which vocabulary produced its terms.
_METADATA_MODELS = ("chem_dcat_ap", "dcat_ap_plus")


def model_versions() -> list[str]:
    """``name version`` for each metadata model this crate's vocabulary comes from."""
    out = []
    for package in _METADATA_MODELS:
        try:
            out.append(f"{package} {metadata.version(package)}")
        except metadata.PackageNotFoundError:
            continue
    return out


def producer_node() -> dict:
    """The SoftwareApplication graph node ``export_eln`` embeds in every crate.

    ``version`` is this client's; ``softwareRequirements`` carries the metadata-model versions,
    kept separate so the two are never confused for one another.
    """
    node = {
        "@id": PRODUCER_ID,
        "@type": "SoftwareApplication",
        "name": PRODUCER_NAME,
        "url": PRODUCER_URL,
        "version": producer_version(),
    }
    models = model_versions()
    if models:
        node["softwareRequirements"] = ", ".join(models)
    return node
