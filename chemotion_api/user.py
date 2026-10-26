import abc
import json
import re
from dataclasses import dataclass, field
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


@dataclass
class UserLabel:
    """A user label as exposed by Grape (``/api/v1/user_labels/list_labels``).

    Labels are what the ELN shows as coloured tags on samples and reactions. Elements carry only
    the label **ids**, so this type is what turns those ids back into titles.

    ``access_level`` is ``0`` for a private label (visible only to its owner) and ``1`` or ``2``
    for a shared one; see :attr:`is_shared`.
    """
    id: int | None = None
    user_id: int | None = None
    access_level: int | None = None
    title: str | None = None
    description: str | None = None
    color: str | None = None
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_json(cls, data: dict) -> UserLabel:
        """Build a :class:`UserLabel` from a raw Grape user-label payload.

        :param data: the label ``dict`` as returned by the API.
        :return: the parsed :class:`UserLabel` (the raw payload is kept in ``raw``).
        """
        return cls(
            id=data.get('id'),
            user_id=data.get('user_id'),
            access_level=data.get('access_level'),
            title=data.get('title'),
            description=data.get('description'),
            color=data.get('color'),
            raw=data,
        )

    @property
    def is_shared(self) -> bool:
        """Whether this label is shared (``access_level`` 1 or 2) rather than private (``0``)."""
        return self.access_level in (1, 2)

    @property
    def is_resolved(self) -> bool:
        """Whether this label came from the server, as opposed to standing in for an id.

        An element may carry a label belonging to another user, which the server's ``my_labels``
        filter will not return; resolving such an id yields a placeholder with no
        :attr:`title` — see :meth:`chemotion_api.elements.abstract_element.AbstractElement.user_labels_resolved`.
        """
        return self.title is not None

    @property
    def display_title(self) -> str:
        """The title, or ``#<id>`` when the label could not be resolved.

        Use this rather than :attr:`title` when building user-facing strings: ``title`` is
        deliberately ``None`` for an unresolvable label, which would otherwise blow up a
        ``", ".join(...)``.
        """
        return self.title if self.title is not None else f'#{self.id}'

    def to_dict(self) -> dict:
        """Return this label as a ``dict`` shaped for ``PUT /api/v1/user_labels/save_label``.

        :return: the label serialized for sending back to the API.
        """
        return {
            'id': self.id, 'title': self.title, 'description': self.description,
            'color': self.color, 'access_level': self.access_level,
        }


class User(abc.ABC):
    @classmethod
    def load_me(cls, session: Connection):
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

    def get_affiliations(self) -> list[Affiliation]:
        """Fetch this user's affiliations from ``GET /api/v1/affiliations``.

        The endpoint returns a bare JSON array of user-affiliation rows (no root key), each
        carrying the joined ``organization``/``department``/``group``/``country`` values.

        :return: the parsed affiliations, in the order the server returned them.
        :raise PermissionError: if the affiliations cannot be fetched. Make sure you are logged in.
        """
        res = self._session.get('/api/v1/affiliations')
        if res.status_code == 401:
            raise PermissionError('Not allowed to fetch affiliations (Login first)')
        if res.status_code != 200:
            raise ConnectionError(f'{res.status_code} -> {res.text}')
        return [Affiliation.from_json(row) for row in res.json()]

    def get_user_labels(self, refresh: bool = False) -> list[UserLabel]:
        """Fetch the user labels visible to this user from ``GET /api/v1/user_labels/list_labels``.

        That is this user's own private labels (``access_level`` 0) plus every shared one
        (1 and 2). The server's ordering is preserved — it sorts by access level, position and
        title, which is the order the ELN itself shows.

        The underlying request is cached on the connection; pass ``refresh=True`` to refetch.

        :param refresh: drop the cached labels and fetch them again.
        :return: the parsed labels, in server order.
        :raise PermissionError: if the labels cannot be fetched. Make sure that you are logged in.
        """
        if refresh:
            self._session.reset_user_labels()
        return [UserLabel.from_json(row) for row in self._session.user_labels]

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
        # `params=` rather than interpolation: a name containing &, # or a space would otherwise
        # be read as extra query parameters or truncate the value.
        res = _session.get('/api/v1/users/name.json',
                           params={'name': name, 'type': 'Person'})
        if res.status_code != 200:
            raise ConnectionError(f"{res.status_code} -> {res.text}")
        return [Person(_session).populate(x) for x in res.json()["users"]]


