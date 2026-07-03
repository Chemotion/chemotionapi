"""User accounts and related entities exposed by the API: User, Admin, Person, Group, Device and Affiliation."""
import abc
import json
import re
from dataclasses import dataclass, field
from typing import cast

from chemotion_api.connection import Connection


@dataclass
class Affiliation:
    """A user affiliation as exposed by Grape (`/api/v1/affiliations`)."""
    id: int | None = None
    organization: str | None = None
    department: str | None = None
    group: str | None = None
    country: str | None = None
    from_date: str | None = None
    to_date: str | None = None
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_json(cls, data: dict) -> Affiliation:
        """Build an :class:`Affiliation` from a raw Grape affiliation payload.

        :param data: the affiliation ``dict`` as returned by the API.
        :return: the parsed :class:`Affiliation` (the raw payload is kept in ``raw``).
        """
        return cls(
            id=data.get('id'),
            organization=data.get('organization'),
            department=data.get('department'),
            group=data.get('group'),
            country=data.get('country'),
            from_date=data.get('from'),
            to_date=data.get('to'),
            raw=data,
        )

    @property
    def name(self) -> str:
        """Human-readable affiliation name (organization, finer units appended)."""
        parts = [p for p in (self.organization, self.department, self.group) if p]
        return ", ".join(parts) if parts else (self.organization or "")

    def to_dict(self) -> dict:
        """Return this affiliation as a Grape-compatible ``dict`` (``from``/``to`` date keys).

        :return: the affiliation serialized for sending back to the API.
        """
        return {
            'id': self.id, 'organization': self.organization, 'department': self.department,
            'group': self.group, 'country': self.country, 'from': self.from_date, 'to': self.to_date,
        }


class User(abc.ABC):  # noqa: B024 — ABC marks the class as non-instantiable by convention; subclasses override behaviour via attributes, not abstract methods
    """Abstract base for the account entities exposed by the API.

    Concrete subclasses are :class:`Person`, :class:`Group`, :class:`Device` and :class:`Admin`.
    Holds the fields common to every account (id, email, names, initials) and the helpers to load
    the current user, dispatch a payload to the right subclass and inspect the account type.
    """
    @classmethod
    def load_me(cls, session: Connection):
        """Fetch the currently authenticated account and return it as the right subclass.

        :param session: an authenticated :class:`~chemotion_api.connection.Connection`.
        :return: a :class:`User` subclass instance for the current account.
        :raises PermissionError: if not logged in (HTTP 401).
        :raises ConnectionError: on any other non-200 response.
        """
        user_url = '/api/v1/users/current.json'
        res = session.get(user_url)
        if res.status_code == 401:
            raise PermissionError('Not allowed to fetch user (Login first)')
        elif res.status_code != 200:
            raise ConnectionError(f'{res.status_code} -> {res.text}')
        data = res.json()['user']
        return cls.factor_user(session, data)

    @classmethod
    def factor_user(cls, session: Connection, data: dict):
        """Instantiate and populate the correct :class:`User` subclass for a payload.

        :param session: the connection to bind the new user to.
        :param data: a user payload whose ``type`` selects the subclass.
        :return: a populated :class:`Device`, :class:`Admin`, :class:`Group` or :class:`Person`.
        """
        user: User
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
        self.devices: list[Device] = []
        self.groups: list[Group] = []
        self.id: int | None = None
        self.email: str | None = None
        self.user_type: str | None = None
        self.first_name: str | None = None
        self.last_name: str | None = None
        self.initials: str | None = None
        self._affiliations: list[Affiliation] | None = None

    def get_affiliations(self, reload: bool = False) -> list[Affiliation]:
        """Fetch this session's affiliations from Grape (`/api/v1/affiliations`), cached.

        :param reload: re-fetch from the server even if already cached.
        :return: list of :class:`Affiliation` (may be empty).
        """
        if self._affiliations is None or reload:
            res = self._session.get('/api/v1/affiliations')
            if res.status_code != 200:
                raise ConnectionError(f"{res.status_code} -> {res.text}")
            data = res.json()
            if isinstance(data, dict):
                data = data.get('affiliations', data.get('data', []))
            self._affiliations = [Affiliation.from_json(a) for a in (data or [])]
        return self._affiliations

    @property
    def affiliations(self) -> list[Affiliation]:
        """This account's affiliations (cached; see :meth:`get_affiliations`)."""
        return self.get_affiliations()

    @affiliations.setter
    def affiliations(self, value):
        # guards User.populate() in case a user payload ever carries an 'affiliations' key
        self._affiliations = value

    @property
    def name_abbreviation(self):
        """The account's initials (alias of :attr:`initials`)."""
        return self.initials

    @name_abbreviation.setter
    def name_abbreviation(self, initials):
        self.initials = initials

    @property
    def name(self):
        """The account's display name (``first_name`` plus ``last_name`` when present)."""
        if self.last_name is None:
            return self.first_name
        return f"{self.first_name} {self.last_name}"

    @name.setter
    def name(self, name):
        self.first_name = name

    def populate(self, json_contnet):
        """Copy a user payload onto this instance, decoding Ruby-hash-style string values.

        Only keys that correspond to existing attributes are set; values that look like a Ruby
        ``"k"=>"v"`` hash literal are parsed into a ``dict``.

        :param json_contnet: the user payload to apply.
        :return: ``self``, for chaining.
        """
        self.user_type = json_contnet.get('type')
        for (key, val) in json_contnet.items():
            if hasattr(self, key):
                if re.match(r'^(\"[^\"]+\"=>\"[^\"]+\",? ?)*$', str(val)) is not None:
                    val = json.loads(f"{{ {val.replace('=>', ':')} }}")
                setattr(self, key, val)
        return self

    def is_admin(self):
        """Whether this account is an admin.

        :return: ``True`` if the account type is ``admin``.
        """
        return self._is_admin(self.user_type)

    def is_device(self):
        """Whether this account is a device.

        :return: ``True`` if the account type is ``device``.
        """
        return self._is_device(self.user_type)

    def is_group(self):
        """Whether this account is a group.

        :return: ``True`` if the account type is ``group``.
        """
        return self._is_group(self.user_type)

    def is_person(self):
        """Whether this account is a person.

        :return: ``True`` if the account type is ``person``.
        """
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
        """Search for person accounts whose name matches the given query.

        :param _session: the connection to query with.
        :param name: the name to search for.
        :return: a list of :class:`Person` instances for the matches.
        :raises ConnectionError: on a non-200 response.
        """
        res = _session.get(f'/api/v1/users/name.json?name={name}&type=Person')
        if res.status_code != 200:
            raise ConnectionError(f"{res.status_code} -> {res.text}")
        return [Person(_session).populate(x) for x in res.json()["users"]]


