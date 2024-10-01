import json
import os
from typing import List
from uuid import uuid4

import requests

from chemotion_api.connection import Connection


class Profile:
    def __init__(self, session: Connection, title: str, id: str, description: str, identifiers: list[dict],
                 tables: list[dict], data: dict, matchTables: bool | None = None, ols: str | None = None) -> None:
        self._session = session
        self.ols = ols
        self.data = data
        self.title = title
        self.id = id
        self.description = description
        self.tables = tables
        self.identifiers = identifiers
        self.matchTables = matchTables
        self._is_saved = False

    def to_dict(self) -> dict:
        result = {
            "ols": self.ols,
            "data": self.data,
            "title": self.title,
            "id": self.id,
            "description": self.description,
            "tables": self.tables,
            "identifiers": self.identifiers,
        }
        if self.matchTables is not None:
            result["matchTables"] = self.matchTables
        if self.ols is not None:
            result["ols"] = self.ols
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def __str__(self):
        return self.title

    def save(self) -> requests.Response:
        if self._is_saved:
            res = self._session.put(f'/api/v1/converter/profiles/{self.id}', data=self.to_dict())
        else:
            res = self._session.post(f'/api/v1/converter/profiles', data=self.to_dict())
        if res.status_code == 200 or res.status_code == 201:
            self._is_saved = True
        return res

    def delete(self):
        return self._session.delete(f'/api/v1/converter/profiles/{self.id}')


class ProfileManager(object):
    """
    Profile manager class
    """

    def __init__(self, session: Connection):
        super().__init__()
        self._session = session
        self._all_profiles = None

    def get_profile(self, profile_id: str) -> Profile:
        return next((p for p in self.profiles if p.id == profile_id), None)

    @property
    def profiles(self) -> List[Profile]:
        if self._all_profiles is None:
            res = self._session.get('api/v1/converter/profiles')
            if res.status_code != 200:
                raise ConnectionError(res.text)

            self._all_profiles = [Profile(self._session, **x) for x in res.json()['profiles']]
        return self._all_profiles

    def new_profile_from_file(self, file_path: str) -> Profile | None:
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r') as f:
                    pd = json.loads(f.read())
                    while self.get_profile(pd['id']) is not None:
                        pd['id'] = uuid4().__str__()
                    return Profile(self._session, **pd)
            except json.decoder.JSONDecodeError:
                pass
        return None