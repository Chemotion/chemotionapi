"""Deleting elements (M0.4) through `DELETE /api/v1/ui_state`, the route the web UI uses.

ELN v4 does not destroy the selection outright: it withdraws it from every collection the user owns
and destroys only records left in no collection. A sample still bound to a reaction or wellplate,
or an element in none of the user's own collections, is kept, so a 200 is not proof that everything
went. The answer's `selecteds` is meant to say what was kept, but ELN main returns built-in elements
there even after destroying them, so the client reloads each element afterwards instead: 404 means
gone, 200 means kept.
"""
import json

import pytest

from chemotion_api.collection import Collection
from chemotion_api.elements.abstract_element import AbstractElement, delete_elements


class _Res:
    def __init__(self, status, payload=None, text="nope"):
        self.status_code, self._payload, self.text = status, payload, text
        self.content = json.dumps(payload).encode() if payload is not None else b""

    def json(self):
        return self._payload


class _Session:
    """DELETE answers from ``responses``; the follow-up GETs answer 200 for ids in ``kept``
    (``(url, id)`` is matched on the id in the URL), 404 for everything else."""

    def __init__(self, *responses, kept=(), get_status=None):
        self._responses, self.calls, self.gets = list(responses), [], []
        self._kept, self._get_status = set(kept), get_status

    def delete(self, url, data=None, **kwargs):
        self.calls.append((url, json.loads(data), kwargs.get("headers")))
        return self._responses.pop(0) if self._responses else _Res(200, {"selecteds": []})

    def get(self, url, **kwargs):
        self.gets.append(url)
        if self._get_status is not None:
            return _Res(self._get_status)
        return _Res(200, {}) if url in self._kept else _Res(404, {"error": "404 Not Found"})

    @staticmethod
    def get_json_session_header():
        return {"Content-Type": "application/json"}


class _Plain:
    """Just enough element for delete_elements: id, kind, saved state, session."""

    def __init__(self, kind, elem_id, session=None, is_new=False):
        self.element_type, self.id, self.is_new, self._session = kind, elem_id, is_new, session

    delete = AbstractElement.delete


def _collection(session, col_id=11):
    col = Collection.__new__(Collection)
    col._id, col.label = col_id, "Source"
    root = type("_Root", (), {"_session": session})()
    col.get_root = lambda: root
    return col


def test_one_request_names_every_element_by_id_and_kind():
    session = _Session()
    kept = delete_elements(session, [_Plain("sample", 1), _Plain("sample", 2), _Plain("reaction", 7),
                                     _Plain("my_generic", 9)])
    assert kept == []
    (url, body, headers), = session.calls
    assert url == "/api/v1/ui_state"
    assert headers == {"Content-Type": "application/json"}
    assert body["sample"] == {"checkedAll": False, "checkedIds": [1, 2]}
    assert body["reaction"] == {"checkedAll": False, "checkedIds": [7]}
    assert body["my_generic"] == {"checkedAll": False, "checkedIds": [9]}  # generic: its klass name
    assert body["selecteds"] == [{"type": "sample", "id": 1}, {"type": "sample", "id": 2},
                                 {"type": "reaction", "id": 7}, {"type": "my_generic", "id": 9}]


def test_checked_all_is_never_sent():
    session = _Session()
    delete_elements(session, [_Plain("sample", 1)])
    (_, body, _), = session.calls
    assert all(sel["checkedAll"] is False for key, sel in body.items()
               if isinstance(sel, dict) and "checkedIds" in sel)


def test_without_a_collection_the_selection_is_made_in_all():
    session = _Session()
    delete_elements(session, [_Plain("sample", 1)])
    (_, body, _), = session.calls
    assert body["currentCollection"] == {}  # the server reads a missing id as the user's "All"


def test_a_collection_scopes_the_selection():
    session = _Session()
    _collection(session, 11).delete_elements(_Plain("sample", 1))
    (_, body, _), = session.calls
    assert body["currentCollection"] == {"id": 11}


@pytest.mark.parametrize("flag", [False, True])
def test_delete_subsamples_is_passed_through(flag):
    session = _Session()
    delete_elements(session, [_Plain("reaction", 7)], delete_subsamples=flag)
    (_, body, _), = session.calls
    assert body["options"] == {"deleteSubsamples": flag}


def test_elements_that_still_load_afterwards_are_returned_as_kept():
    a, b, c = _Plain("sample", 1), _Plain("sample", 2), _Plain("reaction", 7)
    session = _Session(kept={"/api/v1/samples/2.json"})
    assert delete_elements(session, [a, b, c]) == [b]
    assert session.gets == ["/api/v1/samples/1.json", "/api/v1/samples/2.json", "/api/v1/reactions/7.json"]


def test_kept_is_decided_per_kind_and_id():
    """A sample and a reaction can share an id; keeping one must not report the other."""
    sample, reaction = _Plain("sample", 5), _Plain("reaction", 5)
    session = _Session(kept={"/api/v1/reactions/5.json"})
    assert delete_elements(session, [sample, reaction]) == [reaction]


def test_the_selecteds_echo_is_not_trusted():
    """ELN main echoes destroyed built-in elements back in `selecteds`; only the reload counts."""
    session = _Session(_Res(200, {"selecteds": [{"type": "sample", "id": 1}]}))
    assert delete_elements(session, [_Plain("sample", 1)]) == []


def test_generic_elements_are_checked_on_the_generic_route():
    session = _Session(kept={"/api/v1/generic_elements/9.json"})
    g = _Plain("my_generic", 9)
    assert delete_elements(session, [g]) == [g]


@pytest.mark.parametrize("status", [401, 403])
def test_an_element_you_can_no_longer_read_is_gone_from_your_view(status):
    assert delete_elements(_Session(get_status=status), [_Plain("sample", 1)]) == []


def test_a_failing_check_says_the_delete_already_happened():
    with pytest.raises(ConnectionError, match="delete request was accepted"):
        delete_elements(_Session(get_status=500), [_Plain("sample", 1)])


def test_a_204_with_everything_gone_keeps_nothing():
    assert delete_elements(_Session(_Res(204)), [_Plain("sample", 1)]) == []


@pytest.mark.parametrize("elements, match", [
    ([], "No elements"),
    ([_Plain("sample", None)], "not been saved"),
    ([_Plain("sample", 3, is_new=True)], "not been saved"),
])
def test_nothing_is_sent_for_an_empty_or_unsaved_selection(elements, match):
    session = _Session()
    with pytest.raises(ValueError, match=match):
        delete_elements(session, elements)
    assert session.calls == [] and session.gets == []


@pytest.mark.parametrize("status, error", [(403, PermissionError), (404, ValueError), (500, ConnectionError)])
def test_errors_are_raised_not_swallowed(status, error):
    with pytest.raises(error):
        delete_elements(_Session(_Res(status, text="boom")), [_Plain("sample", 1)])


def test_element_delete_reports_whether_it_went():
    assert _Plain("sample", 1, _Session()).delete() is True
    assert _Plain("sample", 1, _Session(kept={"/api/v1/samples/1.json"})).delete() is False


def test_a_collection_that_cannot_hold_elements_refuses():
    with pytest.raises(ValueError, match="cannot hold elements"):
        _collection(_Session(), col_id=None).delete_elements(_Plain("sample", 1))
