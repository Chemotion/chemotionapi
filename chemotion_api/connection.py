import base64
import json
import re
import time
import typing
from urllib.parse import urlsplit

import requests
from dateutil.parser import parse as parsedate
from requests.exceptions import ConnectionError as CError, ProxyError, SSLError, Timeout
from chemotion_api.schema_manager import SchemaManager


_DEFAULT_PORTS = {'http': 80, 'https': 443}


def _origin(parts) -> tuple[str, str | None, int | None]:
    """``(scheme, host, port)`` with host case and a default port normalised away.

    ``https://ELN.example.org:443`` and ``https://eln.example.org`` are the same origin.
    """
    scheme = parts.scheme.lower()
    return scheme, parts.hostname, parts.port or _DEFAULT_PORTS.get(scheme)


class TokenExpiredError(PermissionError):
    """The bearer token's own ``exp`` claim has passed, so the server would refuse it.

    Raised before the request is sent. A ``PermissionError``, as a failed login is. Log in again
    (``Instance.login``) or supply a fresh token (``Instance.login_token``).
    """


def _jwt_expiry(token: str) -> float | None:
    """The ``exp`` claim of a JWT as a Unix time, read without verifying the signature.

    ``None`` for anything that is not a three-part JWT with a numeric ``exp`` — e.g. a
    ``chemtoken_…`` API token — so only a token that says it has expired is ever refused.
    """
    parts = token.split('.')
    if len(parts) != 3:
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + '=' * (-len(parts[1]) % 4)))
    except (ValueError, TypeError):
        return None
    exp = payload.get('exp') if isinstance(payload, dict) else None
    return float(exp) if isinstance(exp, (int, float)) and not isinstance(exp, bool) else None


class ChemotionRequestError(requests.exceptions.RequestException, ConnectionError):
    """Raised when the Chemotion server rejects a request.

    Ported from version-3 (PR #6), with one deliberate change: it also inherits the **builtin**
    ``ConnectionError``. This client has always raised that, so a straight port would have broken
    every ``except ConnectionError`` a user has written. Both bases derive from ``OSError``, so
    the combination is legal and the port becomes strictly additive — richer messages, same
    handlers.

    :ivar status_code: HTTP status of the response
    :ivar method: HTTP method of the request
    :ivar url: URL of the request
    :ivar context: what the request was about (e.g. ``saving sample 12``), or ``None``
    :ivar snippet: a short form of the body — the ``<title>`` of an HTML error page rather than
        the whole page, which is the difference between a readable traceback and 40 KB of markup
    """

    def __init__(self, response: requests.Response, context: str | None = None):
        self.status_code = response.status_code
        request = getattr(response, 'request', None)
        self.method = request.method if request is not None else None
        self.url = request.url if request is not None else getattr(response, 'url', None)
        self.context = context
        self.snippet = self._snippet(response)
        message = f'{self.status_code} -> {self.snippet} [{self.method} {self.url}]'
        if context:
            message += f' ({context})'
        super().__init__(message, response=response)

    @staticmethod
    def _snippet(response: requests.Response, max_length: int = 500) -> str:
        """The useful part of a response body."""
        text = getattr(response, 'text', '') or ''
        if '<html' in text[:200].lower():
            title = re.search(r'<title>(.*?)</title>', text, re.IGNORECASE | re.DOTALL)
            return title.group(1).strip() if title else 'HTML error page'
        return text if len(text) <= max_length else text[:max_length] + '...'


class ChemotionServerError(ChemotionRequestError):
    """A 5xx from the server — usually a server-side failure triggered by data it would not
    accept, such as a sample whose molecule never resolved."""


def request_error(response: requests.Response,
                  context: str | None = None) -> ChemotionRequestError:
    """Build the right error for a failed response: 5xx is the server's fault, 4xx the caller's.

    :param response: the failed response
    :param context: description of what the request was doing (e.g. ``saving sample 12``)
    :return: a :class:`ChemotionServerError` for 5xx responses, otherwise a
        :class:`ChemotionRequestError`
    """
    if response.status_code >= 500:
        return ChemotionServerError(response, context)
    return ChemotionRequestError(response, context)


#: Methods safe to send again after a transport failure. A write is never retried: if the server
#: received it before the connection broke, a second attempt would apply it twice.
_IDEMPOTENT_METHODS = frozenset({'get', 'head', 'options'})

#: Seconds to wait before retry *n*, multiplied by the attempt number — so 1s, then 2s.
_RETRY_BACKOFF_SECONDS = 1.0


