"""Server version detection and the JSON-LD ``@type`` IRIs derived from it."""
import re

import requests

#: Major ELN version this client speaks. v4 rewrote collections and sharing, renumbered share
#: permission levels and dropped the /syncCollections namespace, so there is no meaningful
#: overlap with 3.x — hence a hard gate rather than a compatibility layer.
SUPPORTED_ELN_MAJOR = 4


class UnsupportedServerVersion(Exception):
    """Raised when the Chemotion instance is not a version this client supports."""


class SchemaManager:
    """Parses the instance version out of ``/about`` and builds JSON-LD model-type IRIs from it.

    ``/about`` is a plain Rails page (not part of the Grape API) and is served without
    authentication, so the version — and therefore the compatibility check — is available before
    any credentials are sent.
    """

    iri_prefix = 'chemotion'

    #: The version line rendered by app/views/pages/about.haml, e.g. "Version: v4.0.0-rc-260818".
    #: Captured loosely on purpose: releases appear as `v4.0.0`, release candidates as
    #: `v4.0.0-rc`, and rolling builds add a date (`-260818`). The trailing group keeps whatever
    #: follows the dotted numbers, because that suffix is the only thing distinguishing two
    #: rolling builds — v4 ships under a moving `next-release` tag with no immutable version, so
    #: `4.0.0` alone cannot tell two servers months apart from each other.
    #: `/about` is an HTML page, so the suffix must stop at the next tag — a bare `\S*` swallows
    #: the closing `</h4>` and puts markup into the recorded version.
    _VERSION_RE = re.compile(r'Version:\s*v?(\d+)\.(\d+)(?:\.(\d+))?([^\s<]*)')

    #: The build revision, when /about reports one. Best-effort: absent on some builds, and at
    #: least one instance renders it with a trailing newline.
    _REVISION_RE = re.compile(r'Current revision:\s*([^\s<]+)')

    def __init__(self, res: requests.Response, check_version: bool = True):
        """
        :param res: the response for ``GET /about``.
        :param check_version: raise :class:`UnsupportedServerVersion` unless the instance is a
            supported major version. Only pass ``False`` to inspect an unsupported instance
            deliberately (the version is still parsed).
        :raises UnsupportedServerVersion: if the version cannot be parsed, or is not supported.
        """
        match = self._VERSION_RE.search(res.text)
        if match is None:
            # Previously this fell back to the literal string 'TEST', which silently poisoned every
            # built-in element's @type IRI. A version we cannot read is a hard error: it means we
            # are not talking to a Chemotion instance we understand.
            raise UnsupportedServerVersion(
                'Could not read the Chemotion version from /about '
                f'(HTTP {res.status_code}). Is this URL a Chemotion instance? '
                f'This client requires ELN v{SUPPORTED_ELN_MAJOR}.'
            )

        self.major = int(match.group(1))
        self.minor = int(match.group(2))
        self.patch = int(match.group(3)) if match.group(3) else 0
        #: Full dotted version as reported by the server, e.g. ``'4.0.0'``.
        self.version = f'{self.major}.{self.minor}.{self.patch}'
        #: The version exactly as /about renders it, e.g. ``'v4.0.0-rc-260818'``. This is what
        #: identifies a specific build; :attr:`version` deliberately drops the suffix.
        self.version_string = f'v{self.version}{match.group(4) or ""}'
        revision = self._REVISION_RE.search(res.text)
        #: The build revision from /about, when it reports one; ``None`` otherwise.
        self.revision = revision.group(1).strip() if revision else None

        if check_version and self.major != SUPPORTED_ELN_MAJOR:
            raise UnsupportedServerVersion(
                f'This Chemotion instance runs ELN {self.version}, but this client only supports '
                f'ELN v{SUPPORTED_ELN_MAJOR}. For an ELN 3.1.x server use the 312.x release line '
                'of chemotion-api instead.'
            )

    @property
    def model_type_version(self) -> str:
        """The version segment used in built-in elements' ``@type`` IRIs — ``major.minor``.

        Deliberately coarser than :attr:`version`: deployments track rolling release candidates
        (``v4.0.0-rc-260818``), and a patch- or date-level segment would make the semantic type of
        the *same* element churn on every server rebuild.
        """
        return f'{self.major}.{self.minor}'

    def generate_model_type(self, tpye_name: str, schema_version):
        """Build the JSON-LD model-type IRI for an element class.

        :param tpye_name: element class name (lower-cased in the IRI).
        :param schema_version: a generic class's own schema version, or ``None`` for a built-in
            class, in which case the instance version is used.
        """
        if schema_version is not None:
            return f'{self.iri_prefix}:generic_type/{tpye_name.lower()}/{schema_version}'
        return f'{self.iri_prefix}:type/{tpye_name.lower()}/{self.model_type_version}'
