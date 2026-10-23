from types import SimpleNamespace

import pytest
from requests.exceptions import RequestException

from chemotion_api.connection import ChemotionRequestError, ChemotionServerError, request_error
from chemotion_api.elements import ElementSet
from chemotion_api.utils.solvent_manager import get_solvent_info


def _response(status_code, text, headers=None):
    return SimpleNamespace(status_code=status_code, text=text, headers=headers or {}, url='http://eln/x',
                           request=SimpleNamespace(method='POST', url='http://eln/api/v1/samples'))


def test_server_error_reports_title_and_request():
    html = '<!DOCTYPE html><html><head><title>We\'re sorry, but something went wrong (500)</title></head></html>'
    error = request_error(_response(500, html), 'saving sample (new)')
    assert isinstance(error, ChemotionServerError) and isinstance(error, RequestException)
    assert str(error) == ("500 -> We're sorry, but something went wrong (500) "
                          "[POST http://eln/api/v1/samples] (saving sample (new))")


def test_client_error_keeps_json_body():
    error = request_error(_response(400, '{"error":"name is missing"}'))
    assert type(error) is ChemotionRequestError
    assert error.status_code == 400 and error.snippet == '{"error":"name is missing"}'


def test_unknown_solvent_suggests_names():
    with pytest.raises(KeyError, match=r'Solvent "Piperidine" is not available.*"Pyridine"'):
        get_solvent_info('Piperidine')
    with pytest.raises(KeyError, match=r'"Tetrahydrofuran \(THF\)"'):
        get_solvent_info('THF')
    assert get_solvent_info('Pyridine')['smiles']


class _ListSession:
    def get(self, url, data):
        page = data['page']
        samples = [{'id': i, 'type': 'sample'} for i in range((page - 1) * 2, min(page * 2, 3))]
        return SimpleNamespace(status_code=200, headers={'X-Total-Pages': '2', 'X-Total': '3'},
                               json=lambda: {'samples': samples})


def test_element_set_length_is_total_not_page_size(monkeypatch):
    elements = ElementSet(_ListSession(), {'name': 'sample', 'is_generic': False}, collection_id=1)
    monkeypatch.setattr(elements, '_get_element_class',
                        lambda: lambda segments, session, json_data: SimpleNamespace(
                            mark_partial=lambda: None, id=json_data['id']))
    monkeypatch.setattr('chemotion_api.elements.GenericSegments', lambda session: None)
    elements.load_elements(per_page=2)
    assert len(elements) == 3
    assert [e.id for e in elements] == [0, 1, 2]
