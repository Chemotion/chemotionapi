import json

import requests
from dateutil.parser import parse as parsedate
from requests.exceptions import ConnectionError as CError
from chemotion_api.schema_manager import SchemaManager


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

    def get(self, url_path: str = '', **kwargs) -> requests.Response:
        return self._send_request('get', url_path, self.get_default_session_header(), kwargs)

    def post(self, url_path: str = '', **kwargs) -> requests.Response:
        return self._send_request('post', url_path, self.get_json_session_header(), kwargs)

    def patch(self, url_path: str = '', **kwargs) -> requests.Response:
        return self._send_request('patch', url_path, self.get_json_session_header(), kwargs)

    def put(self, url_path: str = '', **kwargs) -> requests.Response:
        return self._send_request('put', url_path, self.get_json_session_header(), kwargs)

    def _send_request(self, method: str, url_path: str, default_header: dict, kwargs: dict) -> requests.Response:
        kwargs['verify'] = kwargs.get('verify', self._verify)
        kwargs['url'] = kwargs.get('url', f"{self._host_url}/{url_path.lstrip('/')}")
        kwargs['headers'] = kwargs.get('headers', default_header)
        kwargs['timeout'] = kwargs.get('timeout', (2, 15))
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
