from chemotion_api.connection import Connection


class AdminMenu:
    def __init__(self, session: Connection):
        self._session = session

    def greate_device(self, first_name: str, last_name: str, name_abbreviation: str):
        payload = {'first_name': first_name,
                   'last_name': last_name,
                   'rootType': "Device",
                   "name_abbreviation": name_abbreviation}

        res = self._session.post('/api/v1/admin/group_device/create',
                                 headers=self._session.get_default_session_header(),
                                 data=payload)

        if res.status_code == 401:
            raise PermissionError('Not allowed to greate device (only Admin)')
        elif res.status_code != 201 and res.status_code != 200:
            raise ConnectionError(f"Error ({res.status_code}) \n{res.text}")

        return res.json()