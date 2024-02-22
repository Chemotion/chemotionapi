import hashlib
import os
import uuid

import magic

from chemotion_api.connection import Connection


class Attachment(dict):

    def __init__(self, con: Connection, data: dict[str:str]):
        self._con = con
        super().__init__(data)

    def load_file(self) -> bytes:
        res = self._con.get(f"/api/v1/attachments/{self['id']}")
        if res.status_code != 200:
            raise ConnectionError('{} -> {}'.format(res.status_code, res.text))

        return res.content

    def save_file(self, directory: str = '.') -> str:
        if not os.path.isdir(directory):
            raise NotADirectoryError(f"{directory} is not a directory")
        res = self._con.get(f"/api/v1/attachments/{self['id']}")
        if res.status_code != 200:
            raise ConnectionError('{} -> {}'.format(res.status_code, res.text))
        file_path = os.path.join(directory, self['filename'])
        with open(file_path, 'wb+') as f:
            f.write(res.content)

        return os.path.abspath(file_path)


class Attachments:
    def __init__(self, con: Connection, attachment_data: list[dict]):
        if attachment_data is None:
            attachment_data = []
        self.attachment_data = [Attachment(con, x) for x in attachment_data]
        self._con = con
        self._to_uploads = []

    def load_attachment(self, id: str | int | None = None, identifier: str | None = None) -> Attachment:
        if identifier is not None and id is None:
            key = 'identifier'
        elif id is not None:
            key = 'id'
            identifier = id
        else:
            raise ValueError(f'Either id or identifier must be not None!')

        for attachment in self.attachment_data:
            if attachment[key] == identifier:
                return attachment
        raise ValueError(f'{key} {identifier} not found!')

    def add_file(self, file_path):
        filename = os.path.basename(file_path)
        hash_md5 = hashlib.md5()
        file_uuid = uuid.uuid4().__str__()
        file_magic = magic.Magic(mime=True)
        with open(file_path, 'rb') as f:
            upload_file_obj = {
                'file_uuid': file_uuid,
                'file_path': file_path,
                'filename': filename,
                'mime_type': file_magic.from_file(file_path)

            }
            while chunk := f.read(8192):
                hash_md5.update(chunk)

            f.close()
            data = {
                "file": {
                    "preview": f"blob:http://0.0.0.0:3000/{file_uuid}"
                },
                "name": filename,
                "filename": filename,
                "is_deleted": False,
                "_preview": "/images/wild_card/not_available.svg",
                "is_image_field": False,
                "filesize": 1367,
                "id": file_uuid,
                "is_new": True,
                "_checksum": hash_md5.hexdigest(),
                "identifier": file_uuid
            }
            self._to_uploads.append(upload_file_obj)
            return data

    def save(self, id: int):
        files = [('files[]', (x['filename'], open(x['file_path'], 'rb'), x['mime_type'])) for x in self._to_uploads]

        data = {'attfilesIdentifier[]': [x['file_uuid'] for x in self._to_uploads],
                'attachable_type': 'ResearchPlan',
                'attachable_id': id}
        res = self._con.post('/api/v1/attachable/update_attachments_attachable', data=data, files=files)
        return res
