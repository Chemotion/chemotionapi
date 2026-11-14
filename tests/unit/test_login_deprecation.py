"""Password login is deprecated in favour of API tokens (2026-11-13).

``Instance.login`` and ``Instance(url, username=..., password=...)`` still log in, but issue a
``FutureWarning`` pointing at the token route; ``Instance(url, token=...)`` and ``login_token`` do
not warn.
"""
import warnings

import pytest

from chemotion_api import Instance, PASSWORD_LOGIN_DEPRECATED
from chemotion_api.connection import Connection
from tests.unit.test_version_guard import _GatedConnection, _instance


class _PingableConnection(_GatedConnection, Connection):
    """A ``Connection`` (so ``Instance`` takes it as one) that serves /about, the ping
    ``test_connection`` sends, and records POSTs. ``Connection.__init__`` is skipped: no network."""

    def __init__(self, version):
        _GatedConnection.__init__(self, version)

    def get(self, **kwargs):
        return type("R", (), {"status_code": 204})()


def test_login_warns_and_still_logs_in():
    con = _GatedConnection("v4.0.1")
    with pytest.warns(FutureWarning, match="login_token") as record:
        _instance(con).login("user", "secret")
    assert len(record) == 1
    assert record[0].filename == __file__, "the warning must name the caller's line, not ours"
    assert con.token == "t" and len(con.posts) == 1


def test_constructor_with_password_warns_once_and_logs_in():
    con = _PingableConnection("v4.0.1")
    with pytest.warns(FutureWarning) as record:
        Instance(con, username="user", password="secret")
    assert [str(w.message) for w in record] == [PASSWORD_LOGIN_DEPRECATED]
    assert record[0].filename == __file__
    assert con.token == "t"


def test_constructor_with_token_logs_in_without_a_warning():
    con = _PingableConnection("v4.0.1")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        Instance(con, token="chemtoken_abc")
    assert con.token == "chemtoken_abc" and con.posts == []


def test_login_token_does_not_warn():
    con = _GatedConnection("v4.0.1")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        _instance(con).login_token("chemtoken_abc")
    assert con.token == "chemtoken_abc"


def test_constructor_refuses_a_token_together_with_a_password():
    con = _PingableConnection("v4.0.1")
    with pytest.raises(ValueError):
        Instance(con, username="user", password="secret", token="chemtoken_abc")
    assert con.posts == [] and not hasattr(con, "token")
