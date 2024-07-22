import hashlib
import json
import os
import uuid

MAX_UPLOAD_SIZE = 5000


class AnalysesManager():
    @staticmethod
    def build_new_analyses():
        json_path = os.path.join(os.path.dirname(__file__), 'empty_elements/analyses.json')
        data = {}
        if os.path.exists(json_path):
            with open(json_path, 'r') as f:
                data = json.loads(f.read())
        data['id'] = uuid.uuid4().__str__()
        return data

    @staticmethod
    def build_new_dataset():
        json_path = os.path.join(os.path.dirname(__file__), 'empty_elements/dataset.json')
        data = {}
        if os.path.exists(json_path):
            with open(json_path, 'r') as f:
                data = json.loads(f.read())
        data['id'] = uuid.uuid4().__str__()
        return data

    @staticmethod
    def upload_file(session, file_path: str, file_uuid: str):
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
