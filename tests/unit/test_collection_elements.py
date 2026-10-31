"""Moving elements between collections on ELN v4.

Adopted from Martin's version-3 feature (PR #6) but **retargeted**: his implementation calls
`/api/v1/collections/elements`, and all three verbs of that route are removed between v3.1.2 and
v4.0.0. v4 replaces them with `POST /api/v1/collection_elements` and
`DELETE /api/v1/collection_elements/:collection_id`.

Two v4 behaviours drive most of what is asserted here:

* **There is no move endpoint.** A move is POST-then-DELETE, so it is not atomic.
* **DELETE can answer 200, and 200 is not success.** When a sample belongs to a reaction or
  wellplate still in the collection it cannot be removed on its own, and the server reports
  `{"locked_sample_ids": [...]}` rather than 204.
"""
import json

import pytest

from chemotion_api.collection import Collection


class _Res:
    def __init__(self, status, payload=None, text="nope"):
        self.status_code, self._payload, self.text = status, payload, text
        self.content = json.dumps(payload).encode() if payload is not None else b""

    def json(self):
        return self._payload


class _Session:
    def __init__(self, *responses):
        self._responses, self.calls = list(responses), []

    def _next(self):
        return self._responses.pop(0) if self._responses else _Res(204)

    def post(self, url, data=None, **kwargs):
        self.calls.append(("post", url, data))
        return self._next()

    def delete(self, url, data=None, **kwargs):
        self.calls.append(("delete", url, json.loads(data) if isinstance(data, str) else data))
        return self._next()

    @staticmethod
    def get_json_session_header():
        return {"Content-Type": "application/json"}


def _collection(session, col_id=11, label="Source"):
    col = Collection.__new__(Collection)
    col._id = col_id
    col.label = label
    root = type("_Root", (), {"_session": session})()
    col.get_root = lambda: root
    return col


def _element(kind, elem_id):
    return type("_E", (), {"element_type": kind, "id": elem_id, "is_new": False})()


def test_assign_sends_one_request_grouped_by_kind():
    session = _Session(_Res(201, {"status": 204}))
    source, dest = _collection(session), _collection(session, 12, "Dest")
    source.assign_elements(dest, _element("sample", 1), _element("sample", 2),
                           _element("reaction", 7))
    (method, url, data), = session.calls
    assert (method, url) == ("post", "/api/v1/collection_elements")
    assert data["collection_id"] == 12
    assert data["ui_state"]["currentCollection"] == {"id": 11}
    assert data["ui_state"]["sample"]["checkedIds"] == [1, 2]
    assert data["ui_state"]["reaction"]["checkedIds"] == [7]


def test_checked_all_is_never_sent():
    """The server reduces checkedAll to `where.not(id: unchecked_ids)` over the whole element
    class -- not this collection. One request could attach a user's entire sample library."""
    session = _Session(_Res(201, {"status": 204}))
    source, dest = _collection(session), _collection(session, 12)
    source.assign_elements(dest, _element("sample", 1))
    (_, _, data), = session.calls
    assert data["ui_state"]["sample"]["checkedAll"] is False
    assert all(v is not True for k, v in data["ui_state"]["sample"].items())


def test_remove_targets_the_collection_in_the_path():
    session = _Session(_Res(204))
    source = _collection(session)
    assert source.remove_elements(_element("sample", 1)) == []
    (method, url, data), = session.calls
    assert (method, url) == ("delete", "/api/v1/collection_elements/11")
    assert "collection_id" not in data and data["ui_state"]["currentCollection"] == {"id": 11}


def test_a_200_with_locked_samples_is_not_success():
    """The whole reason remove_elements returns a list rather than None."""
    session = _Session(_Res(200, {"locked_sample_ids": [4, 9]}))
    assert _collection(session).remove_elements(_element("sample", 4)) == [4, 9]


def test_move_is_add_then_remove_in_that_order():
    session = _Session(_Res(201, {"status": 204}), _Res(204))
    source, dest = _collection(session), _collection(session, 12, "Dest")
    assert source.move_elements(dest, _element("sample", 1)) == []
    assert [c[0] for c in session.calls] == ["post", "delete"]


def test_a_half_completed_move_reports_what_is_now_in_both(caplog):
    """v4 has no move endpoint. If the removal is refused the elements stay in both collections --
    a valid state, but not what was asked for, so the caller is told rather than left guessing."""
    session = _Session(_Res(201, {"status": 204}), _Res(200, {"locked_sample_ids": [1]}))
    source, dest = _collection(session), _collection(session, 12, "Dest")
    with caplog.at_level("WARNING"):
        assert source.move_elements(dest, _element("sample", 1)) == [1]
    assert "both" in caplog.text


def test_an_unsaved_element_is_refused_before_any_request():
    session = _Session()
    unsaved = type("_E", (), {"element_type": "sample", "id": None, "is_new": True})()
    with pytest.raises(ValueError, match="not been saved"):
        _collection(session).remove_elements(unsaved)
    assert session.calls == []


def test_an_unexercised_kind_is_refused_rather_than_guessed():
    """The server may well accept a wellplate; this client only sends kinds it has exercised."""
    session = _Session()
    with pytest.raises(ValueError, match="not implemented"):
        _collection(session).remove_elements(_element("wellplate", 3))
    assert session.calls == []


def test_no_elements_is_refused():
    session = _Session()
    with pytest.raises(ValueError, match="No elements"):
        _collection(session).remove_elements()
    assert session.calls == []


def test_a_collection_without_an_id_cannot_hold_elements():
    session = _Session()
    col = _collection(session)
    col._id = None
    with pytest.raises(ValueError, match="cannot hold elements"):
        col.remove_elements(_element("sample", 1))


@pytest.mark.parametrize("status, exc", [(403, PermissionError), (404, ValueError),
                                         (500, ConnectionError)])
def test_failures_map_to_documented_exceptions(status, exc):
    session = _Session(_Res(status))
    with pytest.raises(exc):
        _collection(session).remove_elements(_element("sample", 1))


def test_a_failed_removal_still_tells_you_the_addition_happened():
    """The exception from the DELETE says "forbidden"; it does not say the elements are now in
    both collections, which is the one thing the caller cannot infer. Without this they would
    read a raised move as "nothing changed"."""
    session = _Session(_Res(201, {"status": 204}), _Res(403))
    source, dest = _collection(session), _collection(session, 12, "Dest")
    with pytest.raises(PermissionError, match="both collections"):
        source.move_elements(dest, _element("sample", 1))
    assert [c[0] for c in session.calls] == ["post", "delete"]


def test_the_failed_move_message_names_both_collections():
    session = _Session(_Res(201, {"status": 204}), _Res(500))
    source, dest = _collection(session, 11, "Source"), _collection(session, 12, "Dest")
    with pytest.raises(ConnectionError) as excinfo:
        source.move_elements(dest, _element("sample", 1))
    assert "Dest" in str(excinfo.value) and "Source" in str(excinfo.value)
