"""Manage an element's analyses and datasets, including file upload and download."""
import hashlib
import json
import os
import uuid

from chemotion_api.utils import resource_path

MAX_UPLOAD_SIZE = 5000


class AnalysesManager:
    """Helpers to build empty analysis/dataset JSON and to upload dataset files in chunks."""

    @staticmethod
    def build_new_analyses():
        """
        Build a fresh, empty analysis JSON payload with a new UUID.

        :return: A new analysis dict
        """
        json_path = os.path.join(resource_path(__file__), 'empty_elements/analyses.json')
        data = {}
        if os.path.exists(json_path):
            with open(json_path) as f:
                data = json.loads(f.read())
        data['id'] = uuid.uuid4().__str__()
        return data

    @staticmethod
    def build_new_dataset():
        """
        Build a fresh, empty dataset JSON payload with a new UUID.

        :return: A new dataset dict
        """
        json_path = os.path.join(resource_path(__file__), 'empty_elements/dataset.json')
        data = {}
        if os.path.exists(json_path):
            with open(json_path) as f:
                data = json.loads(f.read())
        data['id'] = uuid.uuid4().__str__()
        return data

    @staticmethod
    def upload_file(session, file_path: str, file_uuid: str):
        """
        Upload a file to the server in chunks and finalize it with an MD5 checksum.

        :param session: the connection used to issue the upload requests
        :param file_path: path to the local file to upload
        :param file_uuid: the attachment key/UUID the chunks are uploaded under

        :return: the upload-completion payload (key, filename and checksum)

        :raises PermissionError: if the server rejects a chunk with a 401 status
        :raises ConnectionError: if any chunk or the completion request fails
        """
        with open(file_path, 'rb') as f:
            body = f.read()
            file_name = os.path.basename(file_path)
            key = file_uuid
            snippet = 0
            counter = 0
            hash_md5 = hashlib.md5()
            while snippet < len(body):
                start_snippet = snippet
                snippet += MAX_UPLOAD_SIZE
                file_chunk = body[start_snippet:snippet]
                hash_md5.update(file_chunk)
                payload = {'file': (file_name, file_chunk)}
                res = session.post('/api/v1/attachments/upload_chunk', data={'key': key, 'counter': counter},
                                   files=payload)
                counter += 1
                if res.status_code == 401:
                    raise PermissionError('Not allowed to delete device (Only for super devices or admins)')
                elif (res.status_code != 200 and res.status_code != 201):
                    raise ConnectionError()
            data = {'key': key, 'filename': file_name, 'checksum': hash_md5.hexdigest()}
            res = session.post('/api/v1/attachments/upload_chunk_complete',
                               data=data)
            if res.status_code == 401:
                raise PermissionError('Not allowed to delete device (Only for super devices or admins)')
            elif (res.status_code != 200 and res.status_code != 201):
                raise ConnectionError(f'{res.status_code} -> {res.text}')

            return data
