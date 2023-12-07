import hashlib
import uuid

from requests.exceptions import ConnectionError
from chemotion_api.connection import Connection

MAX_UPLOAD_SIZE = 5000


class User:
    id: int = None
    name: str = None
    email: str = None
    user_type: str = None

    @classmethod
    def load_me(cls, session: Connection):
        user_url = '/api/v1/users/current.json'
        res = session.get(user_url)
        if res.status_code == 401:
            raise PermissionError('Not allowed to fetch user (Login first)')
        elif res.status_code != 200:
            raise ConnectionError('{} -> {}'.format(res.status_code, res.text))
        data = res.json()['user']

        if cls._is_device(data['type']):
            user = Device(session)
        elif cls._is_admin(data['type']):
            user = Admin(session)
        elif cls._is_group(data['type']):
            user = Group(session)
        else:
            user = Person(session)

        user.populate(data)

        return user

    def __init__(self, session: Connection):
        self._session = session
        self.devices = []
        self.groups = []

    def populate(self, json_contnet):
        self.user_type = json_contnet.get('type')
        for (key, val) in json_contnet.items():
            if hasattr(self, key):
                setattr(self, key, val)
        return self

    def is_admin(self):
        return self._is_admin(self.user_type)

    def is_device(self):
        return self._is_device(self.user_type)

    def is_group(self):
        return self._is_group(self.user_type)

    @classmethod
    def _is_admin(cls, type):
        return type.lower() == 'admin'

    @classmethod
    def _is_device(cls, type):
        return type.lower() == 'device'

    @classmethod
    def _is_group(cls, type):
        return type.lower() == 'group'


class Person(User):
    samples_count: int = None
    reactions_count: int = None
    reaction_name_prefix: str = None
    layout: dict[str:str] = None
    unconfirmed_email: str = None
    confirmed_at: str = None
    current_sign_in_at: str = None
    locked_at = None
    is_templates_moderator: bool = None
    molecule_editor: bool = None
    account_active: bool = None
    matrix: int = None
    counters: dict[str:str] = None
    generic_admin: dict[str:bool] = None
    initials: str = None
    first_name: str = None
    last_name: str = None


class Admin(Person):
    def fetchDevices(self):
        d_list = self.fetchGroupAndDevice('Device')
        self.devices = [Device(self._session).populate(x | {'type': type}) for x in d_list]

    def fetchGroups(self):
        g_list = self.fetchGroupAndDevice('Group')
        self.groups = [Device(self._session).populate(x | {'type': type}) for x in g_list]

    def fetchGroupAndDevice(self, type):
        user_url = f'/api/v1/admin/group_device/list?type={type}'
        res = self._session.get(user_url)
        if res.status_code == 401:
            raise PermissionError('Not allowed to fetch user (Login first)')
        elif res.status_code != 200:
            raise ConnectionError('{} -> {}'.format(res.status_code, res.text))

        return res.json()['list']


class Group(User):
    name_abbreviation: str = None


class Device(User):
    is_super_device: bool = None
    name_abbreviation: str = None

    def get_jwt(self):
        return DeviceManager(self._session).get_jwt_for_device(self.id)

    def delete(self):
        url = f"/api/v1/admin/group_device/update/{self.id}"
        res = self._session.put(url, data={
            "action": "RootDel",
            "rootType": "Device",
            "id": self.id,
            "destroy_obj": True,
            "rm_users": []
        })
        if res.status_code == 401:
            raise PermissionError('Not allowed to delete device (Only for super devices or admins)')
        elif res.status_code != 200:
            raise ConnectionError('{} -> {}'.format(res.status_code, res.text))



    def upload_file(self, file_path: str):
        with open(file_path, 'rb') as f:
            body = f.read()

            key = uuid.uuid1().__str__()
            snippet = 0
            counter = 0
            hash_md5 = hashlib.md5()
            while snippet < len(body):
                start_snippet = snippet
                snippet += MAX_UPLOAD_SIZE
                file_chunk = body[start_snippet:snippet]
                hash_md5.update(file_chunk)
                payload = {'file': (file_path, file_chunk)}
                res = self._session.post('/api/v1/attachments/upload_chunk', headers=self._session.get_default_session_header(), data={'key': key, 'counter': counter}, files=payload)
                counter += 1
                if res.status_code == 401:
                    raise PermissionError('Not allowed to delete device (Only for super devices or admins)')
                elif (res.status_code != 200 and res.status_code != 201):
                    raise ConnectionError()
            res = self._session.post('/api/v1/attachments/upload_raw_chunk_complete', data={'key': key, 'filename': file_path, 'checksum': hash_md5.hexdigest()})
            if res.status_code == 401:
                raise PermissionError('Not allowed to delete device (Only for super devices or admins)')
            elif (res.status_code != 200 and res.status_code != 201):
                raise ConnectionError()




class DeviceManager:
    def __init__(self, session: Connection):
        self._session = session

    def get_jwt_for_device(self, id: int):
        user_url = f'/api/v1/devices/remote/jwt/{id}'
        res = self._session.get(user_url)
        if res.status_code == 401:
            raise PermissionError('Not allowed to fetch JWT (Only for super devices or admins)')
        elif res.status_code != 200:
            raise ConnectionError('{} -> {}'.format(res.status_code, res.text))

        return res.json()['token']

    def create_new_device(self, first_name: str, last_name: str, name_abbreviation: str, email: str = None) -> Device:
        user_url = f'/api/v1/devices/remote/create'
        data = {
            'first_name': first_name,
            'last_name': last_name,
            'name_abbreviation': name_abbreviation,
        }
        if  email is not None: data['email'] = email
        res = self._session.post(user_url, data = data)
        if res.status_code == 401:
            raise PermissionError('Create device not is allowed! (Only for super devices or admins)')
        elif res.status_code != 201 or res.json().get('error') is not None:
            raise ConnectionError('{} -> {}'.format(res.status_code, res.text))

        return Device(self._session).populate(res.json())