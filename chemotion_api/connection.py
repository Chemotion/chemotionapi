import json
import re

import requests
from dateutil.parser import parse as parsedate
from requests.exceptions import ConnectionError as CError, RequestException
from chemotion_api.schema_manager import SchemaManager


class ChemotionRequestError(RequestException):
    """
    Raised if the Chemotion server rejects a request. It extends ``requests.exceptions.RequestException``.

    :ivar status_code: HTTP status of the response
    :ivar method: HTTP method of the request
    :ivar url: URL of the request
    :ivar context: description of the object the request was about (e.g. ``sample 12``), or None
    :ivar snippet: short version of the response body (the title of an HTML error page)
    """

    def __init__(self, response: requests.Response, context: str | None = None):
        self.status_code = response.status_code
        self.method = response.request.method if response.request is not None else None
        self.url = response.request.url if response.request is not None else response.url
        self.context = context
        self.snippet = self._snippet(response)
        message = f'{self.status_code} -> {self.snippet} [{self.method} {self.url}]'
        if context:
            message += f' ({context})'
        super().__init__(message, response=response)

    @staticmethod
    def _snippet(response: requests.Response, max_length: int = 500) -> str:
        text = response.text or ''
        if '<html' in text[:200].lower():
            title = re.search(r'<title>(.*?)</title>', text, re.IGNORECASE | re.DOTALL)
            return title.group(1).strip() if title else 'HTML error page'
        return text if len(text) <= max_length else text[:max_length] + '...'


class ChemotionServerError(ChemotionRequestError):
    """
    Raised if the Chemotion server fails with a 5xx status. This is usually a server-side bug triggered by
    invalid data, e.g. a sample without a valid molecule.
    """


class ChemotionRejectedError(ChemotionRequestError, ConnectionError, ValueError):
    """The server answered with a success status but said in the body that it did not do it.

    The ELN does this on several routes: ``201`` with ``{"errors": {...}}`` for a refused create,
    ``200`` with ``{"error": "..."}`` for a rescued exception, ``{"success": false}``. Checking only
    the status code reads each as success. The connection checks every JSON reply for these keys
    and raises this; a call that reads such a body itself passes ``allow_error_body=True``.

    It is a ``ConnectionError`` and a ``ValueError`` as well, so handlers written for what the
    methods raised before keep catching it.

    :ivar body: the decoded reply
    """

    def __init__(self, response: requests.Response, body: dict, context: str | None = None):
        self.body = body
        super().__init__(response, context)


def _rejection(body) -> bool:
    """Whether a decoded 2xx reply says the request failed.

    ``error`` / ``errors`` count only when they carry something: ``{"error": 0}`` (a public route)
    and ``{"errors": []}`` are successes.
    """
    if not isinstance(body, dict):
        return False
    return bool(body.get('error')) or bool(body.get('errors')) or body.get('success') is False


def request_error(response: requests.Response, context: str | None = None) -> ChemotionRequestError:
    """
    :param response: the failed response
    :param context: description of the object the request was about
    :return: a :class:`ChemotionServerError` for 5xx responses, otherwise a :class:`ChemotionRequestError`
    """
    if response.status_code >= 500:
        return ChemotionServerError(response, context)
    return ChemotionRequestError(response, context)


class Connection(requests.Session):
    def __init__(self, host_url: str, verify_ssl: bool = True):
        super().__init__()
        self._host_url = host_url.strip('/')
        self._verify = verify_ssl
        self._bearer_token = None
        self.tzinfo = None
        self._schema_manager = None

    @property
    def schema_manager(self) -> SchemaManager:
        if self._schema_manager is None:
            res = self.get('/about')
            self._schema_manager = SchemaManager(res)
        return self._schema_manager


    def reset_bearer_token(self):
        self._bearer_token = None

    def set_bearer_token(self, token: str):
        self._bearer_token = token

    @property
    def bearer_token(self):
        return self._bearer_token

    @property
    def host_url(self):
        return self._host_url

    def delete(self, url_path: str = '', **kwargs) -> requests.Response:
        return self._send_request('delete', url_path, self.get_default_session_header(), kwargs)

    def get(self, url_path: str = '', **kwargs) -> requests.Response:
        return self._send_request('get', url_path, self.get_default_session_header(), kwargs)

    def post(self, url_path: str = '', **kwargs) -> requests.Response:
        return self._send_request('post', url_path, self.get_json_session_header(), kwargs)

    def patch(self, url_path: str = '', **kwargs) -> requests.Response:
        return self._send_request('patch', url_path, self.get_json_session_header(), kwargs)

    def put(self, url_path: str = '', **kwargs) -> requests.Response:
        return self._send_request('put', url_path, self.get_json_session_header(), kwargs)

    def _send_request(self, method: str, url_path: str, default_header: dict, kwargs: dict) -> requests.Response:
        allow_error_body = kwargs.pop('allow_error_body', False)
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
            raise ConnectionError(str(e))
        if self.tzinfo is None:
            if 'Date' in res.headers:
                self.tzinfo = parsedate(res.headers['Date']).astimezone().tzinfo
        if not allow_error_body and not kwargs.get('stream'):
            self._raise_on_rejection(res)
        return res

    @staticmethod
    def _raise_on_rejection(res: requests.Response) -> None:
        """Raise :class:`ChemotionRejectedError` for a 2xx JSON reply that reports a failure.

        The body is only decoded when it mentions one of the keys, so a large listing costs a
        byte search, not a second parse.
        """
        if not 200 <= res.status_code < 300:
            return
        if 'json' not in (res.headers.get('Content-Type') or ''):
            return
        content = res.content or b''
        if b'"error' not in content and b'"success"' not in content:
            return
        try:
            body = res.json()
        except ValueError:
            return
        if _rejection(body):
            raise ChemotionRejectedError(res, body)

    def get_default_session_header(self) -> dict[str, str]:
        headers = {'User-Agent': 'Mozilla/5.0'}
        if self._bearer_token is not None:
            headers["Authorization"] = f"Bearer {self._bearer_token}"
        return headers

    def get_json_session_header(self) -> dict[str, str]:
        header = self.get_default_session_header()
        header['Content-Type'] = 'application/json'
        return header
