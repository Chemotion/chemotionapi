"""ElementSet.page = n: works before the first load, and refuses a page that does not exist.

Before 401.0 the setter compared n with max_page, which is 1 until something has loaded, so
`page = 5` on a fresh set was ignored — silently. A downstream app (ChemAssistent) set the private
`_page` to get around it.
"""
from types import SimpleNamespace

import pytest

from chemotion_api.elements import ElementSet


class _Server:
    """Six samples, two per page; an out-of-range page is answered with page 1, as the ELN does."""

    def __init__(self):
        self.pages_requested = []

    def get(self, url, data=None, **kw):
        page = data['page'] if data['page'] <= 3 else 1
        self.pages_requested.append(data['page'])
        rows = [{'id': i, 'type': 'sample', 'short_label': f'S-{i}', 'name': f's{i}'}
                for i in range(2 * page - 1, 2 * page + 1)]
        return SimpleNamespace(status_code=200, headers={'X-Total-Pages': '3', 'X-Total': '6'},
                               json=lambda: {'samples': rows})


def _set(monkeypatch):
    server = _Server()
    monkeypatch.setattr('chemotion_api.elements.GenericSegments', lambda session: SimpleNamespace(all_classes=[]))
    monkeypatch.setattr(ElementSet, '_get_element_class',
                        lambda self: lambda seg, ses, json_data: SimpleNamespace(
                            json_data=json_data, id=json_data['id'], mark_partial=lambda: None))
    es = ElementSet(server, {'name': 'sample', 'is_generic': False, 'label': 'Sample'}, 7)
    es._per_page = 2
    return es, server


def test_jumping_to_a_page_before_anything_is_loaded(monkeypatch):
    es, server = _set(monkeypatch)
    es.page = 3
    assert server.pages_requested == [3]
    assert [e.id for e in list.__iter__(es)] == [5, 6]
    assert es.page == 3 and es.max_page == 3


@pytest.mark.parametrize("page", [4, 0, -1, 'two'])
def test_a_page_that_does_not_exist_raises(monkeypatch, page):
    es, _ = _set(monkeypatch)
    with pytest.raises(IndexError):
        es.page = page


def test_a_known_out_of_range_page_raises_without_a_request(monkeypatch):
    es, server = _set(monkeypatch)
    es.page = 1
    with pytest.raises(IndexError):
        es.page = 9
    assert server.pages_requested == [1]
