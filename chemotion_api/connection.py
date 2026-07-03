"""HTTP session and authentication layer for the Chemotion REST/Grape API."""
import json

import requests
from dateutil.parser import parse as parsedate
from requests.adapters import HTTPAdapter
from requests.exceptions import ConnectionError as CError
from urllib3.util.retry import Retry
from chemotion_api.schema_manager import SchemaManager


class Connection(requests.Session):
    """A :class:`requests.Session` configured for the Chemotion REST/Grape API.

    The HTTP verb methods (:meth:`get`, :meth:`post`, …) take a host-relative ``url_path`` instead
    of a full URL, attach the right default headers (including the bearer token when set), apply a
    retry policy for idempotent requests and serialize JSON bodies automatically.

    :param host_url: base URL of the Chemotion instance (trailing slashes are stripped).
    :param verify_ssl: whether to verify TLS certificates on every request.
    """
    def __init__(self, host_url: str, verify_ssl: bool = True):
        super().__init__()
        self._host_url = host_url.strip('/')
        self._verify = verify_ssl
        self._bearer_token: str | None = None
        self.tzinfo = None
        self._schema_manager: SchemaManager | None = None
        # Shared cache for the generic segment classes (/api/v1/segments/klasses.json), so the
        # per-call GenericSegments instances fetch it once per connection instead of per page/load.
        self._generic_segment_classes: list | None = None
        self._mount_retries()

    def _mount_retries(self):
        """Retry transient failures (connection errors, 502/503/504) with exponential backoff.
        Only idempotent methods are retried so POST/PATCH are never re-sent (avoids duplicate
        writes)."""
        retry = Retry(
            total=3, connect=3, read=2, backoff_factor=0.5,
            status_forcelist=(502, 503, 504),
            allowed_methods=frozenset(['GET', 'HEAD', 'OPTIONS', 'PUT', 'DELETE']),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.mount('http://', adapter)
        self.mount('https://', adapter)

    @property
    def schema_manager(self) -> SchemaManager:
        """The :class:`~chemotion_api.schema_manager.SchemaManager` for this instance.

        Created lazily on first access by querying ``/about`` and cached afterwards.

        :return: the schema manager bound to this connection.
        """
        if self._schema_manager is None:
            res = self.get('/about')
            self._schema_manager = SchemaManager(res)
        return self._schema_manager


    def reset_bearer_token(self):
        """Clear the stored bearer token so subsequent requests are sent unauthenticated."""
        self._bearer_token = None

    def set_bearer_token(self, token: str):
        """Store a bearer token to be sent as the ``Authorization`` header on later requests.

        :param token: the bearer token value (without the ``Bearer`` prefix).
        """
        self._bearer_token = token

    @property
    def bearer_token(self):
        """The currently stored bearer token, or ``None`` if unauthenticated."""
        return self._bearer_token

    @property
    def host_url(self):
        """The instance base URL this connection targets (without trailing slash)."""
        return self._host_url

    # These intentionally replace requests.Session's url-based signature with a host-relative
    # url_path API, so the override-incompatibility is by design.
    def delete(self, url_path: str = '', **kwargs) -> requests.Response:  # type: ignore[override]
        """Send a ``DELETE`` request to a host-relative path with the default headers.

        :param url_path: path relative to :attr:`host_url`.
        :param kwargs: extra arguments forwarded to :class:`requests.Session`.
        :return: the HTTP response.
        :raises ConnectionError: if the underlying connection fails.
        """
        return self._send_request('delete', url_path, self.get_default_session_header(), kwargs)

    def get(self, url_path: str = '', **kwargs) -> requests.Response:  # type: ignore[override]
        """Send a ``GET`` request to a host-relative path with the default headers.

        :param url_path: path relative to :attr:`host_url`.
        :param kwargs: extra arguments forwarded to :class:`requests.Session`.
        :return: the HTTP response.
        :raises ConnectionError: if the underlying connection fails.
        """
        return self._send_request('get', url_path, self.get_default_session_header(), kwargs)

    def post(self, url_path: str = '', **kwargs) -> requests.Response:  # type: ignore[override]
        """Send a ``POST`` request to a host-relative path with JSON headers.

        Non-string ``data`` is serialized to a JSON body automatically.

        :param url_path: path relative to :attr:`host_url`.
        :param kwargs: extra arguments forwarded to :class:`requests.Session`.
        :return: the HTTP response.
        :raises ConnectionError: if the underlying connection fails.
        """
        return self._send_request('post', url_path, self.get_json_session_header(), kwargs)

    def patch(self, url_path: str = '', **kwargs) -> requests.Response:  # type: ignore[override]
        """Send a ``PATCH`` request to a host-relative path with JSON headers.

        Non-string ``data`` is serialized to a JSON body automatically.

        :param url_path: path relative to :attr:`host_url`.
        :param kwargs: extra arguments forwarded to :class:`requests.Session`.
        :return: the HTTP response.
        :raises ConnectionError: if the underlying connection fails.
        """
        return self._send_request('patch', url_path, self.get_json_session_header(), kwargs)

    def put(self, url_path: str = '', **kwargs) -> requests.Response:  # type: ignore[override]
        """Send a ``PUT`` request to a host-relative path with JSON headers.

        Non-string ``data`` is serialized to a JSON body automatically.

        :param url_path: path relative to :attr:`host_url`.
        :param kwargs: extra arguments forwarded to :class:`requests.Session`.
        :return: the HTTP response.
        :raises ConnectionError: if the underlying connection fails.
        """
        return self._send_request('put', url_path, self.get_json_session_header(), kwargs)

    def _send_request(self, method: str, url_path: str, default_header: dict, kwargs: dict) -> requests.Response:
        kwargs['verify'] = kwargs.get('verify', self._verify)
        kwargs['url'] = kwargs.get('url', f"{self._host_url}/{url_path.lstrip('/')}")
        kwargs['headers'] = kwargs.get('headers', default_header)
        kwargs['timeout'] = kwargs.get('timeout', (2, 500))
        if 'files' in kwargs:
            if 'Content-Type' in kwargs['headers']:
                del kwargs['headers']['Content-Type']
        elif 'data' in kwargs and not isinstance(kwargs['data'], str) and kwargs['headers'].get(
                'Content-Type') == 'application/json':
            kwargs['data'] = json.dumps(kwargs.get('data', {}))
        try:
            res = getattr(super(), method)(**kwargs)
        except CError as e:
            raise ConnectionError(str(e)) from e
        if self.tzinfo is None:
            if 'Date' in res.headers:
                self.tzinfo = parsedate(res.headers['Date']).astimezone().tzinfo

        return res

    def get_default_session_header(self) -> dict[str, str]:
        """Build the default request headers, including the bearer token when one is set.

        :return: a headers ``dict`` with a ``User-Agent`` and, if authenticated, an
            ``Authorization: Bearer …`` entry.
        """
        headers = {'User-Agent': 'Mozilla/5.0'}
        if self._bearer_token is not None:
            headers["Authorization"] = f"Bearer {self._bearer_token}"
        return headers

    def get_json_session_header(self) -> dict[str, str]:
        """Build the default headers plus a ``Content-Type: application/json`` entry.

        :return: a headers ``dict`` suitable for sending a JSON request body.
        """
        header = self.get_default_session_header()
        header['Content-Type'] = 'application/json'
        return header
