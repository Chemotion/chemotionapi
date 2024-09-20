import abc
import hashlib
import json
import re
import uuid
from chemotion_api.connection import Connection


class User(abc.ABC):
    @classmethod
    def load_me(cls, session: Connection):
        user_url = '/api/v1/users/current.json'
        res = session.get(user_url)
        if res.status_code == 401:
            raise PermissionError('Not allowed to fetch user (Login first)')
        elif res.status_code != 200:
            raise ConnectionError('{} -> {}'.format(res.status_code, res.text))
        data = res.json()['user']
        return cls.factor_user(session, data)

    @classmethod
    def factor_user(cls, session: Connection, data: dict):
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
        self.id: int | None = None
        self.email: str | None = None
        self.user_type: str | None = None
        self.first_name: str | None = None
        self.last_name: str | None = None
        self.initials: str | None = None

    @property
    def name_abbreviation(self):
        return self.initials

    @name_abbreviation.setter
    def name_abbreviation(self, initials):
        self.initials = initials

    @property
    def name(self):
        if self.last_name is None:
            return self.first_name
        return f"{self.first_name} {self.last_name}"

    @name.setter
    def name(self, name):
        self.first_name = name

    def populate(self, json_contnet):
        self.user_type = json_contnet.get('type')
        for (key, val) in json_contnet.items():
            if hasattr(self, key):
                if re.match(r'^(\"[^\"]+\"=>\"[^\"]+\",? ?)*$', str(val)) is not None:
                    val = json.loads(f"{{ {val.replace('=>', ':')} }}")
                setattr(self, key, val)
        return self

    def is_admin(self):
        return self._is_admin(self.user_type)

    def is_device(self):
        return self._is_device(self.user_type)

    def is_group(self):
        return self._is_group(self.user_type)

    def is_person(self):
        return self._is_person(self.user_type)

    @classmethod
    def _is_admin(cls, type):
        return type.lower() == 'admin'

    @classmethod
    def _is_device(cls, type):
        return type.lower() == 'device'

    @classmethod
    def _is_group(cls, type):
        return type.lower() == 'group'

    @classmethod
    def _is_person(cls, type):
        return type.lower() == 'person'

    @classmethod
    def find_user_by_name(cls, _session: Connection, name: str) -> list:
        res = _session.get(f'/api/v1/users/name.json?name={name}&type=Person')
        if res.status_code != 200:
            raise ConnectionError(f"{res.status_code} -> {res.text}")
        return [Person(_session).populate(x) for x in res.json()["users"]]


class Group(User):

    def __init__(self, session: Connection):
        super().__init__(session)

    def add_users(self, *users: User):
        return self.add_users_by_id(*[u.id for u in users if u.is_person()])

    def populate(self, json_contnet):
        json_contnet['type'] = json_contnet.get('type', 'group')
        return super().populate(json_contnet)

    def add_users_by_id(self, *users: int):
        payload = {
            'destroy_group': False,
            'add_users': users,
            'id': self.id
        }
        res = self._session.put(f'/api/v1/groups/upd/{self.id}', data=payload)
        if res.status_code != 200:
            raise ConnectionError(f'{res.status_code} -> {res.text}')



class Person(User):

    def __init__(self, session: Connection):
        super().__init__(session)
        self.samples_count: int | None = None
        self.reactions_count: int | None = None
        self.reaction_name_prefix: str | None = None
        self.layout: dict[str:str] = None
        self.unconfirmed_email: str | None = None
        self.confirmed_at: str | None = None
        self.current_sign_in_at: str | None = None
        self.locked_at = None
        self.is_templates_moderator: bool | None = None
        self.molecule_editor: bool | None = None
        self.account_active: bool | None = None
        self.matrix: int | None = None
        self.counters: dict[str:str] | None = None
        self.generic_admin: dict[str:bool] = None

    def populate(self, json_contnet):
        json_contnet['type'] = json_contnet.get('type', 'person')
        return super().populate(json_contnet)

    def create_group(self, first_name: str, last_name: str, name_abbreviation: str) -> Group:
        data = {
            'group_param': {
                "first_name": first_name,
                "last_name": last_name,
                "name_abbreviation": name_abbreviation,
                "users": [
                    self.id
                ]
            }
        }
        url = "/api/v1/groups/create"
        res = self._session.post(url, data=data)
        if res.status_code != 201:
            raise ConnectionError(f'{res.status_code} -> {res.text}')
        data = res.json()
        if 'error' in data:
            raise ConnectionError(f'{res.text}')
        data['type'] = 'group'
        return Group(self._session).populate(data['group'])


