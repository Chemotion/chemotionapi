"""Transport behaviour of :class:`Connection`: where credentials may go, and what may be retried.

Both rules exist because a downstream consumer (`chemotion-sample-manager`) had to subclass
`Connection` and override the private `_send_request` to get them. These tests pin the behaviour
offline so it cannot regress without a live server noticing.
"""
import pytest
from requests.exceptions import ConnectionError as CError

from chemotion_api.connection import Connection


def _conn(**kwargs):
    return Connection('https://eln.example.org', **kwargs)


# --- where credentials may go -------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "https://eln.example.org/api/v1/samples",   # same origin
    "/api/v1/samples",                          # relative — gets the host prefixed
    "api/v1/samples",
])
def test_same_origin_and_relative_urls_are_allowed(url):
    _conn()._assert_same_origin(url)


@pytest.mark.parametrize("url", [
    "https://evil.example.com/api/v1/samples",          # different host
    "http://eln.example.org/api/v1/samples",            # downgraded scheme
    "https://eln.example.org.evil.com/api/v1/samples",  # suffix that merely looks like ours
])
def test_a_foreign_url_is_refused(url):
    """Every request carries the bearer token, so a foreign host would be handed the session.

    The third case is the one a naive `startswith` check lets through.
    """
    with pytest.raises(ConnectionError, match="Refusing to send credentials"):
        _conn()._assert_same_origin(url)


# --- what may be retried ------------------------------------------------------------------

class _Boom:
    """Stands in for `requests.Session`, counting calls and raising a transport error."""

    def __init__(self, fail_times: int):
        self.fail_times, self.calls = fail_times, 0

    def __call__(self, **kwargs):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise CError("connection reset")
        return type("R", (), {"headers": {}, "status_code": 200})()


def _send(conn, method, boom):
    import unittest.mock as mock
    with mock.patch.object(type(conn).__mro__[1], method, boom, create=True):
        return conn._send_request(method, '/api/v1/samples', {}, {})


def test_a_read_is_retried_and_can_succeed(monkeypatch):
    monkeypatch.setattr('chemotion_api.connection.time.sleep', lambda _: None)
    conn, boom = _conn(retries=3), _Boom(fail_times=2)
    _send(conn, 'get', boom)
    assert boom.calls == 3, "a GET should be attempted up to `retries` times"


def test_a_read_gives_up_after_the_configured_attempts(monkeypatch):
    monkeypatch.setattr('chemotion_api.connection.time.sleep', lambda _: None)
    conn, boom = _conn(retries=3), _Boom(fail_times=99)
    with pytest.raises(ConnectionError, match="after 3 attempts"):
        _send(conn, 'get', boom)
    assert boom.calls == 3


def test_a_write_is_never_retried(monkeypatch):
    """A POST the server may already have applied must not be sent twice.

    The caller is told the write's fate is unknown rather than having it silently duplicated.
    """
    monkeypatch.setattr('chemotion_api.connection.time.sleep', lambda _: None)
    conn, boom = _conn(retries=3), _Boom(fail_times=99)
    with pytest.raises(ConnectionError, match="was not retried"):
        _send(conn, 'post', boom)
    assert boom.calls == 1, "a write must be attempted exactly once"


def test_a_failed_write_does_not_sleep_before_raising(monkeypatch):
    """It is never retried, so a backoff pause before failing is pure latency."""
    slept = []
    monkeypatch.setattr('chemotion_api.connection.time.sleep', slept.append)
    with pytest.raises(ConnectionError):
        _send(_conn(retries=3), 'post', _Boom(fail_times=99))
    assert slept == [], f"a write slept {slept} before raising"


def test_a_failed_read_backs_off_between_attempts(monkeypatch):
    slept = []
    monkeypatch.setattr('chemotion_api.connection.time.sleep', slept.append)
    with pytest.raises(ConnectionError):
        _send(_conn(retries=3), 'get', _Boom(fail_times=99))
    assert slept == [1.0, 2.0], "expected a growing pause between the three attempts"


def test_retries_can_be_switched_off(monkeypatch):
    monkeypatch.setattr('chemotion_api.connection.time.sleep', lambda _: None)
    conn, boom = _conn(retries=1), _Boom(fail_times=99)
    with pytest.raises(ConnectionError):
        _send(conn, 'get', boom)
    assert boom.calls == 1


