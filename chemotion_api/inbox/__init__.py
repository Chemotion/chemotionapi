"""Access the Chemotion inbox: uploaded files awaiting assignment to elements.

The inbox holds attachments grouped by sender box plus a set of unsorted (unlinked) attachments.
:class:`Inbox` is the entry point; :class:`SenderBox` lazily loads one box's attachments; and
:class:`UniqueDict` keeps duplicate filenames distinct by suffixing them.
"""
import os
import uuid
from typing import cast

from chemotion_api.connection import Connection
from chemotion_api.elements.attachments import Attachment
import magic

class UniqueDict(dict):
    """A ``dict`` that never overwrites a key: duplicates get a ``_2``, ``_3``, ... suffix."""

    def __setitem__(self, key, value):
        """Insert ``value`` under ``key``, suffixing the key to keep it unique if it already exists."""
        # optional processing here
        org_key = key
        idx = 1
        while key in self:
            idx += 1
            key = f'{org_key}_{idx}'
        super().__setitem__(key, value)

class SenderBox:
    """One inbox sender box; its attachments are loaded lazily and paginated on access.

    :param con: an authenticated :class:`~chemotion_api.connection.Connection`.
    :param json_data: the box's summary JSON (must contain its ``id``).
    """

    def __init__(self, con: Connection, json_data: dict):
        self._content: UniqueDict | None = None
        self._con = con
        self._json_data = json_data

    @property
    def attachments(self) -> UniqueDict:
        """The box's attachments as ``{child_name: {filename: Attachment}}``, loaded on first access."""
        if self._content is None:
            self.load()
        return cast("UniqueDict", self._content)


    def load(self):
        """Fetch all pages of this box's containers and populate :attr:`attachments`.

        :raises ConnectionError: if a page cannot be fetched.
        """
        self._content = UniqueDict()
        page = 0
        content_length = -1
        while content_length != 0:
            page += 1
            res = self._con.get(f'/api/v1/inbox/containers/{self._json_data["id"]}?dataset_page={page}&sort_column=name')
            if res.status_code != 200:
                raise ConnectionError(f"Inbox could not be fetched! {res} -> {res.status_code}")
            json_res = res.json()['inbox']
            content_length = len(json_res['children'])
            for child in json_res['children']:
                att_dict = UniqueDict()
                for att in child['attachments']:
                    att_dict[att['filename']] = Attachment(self._con, att)

                self._content[child['name']] = att_dict


class Inbox:
    """The user's inbox: sender boxes plus unsorted (unlinked) attachments.

    :param con: an authenticated :class:`~chemotion_api.connection.Connection`.
    """

    def __init__(self, con: Connection):
        self._content: UniqueDict | None = None
        self._unsorted_content: UniqueDict | None = None
        self._con = con

    @property
    def sorted_boxs(self) -> UniqueDict:
        """The sender boxes as ``{box_name: SenderBox}``, loaded on first access."""
        if self._content is None:
            self.load()
        return cast("UniqueDict", self._content)

    @property
    def unsorted_attachments(self) -> UniqueDict:
        """The unlinked attachments as ``{filename: Attachment}``, loaded on first access."""
        if self._content is None:
            self.load()
        return cast("UniqueDict", self._unsorted_content)

    def load(self):
        """Fetch all pages of the inbox, populating sender boxes and unsorted attachments.

        :raises ConnectionError: if a page cannot be fetched.
        """
        page = 0
        max_page = 1
        per_page = 20
        json_res = {}
        self._content = UniqueDict()
        self._unsorted_content = UniqueDict()
        while page < max_page:
            page += 1
            res = self._con.get(f'/api/v1/inbox?cnt_only=false&page={page}&per_page={per_page}&sort_column=name')
            if res.status_code != 200:
                raise ConnectionError(f"Inbox could not be fetched! {res} -> {res.status_code}")
            json_res = res.json()['inbox']
            max_page = 1 + json_res['count'] // per_page
            for child in json_res['children']:
                self._content[child['name']] = SenderBox(self._con, child)
        for child in json_res['unlinked_attachments']:
            self._unsorted_content[child['filename']] = Attachment(self._con, child)

    def upload(self, file_path: str):
        """Upload a local file into the inbox as an unlinked attachment.

        The file's MIME type is detected with ``libmagic``.

        :param file_path: path to the local file to upload.
        :return: the raw server response.
        """
        param_name = uuid.uuid4().__str__()
        file_magic = magic.Magic(mime=True)

        files = [(param_name, (os.path.basename(file_path), open(file_path, 'rb'), file_magic.from_file(file_path)))]
        res = self._con.post('/api/v1/attachments/upload_to_inbox', data={}, files=files)
        return res

