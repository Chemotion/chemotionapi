"""Resolve technique/method labels to ontology IRIs, with an OLS fallback.

Built on ``requests`` and the chemotion-api logging conventions.
Network access is optional and never fatal:
all errors are caught, logged, and treated as a miss. A JSON cache (with a
*negative cache* for known misses) keeps repeated/offline runs cheap and deterministic.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

OLS_SEARCH_URL = "https://www.ebi.ac.uk/ols4/api/search"
# "CHMO:0000595 | proton nuclear magnetic resonance spectroscopy (1H NMR)"
_EMBEDDED_KIND_RE = re.compile(r"^\s*([A-Za-z]+):(\d+)\b")


@dataclass(frozen=True)
class OntologyTerm:
    """A resolved ontology term."""
    iri: str
    label: str


def obo_code_to_iri(code: str) -> str | None:
    """``"CHMO:0000595"`` -> ``"http://purl.obolibrary.org/obo/CHMO_0000595"``."""
    m = re.match(r"^\s*([A-Za-z]+):(\d+)\s*$", code or "")
    if not m:
        return None
    return f"http://purl.obolibrary.org/obo/{m.group(1).upper()}_{m.group(2)}"


def parse_embedded_kind(kind: str | None) -> OntologyTerm | None:
    """Extract an OntologyTerm from a Chemotion ``extended_metadata.kind`` string.

    Returns ``None`` when the string carries no ``PREFIX:NUMBER`` code.
    """
    if not kind:
        return None
    m = _EMBEDDED_KIND_RE.match(kind)
    if not m:
        return None
    iri = obo_code_to_iri(f"{m.group(1)}:{m.group(2)}")
    if iri is None:
        return None
    label = kind.split("|", 1)[1].strip() if "|" in kind else kind.strip()
    return OntologyTerm(iri=iri, label=label)


class OlsCache:
    """JSON cache of OLS lookups, keyed ``ontology -> label -> {iri,label}|null``.

    ``null`` is a *negative cache* entry recording a previous miss.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else None
        self._data: dict[str, dict[str, dict | None]] = {}
        if self.path and self.path.is_file():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:  # corrupt/unreadable → start empty
                logger.warning("Could not read OLS cache %s: %s", self.path, exc)

    def get(self, ontology: str, label: str) -> tuple[bool, OntologyTerm | None]:
        """Return ``(hit, term)``. ``hit`` distinguishes a cached miss from "not cached"."""
        bucket = self._data.get(ontology, {})
        if label not in bucket:
            return False, None
        entry = bucket[label]
        if entry is None:
            return True, None  # negative cache hit
        return True, OntologyTerm(iri=entry["iri"], label=entry["label"])

    def put(self, ontology: str, label: str, term: OntologyTerm | None) -> None:
        """Cache a lookup result for ``(ontology, label)``; ``None`` records a negative-cache miss."""
        self._data.setdefault(ontology, {})[label] = (
            None if term is None else {"iri": term.iri, "label": term.label}
        )

    def save(self) -> None:
        """Write the cache to its JSON file (no-op if no path was configured)."""
        if not self.path:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        except OSError as exc:  # pragma: no cover - disk errors
            logger.warning("Could not write OLS cache %s: %s", self.path, exc)


def query_ols(label: str, ontology: str = "chmo",
              cache: OlsCache | None = None, timeout: float = 10.0) -> OntologyTerm | None:
    """Look up ``label`` in OLS4 within ``ontology``; cached and network-error tolerant."""
    if not label or not ontology:
        return None
    if cache is not None:
        cached_hit, cached_term = cache.get(ontology, label)
        if cached_hit:
            return cached_term
    term: OntologyTerm | None = None
    try:
        import requests
        resp = requests.get(
            OLS_SEARCH_URL,
            params={"q": label, "ontology": ontology, "rows": "5"},
            timeout=timeout,
        )
        resp.raise_for_status()
        docs = (resp.json().get("response", {}) or {}).get("docs", []) or []
        for doc in docs:
            iri, lab = doc.get("iri"), doc.get("label")
            if iri and lab:
                term = OntologyTerm(iri=iri, label=lab)
                break
    except Exception as exc:  # network/HTTP/JSON — never fatal
        logger.warning("OLS lookup failed for %r in %s: %s", label, ontology, exc)
        term = None
    if cache is not None:
        cache.put(ontology, label, term)
    return term


def resolve_ontology_term(
    label: str | None,
    embedded_kind: str | None = None,
    ontology: str = "chmo",
    cache: OlsCache | None = None,
    enable_ols: bool = True,
) -> OntologyTerm | None:
    """Resolve a technique/analysis label to an ontology term.

    Order: (1) an ontology code embedded in ``embedded_kind`` → (2) OLS lookup on
    ``label`` (or the kind's label) when ``enable_ols`` → (3) ``None`` (caller uses a
    placeholder). chem-dcat-ap typed mapping is handled upstream by ``to_dcat_ap`` and
    is not repeated here.
    """
    embedded = parse_embedded_kind(embedded_kind)
    if embedded is not None:
        return embedded
    query = label or (embedded_kind.split("|", 1)[-1].strip() if embedded_kind else None)
    if enable_ols and query:
        return query_ols(query, ontology=ontology, cache=cache)
    return None
