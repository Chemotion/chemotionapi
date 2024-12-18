import os
import uuid

from chemotion_api.connection import Connection
from chemotion_api.elements.attachments import Attachment
import magic

class UniqueDict(dict):

    def __setitem__(self, key, value):
        # optional processing here
        org_key = key
        idx = 1
        while key in self:
            idx += 1
            key = f'{org_key}_{idx}'
        super().__setitem__(key, value)

class SenderBox:
    def __init__(self, con: Connection, json_data: dict):
        self._content = None
        self._con = con
        self._json_data = json_data

    @property
    def attachments(self) -> UniqueDict[str:UniqueDict[str:Attachment]] :
        if self._content is None:
            self.load()
        return self._content


    def load(self):
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
    def __init__(self, con: Connection):
        self._content = None
        self._unsorted_content = None
        self._con = con

    @property
    def sorted_boxs(self) -> UniqueDict[str:SenderBox] :
        if self._content is None:
            self.load()
        return self._content

    @property
    def unsorted_attachments(self) -> UniqueDict[str:Attachment] :
        if self._content is None:
            self.load()
        return self._unsorted_content

    def load(self):
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
        param_name = uuid.uuid4().__str__()
        file_magic = magic.Magic(mime=True)

        files = [(param_name, (os.path.basename(file_path), open(file_path, 'rb'), file_magic.from_file(file_path)))]
        res = self._con.post('/api/v1/attachments/upload_to_inbox', data={}, files=files)
        return res

