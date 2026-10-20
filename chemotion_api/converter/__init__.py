import json
import os
from typing import List
from uuid import uuid4

import requests

from chemotion_api.connection import Connection


class Profile:
    """
    A converter profile. It tells the Chemotion converter how to read the metadata of an uploaded
    measurement file. Profiles are listed and created with the :class:`ProfileManager`.

    Attributes: ``id``, ``title``, ``description``, ``identifiers`` (how a file is matched),
    ``tables`` (where the data is read from), ``data``, ``matchTables`` and ``ols`` (ontology term id).
    """

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
        """
        :return: the profile in the format of the converter API
        """
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
        """
        :return: the profile as JSON string, e.g. to store it as file for :meth:`ProfileManager.new_profile_from_file`
        """
        return json.dumps(self.to_dict())

    def __str__(self):
        return self.title

    def save(self) -> requests.Response:
        """
        Creates the profile on the server, or updates it if it already exists there.

        :return: response of the request
        """
        if self._is_saved:
            res = self._session.put(f'/api/v1/converter/profiles/{self.id}', data=self.to_dict())
        else:
            res = self._session.post(f'/api/v1/converter/profiles', data=self.to_dict())
        if res.status_code == 200 or res.status_code == 201:
            self._is_saved = True
        return res

    def delete(self) -> requests.Response:
        """
        Deletes the profile on the server.

        :return: response of the request
        """
        return self._session.delete(f'/api/v1/converter/profiles/{self.id}')


class ProfileManager(object):
    """
    Lists, loads and creates converter profiles. Use :meth:`chemotion_api.Instance.get_profile_manager`
    to get one.

    Usage::

    >>> pm = instance.get_profile_manager()
    >>> for profile in pm.profiles:
    >>>     print(profile.id, profile.title)
    >>> profile = pm.new_profile_from_file('./my_profile.json')
    >>> profile.save()
    >>> pm.get_profile(profile.id).delete()
    """

    def __init__(self, session: Connection):
        super().__init__()
        self._session = session
        self._all_profiles = None

    def get_profile(self, profile_id: str) -> Profile | None:
        """
        :param profile_id: ID of the profile
        :return: the profile, or None if there is no profile with this ID
        """
        return next((p for p in self.profiles if p.id == profile_id), None)

    @property
    def profiles(self) -> List[Profile]:
        """
        All converter profiles on the server. They are loaded once and cached.

        :raises ConnectionError: if the profiles cannot be loaded
        """
        if self._all_profiles is None:
            res = self._session.get('api/v1/converter/profiles')
            if res.status_code != 200:
                raise ConnectionError(res.text)

            self._all_profiles = [Profile(self._session, **x) for x in res.json()['profiles']]
            # Profiles from the server are updated, not created again, when saved
            for profile in self._all_profiles:
                profile._is_saved = True
        return self._all_profiles

    def new_profile_from_file(self, file_path: str) -> Profile | None:
        """
        Creates a new profile from a JSON file (e.g. exported from the Chemotion converter). If a profile with
        the same ID exists, the new profile gets a new ID. The profile is not saved.

        :param file_path: path to the JSON file
        :return: the new profile, or None if the file does not exist or is not valid JSON
        """
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