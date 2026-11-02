"""Attachment containers for elements and datasets, with chunked upload and streaming download."""
import contextlib
import hashlib
import json
import os
import uuid
from collections import OrderedDict
from collections.abc import Sequence, Iterator
from typing import cast

from chemotion_api.utils import safe_join
import magic
import requests

from chemotion_api.connection import Connection
from chemotion_api.elements.analyses_manager import AnalysesManager
from chemotion_api.utils import AttrAccessMixin


class Attachment(AttrAccessMixin, dict):
    """
    An Attachment is a dict object to read one attachment of an element.
    It allows to load Attachments as bytes or save it to a file. Its keys (e.g. ``id``, ``filename``) can be
    read as attributes as well: ``att.filename`` is ``att['filename']``.

    Usage::

    >>> from chemotion_api import Instance
    >>> import logging
    >>> try:
    >>>     instance = Instance('http(d)://xxx.xxx.xxx').test_connection().login('<USER>', "<PASSWORD>")
    >>> except ConnectionError as e:
    >>>     logging.error(f"A connection to Chemotion ({instance.host_url}) cannot be established")
    >>> rp = instance.get_generic_by_label('My Generic',1)
    >>> att = rp.attachments
    >>> att.load_attachment(filename='MyAttachment.txt').save_file('.')

    :param con: Host connection object.
    :param data: attachment information (from the sever)
    """

    @property
    def previewable(self) -> bool | None:
        """Whether the server can render a preview thumbnail for this attachment.

        Added to the attachment entity in ELN v4.0.0. Read-only and server-computed; ``None`` when
        the server did not say, which is not the same as "no".
        """
        value = self.get('previewable')
        return value if isinstance(value, bool) else None

    def __init__(self, con: Connection, data: dict[str, str]):
        self._con = con
        super().__init__(data)

    def load_file(self) -> bytes:
        """
        Loads an attachment file as binary object

        :return:  file as binary object
        """
        res = self._con.get(f"/api/v1/attachments/{self['id']}")
        if res.status_code != 200:
            raise ConnectionError(f'{res.status_code} -> {res.text}')

        return res.content

    def iter_file(self, chunk_size: int = 1 << 20) -> Iterator[bytes]:
        """Stream the attachment file in chunks instead of loading it fully into memory.

        :param chunk_size: bytes per chunk (default 1 MiB).
        :yields: successive byte chunks of the file.
        """
        res = self._con.get(f"/api/v1/attachments/{self['id']}", stream=True)
        if res.status_code != 200:
            # Read the body *before* closing: with stream=True nothing has been consumed yet, and
            # `.text` on a closed response comes back empty, losing the server's error message.
            body = res.text
            res.close()
            raise ConnectionError(f'{res.status_code} -> {body}')
        try:
            for chunk in res.iter_content(chunk_size=chunk_size):
                if chunk:
                    yield chunk
        finally:
            res.close()

    def save_file(self, directory: str = '.') -> str:
        """
        Loads an attachment file to your local filesystem

        :param directory: path to the directory where the file shall be saved

        :return: full path to the file

        :raises NotADirectoryError: if the directory does not exist
        """
        if not os.path.isdir(directory):
            raise NotADirectoryError(f"{directory} is not a directory")
        res = self._con.get(f"/api/v1/attachments/{self['id']}")
        if res.status_code != 200:
            raise ConnectionError(f'{res.status_code} -> {res.text}')
        # The filename comes from the server record, so it is data, not a trusted path.
        file_path = safe_join(directory, self['filename'])
        with open(file_path, 'wb+') as f:
            f.write(res.content)

        return os.path.abspath(file_path)