class Group(User):

    def __init__(self, session: Connection):
        super().__init__(session)

    def add_users(self, *users: User):
        """Add people to this group.

        Non-people (devices, nested groups) are ignored, matching the previous behaviour.
        """
        return self.add_users_by_id(*[u.id for u in users if u.is_person()])

    def populate(self, json_contnet):
        json_contnet['type'] = json_contnet.get('type', 'group')
        return super().populate(json_contnet)

    def add_users_by_id(self, *users: int):
        """``POST /api/v1/groups/:id/members``.

        ELN v4.0.0 replaced ``PUT /groups/upd/:id`` — which carried `add_users`, `rm_users` and a
        `destroy_group` flag in one payload — with REST sub-resources. The server ignores ids that
        are already members, so this is idempotent.

        :raises PermissionError: if the caller does not administrate the group (401).
        :raises ConnectionError: on any other failure.
        """
        if not users:
            return None
        res = self._session.post(f'/api/v1/groups/{self.id}/members',
                                 data={'user_ids': list(users)})
        return self._apply_group_response(res, 'add users to')

    def remove_users(self, *users: User):
        """Remove people from this group (see :meth:`remove_user_by_id`)."""
        for user in users:
            if user.is_person():
                self.remove_user_by_id(user.id)
        return self

    def remove_user_by_id(self, user_id: int):
        """``DELETE /api/v1/groups/:id/members/:user_id``.

        A member may also remove *themselves* without administrating the group — the server's
        policy allows leaving.
        """
        res = self._session.delete(f'/api/v1/groups/{self.id}/members/{user_id}')
        return self._apply_group_response(res, 'remove a member from')

    def promote_admin(self, user_id: int):
        """``POST /api/v1/groups/:id/admins/:user_id`` — make an existing member an admin."""
        res = self._session.post(f'/api/v1/groups/{self.id}/admins/{user_id}', data={})
        return self._apply_group_response(res, 'promote an admin of')

    def demote_admin(self, user_id: int):
        """``DELETE /api/v1/groups/:id/admins/:user_id``.

        :raises ValueError: if this is the group's last admin — the server refuses with 422 rather
            than leaving a group nobody can administrate.
        """
        res = self._session.delete(f'/api/v1/groups/{self.id}/admins/{user_id}')
        return self._apply_group_response(res, 'demote an admin of')

    def delete(self):
        """``DELETE /api/v1/groups/:id``. Returns the destroyed id the server reports."""
        res = self._session.delete(f'/api/v1/groups/{self.id}')
        if res.status_code == 401:
            raise PermissionError(f'You do not administrate group {self.id}, so you cannot delete it.')
        if res.status_code == 404:
            raise ValueError(f'Group {self.id} does not exist.')
        if res.status_code not in (200, 201, 204):
            raise ConnectionError(f'{res.status_code} -> {res.text}')
        return (res.json() or {}).get('destroyed_id') if res.content else self.id

    def _apply_group_response(self, res, action: str):
        """Refresh this group from a ``{"group": …}`` response, mapping the documented failures.

        The group endpoints answer 401 for "you do not administrate this", 404 for a group that is
        gone, and 422 (`RecordInvalid`, or "Cannot remove the last admin") for a refused change.
        Collapsing those into one ConnectionError lost the distinction that matters to a caller.
        """
        if res.status_code == 401:
            raise PermissionError(f'You do not administrate group {self.id}, so you cannot {action} it.')
        if res.status_code == 404:
            raise ValueError(f'Group {self.id} does not exist.')
        if res.status_code == 422:
            raise ValueError(f'The server refused to {action} group {self.id}: {res.text}')
        if res.status_code not in (200, 201):
            raise ConnectionError(f'{res.status_code} -> {res.text}')
        payload = res.json()
        if isinstance(payload, dict) and 'group' in payload:
            self.populate(payload['group'])
        return self



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

    def get_next_short_label(self, type_name):
        if type_name == 'sample':
            return '{}-{}'.format(self.initials, self.counters[type_name + 's'])
        if type_name == 'reaction':
            return '{}-R{}'.format(self.initials, self.counters[type_name + 's'])
        return f"{self.initials}-{type_name}{self.counters.get(type_name + 's', self.counters.get(type_name, 0))}"

    def create_group(self, first_name: str, last_name: str, name_abbreviation: str,
                     email: str | None = None, users: list[int] | None = None) -> Group:
        """Create a group, with this user as its first member and administrator.

        ``POST /api/v1/groups``. ELN v4.0.0 moved this off ``POST /groups/create`` and flattened
        the payload — the old nested ``{"group_param": {…}}`` body is not accepted.

        :param email: optional contact address. The server mints a throwaway
            ``<epoch>@eln.edu`` when none is given, so leaving this unset is supported but makes
            the group harder to identify later.
        :param users: ids of further members to add at creation. The caller is always included.
        :raises ValueError: if the server rejects the group (422), e.g. a duplicate abbreviation.
        """
        data = {
            'first_name': first_name,
            'last_name': last_name,
            'name_abbreviation': name_abbreviation,
            'users': list(dict.fromkeys([*(users or []), self.id])),
        }
        if email:
            data['email'] = email
        res = self._session.post('/api/v1/groups', data=data)
        if res.status_code == 422:
            # The server turns RecordInvalid into a readable message; surfacing its text is far
            # more useful than "422", since it names the offending attribute.
            raise ValueError(f'The server refused to create this group: {res.text}')
        if res.status_code not in (200, 201):
            raise ConnectionError(f'{res.status_code} -> {res.text}')
        payload = res.json()
        if 'error' in payload:
            raise ConnectionError(f'{res.text}')
        return Group(self._session).populate(payload['group'] | {'type': 'group'})

    def get_groups(self) -> list[Group]:
        """Every group this user belongs to or administrates (``GET /api/v1/groups``)."""
        res = self._session.get('/api/v1/groups')
        if res.status_code != 200:
            raise ConnectionError(f'{res.status_code} -> {res.text}')
        return [Group(self._session).populate(entry | {'type': 'group'})
                for entry in res.json().get('currentGroups', [])]


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
            raise ConnectionError(f'{res.status_code} -> {res.text}')


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
            raise ConnectionError(f'{res.status_code} -> {res.text}')

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
            raise ConnectionError(f'{res.status_code} -> {res.text}')

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
            raise ConnectionError(f'{res.status_code} -> {res.text}')

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