class Device(User):

    def __init__(self, session: Connection):
        super().__init__(session)
        self.is_super_device: bool | None = None

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


class Admin(Person):

    def __init__(self, session: Connection):
        super().__init__(session)
        self.users: list[User] = []
        self.devices: list[Device] = []
        self.groups: list[Group] = []
        self.admins: list[Admin] = []

    def populate(self, json_contnet):
        json_contnet['type'] = json_contnet.get('type', 'admin')
        return super().populate(json_contnet)

    def fetchUsers(self):
        user_url = f'/api/v1/admin_user/listUsers/all.json'
        res = self._session.get(user_url)
        if res.status_code == 401:
            raise PermissionError('Not allowed to fetch user (Login first)')
        elif res.status_code != 200:
            raise ConnectionError('{} -> {}'.format(res.status_code, res.text))

        self.users: list[User] = []
        self.devices: list[Device] = []
        self.groups: list[Group] = []
        self.admins: list[Admin] = []
        for u_data in res.json()['users']:
            user = self.factor_user(self._session, u_data)
            if user.is_admin():
                self.admins.append(user)
            elif user.is_device():
                self.devices.append(user)
            elif user.is_group():
                self.groups.append(user)
            else:
                self.users.append(user)

    def create_device(self, first_name: str, last_name: str, name_abbreviation: str) -> Device:
        data = self._create_group_device(first_name=first_name, last_name=last_name,
                                         name_abbreviation=name_abbreviation, rootType='Device')
        return Device(self._session).populate(data)

    def create_group(self, first_name: str, last_name: str, name_abbreviation: str) -> Group:
        data = self._create_group_device(first_name=first_name, last_name=last_name,
                                         name_abbreviation=name_abbreviation, rootType='Group')
        return Group(self._session).populate(data)

    def create_person(self, first_name: str, last_name: str, name_abbreviation: str, password: str,
                      email: str) -> Person:
        data = {
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "name_abbreviation": name_abbreviation,
            "password": password,
            "type": "Person"
        }
        url = "/api/v1/admin/users/"
        res = self._session.post(url, data=data)
        if res.status_code != 201:
            raise ConnectionError(f'{res.status_code} -> {res.text}')

        return [x for x in self.find_user_by_name(self._session, f"{first_name} {last_name}") if
                x.name_abbreviation == name_abbreviation][0]

    def _create_group_device(self, first_name: str, last_name: str, name_abbreviation: str, rootType: str):
        url = '/api/v1/admin/group_device/create'
        group = dict(first_name=first_name, last_name=last_name, name_abbreviation=name_abbreviation, rootType=rootType)
        res = self._session.post(url, data=group)
        if res.status_code != 201:
            raise ConnectionError(f'{res.status_code} -> {res.text}')
        data = res.json()
        if 'error' in data:
            raise ConnectionError(f'{res.text}')
        return data

    def fetchDevices(self) -> list[Device]:
        u_type = 'Device'
        d_list = self.fetchGroupAndDevice(u_type)
        self.devices = [Device(self._session).populate(x | {'type': u_type}) for x in d_list]
        return self.devices

    def fetchGroups(self) -> list[Group]:
        u_type = 'Group'
        g_list = self.fetchGroupAndDevice(u_type)
        self.groups = [Group(self._session).populate(x | {'type': u_type}) for x in g_list]
        return self.groups

    def fetchGroupAndDevice(self, type: str) -> list[dict]:
        user_url = f'/api/v1/admin/group_device/list?type={type}'
        res = self._session.get(user_url)
        if res.status_code == 401:
            raise PermissionError('Not allowed to fetch user (Login first)')
        elif res.status_code != 200:
            raise ConnectionError('{} -> {}'.format(res.status_code, res.text))

        return res.json()['list']


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
        if email is not None: data['email'] = email
        res = self._session.post(user_url, data=data)
        if res.status_code == 401:
            raise PermissionError('Create device not is allowed! (Only for super devices or admins)')
        elif res.status_code != 201 or res.json().get('error') is not None:
            raise ConnectionError('{} -> {}'.format(res.status_code, res.text))

        return Device(self._session).populate(res.json())

    def add_users_to_group(self, group: Group, *users: User):
        return self.add_users_to_group_by_id(group, *[u.id for u in users if u.is_person()])

    def add_users_to_group_by_id(self, group: Group, *users: int):
        payload = {
            'action': "NodeAdd",
            'actionType': "Person",
            'add_users': users,
            'id': group.id,
            'rootType': "Group",
        }
        res = self._session.put(f'/api/v1/admin/group_device/update/{group.id}', data=payload)
        if res.status_code != 200:
            raise ConnectionError(f'{res.status_code} -> {res.text}')