class Attachments(Sequence):
    """
    Attachments is a container object to manage (read/write) all attachments of an element.
    Each attachment is a :class:`chemotion_api.elements.attachments.Attachment`.
    It allows to load Attachments or add new ones.
    Attachments can be iterated and indexed!


    Usage::

    >>> from chemotion_api import Instance
    >>> import logging
    >>> try:
    >>>     instance = Instance('http(d)://xxx.xxx.xxx').test_connection().login('<USER>', "<PASSWORD>")
    >>> except ConnectionError as e:
    >>>     logging.error(f"A connection to Chemotion ({instance.host_url}) cannot be established")
    >>> rp = instance.get_research_plan(1)
    >>> att = rp.attachments
    >>> att.load_attachment(filename='MyAttachment.txt')
    >>> att.add_file('./MySecondAttachment.txt')
    >>> rp.save()

    :param con: Host connection object.
    :param attachment_data: list of attachment information (from the sever)
    """

    def __init__(self, con: Connection, attachment_data: list[dict] | None = None):
        super().__init__()
        if attachment_data is None:
            attachment_data = []
        self._attachment_data = [Attachment(con, x) for x in attachment_data]
        self._new_attachment_data: list = []
        self._con = con
        self._to_uploads: list = []             # Direct inheritance

            # Extra method not required by the ABC
    def __getitem__(self, index: int) -> Attachment:  # type: ignore[override]
        return self.attachment_data[index]
    def __len__(self):
        return len(self.attachment_data)

    @property
    def attachment_data(self) -> list:
        """
        The Attachment data contains all information needed to save the Attachments.

        :return: List of all attachment data
        """
        return self._attachment_data + self._new_attachment_data

    def load_attachment(self, id: str | int | None = None, identifier: str | None = None,
                        filename: str | None = None) -> Attachment:
        """
        Finds an attachment. One of the parameters Id, Identifier or filename must be set in order to find the desired attachment.
        If Id is set, all other parameters are ignored; if Identifier is set, filename is ignored.
        Only saved attachments are found: reload the element after adding a file (``element.save(True)``).

        :param id: DB id of the attachment
        :param identifier: UUID of the attachment
        :param filename: name of the attachment

        :raises ValueError: If no file fits the parameters.

        :return: Attachment Object
        """
        if id is not None:
            key = 'id'
            identifier = cast("str | None", id)
        elif identifier is not None:
            key = 'identifier'
        elif filename is not None:
            key = 'filename'
            identifier = filename
        else:
            raise ValueError(f'Either id or identifier must be not None!')

        for attachment in self._attachment_data:
            if attachment[key] == identifier:
                return attachment
        raise ValueError(f'{key} {identifier} not found!')

    def add_file(self, file_path: str) -> dict:
        """
        Adds a file to the elements attachment container. The file is uploaded when the element is saved.

        :param file_path: Path to the file to be uploaded on your device

        :return: a summary of the file
        """
        filename = os.path.basename(file_path)
        file_uuid = uuid.uuid4().__str__()
        file_magic = magic.Magic(mime=True)
        with open(file_path, 'rb') as f:
            upload_file_obj = {
                'file_uuid': file_uuid,
                'file_path': file_path,
                'filename': filename,
                'mime_type': file_magic.from_file(file_path)

            }
            chunk = f.read()

            f.close()
            data: dict[str, object] = OrderedDict(file={"preview": f"{self._con.host_url}/images/wild_card/not_available.svg"},
                               name=filename,
                               filename=filename,
                               is_deleted=False,
                               _preview="/images/wild_card/not_available.svg",
                               is_image_field=filename.lower().endswith(
                                   ('.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.gif')),
                               filesize=len(chunk),
                               id=file_uuid,
                               is_new=True)
            data_hash_str = json.dumps(data, separators=(',', ':'))
            data_hash = hashlib.sha256(data_hash_str.encode()).hexdigest()
            data = dict(data)
            data["_checksum"] = data_hash
            data["identifier"] = file_uuid

            self._to_uploads.append(upload_file_obj)
            self._new_attachment_data.append(data)
            return data

    def save(self, id: int, element_type: str) -> requests.Response:
        """
        Updates or creates the Attachments of an Element after saving it!

        Queued files are uploaded once: the upload queue is cleared only after a successful
        (2xx) request, so calling ``save()`` again after a failed upload resends the pending
        files instead of silently losing them.

        :param id: ID of the element
        :param element_type: attachable type in CamelCase, e.g. 'Element' (generic elements), 'ResearchPlan' or 'Sample'

        :return: response of the request

        :raises requests.RequestException: if the server returns a non-2xx response; the
            upload queue is left intact so a retried ``save()`` resends the pending files.
        """
        if element_type == 'Element':
            return self._save_generic(id)
        with contextlib.ExitStack() as stack:
            files = [('files[]', (x['filename'], stack.enter_context(open(x['file_path'], 'rb')), x['mime_type']))
                     for x in self._to_uploads]
            data = {'attfilesIdentifier[]': [x['file_uuid'] for x in self._to_uploads],
                    'attachable_type': element_type,
                    'attachable_id': id}
            res = self._con.post('/api/v1/attachable/update_attachments_attachable', data=data, files=files)
        self._raise_or_mark_done(res)
        return res

    def _save_generic(self, id: int):
        with contextlib.ExitStack() as stack:
            files = [('attfiles[]', (x['filename'], stack.enter_context(open(x['file_path'], 'rb')), x['mime_type']))
                     for x in self._to_uploads]
            data = {'attfilesIdentifier[]': [x['file_uuid'] for x in self._to_uploads],
                    'att_type': 'Element',
                    'att_id': id,
                    'seInfo': {}}
            res = self._con.post('/api/v1/generic_elements/upload_generics_files', data=data, files=files)
        self._raise_or_mark_done(res)
        return res

    def _raise_or_mark_done(self, res: requests.Response | None) -> None:
        """Move the upload queue into ``_attachment_data`` only on a successful (2xx) response.

        On failure (or no response at all) the queue is left untouched and a
        ``RequestException`` is raised, so the caller can retry ``save()`` without losing or
        duplicating the pending uploads.
        """
        # Any 2xx, not just 200/201: the endpoint may legitimately answer 204 No Content, and
        # treating that as a failure would raise *after* the upload had actually succeeded — then
        # the retry would upload everything a second time.
        if res is not None and 200 <= res.status_code < 300:
            self._mark_uploads_done()
            return
        status = res.status_code if res is not None else "no response"
        body = res.text if res is not None else ""
        raise requests.RequestException(
            f"Failed to upload attachments (status: {status}): {body}")

    def _mark_uploads_done(self):
        """Move freshly uploaded attachment data into the regular list and clear the queue."""
        self._attachment_data += [Attachment(self._con, x) for x in self._new_attachment_data]
        self._new_attachment_data = []
        self._to_uploads = []

