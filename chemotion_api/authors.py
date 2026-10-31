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

import re
from dataclasses import dataclass, field
from typing import Optional


#: An ORCID iD is four groups of four characters; the last may be X (the ISO 7064 check digit).
_ORCID_RE = re.compile(r"^(\d{4})-(\d{4})-(\d{4})-(\d{3}[\dX])$")

#: A ROR id is "0" followed by 6 crockford-base32 chars and two check digits.
_ROR_RE = re.compile(r"^0[0-9a-hj-km-np-tv-z]{6}\d{2}$")


def _orcid_checksum_valid(digits: str) -> bool:
    """Verify an ORCID iD's ISO 7064 MOD 11-2 check digit.

    Syntax alone is not enough: a mistyped iD usually still looks like four groups of four, and
    would then be published as somebody else's identity.
    """
    total = 0
    for char in digits[:-1]:
        total = (total + int(char)) * 2
    remainder = total % 11
    expected = (12 - remainder) % 11
    return digits[-1].upper() == ("X" if expected == 10 else str(expected))


#: Crockford base32, as ROR uses it (no i, l, o, u).
_ROR_ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"


def _ror_checksum_valid(ror: str) -> bool:
    """Verify a ROR id's ISO 7064 MOD 97-10 check digits.

    Same reasoning as the ORCID check digit: a mistyped ROR usually still has the right shape,
    and would then name the wrong institution as the crate's publisher.
    """
    number = 0
    for char in ror[:-2]:
        number = number * 32 + _ROR_ALPHABET.index(char)
    return f"{98 - ((number * 100) % 97):02d}" == ror[-2:]


def _bare_id(value: str, host: str) -> str:
    """Strip an optional ``https://<host>/`` prefix, returning the bare identifier.

    The prefix is matched **anchored**: ``https://evil.example/orcid.org/0000-0002-1825-0097``
    keeps its full text and therefore fails the syntax check, rather than being quietly reduced
    to the real iD it name-drops.
    """
    text = value.strip().rstrip("/")
    return re.sub(rf"^(?:https?://)?(?:www\.)?{re.escape(host)}/", "", text, flags=re.IGNORECASE)


def _normalize_orcid(orcid: str) -> str:
    """Return ``orcid`` as a full ``https://orcid.org/...`` URL.

    Anything beginning ``http`` used to be passed through untouched, so
    ``orcid="http://evil.example/ada"`` became the crate's authorship ``@id`` verbatim — and the
    first affiliation is additionally promoted to ``sdPublisher``. The identifier is now rebuilt
    from its validated bare form, so only orcid.org can ever be named.

    :raises ValueError: if it is not a syntactically valid ORCID iD with a correct check digit.
    """
    bare = _bare_id(orcid, "orcid.org")
    if not _ORCID_RE.match(bare) or not _orcid_checksum_valid(bare.replace("-", "")):
        raise ValueError(
            f"{orcid!r} is not a valid ORCID iD. Expected 0000-0002-1825-0097 (four groups of "
            "four, last digit may be X) — check for a typo; the final character is a checksum.")
    return f"https://orcid.org/{bare}"


def _normalize_ror(ror: str) -> str:
    """Return ``ror`` as a full ``https://ror.org/...`` URL.

    Same reasoning as :func:`_normalize_orcid`: rebuilt from the validated bare id rather than
    trusting whatever the caller passed.

    :raises ValueError: if it is not a syntactically valid ROR id.
    """
    bare = _bare_id(ror, "ror.org").lower()
    if not _ROR_RE.match(bare) or not _ror_checksum_valid(bare):
        raise ValueError(
            f"{ror!r} is not a valid ROR id. Expected 05gq02987 — '0' then six characters then "
            "two check digits. Look it up at https://ror.org.")
    return f"https://ror.org/{bare}"


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
        _normalize_ror(self.ror)


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
                "orcid='https://orcid.org/0000-0002-1825-0097' (register/look it up at https://orcid.org)."
            )
        if not self.affiliations:
            raise ValueError(
                f"Author '{self.name}' has no affiliation. Provide at least one "
                "AuthorAffiliation(name='Your Organization', ror='https://ror.org/<id>')."
            )
        for aff in self.affiliations:
            aff.validate(self.name)
        # Checked last: a *missing* ORCID or affiliation is the more useful thing to report first.
        _normalize_orcid(self.orcid)


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
