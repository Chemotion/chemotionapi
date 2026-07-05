"""Attachment containers for elements and datasets, with chunked upload and streaming download."""
import contextlib
import hashlib
import json
import os
import uuid
from collections import OrderedDict
from collections.abc import Sequence, Iterator
from typing import cast, overload
import magic
import requests

from chemotion_api.connection import Connection
from chemotion_api.utils import safe_download_filename
from chemotion_api.elements.analyses_manager import AnalysesManager


class Attachment(dict):
    """
    Attachment are a dict object to read one attachment of an element.
    It allows to load Attachments as bytes or save it to a file.

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

    def __init__(self, con: Connection, data: dict[str, str]):
        self._con = con
        super().__init__(data)

    def load_file(self) -> bytes:
        """
        Loads an attachment file as binary object.

        The whole file is held in memory (that is this method's contract);
        use :meth:`iter_file` to stream large attachments instead.

        :return:  file as binary object
        """
        return b''.join(self.iter_file())

    def iter_file(self, chunk_size: int = 1 << 20) -> Iterator[bytes]:
        """Stream the attachment file in chunks instead of loading it fully into memory.

        :param chunk_size: bytes per chunk (default 1 MiB).
        :yields: successive byte chunks of the file.
        """
        res = self._con.get(f"/api/v1/attachments/{self['id']}", stream=True)
        if res.status_code != 200:
            res.close()
            raise ConnectionError(f'{res.status_code} -> {res.text}')
        try:
            for chunk in res.iter_content(chunk_size=chunk_size):
                if chunk:
                    yield chunk
        finally:
            res.close()

    def save_file(self, directory: str = '.') -> str:
        """
        Loads an attachment file to your local filesystem

        :param directory: path to the directory where the file shell be saved

        :return: full path to the file
        """
        if not os.path.isdir(directory):
            raise NotADirectoryError(f"{directory} is not a directory")
        # the filename comes from server JSON — reduce it to a safe basename so it
        # cannot escape the target directory (e.g. '../../x' or an absolute path)
        file_path = os.path.join(directory, safe_download_filename(self['filename'], f"attachment_{self['id']}"))
        with open(file_path, 'wb+') as f:
            for chunk in self.iter_file():
                f.write(chunk)

        return os.path.abspath(file_path)


class Attachments(Sequence):
    """
    Attachments is a container object to manage (read/write) all attachments of an element.
    Each attachemnt is a :class:`chemotion_api.elements.attachments.Attachment`.
    It allows to load Attachments or add new ones.
    Attachment can be iterated!


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
    @overload
    def __getitem__(self, index: int) -> Attachment: ...

    @overload
    def __getitem__(self, index: slice) -> list[Attachment]: ...

    def __getitem__(self, index):
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
        Loads an attachment from the server. One of the parameters Id, Identifier or filename must be set in order to find the desired attachment.
        If Id is set, all other parameters are ignored; if Identifier is set, filename is ignored.

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
            raise ValueError('Either id or identifier must be not None!')

        for attachment in self._attachment_data:
            if attachment[key] == identifier:
                return attachment
        raise ValueError(f'{key} {identifier} not found!')

    def add_file(self, file_path: str) -> dict:
        """
        Adds a file to the elements attachment container

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

    def save(self, id: int, element_type: str) -> requests.Response | None:
        """
        Updates or creates the Attachments of an Element after saving it!

        Queued files are uploaded once: the upload queue is cleared after a successful
        request, so calling ``save()`` again does not create duplicate attachments.

        :param id: ID of the element
        :param element_type: must be in 'Element' or 'ResearchPlan'

        :return: response of the request
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
        self._mark_uploads_done()
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
        self._mark_uploads_done()
        return res

    def _mark_uploads_done(self):
        """Move freshly uploaded attachment data into the regular list and clear the queue."""
        self._attachment_data += [Attachment(self._con, x) for x in self._new_attachment_data]
        self._new_attachment_data = []
        self._to_uploads = []

class MutableAttachments(Attachments):
    """
    Same as :class:`chemotion_api.elements.attachments.Attachments` only add File is not allowed.
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

    def save(self, id: int = -1, element_type: str = '') -> requests.Response | None:
        """
        Upload all queued files via :meth:`AnalysesManager.upload_file`.

        The upload queue is cleared afterwards, so calling ``save()`` again does not
        re-upload the same files.

        :param id: unused (kept for signature compatibility with :meth:`Attachments.save`)
        :param element_type: unused (kept for signature compatibility)

        :return: None
        """
        for x in self._to_uploads:
            AnalysesManager.upload_file(self._con, x['file_path'], x['file_uuid'])
        self._mark_uploads_done()
        return None