# --- 2026-11-13 review: which transport errors are retried, and what an origin is ---------

class _Raises:
    def __init__(self, exc):
        self.exc, self.calls = exc, 0

    def __call__(self, **kwargs):
        self.calls += 1
        raise self.exc


@pytest.mark.parametrize("exc_name", ["SSLError", "ProxyError"])
def test_configuration_errors_are_not_retried(monkeypatch, exc_name):
    import requests.exceptions as rex
    sleeps = []
    monkeypatch.setattr('chemotion_api.connection.time.sleep', sleeps.append)
    boom = _Raises(getattr(rex, exc_name)("bad certificate"))
    with pytest.raises(ConnectionError):
        _send(_conn(retries=3), 'get', boom)
    assert boom.calls == 1 and sleeps == []


def test_a_read_timeout_on_a_get_is_retried_and_keeps_its_type(monkeypatch):
    from requests.exceptions import ReadTimeout
    monkeypatch.setattr('chemotion_api.connection.time.sleep', lambda _: None)
    boom = _Raises(ReadTimeout("slow"))
    with pytest.raises(ReadTimeout):
        _send(_conn(retries=3), 'get', boom)
    assert boom.calls == 3


def test_a_read_timeout_on_a_write_is_not_retried(monkeypatch):
    from requests.exceptions import ReadTimeout
    boom = _Raises(ReadTimeout("slow"))
    with pytest.raises(ReadTimeout):
        _send(_conn(retries=3), 'post', boom)
    assert boom.calls == 1


@pytest.mark.parametrize("host_url, url", [
    ("https://ELN.example.org", "https://eln.example.org/api/v1/samples"),
    ("https://eln.example.org:443", "https://eln.example.org/api/v1/samples"),
    ("https://eln.example.org", "HTTPS://eln.example.org:443/api/v1/samples"),
])
def test_the_same_origin_spelled_differently_is_allowed(host_url, url):
    Connection(host_url)._assert_same_origin(url)


def test_a_different_port_is_a_different_origin():
    with pytest.raises(ConnectionError, match="Refusing to send credentials"):
        _conn()._assert_same_origin("https://eln.example.org:8443/api/v1/samples")


# --- an expired token is refused locally; a 401 is never read as "log in again" -----------

def _jwt(exp):
    import base64, json as _json
    enc = lambda d: base64.urlsafe_b64encode(_json.dumps(d).encode()).rstrip(b'=').decode()
    return f"{enc({'alg': 'HS256'})}.{enc({'user_id': 1, 'exp': exp})}.sig"


def test_an_expired_token_is_refused_before_sending(monkeypatch):
    import time
    from chemotion_api.connection import TokenExpiredError
    conn, boom = _conn(), _Boom(fail_times=0)
    conn.set_bearer_token(_jwt(time.time() - 60))
    with pytest.raises(TokenExpiredError, match="Log in again"):
        _send(conn, 'get', boom)
    assert boom.calls == 0
    assert isinstance(TokenExpiredError(), PermissionError)


def test_a_valid_token_is_sent():
    import time
    conn, boom = _conn(), _Boom(fail_times=0)
    conn.set_bearer_token(_jwt(time.time() + 3600))
    _send(conn, 'get', boom)
    assert boom.calls == 1


@pytest.mark.parametrize("path", ["/api/v1/public/token", "/api/v1/public/ping", "/about"])
def test_public_routes_ignore_an_expired_token_so_login_still_works(path):
    import time, unittest.mock as mock
    conn, boom = _conn(), _Boom(fail_times=0)
    conn.set_bearer_token(_jwt(time.time() - 60))
    with mock.patch.object(type(conn).__mro__[1], 'post', boom, create=True):
        conn._send_request('post', path, {}, {})
    assert boom.calls == 1


@pytest.mark.parametrize("token", ["chemtoken_abc123", "not.a-jwt", "a.b.c"])
def test_tokens_that_carry_no_expiry_are_never_refused(token):
    conn, boom = _conn(), _Boom(fail_times=0)
    conn.set_bearer_token(token)
    _send(conn, 'get', boom)
    assert boom.calls == 1
