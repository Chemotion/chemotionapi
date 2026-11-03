"""The ontology vocabulary an instance publishes about itself.

A Chemotion instance ships its own OLS term trees (CHMO, RXNO, BAO) and an admin can edit
and extend them, so the label an ELN *displays* for a technique is not always the label EBI
would return for the same text. A crate should say what the ELN says: these terms therefore
outrank the EBI OLS4 fallback in :func:`~chemotion_api.ontology.resolve_ontology_term`.

The source is ``GET /api/v1/ols_terms/list?name=<ontology>&edited=false``, which serves the
instance's ``public/ontologies/<ontology>.json`` — the full tree, exactly as the instance
stores it. ``edited=true`` is deliberately *not* used: it returns only the enabled subset and
overwrites the first root's ``children`` with the calling user's recently-used term ids, which
is a UI convenience that would both truncate and corrupt the vocabulary for our purpose. A
term that is disabled in the picker still resolves to the right IRI and the instance's own
label, which is all this lookup needs.

Like every other part of the ontology package, this is best-effort: a failure downgrades the
annotation and is never fatal. An export with no instance behind it (an offline export from a
dump, where the connection is
:class:`~chemotion_api.offline.offline_collection.OfflineConnection`) has nothing to ask, and
falls straight through to the EBI lookup.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from chemotion_api.eln_producer import OFFLINE_HOST
from chemotion_api.ontology.ols_lookup import OntologyTerm, parse_embedded_kind

logger = logging.getLogger(__name__)

INSTANCE_TERMS_PATH = "/api/v1/ols_terms/list"
#: The ontologies ``ols_terms/list`` accepts; anything else is rejected by the server.
SUPPORTED_ONTOLOGIES = ("chmo", "rxno", "bao")


def _norm(text: str | None) -> str:
    """Fold a label to a comparison key: case-insensitive, whitespace-collapsed."""
    return re.sub(r"\s+", " ", (text or "").strip()).casefold()


def _iter_nodes(nodes: Any) -> Any:
    """Walk the nested ``children`` tree, skipping anything that is not a term object."""
    if not isinstance(nodes, list):
        return
    for node in nodes:
        if not isinstance(node, dict):
            continue
        yield node
        yield from _iter_nodes(node.get("children"))


def _term_of(node: dict) -> OntologyTerm | None:
    """Read one tree node as a term, or ``None`` for a node that does not name one.

    The code is taken from ``value``, which the server renders as
    ``"CHMO:0000595 | 13C NMR"`` (or ``"<id> | <label> (<synonym>)"`` for a term with a
    synonym) — the same shape as an analysis' embedded ``kind``, so the same parser reads it.

    ``term_id`` is **not** used, even though every node has the key: the published tree is
    built from string-keyed hashes while the entity exposes ``term_id`` as an attribute, so
    it serialises as ``null`` throughout. ``value`` is built in a block that reads the string
    key, and carries the id. Measured against a live instance: of 2362 CHMO nodes, 0 had a
    usable ``term_id`` and 2361 had a parseable ``value`` — the one exception being the
    ``-- Recently selected --`` group header, which names no term and is correctly skipped.
    ``synonyms`` serialises as ``null`` for the same reason, so it is read only when the
    server does send it.

    ``search`` is deliberately ignored: its synonym separator has differed between generators
    (``"<id> | <label>|<synonym>"`` on the instance measured, ``"…(<syn>)|<a>,<b>"`` in the
    current entity source), so it cannot be split reliably.
    """
    term = parse_embedded_kind(node.get("value"))
    if term is None:
        return None
    label = term.label
    synonym = node.get("synonym")
    # The tree displays "label (synonym)"; a DefinedTerm name wants the bare label.
    if isinstance(synonym, str) and synonym and label.endswith(f"({synonym})"):
        label = label[: -len(f"({synonym})")].strip() or label
    return OntologyTerm(iri=term.iri, label=label)


def index_terms_by_iri(payload: Any) -> dict[str, OntologyTerm]:
    """Flatten an ``ols_terms/list`` payload into ``IRI -> term``.

    The reverse of :func:`index_instance_terms`, for naming a term we hold an identifier for
    but no label — which is every ontology IRI chem-dcat-ap emits. Note the instance's trees
    are not confined to the ontology they are filed under (the ``chmo`` tree carries ``BFO``
    terms, the ``rxno`` tree carries ``CHEBI`` ones), so a caller should search all of them
    rather than inferring the file from the IRI prefix.
    """
    index: dict[str, OntologyTerm] = {}
    if not isinstance(payload, dict):
        return index
    for node in _iter_nodes(payload.get("ols_terms")):
        term = _term_of(node)
        if term is not None:
            index.setdefault(term.iri, term)
    return index


def index_instance_terms(payload: Any) -> dict[str, OntologyTerm]:
    """Flatten an ``ols_terms/list`` payload into ``normalised text -> term``.

    Labels are indexed before synonyms, so a term named *X* always wins over a different term
    that merely lists *X* as a synonym, whatever order the tree happens to arrive in.
    """
    primary: dict[str, OntologyTerm] = {}
    secondary: dict[str, OntologyTerm] = {}
    if not isinstance(payload, dict):
        return primary
    # `ols_terms` is null on an instance that publishes no file for this ontology (measured: bao
    # on the test stack), so this is not merely defensive.
    for node in _iter_nodes(payload.get("ols_terms")):
        term = _term_of(node)
        if term is None:
            continue
        label = term.label
        for key in (label, node.get("title")):
            if isinstance(key, str) and _norm(key):
                primary.setdefault(_norm(key), term)
        synonyms = node.get("synonyms")
        for key in (node.get("synonym"), *(synonyms if isinstance(synonyms, list) else ())):
            if isinstance(key, str) and _norm(key):
                secondary.setdefault(_norm(key), term)
    for key, term in secondary.items():
        primary.setdefault(key, term)
    return primary


class InstanceVocabulary:
    """Lazily fetched, per-ontology index of the terms an instance publishes.

    Each ontology is fetched at most once per instance of this class — including a failure,
    which is remembered as an empty index so a down or old server is asked once, not once per
    analysis. The result is *not* written to :class:`~chemotion_api.ontology.OlsCache`: that
    file is portable between runs and instances, and an instance-specific label must never be
    replayed against a different instance.
    """

    def __init__(self, session: Any, timeout: float = 10.0) -> None:
        self._session = session
        self._timeout = timeout
        self._indexes: dict[str, dict[str, OntologyTerm]] = {}
        self._iri_indexes: dict[str, dict[str, OntologyTerm]] = {}

    @classmethod
    def from_session(cls, session: Any) -> InstanceVocabulary | None:
        """Build a vocabulary for ``session``, or ``None`` when there is no instance to ask."""
        if session is None or not hasattr(session, "get"):
            return None
        host = (getattr(session, "host_url", "") or "").strip("/")
        if not host or host == OFFLINE_HOST:
            # An export from a dump has no server behind it; say so once instead of issuing a
            # request that cannot be answered.
            logger.debug("No instance behind this export; skipping its ontology vocabulary.")
            return None
        return cls(session)

    def _index(self, ontology: str) -> dict[str, OntologyTerm]:
        key = (ontology or "").lower()
        if key in self._indexes:
            return self._indexes[key]
        index: dict[str, OntologyTerm] = {}
        by_iri: dict[str, OntologyTerm] = {}
        if key in SUPPORTED_ONTOLOGIES:
            try:
                res = self._session.get(
                    INSTANCE_TERMS_PATH,
                    params={"name": key, "edited": "false"},
                    timeout=self._timeout,
                )
                res.raise_for_status()
                payload = res.json()
                index = index_instance_terms(payload)
                by_iri = index_terms_by_iri(payload)
            except Exception as exc:  # HTTP/JSON/transport — never fatal
                logger.warning("Could not read the instance's %s terms: %s", key, exc)
                index, by_iri = {}, {}
            else:
                logger.debug("Instance %s vocabulary: %d searchable names.", key, len(index))
        elif key:
            # Not a silent miss: the server hard-restricts `name` to chmo|rxno|bao, so asking
            # for anything else can only mean the caller expected an ontology this client does
            # not yet know about (MOP is requested upstream in ComPlat/chemotion_ELN#1633).
            # Falling through to EBI without a word would look exactly like "the instance has
            # no such term".
            logger.info(
                "Ontology %r is not one the instance publishes (%s); using the public lookup "
                "instead.", key, "/".join(SUPPORTED_ONTOLOGIES))
        self._indexes[key] = index
        self._iri_indexes[key] = by_iri
        return index

    def lookup(self, text: str | None, ontology: str = "chmo") -> OntologyTerm | None:
        """Resolve ``text`` against the instance's own ``ontology`` terms."""
        key = _norm(text)
        if not key:
            return None
        return self._index(ontology).get(key)

    def label_for_iri(self, iri: str | None) -> str | None:
        """Name a term we hold an IRI for, searching every ontology the instance publishes.

        The trees are not confined to the ontology they are filed under — the instance's
        ``chmo`` tree carries ``BFO`` terms and its ``rxno`` tree carries ``CHEBI`` ones — so
        the IRI prefix is not a reliable guide to which file holds it. Each tree is fetched at
        most once, so searching all of them costs no extra requests after the first miss.
        """
        if not iri:
            return None
        for ontology in SUPPORTED_ONTOLOGIES:
            self._index(ontology)  # ensure fetched; populates the IRI index alongside
            term = self._iri_indexes.get(ontology, {}).get(iri)
            if term is not None:
                return term.label
        return None
