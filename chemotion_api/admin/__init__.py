"""Admin-only operations exposed over the Chemotion REST API.

These calls require the logged-in user to have administrator privileges; the server returns
``401`` otherwise.
"""
import warnings

from chemotion_api.connection import Connection


class AdminMenu:
    """Wrapper for administrator-only API endpoints.

    :param session: an authenticated :class:`~chemotion_api.connection.Connection`.
    """

    def __init__(self, session: Connection):
        self._session = session

    def create_device(self, first_name: str, last_name: str, name_abbreviation: str):
        """Create a new group device on the server (admin only).

        :param first_name: device first name.
        :param last_name: device last name.
        :param name_abbreviation: short abbreviation identifying the device.
        :return: the created device as returned by the server (parsed JSON).
        :raises PermissionError: if the user is not allowed to create the device (HTTP 401).
        :raises ConnectionError: if the server responds with any other non-success status.
        """
        payload = {'first_name': first_name,
                   'last_name': last_name,
                   'rootType': "Device",
                   "name_abbreviation": name_abbreviation}

        res = self._session.post('/api/v1/admin/group_device/create',
                                 headers=self._session.get_default_session_header(),
                                 data=payload)

        if res.status_code == 401:
            raise PermissionError('Not allowed to create device (only Admin)')
        elif res.status_code != 201 and res.status_code != 200:
            raise ConnectionError(f"Error ({res.status_code}) \n{res.text}")

        return res.json()

    def greate_device(self, first_name: str, last_name: str, name_abbreviation: str):
        """Deprecated misspelled alias for :meth:`create_device`.

        .. deprecated::
            Use :meth:`create_device` instead; this alias is retained for backward
            compatibility and will be removed in a future release.
        """
        warnings.warn(
            "AdminMenu.greate_device is deprecated; use create_device instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.create_device(first_name, last_name, name_abbreviation)