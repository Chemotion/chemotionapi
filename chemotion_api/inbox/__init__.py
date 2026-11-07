import os
import uuid

from chemotion_api.connection import Connection, request_error
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
            # Ceiling, not 1 + floor: at an exact multiple of per_page the extra page is out of range,
            # and the server answers an out-of-range page with page 1 again, duplicating every box.
            max_page = max(1, -(-json_res['count'] // per_page))
            for child in json_res['children']:
                self._content[child['name']] = SenderBox(self._con, child)
        for child in json_res['unlinked_attachments']:
            self._unsorted_content[child['filename']] = Attachment(self._con, child)

    def upload(self, file_path: str):
        param_name = uuid.uuid4().__str__()
        file_magic = magic.Magic(mime=True)

        with open(file_path, 'rb') as fh:
            files = [(param_name, (os.path.basename(file_path), fh, file_magic.from_file(file_path)))]
            res = self._con.post('/api/v1/attachments/upload_to_inbox', data={}, files=files)
        if not 200 <= res.status_code < 300:
            raise request_error(res, f'uploading {os.path.basename(file_path)} to the inbox')
        return res

    def unlinked_attachments(self, sort_by: str = 'name') -> list[Attachment]:
        """The files in your inbox that are in no sender box (``GET /api/v1/inbox/unlinked_attachments``),
        e.g. those from :meth:`upload`.

        :param sort_by: ``'name'`` or ``'created_at'`` (newest first).
        """
        if sort_by not in ('name', 'created_at'):
            raise ValueError("sort_by is 'name' or 'created_at'.")
        res = self._con.get('/api/v1/inbox/unlinked_attachments', params={'sort_column': sort_by})
        if res.status_code != 200:
            raise request_error(res, 'loading the unlinked inbox attachments')
        data = res.json() or {}
        data = data.get('inbox', data)  # the listing comes wrapped in {'inbox': ...}
        return [Attachment(self._con, a) for a in data.get('unlinked_attachments') or []]

    def search_samples(self, query: str) -> list[dict]:
        """Your samples matching ``query`` (short label or name), as the inbox's *assign* search
        finds them: ``{'id', 'name', 'short_label', 'type'}`` dicts, where ``type`` is the sample's
        role in a reaction (``'Product'``, …) or ``None``."""
        return self._search('samples', query)

    def search_reactions(self, query: str) -> list[dict]:
        """Your reactions matching ``query`` (short label or name), as the inbox's *assign* search
        finds them: ``{'id', 'name', 'short_label', 'type', 'variation'}`` dicts. A query ending in
        ``-v<n>`` also returns that variation number."""
        return self._search('reactions', query)

    def _search(self, kind: str, query: str) -> list[dict]:
        if not query:
            return []
        res = self._con.get(f'/api/v1/inbox/{kind}', params={'search_string': query})
        if res.status_code != 200:
            raise request_error(res, f'searching {kind} for the inbox')
        return res.json().get(kind) or []

    def assign(self, attachment: Attachment | int, element, variation: int | None = None) -> dict:
        """Move an inbox file onto a sample or reaction, as dropping it on the element in the UI does.

        ``POST /api/v1/inbox/samples/:id`` or ``/inbox/reactions/:id``. The server creates a new
        analysis on the element, named after the file (without extension), with one dataset holding
        the file. Reload the element to see it.

        :param attachment: an inbox attachment (from :attr:`sorted_boxs`,
            :attr:`unsorted_attachments` or :meth:`unlinked_attachments`), or its id.
        :param element: a saved :class:`~chemotion_api.elements.Sample` or
            :class:`~chemotion_api.elements.Reaction`.
        :param variation: for a reaction, the id of a variation to link the new analysis to.
        :return: the new dataset container, as the server returns it.
        :raises PermissionError: if you may not edit the element, or the file is not in your inbox.
        """
        kind = getattr(element, 'element_type', None)
        if kind not in ('sample', 'reaction'):
            raise ValueError('Inbox files can be assigned to samples and reactions only.')
        if getattr(element, 'id', None) is None:
            raise ValueError(f'Save the {kind} before assigning files to it.')
        if variation is not None and kind != 'reaction':
            raise ValueError('Only reactions have variations.')
        attachment_id = attachment if isinstance(attachment, int) else attachment['id']
        body: dict = {'attachment_id': attachment_id}
        if variation is not None:
            body['variation'] = variation
        res = self._con.post(f'/api/v1/inbox/{kind}s/{element.id}', data=body)
        if res.status_code == 401:
            raise PermissionError(f'Cannot assign attachment {attachment_id} to {kind} {element.id}: '
                                  'you may not edit the element, or the file is not in your inbox.')
        if res.status_code == 404:
            raise ValueError(f'No such {kind} or attachment ({element.id}, {attachment_id}).')
        if res.status_code not in (200, 201):
            raise request_error(res, f'assigning attachment {attachment_id} to {kind} {element.id}')
        # The file has left the inbox; the cached listing is stale.
        self._content = self._unsorted_content = None
        return res.json()['container']
