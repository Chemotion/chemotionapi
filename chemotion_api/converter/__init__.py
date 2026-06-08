"""Manage Chemotion converter profiles.

Converter profiles describe how to map instrument/data files into Chemotion datasets. This
module wraps the ``/api/v1/converter/profiles`` endpoints, modelling a single profile as a
:class:`Profile` and the server-side collection as a :class:`ProfileManager`.
"""
import json
import os
from typing import Any
from uuid import uuid4

import requests

from chemotion_api.connection import Connection


class Profile:
    """A single converter profile, persisted to the server via :meth:`save`.

    :param session: an authenticated :class:`~chemotion_api.connection.Connection`.
    :param title: human-readable profile title.
    :param id: profile id (UUID string).
    :param description: profile description.
    :param identifiers: list of identifier definitions.
    :param tables: list of table-mapping definitions.
    :param data: the profile's mapping data payload.
    :param matchTables: optional flag controlling table matching.
    :param ols: optional OLS ontology reference.
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
        """Serialize the profile to a plain dict suitable for the API payload."""
        result: dict[str, Any] = {
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
        """Return the profile serialized as a JSON string."""
        return json.dumps(self.to_dict())

    def __str__(self):
        """Return the profile title."""
        return self.title

    def save(self) -> requests.Response:
        """Persist the profile to the server (POST on first save, PUT thereafter).

        :return: the raw server response; on success ``self`` is marked as saved.
        """
        if self._is_saved:
            res = self._session.put(f'/api/v1/converter/profiles/{self.id}', data=self.to_dict())
        else:
            res = self._session.post(f'/api/v1/converter/profiles', data=self.to_dict())
        if res.status_code == 200 or res.status_code == 201:
            self._is_saved = True
        return res

    def delete(self):
        """Delete this profile from the server.

        :return: the raw server response.
        """
        return self._session.delete(f'/api/v1/converter/profiles/{self.id}')


class ProfileManager:
    """Access and cache the converter profiles available on the server.

    :param session: an authenticated :class:`~chemotion_api.connection.Connection`.
    """

    def __init__(self, session: Connection):
        super().__init__()
        self._session = session
        self._all_profiles: list[Profile] | None = None

    def get_profile(self, profile_id: str) -> Profile | None:
        """Return the profile with the given id, or ``None`` if not found.

        :param profile_id: the profile id to look up.
        """
        return next((p for p in self.profiles if p.id == profile_id), None)

    @property
    def profiles(self) -> list[Profile]:
        """All profiles on the server, fetched once and cached.

        :raises ConnectionError: if the profiles cannot be fetched.
        """
        if self._all_profiles is None:
            res = self._session.get('api/v1/converter/profiles')
            if res.status_code != 200:
                raise ConnectionError(res.text)

            self._all_profiles = [Profile(self._session, **x) for x in res.json()['profiles']]
        return self._all_profiles

    def new_profile_from_file(self, file_path: str) -> Profile | None:
        """Build a (not-yet-saved) :class:`Profile` from a JSON file on disk.

        If the file's id collides with an existing profile, a fresh UUID is assigned.

        :param file_path: path to a JSON profile definition.
        :return: a new :class:`Profile`, or ``None`` if the file is missing or not valid JSON.
        """
        if os.path.exists(file_path):
            try:
                with open(file_path) as f:
                    pd = json.loads(f.read())
                    while self.get_profile(pd['id']) is not None:
                        pd['id'] = uuid4().__str__()
                    return Profile(self._session, **pd)
            except json.decoder.JSONDecodeError:
                pass
        return None