class Group(User):
    """A user group account that bundles several person accounts together."""

    def __init__(self, session: Connection):
        super().__init__(session)

    def add_users(self, *users: User):
        """Add person accounts to this group (non-person users are ignored).

        :param users: the :class:`User` accounts to add.
        :raises ConnectionError: on a non-200 response.
        """
        return self.add_users_by_id(*cast(list[int], [u.id for u in users if u.is_person()]))

    def populate(self, json_contnet):
        """Populate this group, defaulting the account type to ``group``.

        :param json_contnet: the group payload to apply.
        :return: ``self``, for chaining.
        """
        json_contnet['type'] = json_contnet.get('type', 'group')
        return super().populate(json_contnet)

    def add_users_by_id(self, *users: int):
        """Add users to this group by their account ids.

        :param users: the account ids to add to the group.
        :raises ConnectionError: on a non-200 response.
        """
        payload = {
            'destroy_group': False,
            'add_users': users,
            'id': self.id
        }
        res = self._session.put(f'/api/v1/groups/upd/{self.id}', data=payload)
        if res.status_code != 200:
            raise ConnectionError(f'{res.status_code} -> {res.text}')



class Person(User):
    """A human user account, with sample/reaction counters, layout and permission flags."""

    def __init__(self, session: Connection):
        super().__init__(session)
        self.samples_count: int | None = None
        self.reactions_count: int | None = None
        self.reaction_name_prefix: str | None = None
        self.layout: dict[str, str] | None = None
        self.unconfirmed_email: str | None = None
        self.confirmed_at: str | None = None
        self.current_sign_in_at: str | None = None
        self.locked_at = None
        self.is_templates_moderator: bool | None = None
        self.molecule_editor: bool | None = None
        self.account_active: bool | None = None
        self.matrix: int | None = None
        self.counters: dict[str, str] | None = None
        self.generic_admin: dict[str, bool] | None = None

    def populate(self, json_contnet):
        """Populate this person, defaulting the account type to ``person``.

        :param json_contnet: the person payload to apply.
        :return: ``self``, for chaining.
        """
        json_contnet['type'] = json_contnet.get('type', 'person')
        return super().populate(json_contnet)

    def get_next_short_label(self, type_name):
        """Build the next short label for an element type from this person's counters.

        :param type_name: the element type name (e.g. ``"sample"``, ``"reaction"``).
        :return: the short label string (prefixed with the person's initials).
        """
        if type_name == 'sample':
            return '{}-{}'.format(self.initials, self.counters[type_name + 's'])
        if type_name == 'reaction':
            return '{}-R{}'.format(self.initials, self.counters[type_name + 's'])
        return f"{self.initials}-{type_name}{self.counters.get(type_name + 's', self.counters.get(type_name, 0))}"

    def create_group(self, first_name: str, last_name: str, name_abbreviation: str) -> Group:
        """Create a new group owned by this person.

        :param first_name: the group's first name.
        :param last_name: the group's last name.
        :param name_abbreviation: the group's name abbreviation (initials).
        :return: the newly created :class:`Group`.
        :raises ConnectionError: on a non-201 response or if the server returns an error.
        """
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
    """A device account (e.g. an instrument) that can authenticate against the API."""

    def __init__(self, session: Connection):
        super().__init__(session)
        self.is_super_device: bool | None = None

    def get_jwt(self):
        """Fetch a remote-access JWT for this device.

        :return: the device's JWT as a string.
        :raises PermissionError: if not allowed (only super devices or admins; HTTP 401).
        :raises ConnectionError: on any other non-200 response.
        """
        return DeviceManager(self._session).get_jwt_for_device(self.id)

    def delete(self):
        """Delete this device account on the server.

        :raises PermissionError: if not allowed (only super devices or admins; HTTP 401).
        :raises ConnectionError: on any other non-200 response.
        """
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
            raise ConnectionError(f'{res.status_code} -> {res.text}')


