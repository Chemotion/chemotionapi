"""Literature references on elements and collections (``/api/v1/literatures``, M2.6)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from chemotion_api.connection import Connection, request_error

#: ``literature_api.rb``'s DOI pattern: ``10.<prefix>/<suffix>``.
_DOI = re.compile(r'(?:\s*10\.)(\S+)/(\S+)')

#: Reference types (``litype``) the server accepts; ``citedOwn`` is the UI's default.
REFERENCE_TYPES = ('citedOwn', 'citedRef', 'referTo', 'literatureOfSource', 'additionalLiterature')
#: Element types that take references: the built-in ones (``API::ELEMENT_CLASS``).
REFERENCEABLE_TYPES = ('sample', 'reaction', 'wellplate', 'screen', 'research_plan')


@dataclass
class Reference:
    """One literature reference, as linked to an element.

    ``id`` is the literature record (shared by every element citing it); ``link_id`` is this
    element's link to it, which is what removing or retyping a reference acts on.
    """
    id: int | None = None
    link_id: int | None = None
    title: str | None = None
    doi: str | None = None
    url: str | None = None
    isbn: str | None = None
    litype: str | None = None
    refs: dict[str, Any] = field(default_factory=dict)
    user_name: str | None = None
    count: int | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def bibtex(self) -> str | None:
        return (self.refs or {}).get('bibtex')

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Reference:
        return cls(id=data.get('id'), link_id=data.get('literal_id'), title=data.get('title'),
                   doi=data.get('doi'), url=data.get('url'), isbn=data.get('isbn'), litype=data.get('litype'),
                   refs=data.get('refs') or {}, user_name=data.get('user_name'), count=data.get('count'), raw=data)


def _element_params(element_type: str, element_id: int) -> dict[str, Any]:
    if element_type not in REFERENCEABLE_TYPES:
        raise ValueError(f'References are not supported on {element_type} elements '
                         f'(only on {", ".join(REFERENCEABLE_TYPES)}).')
    return {'element_type': element_type, 'element_id': element_id}


def _check_type(litype: str) -> str:
    if litype not in REFERENCE_TYPES:
        raise ValueError(f'Unknown reference type {litype!r}; use one of {", ".join(REFERENCE_TYPES)}.')
    return litype


def _parse(res, what: str) -> list[Reference]:
    if res.status_code not in (200, 201):
        raise request_error(res, what)
    data = res.json() or {}
    if isinstance(data, dict) and data.get('error'):
        raise ConnectionError(f'{what}: {data["error"]}')
    return [Reference.from_json(r) for r in data.get('literatures') or []]


def load_references(session: Connection, element_type: str, element_id: int) -> list[Reference]:
    res = session.get('/api/v1/literatures', params=_element_params(element_type, element_id))
    return _parse(res, f'loading the references of {element_type} {element_id}')


def add_reference(session: Connection, element_type: str, element_id: int, *, doi: str | None = None,
                  url: str | None = None, title: str | None = None, isbn: str | None = None,
                  bibtex: str | None = None, litype: str = 'citedOwn') -> list[Reference]:
    if not any((doi, url, title, isbn)):
        raise ValueError('A reference needs a DOI, URL, title or ISBN.')
    ref: dict[str, Any] = {'is_new': True, 'litype': _check_type(litype), 'doi': doi, 'url': url,
                           'title': title, 'isbn': isbn}
    ref = {k: v for k, v in ref.items() if v is not None}
    if bibtex is not None:
        ref['refs'] = {'bibtex': bibtex}
    res = session.post('/api/v1/literatures', data=_element_params(element_type, element_id) | {'ref': ref})
    return _parse(res, f'adding a reference to {element_type} {element_id}')


def remove_reference(session: Connection, element_type: str, element_id: int, reference: Reference) -> None:
    if reference.link_id is None:
        raise ValueError('This reference is not linked to an element.')
    res = session.delete('/api/v1/literatures',
                         params=_element_params(element_type, element_id) | {'id': reference.link_id})
    if res.status_code not in (200, 204):
        raise request_error(res, f'removing reference {reference.link_id} from {element_type} {element_id}')


def set_reference_type(session: Connection, element_type: str, element_id: int, reference: Reference,
                       litype: str) -> list[Reference]:
    if reference.link_id is None:
        raise ValueError('This reference is not linked to an element.')
    res = session.put('/api/v1/literatures', data=_element_params(element_type, element_id)
                      | {'id': reference.link_id, 'litype': _check_type(litype)})
    return _parse(res, f'changing the type of reference {reference.link_id}')


def doi_metadata(session: Connection, doi: str) -> dict[str, Any]:
    """BibTeX for a DOI, fetched by the server from doi.org: ``{'bibtex': str, 'BTjson': dict}``."""
    # Checked here with the server's own pattern: its check calls `error(400)` instead of Grape's
    # `error!`, so an invalid DOI comes back as a 500 rather than a 400.
    if not _DOI.search(doi or ''):
        raise ValueError(f'Not a DOI: {doi!r}')
    res = session.get('/api/v1/literatures/doi/metadata', params={'doi': doi})
    if res.status_code != 200:
        raise request_error(res, f'looking up DOI {doi}')
    return res.json()


def collection_references(session: Connection, collection_id: int) -> dict[str, list[Reference]]:
    res = session.get('/api/v1/literatures/collection', params={'id': collection_id})
    if res.status_code != 200:
        raise request_error(res, f'loading the references of collection {collection_id}')
    data = res.json() or {}
    keys = {'collection': 'collectionRefs', 'sample': 'sampleRefs', 'reaction': 'reactionRefs',
            'research_plan': 'researchPlanRefs'}
    return {kind: [Reference.from_json(r) for r in data.get(key) or []] for kind, key in keys.items()}
