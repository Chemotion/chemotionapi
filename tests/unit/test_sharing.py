"""Slice 9 / V6: sharing discloses as much as the caller says, and can be revoked."""
import types

import pytest

from chemotion_api.collection import Collection, CollectionSharePermission


class _User:
    def __init__(self, uid):
        self.id = uid

    def is_group(self):
        return False

    def is_person(self):
        return True


def _collection(responses):
    """A Collection whose root hands back a recording session."""
    calls = []

    def _post(url, **kwargs):
        calls.append(("POST", url, kwargs))
        return responses.pop(0)

    def _get(url, **kwargs):
        calls.append(("GET", url, kwargs))
        return responses.pop(0)

    def _delete(url, **kwargs):
        calls.append(("DELETE", url, kwargs))
        return responses.pop(0)

    col = Collection()
    col.id = 7
    session = types.SimpleNamespace(post=_post, get=_get, delete=_delete)
    col.get_root = lambda: types.SimpleNamespace(_session=session)
    return col, calls


def test_share_requires_an_explicit_detail_level():
    """There is no defensible default: the only obvious one (10) discloses every field."""
    col, _ = _collection([])
    with pytest.raises(TypeError, match="detail_level"):
        col.share(CollectionSharePermission.ReadElements, _User(1))


@pytest.mark.parametrize("bad", [-1, 11, 1.5, "10", None, True])
def test_share_rejects_a_detail_level_outside_the_range(bad):
    col, _ = _collection([])
    with pytest.raises(ValueError, match="detail_level must be an integer from 0"):
        col.share(CollectionSharePermission.ReadElements, _User(1), detail_level=bad)


#: The nine element types `collection_share_api.rb` declares, written out literally. Asserting
#: against `SHARE_DETAIL_LEVEL_TYPES` instead would pass even if a key were misspelled or a type
#: dropped — and Grape silently ignores an undeclared param, so the share would under-disclose.
SERVER_DETAIL_LEVEL_TYPES = (
    "celllinesample", "devicedescription", "element", "reaction", "researchplan",
    "sample", "screen", "sequencebasedmacromoleculesample", "wellplate",
)


def test_the_client_knows_exactly_the_types_the_server_declares():
    from chemotion_api.collection import SHARE_DETAIL_LEVEL_TYPES

    assert sorted(SHARE_DETAIL_LEVEL_TYPES) == sorted(SERVER_DETAIL_LEVEL_TYPES)


def test_share_applies_the_chosen_level_to_all_nine_types():
    col, calls = _collection([types.SimpleNamespace(status_code=201, text="")])
    col.share(CollectionSharePermission.ReadElements, _User(1), _User(2), detail_level=3)
    _, url, kwargs = calls[0]
    assert url == "/api/v1/collection_shares"
    assert kwargs["data"]["user_ids"] == [1, 2]
    for element_type in SERVER_DETAIL_LEVEL_TYPES:
        assert kwargs["data"][f"{element_type}_detail_level"] == 3, element_type


def _shares_response(*ids_and_users):
    return types.SimpleNamespace(
        status_code=200,
        json=lambda: {"collection_shares": [
            {"id": sid, "shared_with_id": uid} for sid, uid in ids_and_users]})


def test_unshare_revokes_only_the_named_users():
    """v4 deletes by *share* id, not by collection+user, so the shares are listed and matched."""
    col, calls = _collection([
        _shares_response((11, 1), (12, 2), (13, 3)),
        types.SimpleNamespace(status_code=204, text=""),
    ])
    assert col.unshare(_User(2)) == 1
    assert [c[0] for c in calls] == ["GET", "DELETE"]
    assert calls[1][1] == "/api/v1/collection_shares/12"


def test_unshare_all_revokes_everything():
    col, calls = _collection([
        _shares_response((11, 1), (12, 2)),
        types.SimpleNamespace(status_code=204, text=""),
        types.SimpleNamespace(status_code=204, text=""),
    ])
    assert col.unshare(all=True) == 2
    assert [c[1] for c in calls if c[0] == "DELETE"] == [
        "/api/v1/collection_shares/11", "/api/v1/collection_shares/12"]


def test_unshare_treats_an_already_gone_share_as_revoked():
    col, _ = _collection([
        _shares_response((11, 1)),
        types.SimpleNamespace(status_code=404, text="not found"),
    ])
    assert col.unshare(all=True) == 1


def test_unshare_raises_on_a_real_failure():
    col, _ = _collection([
        _shares_response((11, 1)),
        types.SimpleNamespace(status_code=403, text="Forbidden"),
    ])
    with pytest.raises(ConnectionError, match="403"):
        col.unshare(all=True)


def test_dead_sharing_attributes_are_gone():
    """They were never assigned, so they read as None whether or not a collection was shared."""
    col = Collection()
    for gone in ("is_shared", "is_synchronized", "sample_detail_level",
                 "reaction_detail_level", "screen_detail_level",
                 "wellplate_detail_level", "element_detail_level"):
        assert not hasattr(col, gone), f"{gone} should have been removed"


# --- server fields that set_json was silently discarding -------------------