class Admin(Person):
    """An administrator account, able to list and create users, devices and groups.

    Caches the fetched accounts in :attr:`users`, :attr:`devices`, :attr:`groups` and
    :attr:`admins`.
    """

    def __init__(self, session: Connection):
        super().__init__(session)
        self.users: list[User] = []
        self.devices: list[Device] = []
        self.groups: list[Group] = []
        self.admins: list[Admin] = []

    def populate(self, json_contnet):
        """Populate this admin, defaulting the account type to ``admin``.

        :param json_contnet: the admin payload to apply.
        :return: ``self``, for chaining.
        """
        json_contnet['type'] = json_contnet.get('type', 'admin')
        return super().populate(json_contnet)

    def fetchUsers(self):
        """Fetch all accounts and sort them into :attr:`users`/:attr:`devices`/etc.

        :raises PermissionError: if not logged in (HTTP 401).
        :raises ConnectionError: on any other non-200 response.
        """
        user_url = '/api/v1/admin_user/listUsers/all.json'
        res = self._session.get(user_url)
        if res.status_code == 401:
            raise PermissionError('Not allowed to fetch user (Login first)')
        elif res.status_code != 200:
            raise ConnectionError(f'{res.status_code} -> {res.text}')

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
        """Create a new device account.

        :param first_name: the device's first name.
        :param last_name: the device's last name.
        :param name_abbreviation: the device's name abbreviation (initials).
        :return: the newly created :class:`Device`.
        :raises ConnectionError: on a non-201 response or if the server returns an error.
        """
        data = self._create_group_device(first_name=first_name, last_name=last_name,
                                         name_abbreviation=name_abbreviation, rootType='Device')
        return Device(self._session).populate(data)

    def create_group(self, first_name: str, last_name: str, name_abbreviation: str) -> Group:
        """Create a new group account.

        :param first_name: the group's first name.
        :param last_name: the group's last name.
        :param name_abbreviation: the group's name abbreviation (initials).
        :return: the newly created :class:`Group`.
        :raises ConnectionError: on a non-201 response or if the server returns an error.
        """
        data = self._create_group_device(first_name=first_name, last_name=last_name,
                                         name_abbreviation=name_abbreviation, rootType='Group')
        return Group(self._session).populate(data)

    def create_person(self, first_name: str, last_name: str, name_abbreviation: str, password: str,
                      email: str) -> Person:
        """Create a new person account and return it.

        :param first_name: the person's first name.
        :param last_name: the person's last name.
        :param name_abbreviation: the person's name abbreviation (initials).
        :param password: the initial account password.
        :param email: the account email address.
        :return: the newly created :class:`Person` (looked up by name and abbreviation).
        :raises ConnectionError: on a non-201 response.
        """
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
        """Fetch all device accounts and cache them in :attr:`devices`.

        :return: the list of :class:`Device` accounts.
        :raises PermissionError: if not logged in (HTTP 401).
        :raises ConnectionError: on any other non-200 response.
        """
        u_type = 'Device'
        d_list = self.fetchGroupAndDevice(u_type)
        self.devices = [Device(self._session).populate(x | {'type': u_type}) for x in d_list]
        return self.devices

    def fetchGroups(self) -> list[Group]:
        """Fetch all group accounts and cache them in :attr:`groups`.

        :return: the list of :class:`Group` accounts.
        :raises PermissionError: if not logged in (HTTP 401).
        :raises ConnectionError: on any other non-200 response.
        """
        u_type = 'Group'
        g_list = self.fetchGroupAndDevice(u_type)
        self.groups = [Group(self._session).populate(x | {'type': u_type}) for x in g_list]
        return self.groups

    def fetchGroupAndDevice(self, type: str) -> list[dict]:
        """Fetch the raw group-or-device list of the given type from the admin API.

        :param type: ``"Group"`` or ``"Device"``.
        :return: the list of raw account ``dict`` payloads.
        :raises PermissionError: if not logged in (HTTP 401).
        :raises ConnectionError: on any other non-200 response.
        """
        user_url = f'/api/v1/admin/group_device/list?type={type}'
        res = self._session.get(user_url)
        if res.status_code == 401:
            raise PermissionError('Not allowed to fetch user (Login first)')
        elif res.status_code != 200:
            raise ConnectionError(f'{res.status_code} -> {res.text}')

        return res.json()['list']


