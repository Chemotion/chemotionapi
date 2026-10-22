"""
Ontology terms of template fields. Chemotion (LabIMotion) links a field to a term of the TIB Terminology
Service (NFDI4Chem collection) and stores the term in the field as ``ontology``. The functions here search
the same service as the Chemotion UI.
"""
import requests

TERMINOLOGY_SERVICE_URL = 'https://api.terminology.tib.eu/api'
COLLECTION = 'NFDI4CHEM'
TERM_KEYS = ('id', 'iri', 'label', 'short_form', 'obo_id', 'ontology_name', 'ontology_prefix', 'description', 'type')


def search_terms(query: str, rows: int = 30, url: str = TERMINOLOGY_SERVICE_URL, timeout: float = 30) -> list[dict]:
    """
    Searches ontology terms like the term selection of the Chemotion template designer.

    >>> search_terms('nuclear magnetic resonance spectroscopy')[0]['obo_id']

    :param query: search text or term ID, at least 2 characters
    :param rows: maximum number of results
    :param url: base URL of the terminology service
    :param timeout: request timeout in seconds
    :return: the terms (dicts with the keys of TERM_KEYS) in the order of the service's ranking

    :raises ConnectionError: if the service does not answer successfully
    """
    if not isinstance(query, str) or len(query.strip()) < 2:
        raise ValueError('query must have at least 2 characters')
    params = [('q', query.strip()), ('caller', COLLECTION), ('rows', str(rows)), ('schema', 'collection'),
              ('type', 'class'), ('type', 'property'), ('obsoletes', 'false'), ('local', 'false'),
              ('fieldList', ','.join(TERM_KEYS))]
    try:
        res = requests.get(f'{url}/select', params=params, timeout=timeout)
    except requests.RequestException as e:
        raise ConnectionError(f'Terminology service not reachable: {e}') from e
    if res.status_code != 200:
        raise ConnectionError(f'{res.status_code} -> {res.text}')
    return [clean_term(doc) for doc in res.json().get('response', {}).get('docs', [])]


def get_term(term_id: str, url: str = TERMINOLOGY_SERVICE_URL, timeout: float = 30) -> dict:
    """
    Looks up one ontology term by its ID.

    >>> get_term('CHMO:0000593')['label']
    '1H nuclear magnetic resonance spectroscopy'

    :param term_id: OBO ID ('CHMO:0000593'), short form ('CHMO_0000593') or IRI of the term. If the term is
        part of several ontologies, the one of its own ontology (prefix 'CHMO') is returned
    :param url: base URL of the terminology service
    :param timeout: request timeout in seconds
    :return: the term

    :raises KeyError: if no term has this ID
    """
    term_id = term_id.strip()
    is_iri = term_id.startswith(('http://', 'https://'))
    query = term_id.rstrip('/').rsplit('/', 1)[-1].rsplit('#', 1)[-1] if is_iri else term_id
    candidates = [doc for doc in search_terms(query, rows=100, url=url, timeout=timeout)
                  if (doc.get('iri') == term_id if is_iri else
                      term_id.upper() in (str(doc.get('obo_id')).upper(), str(doc.get('short_form')).upper()))]
    if len(candidates) == 0:
        raise KeyError(f'No ontology term found for "{term_id}"')
    prefix = (candidates[0].get('obo_id') or '').split(':')[0].upper()
    return next((doc for doc in candidates if str(doc.get('ontology_prefix')).upper() == prefix), candidates[0])


def clean_term(term: dict) -> dict:
    """
    Checks an ontology term and returns it with only the keys Chemotion stores.

    :raises TypeError: if the term is not a dict or has no 'iri'
    """
    if not isinstance(term, dict):
        raise TypeError(f'ontology term {type(term)} not supported')
    if not isinstance(term.get('iri'), str) or term['iri'] == '':
        raise TypeError("an ontology term needs an 'iri'")
    return {key: term[key] for key in TERM_KEYS if term.get(key) is not None}
