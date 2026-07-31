"""Manually-specified authorship for ``.eln`` export.

Every exported ``.eln`` must declare its author(s) explicitly — the API user sets them rather
than the export defaulting to the logged-in user. Each :class:`Author` carries an ORCID iD and one
or more :class:`AuthorAffiliation`, each with a ROR (Research Organization Registry) id.

Example::

    from chemotion_api import Author, AuthorAffiliation
    authors = [
        Author(
            name="Ada Lovelace",
            orcid="0000-0002-1825-0097",
            affiliations=[AuthorAffiliation(name="KIT", ror="https://ror.org/04t3en479")],
        ),
    ]
    collection.set_authors(authors)            # or: collection.export_eln(path, authors=authors)
    collection.export_eln("out.eln")
"""
from __future__ import annotations

from dataclasses import dataclass, field


def _normalize_orcid(orcid: str) -> str:
    """Return ``orcid`` as a full ``https://orcid.org/...`` URL (bare ids get the prefix added)."""
    o = orcid.strip()
    return o if o.startswith("http") else f"https://orcid.org/{o.lstrip('/')}"


def _normalize_ror(ror: str) -> str:
    """Return ``ror`` as a full ``https://ror.org/...`` URL (bare ids get the prefix added)."""
    r = ror.strip()
    return r if r.startswith("http") else f"https://ror.org/{r.lstrip('/')}"


@dataclass
class AuthorAffiliation:
    """An author's affiliation, identified by a ROR id.

    :param name: human-readable organization name (e.g. ``"Karlsruhe Institute of Technology"``).
    :param ror: ROR id — either the bare id (``"04t3en479"``) or the full URL
        (``"https://ror.org/04t3en479"``). Look it up at https://ror.org.
    """
    name: str
    ror: str

    @property
    def ror_url(self) -> str:
        """The affiliation's ROR id as a full ``https://ror.org/...`` URL."""
        return _normalize_ror(self.ror)

    def validate(self, author_name: str) -> None:
        """Raise ``ValueError`` if the affiliation is missing its name or ROR id.

        :param author_name: the owning author's name, for clearer error messages.
        """
        if not self.name or not self.name.strip():
            raise ValueError(
                f"Affiliation of author '{author_name}' is missing a name. Provide "
                "AuthorAffiliation(name='Your Organization', ror='https://ror.org/<id>')."
            )
        if not self.ror or not self.ror.strip():
            raise ValueError(
                f"Affiliation '{self.name}' of author '{author_name}' is missing a ROR id. "
                "Provide ror='https://ror.org/<id>' (find your organization's id at https://ror.org)."
            )


@dataclass
class Author:
    """An ``.eln`` author. Requires a name, an ORCID iD, and at least one affiliation.

    :param name: the author's full name.
    :param orcid: ORCID iD — bare (``"0000-0002-1825-0097"``) or full URL. See https://orcid.org.
    :param affiliations: one or more :class:`AuthorAffiliation` (each carrying a ROR id).
    :param email: optional contact e-mail.
    """
    name: str
    orcid: str
    affiliations: list[AuthorAffiliation] = field(default_factory=list)
    email: str | None = None

    @property
    def orcid_url(self) -> str:
        """The author's ORCID iD as a full ``https://orcid.org/...`` URL."""
        return _normalize_orcid(self.orcid)

    def validate(self) -> None:
        """Raise ``ValueError`` with actionable guidance if anything required is missing."""
        if not self.name or not self.name.strip():
            raise ValueError(
                "An author is missing a name. Provide "
                "Author(name='Full Name', orcid='0000-...', affiliations=[AuthorAffiliation(...)])."
            )
        if not self.orcid or not self.orcid.strip():
            raise ValueError(
                f"Author '{self.name}' is missing an ORCID iD. Provide "
                "orcid='https://orcid.org/0000-0000-0000-0000' (register/look it up at https://orcid.org)."
            )
        if not self.affiliations:
            raise ValueError(
                f"Author '{self.name}' has no affiliation. Provide at least one "
                "AuthorAffiliation(name='Your Organization', ror='https://ror.org/<id>')."
            )
        for aff in self.affiliations:
            aff.validate(self.name)


def validate_authors(authors: list[Author] | None) -> list[Author]:
    """Validate the author list for an export; raise a helpful ``ValueError`` if unusable.

    Every ``.eln`` must declare its authors explicitly (no implicit logged-in-user default).
    """
    if not authors:
        raise ValueError(
            "export_eln requires at least one author — authorship is no longer taken from the "
            "logged-in user. Set authors first, e.g.:\n"
            "    from chemotion_api import Author, AuthorAffiliation\n"
            "    collection.set_authors([\n"
            "        Author(name='Ada Lovelace', orcid='0000-0002-1825-0097',\n"
            "               affiliations=[AuthorAffiliation(name='KIT', ror='https://ror.org/04t3en479')]),\n"
            "    ])\n"
            "or pass authors=[...] directly to export_eln(...)."
        )
    for author in authors:
        author.validate()
    return authors