class DeviceManager:
    """Admin/super-device helper for managing device accounts and group membership."""

    def __init__(self, session: Connection):
        self._session = session

    def get_jwt_for_device(self, id: int):
        """Fetch a remote-access JWT for a device by id.

        :param id: the device account id.
        :return: the device's JWT as a string.
        :raises PermissionError: if not allowed (only super devices or admins; HTTP 401).
        :raises ConnectionError: on any other non-200 response.
        """
        user_url = f'/api/v1/devices/remote/jwt/{id}'
        res = self._session.get(user_url)
        if res.status_code == 401:
            raise PermissionError('Not allowed to fetch JWT (Only for super devices or admins)')
        elif res.status_code != 200:
            raise ConnectionError(f'{res.status_code} -> {res.text}')

        return res.json()['token']

    def create_new_device(self, first_name: str, last_name: str, name_abbreviation: str, email: str | None = None) -> Device:
        """Create a new remote device account.

        :param first_name: the device's first name.
        :param last_name: the device's last name.
        :param name_abbreviation: the device's name abbreviation (initials).
        :param email: optional email address for the device.
        :return: the newly created :class:`Device`.
        :raises PermissionError: if not allowed (only super devices or admins; HTTP 401).
        :raises ConnectionError: on a non-201 response or if the server returns an error.
        """
        user_url = '/api/v1/devices/remote/create'
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
            raise ConnectionError(f'{res.status_code} -> {res.text}')

        return Device(self._session).populate(res.json())

    def add_users_to_group(self, group: Group, *users: User):
        """Add person accounts to a group (non-person users are ignored).

        :param group: the target :class:`Group`.
        :param users: the :class:`User` accounts to add.
        :raises ConnectionError: on a non-200 response.
        """
        return self.add_users_to_group_by_id(group, *cast(list[int], [u.id for u in users if u.is_person()]))

    def add_users_to_group_by_id(self, group: Group, *users: int):
        """Add users to a group by their account ids.

        :param group: the target :class:`Group`.
        :param users: the account ids to add.
        :raises ConnectionError: on a non-200 response.
        """
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