class Connection(requests.Session):
    #: (connect, read) seconds. The read half is deliberately long — a large collection export is
    #: slow to produce server-side — but it is near-unbounded, so it is overridable per connection.
    DEFAULT_TIMEOUT: tuple[float, float] = (2, 500)

    #: Attempts for an idempotent request before giving up, the first included.
    DEFAULT_RETRIES: int = 3

    def __init__(self, host_url: str, verify_ssl: bool = True,
                 timeout: float | tuple[float, float] | None = None,
                 retries: int | None = None):
        """
        :param host_url: base URL of the Chemotion instance.
        :param verify_ssl: verify TLS certificates.
        :param timeout: requests timeout for every call on this connection — a ``(connect, read)``
            pair or a single number. Defaults to :attr:`DEFAULT_TIMEOUT`. Individual calls may
            still override it with ``timeout=``.
        :param retries: attempts for a **read** before giving up, defaulting to
            :attr:`DEFAULT_RETRIES`. Writes are never retried whatever this is set to. Pass ``1``
            to disable retrying entirely.
        """
        super().__init__()
        self._host_url = host_url.strip('/')
        self._verify = verify_ssl
        self._timeout = timeout if timeout is not None else self.DEFAULT_TIMEOUT
        self._retries = max(1, retries if retries is not None else self.DEFAULT_RETRIES)
        self._bearer_token = None
        self.tzinfo = None
        self._schema_manager = None
        self._user_labels: list[dict] | None = None
        self._current_user_id: int | None = None

    @property
    def schema_manager(self) -> SchemaManager:
        if self._schema_manager is None:
            res = self.get('/about')
            self._schema_manager = SchemaManager(res)
        return self._schema_manager


    @property
    def user_labels(self) -> list[dict]:
        """Raw user-label payloads from ``/api/v1/user_labels/list_labels``, fetched once.

        Cached per connection because label ids are resolved per *element*: without this, reading
        labels across 500 samples would issue 500 identical requests. The cache is dropped
        whenever the bearer token changes, since the server filters labels by the current user.

        :raise PermissionError: if the labels cannot be fetched. Make sure that you are logged in.
        """
        if self._user_labels is None:
            res = self.get('/api/v1/user_labels/list_labels')
            if res.status_code == 401:
                raise PermissionError('Not allowed to fetch user labels (Login first)')
            if res.status_code != 200:
                raise ConnectionError(f'{res.status_code} -> {res.text}')
            self._user_labels = res.json().get('labels') or []
        return self._user_labels

    def reset_user_labels(self):
        """Drop the cached user labels, and the cached user id, so the next read refetches them."""
        self._user_labels = None
        self._current_user_id = None

    def current_user_id(self) -> int:
        """The logged-in user's id, fetched once per login."""
        if self._current_user_id is None:
            from chemotion_api.user import User
            self._current_user_id = User.load_me(self).id
        return typing.cast(int, self._current_user_id)

    def _assert_token_not_expired(self, url: str) -> None:
        """Refuse to send a bearer token whose own ``exp`` claim has passed.

        The server cannot tell us: it answers ``401 Unauthorized`` both for a dead token and for
        an ordinary permission denial (over a hundred element-policy checks), so a 401 must not be
        read as "log in again". The token itself can — Chemotion JWTs carry ``exp``, six months
        out. Public routes (``/api/v1/public/…``, ``/about``) are exempt, so logging in again with
        an expired token still set works.

        :raises TokenExpiredError: if the token has expired and the route is not public.
        """
        if self._bearer_token is None:
            return
        path = urlsplit(url).path if '://' in url else url
        if path.startswith('/api/v1/public/') or path.startswith('api/v1/public/') \
                or path.rstrip('/') in ('/about', 'about'):
            return
        exp = _jwt_expiry(self._bearer_token)
        if exp is not None and exp <= time.time():
            raise TokenExpiredError(
                'The login token expired at '
                f'{time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(exp))}. Log in again '
                '(Instance.login) or supply a fresh token (Instance.login_token).')

    def reset_bearer_token(self):
        self._bearer_token = None
        # A different (or absent) user sees a different set of labels — never serve the old one.
        self.reset_user_labels()

    def set_bearer_token(self, token: str):
        self._bearer_token = token
        self.reset_user_labels()

    @property
    def bearer_token(self):
        return self._bearer_token

    @property
    def host_url(self):
        return self._host_url

    def delete(self, url_path: str = '', **kwargs) -> requests.Response:
        return self._send_request('delete', url_path, self.get_default_session_header(), kwargs)

    # Each verb takes a path relative to the instance host and applies this session's default
    # headers, auth and timeout. Note they are documented here rather than inheriting
    # requests.Session's docstrings: autodoc renders those with a docutils field-list warning, and
    # the inherited text describes a different signature (absolute URL) than these accept.

    def get(self, url_path: str = '', **kwargs) -> requests.Response:
        """GET ``url_path`` on this instance.

        :param url_path: path relative to the instance host, e.g. ``/api/v1/samples``.
        :param kwargs: passed through to :mod:`requests` (``params``, ``stream``, ``timeout``, …).
        :return: the response.
        """
        return self._send_request('get', url_path, self.get_default_session_header(), kwargs)

    def post(self, url_path: str = '', **kwargs) -> requests.Response:
        """POST to ``url_path`` on this instance, with the JSON request headers.

        :param url_path: path relative to the instance host.
        :param kwargs: passed through to :mod:`requests` (``data``, ``json``, ``files``, …).
        :return: the response.
        """
        return self._send_request('post', url_path, self.get_json_session_header(), kwargs)

    def patch(self, url_path: str = '', **kwargs) -> requests.Response:
        """PATCH ``url_path`` on this instance, with the JSON request headers.

        :param url_path: path relative to the instance host.
        :param kwargs: passed through to :mod:`requests`.
        :return: the response.
        """
        return self._send_request('patch', url_path, self.get_json_session_header(), kwargs)

    def put(self, url_path: str = '', **kwargs) -> requests.Response:
        """PUT ``url_path`` on this instance, with the JSON request headers.

        :param url_path: path relative to the instance host.
        :param kwargs: passed through to :mod:`requests`.
        :return: the response.
        """
        return self._send_request('put', url_path, self.get_json_session_header(), kwargs)

    def _assert_same_origin(self, url: str) -> None:
        """Refuse a URL that points somewhere other than this connection's host.

        Every request carries the bearer token, so a URL whose host is not ours would hand the
        session to a third party. Paths are normally relative and prefixed with ``host_url``, but
        an absolute ``url`` passes through untouched — and a server-supplied one (a download or
        thumbnail link, say) is exactly the case where that matters.

        :raises ConnectionError: if the scheme or host differs from ``host_url``.
        """
        target, origin = urlsplit(url), urlsplit(self._host_url)
        if not target.scheme and not target.netloc:
            return
        if _origin(target) != _origin(origin):
            raise ConnectionError(
                f'Refusing to send credentials to {target.scheme}://{target.netloc} — '
                f'this connection is bound to {origin.scheme}://{origin.netloc}.')

    def _send_request(self, method: str, url_path: str, default_header: dict, kwargs: dict) -> requests.Response:
        self._assert_token_not_expired(kwargs.get('url', url_path))
        kwargs['verify'] = kwargs.get('verify', self._verify)
        kwargs['url'] = kwargs.get('url', f"{self._host_url}/{url_path.lstrip('/')}")
        self._assert_same_origin(kwargs['url'])
        kwargs['headers'] = kwargs.get('headers', default_header)
        kwargs['timeout'] = kwargs.get('timeout', self._timeout)
        if 'files' in kwargs:
            if 'Content-Type' in kwargs['headers']:
                del kwargs['headers']['Content-Type']
        elif 'data' in kwargs and not isinstance(kwargs['data'], str) and kwargs['headers'].get(
                'Content-Type') == 'application/json':
            kwargs['data'] = json.dumps(kwargs.get('data', {}))
        # Retry transport failures, but **only for methods that are safe to repeat**. A POST or
        # PUT that fails after the server received it would be applied twice on a retry, so a
        # write is never retried — the caller is told the write did not happen rather than being
        # left to guess. This is deliberately a transport-level retry: an HTTP error status is a
        # considered answer from the server and is returned to the caller untouched.
        last_error: Exception | None = None
        attempts = self._retries if method in _IDEMPOTENT_METHODS else 1
        for attempt in range(attempts):
            try:
                res = getattr(super(), method)(**kwargs)
                break
            except (SSLError, ProxyError) as e:
                # A certificate or proxy failure is configuration, not a transient fault: the
                # next attempt fails identically, so retrying only delays the error.
                raise ConnectionError(str(e)) from e
            except Timeout as e:
                if not isinstance(e, CError):
                    # A read timeout (the server took the request but did not answer in time) is
                    # not retried: the timeout is long on purpose, so repeating it multiplies the
                    # wait, and the server may still be working on the request. A connect timeout
                    # is also a ConnectionError and is retried below.
                    raise
                last_error = e
                if attempt + 1 < attempts:
                    time.sleep(_RETRY_BACKOFF_SECONDS * (attempt + 1))
            except CError as e:
                last_error = e
                # Compare against the attempts actually allowed, not the configured maximum:
                # a write gets one attempt, so it must raise immediately rather than sleep
                # before failing.
                if attempt + 1 < attempts:
                    time.sleep(_RETRY_BACKOFF_SECONDS * (attempt + 1))
        else:
            if method in _IDEMPOTENT_METHODS:
                raise ConnectionError(
                    f'Could not reach the server after {self._retries} attempts: {last_error}'
                ) from last_error
            raise ConnectionError(
                f'Could not reach the server; the {method.upper()} was not retried, so it may '
                f'or may not have been applied: {last_error}') from last_error
        if self.tzinfo is None:
            if 'Date' in res.headers:
                self.tzinfo = parsedate(res.headers['Date']).astimezone().tzinfo

        return res

    def get_default_session_header(self) -> dict[str, str]:
        headers = {'User-Agent': 'Mozilla/5.0'}
        if self._bearer_token is not None:
            headers["Authorization"] = f"Bearer {self._bearer_token}"
        return headers

    def get_json_session_header(self) -> dict[str, str]:
        header = self.get_default_session_header()
        header['Content-Type'] = 'application/json'
        return header
