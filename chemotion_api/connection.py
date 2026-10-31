import json
import re

import requests
from dateutil.parser import parse as parsedate
from requests.exceptions import ConnectionError as CError
from chemotion_api.schema_manager import SchemaManager


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


class Connection(requests.Session):
    #: (connect, read) seconds. The read half is deliberately long — a large collection export is
    #: slow to produce server-side — but it is near-unbounded, so it is overridable per connection.
    DEFAULT_TIMEOUT: tuple[float, float] = (2, 500)

    def __init__(self, host_url: str, verify_ssl: bool = True,
                 timeout: float | tuple[float, float] | None = None):
        """
        :param host_url: base URL of the Chemotion instance.
        :param verify_ssl: verify TLS certificates.
        :param timeout: requests timeout for every call on this connection — a ``(connect, read)``
            pair or a single number. Defaults to :attr:`DEFAULT_TIMEOUT`. Individual calls may
            still override it with ``timeout=``.
        """
        super().__init__()
        self._host_url = host_url.strip('/')
        self._verify = verify_ssl
        self._timeout = timeout if timeout is not None else self.DEFAULT_TIMEOUT
        self._bearer_token = None
        self.tzinfo = None
        self._schema_manager = None
        self._user_labels: list[dict] | None = None

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
        """Drop the cached user labels so the next read refetches them."""
        self._user_labels = None

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

    def _send_request(self, method: str, url_path: str, default_header: dict, kwargs: dict) -> requests.Response:
        kwargs['verify'] = kwargs.get('verify', self._verify)
        kwargs['url'] = kwargs.get('url', f"{self._host_url}/{url_path.lstrip('/')}")
        kwargs['headers'] = kwargs.get('headers', default_header)
        kwargs['timeout'] = kwargs.get('timeout', self._timeout)
        if 'files' in kwargs:
            if 'Content-Type' in kwargs['headers']:
                del kwargs['headers']['Content-Type']
        elif 'data' in kwargs and not isinstance(kwargs['data'], str) and kwargs['headers'].get(
                'Content-Type') == 'application/json':
            kwargs['data'] = json.dumps(kwargs.get('data', {}))
        try:
            res = getattr(super(), method)(**kwargs)
        except CError as e:
            raise ConnectionError(str(e))
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
