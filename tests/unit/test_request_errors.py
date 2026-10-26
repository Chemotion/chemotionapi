"""Richer errors for a rejected request, ported from version-3 (PR #6).

The old message was `f'{status} -> {text}'`. When the server returns an HTML error page — which
Rails does for a 500 — that put tens of kilobytes of markup into the traceback and told you
neither which request failed nor what it was doing.

One deliberate deviation from the original: these also inherit the **builtin** `ConnectionError`.
This client has always raised that, so a straight port would have broken every `except
ConnectionError` our users have written.
"""
import pytest
import requests

from chemotion_api.connection import (
    ChemotionRequestError, ChemotionServerError, request_error)


def _response(status, text, method="PUT", url="https://eln.example.org/api/v1/samples/12"):
    res = requests.Response()
    res.status_code = status
    res._content = text.encode()
    req = requests.Request(method=method, url=url).prepare()
    res.request = req
    res.url = url
    return res


def test_existing_handlers_still_catch_it():
    """The whole point of the deviation: `except ConnectionError` must keep working."""
    assert issubclass(ChemotionRequestError, ConnectionError)
    assert issubclass(ChemotionRequestError, requests.exceptions.RequestException)


def test_an_html_error_page_is_reduced_to_its_title():
    html = "<html><head><title>Something went wrong (500)</title></head><body>" + "x" * 40000
    err = request_error(_response(500, html), context="saving sample 12")
    assert err.snippet == "Something went wrong (500)"
    assert len(str(err)) < 200                       # not 40 KB of markup


def test_an_html_page_without_a_title_still_says_so():
    err = request_error(_response(500, "<html><body>no title here</body></html>"))
    assert err.snippet == "HTML error page"


def test_a_long_plain_body_is_truncated():
    err = request_error(_response(422, "y" * 5000))
    assert err.snippet.endswith("...") and len(err.snippet) < 600


def test_the_message_names_the_request_and_what_it_was_doing():
    err = request_error(_response(422, "nope"), context="saving sample 12")
    text = str(err)
    assert "422" in text and "PUT" in text and "samples/12" in text
    assert "saving sample 12" in text


def test_5xx_is_a_server_error_and_4xx_is_not():
    assert isinstance(request_error(_response(500, "boom")), ChemotionServerError)
    assert isinstance(request_error(_response(503, "boom")), ChemotionServerError)
    err = request_error(_response(404, "gone"))
    assert isinstance(err, ChemotionRequestError) and not isinstance(err, ChemotionServerError)


def test_a_response_with_no_request_attached_does_not_blow_up():
    """Error construction must never raise — it would mask the failure it is reporting."""
    res = requests.Response()
    res.status_code = 500
    res._content = b"boom"
    err = request_error(res)
    assert err.status_code == 500


@pytest.mark.parametrize("status", [400, 401, 404, 422, 500, 503])
def test_every_status_produces_a_usable_message(status):
    assert str(request_error(_response(status, "body")))


# --- kept from the v3 line: coverage the error-machinery tests above do not provide ---

from types import SimpleNamespace  # noqa: E402

from chemotion_api.elements import ElementSet  # noqa: E402
from chemotion_api.utils.solvent_manager import get_solvent_info  # noqa: E402


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