def test_set_json_captures_the_fields_the_server_actually_sends():
    """`set_json` assigns a key only `if hasattr(self, key)`, so an undeclared attribute silently
    discards data the server did send — including `shared`, the real sharing flag."""
    col = Collection()
    col.set_json({
        "id": 1, "label": "L", "ancestry": "1/2", "position": 3, "is_locked": False,
        "tabs_segment": {"a": 1}, "inventory_id": 7, "inventory_name": "Inv",
        "inventory_prefix": "INV", "shared": True,
    })
    assert col.shared is True
    assert (col.ancestry, col.position, col.inventory_prefix) == ("1/2", 3, "INV")
    assert col.tabs_segment == {"a": 1} and col.inventory_id == 7


def test_set_json_captures_the_shared_with_me_fields():
    col = Collection()
    col.set_json({"id": 2, "label": "S", "permission_level": 3, "owner": "Ada L. (AL)",
                  "owner_name": "Ada Lovelace", "collection_share_id": 9,
                  "shared_via_group": True})
    assert col.permission_level == 3
    assert (col.owner, col.owner_name) == ("Ada L. (AL)", "Ada Lovelace")
    assert col.collection_share_id == 9 and col.shared_via_group is True


def test_sync_collections_users_is_gone():
    """v4 has no sync_collections_users table at all — the attribute was always None."""
    assert not hasattr(Collection(), "sync_collections_users")


def test_share_refuses_a_target_that_is_neither_a_person_nor_a_group():
    """Filtering silently turned a mistake into a share that reached fewer people than asked."""
    class _Device:
        id = 4

        def is_group(self):
            return False

        def is_person(self):
            return False

    col, _ = _collection([])
    with pytest.raises(ValueError, match="takes people and groups"):
        col.share(CollectionSharePermission.ReadElements, _Device(), detail_level=1)


def test_share_refuses_an_empty_target_list():
    col, _ = _collection([])
    with pytest.raises(ValueError, match="at least one person or group"):
        col.share(CollectionSharePermission.ReadElements, detail_level=1)


# ------------------------------------------------------------------ update_share (ELN v4.0.0)

def _collection_with_session(session):
    """A Collection whose get_root() yields a stub session, with no server behind it."""
    from chemotion_api.collection import Collection
    col = Collection.__new__(Collection)
    col._id = 11
    root = type("_Root", (), {"_session": session})()
    col.get_root = lambda: root
    return col


class _RecordingSession:
    def __init__(self, status=200, body=b'{"ok": true}'):
        self.calls = []
        self._status, self._body = status, body

    def put(self, url, data=None, **kwargs):
        self.calls.append((url, data))
        return type("_Res", (), {"status_code": self._status, "text": self._body.decode(),
                                 "content": self._body, "json": lambda self=None: {"ok": True}})()


def test_update_share_sends_the_cascade_flags():
    session = _RecordingSession()
    _collection_with_session(session).update_share(
        7, detail_level=3, apply_to_subcollections=True, include_new_subcollections=True)
    url, data = session.calls[0]
    assert url == "/api/v1/collection_shares/7"
    assert data["apply_to_subcollections"] is True
    assert data["include_new_subcollections"] is True
    assert data["sample_detail_level"] == 3


def test_include_new_subcollections_without_a_cascade_is_refused():
    """The server would ignore it silently — the caller would believe access widened when it did
    not. Better to refuse than to no-op."""
    session = _RecordingSession()
    with pytest.raises(ValueError, match="only applies while cascading"):
        _collection_with_session(session).update_share(7, include_new_subcollections=True)
    assert session.calls == []


def test_update_share_omits_what_it_was_not_asked_to_change():
    """The server declares params with include_missing: false, so a field we do not send is left
    alone. Sending None would reset it."""
    session = _RecordingSession()
    _collection_with_session(session).update_share(7)
    _, data = session.calls[0]
    assert "permission_level" not in data
    assert not any(k.endswith("_detail_level") for k in data)


@pytest.mark.parametrize("bad", [-1, 11, True, "5", 2.5])
def test_update_share_rejects_an_out_of_range_detail_level(bad):
    session = _RecordingSession()
    with pytest.raises(ValueError, match="detail_level"):
        _collection_with_session(session).update_share(7, detail_level=bad)
    assert session.calls == []


@pytest.mark.parametrize("status, exc", [(401, PermissionError), (404, ValueError),
                                         (422, ValueError), (500, ConnectionError)])
def test_update_share_maps_the_documented_failures(status, exc):
    session = _RecordingSession(status=status, body=b"nope")
    with pytest.raises(exc):
        _collection_with_session(session).update_share(7, detail_level=1)


def test_unshare_with_no_users_refuses_instead_of_revoking_everything():
    """`col.unshare(*to_remove)` with an empty list must not mean "revoke everyone".

    An empty list is an ordinary result of filtering, and `share()` already refuses one. The
    destructive inverse should be at least as hard to trigger by accident.
    """
    col, calls = _collection([])
    with pytest.raises(ValueError, match=r'unshare\(all=True\)'):
        col.unshare()
    assert [c for c in calls if c[0] == "DELETE"] == []


def test_unshare_rejects_users_and_all_together():
    col, _ = _collection([])
    with pytest.raises(ValueError, match="not both"):
        col.unshare(_User(2), all=True)
