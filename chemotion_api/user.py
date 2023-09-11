import json

from requests.exceptions import ConnectionError
from chemotion_api.connection import Connection


class User:
    id: int = None
    name: str = None
    first_name: str = None
    last_name: str = None
    initials: str = None
    samples_count: int = None
    reactions_count: int = None
    type: str = None
    reaction_name_prefix: str = None
    layout: dict[str:str] = None
    email: str = None
    unconfirmed_email: str = None
    confirmed_at: str = None
    current_sign_in_at: str = None
    locked_at = None
    is_templates_moderator: bool = None
    molecule_editor: bool = None
    account_active: bool = None
    matrix: int = None
    counters: dict[str:str] = None
    generic_admin: dict[str:bool] = None

    def __init__(self, session: Connection):
        self._session = session

    def load(self):
        user_url = '/api/v1/users/current.json'

        res = self._session.get(user_url)
        if res.status_code == 401:
            raise PermissionError('Not allowed to fetch user (Login first)')
        elif res.status_code != 200:
            raise ConnectionError('{} -> {}'.format(res.status_code, res.text))
        for (key, val) in json.loads(res.content)['user'].items():
            setattr(self, key, val)


    def is_admin(self):
        return self.type == 'admin'

    def is_device(self):
        return self.type == 'device'

    def is_group(self):
        return self.type == 'group'