class MutableAttachments(Attachments):
    """
    Attachments of an analysis dataset. Same as :class:`chemotion_api.elements.attachments.Attachments`, but
    files can only be added through :meth:`chemotion_api.elements.abstract_element.Analyses.add_dataset`.
    """

    def __init__(self, con: Connection, attachment_data: list[dict] | None = None, *file_paths: str):
        super().__init__(con, attachment_data)
        for fp in file_paths:
            super().add_file(fp)

    def add_file(self, file_path: str) -> dict:
        """Adding files this way is not allowed for :class:`MutableAttachments`.

        :param file_path: ignored

        :raises NotImplementedError: always, since add_file is disabled here
        """
        raise NotImplementedError("In a MutableAttachments add_file is not allowed")

    def save(self, id: int = -1, element_type: str = '') -> requests.Response | None:  # type: ignore[override]
        """
        Upload all queued files via :meth:`AnalysesManager.upload_file`.

        :param id: unused (kept for signature compatibility with :meth:`Attachments.save`)
        :param element_type: unused (kept for signature compatibility)

        :return: None

        :raises ConnectionError: from :meth:`AnalysesManager.upload_file` if an upload fails, in
            which case the queue is left intact so the save can be retried.
        """
        for x in self._to_uploads:
            AnalysesManager.upload_file(self._con, x['file_path'], x['file_uuid'])
        # `Attachments.save` was hardened to clear the queue only on success; this override was
        # not, and cleared it never. `AbstractElement.save()` calls this through
        # `AnalysesList.save_attachments`, so every later save re-uploaded every file ever queued
        # on the dataset — N saves meant N copies server-side. `upload_file` raises on failure, so
        # reaching this line means all of them succeeded.
        self._mark_uploads_done()
        return None
