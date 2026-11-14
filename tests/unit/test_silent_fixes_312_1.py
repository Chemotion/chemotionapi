"""Four bugs that gave wrong results without an error, ported from the 401 line for 312.1.

Each test drives the real code path with a stand-in for the server.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from chemotion_api.commands import InstanceManager
from chemotion_api.elements import ElementSet
from chemotion_api.inbox import Inbox


# --- CLI: image lookup -------------------------------------------------------------------------

def _hub(*pages):
    return [MagicMock(status_code=200, json=MagicMock(return_value=p)) for p in pages]


def test_image_versions_match_exactly_follow_pages_and_keep_hyphenated_services():
    pages = ({'results': [{'name': 'eln-1.1.2'}, {'name': 'db-1.1.2'}], 'next': 'page2'},
             {'results': [{'name': 'eln-1.2'}, {'name': 'ketchersvc-sc-1.2'}], 'next': None})
    with patch('chemotion_api.commands.requests.get', side_effect=_hub(*pages)) as get:
        images = InstanceManager.get_image_of_versions('1.2')
    assert images == {'eln': 'ptrxyz/chemotion:eln-1.2', 'ketchersvc-sc': 'ptrxyz/chemotion:ketchersvc-sc-1.2'}
    assert get.call_args.kwargs.get('timeout'), 'a hung registry must not hang the CLI'


def test_no_eln_tag_raises_a_clear_error():
    with patch('chemotion_api.commands.requests.get', side_effect=_hub({'results': [{'name': 'db-1.2'}], 'next': None})):
        with pytest.raises(LookupError, match='eln-'):
            InstanceManager.get_image_of_versions()


# --- CLI: insert-dataset -----------------------------------------------------------------------

def _ols(label="Bob's spectroscopy", definition="ends with '); DROP TABLE dataset_klasses; --"):
    return MagicMock(status_code=200, json=MagicMock(return_value={
        'curie': 'CHMO:0000595', 'label': label, 'definition': {'value': definition}}))


def test_insert_dataset_keeps_ontology_text_out_of_the_sql():
    with patch('chemotion_api.commands.requests.get', return_value=_ols()), \
            patch('chemotion_api.commands.subprocess.Popen') as popen:
        popen.return_value.communicate.return_value = ('', '')
        popen.return_value.returncode = 0
        InstanceManager.insert_dataset('CHMO:0000595')
    command = popen.call_args.args[0]
    sql = popen.return_value.communicate.call_args.args[0]
    assert '-c' not in command and 'ON_ERROR_STOP=1' in command
    assert "Bob's" not in sql and 'DROP TABLE' not in sql
    assert "label=Bob's spectroscopy" in command and ":'label'" in sql


def test_insert_dataset_raises_when_psql_fails():
    with patch('chemotion_api.commands.requests.get', return_value=_ols('x', 'y')), \
            patch('chemotion_api.commands.subprocess.Popen') as popen:
        popen.return_value.communicate.return_value = ('', 'ERROR:  relation does not exist')
        popen.return_value.returncode = 3
        with pytest.raises(ChildProcessError, match='relation does not exist'):
            InstanceManager.insert_dataset('CHMO:0000595')


# --- Inbox -------------------------------------------------------------------------------------

@pytest.mark.parametrize('count, pages', [(0, 1), (19, 1), (20, 1), (21, 2), (40, 2), (41, 3)])
def test_inbox_requests_only_the_pages_that_exist(count, pages):
    requested = []

    def get(url, **kw):
        requested.append(url)
        return SimpleNamespace(status_code=200, json=lambda: {'inbox': {
            'count': count, 'children': [], 'unlinked_attachments': []}})

    Inbox(SimpleNamespace(get=get)).load()
    assert len(requested) == pages, 'a page past the end comes back as page 1, duplicating every box'


# --- ElementSet.page ---------------------------------------------------------------------------

class _Server:
    """`total` samples, two per page; an out-of-range page is answered with page 1, as the ELN does."""

    def __init__(self, total=6):
        self.total, self.pages_requested = total, []

    def get(self, url, data=None, **kw):
        n_pages = -(-self.total // 2)
        page = data['page'] if data['page'] <= n_pages else 1
        self.pages_requested.append(data['page'])
        rows = [{'id': i, 'type': 'sample', 'short_label': f'S-{i}', 'name': f's{i}'}
                for i in range(2 * page - 1, min(2 * page, self.total) + 1)]
        return SimpleNamespace(status_code=200, headers={'X-Total-Pages': str(n_pages), 'X-Total': str(self.total)},
                               json=lambda: {'samples': rows})


def _set(monkeypatch, total=6):
    server = _Server(total)
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


@pytest.mark.parametrize('page', [4, 0, -1, 'two'])
def test_a_page_that_does_not_exist_raises(monkeypatch, page):
    es, _ = _set(monkeypatch)
    with pytest.raises(IndexError):
        es.page = page


def test_page_one_of_an_empty_collection_is_not_an_error(monkeypatch):
    es, server = _set(monkeypatch, total=0)
    es.page = 1
    es.page = 1
    assert len(server.pages_requested) == 2 and list(list.__iter__(es)) == []
