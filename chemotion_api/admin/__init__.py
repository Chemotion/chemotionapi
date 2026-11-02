import warnings

from chemotion_api.connection import Connection


class AdminMenu:
    def __init__(self, session: Connection):
        self._session = session

    def greate_device(self, first_name: str, last_name: str, name_abbreviation: str):
        """Deprecated misspelling of :meth:`create_device`.

        Kept so existing callers keep working; it warns and delegates.
        """
        warnings.warn(
            "AdminMenu.greate_device is a misspelling and will be removed; "
            "use AdminMenu.create_device instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.create_device(first_name, last_name, name_abbreviation)

    def create_device(self, first_name: str, last_name: str, name_abbreviation: str):
        payload = {'first_name': first_name,
                   'last_name': last_name,
                   'rootType': "Device",
                   "name_abbreviation": name_abbreviation}

        res = self._session.post('/api/v1/admin/group_device/create',
                                 headers=self._session.get_default_session_header(),
                                 data=payload)

        if res.status_code == 401:
            raise PermissionError('Not allowed to create a device (only Admin)')
        elif res.status_code != 201 and res.status_code != 200:
            raise ConnectionError(f"Error ({res.status_code}) \n{res.text}")

        return res.json()