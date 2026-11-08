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

    def save_user_label(self, label: UserLabel) -> UserLabel:
        """Create a user label, or update one of your own (``PUT /api/v1/user_labels/save_label``).

        A label without an :attr:`~UserLabel.id` is created; one with an id must be yours. The
        cached label list is dropped, so the next read includes the change.

        :param label: the label; ``access_level`` ``0`` (the default) keeps it private.
        :return: the label as the server stored it.
        :raises ValueError: if the label has no title.
        :raises PermissionError: if the label is not yours (the server answers 404 for that).
        """
        if not label.title:
            raise ValueError('A user label needs a title.')
        body = {k: v for k, v in label.to_dict().items() if v is not None}
        res = self._session.put('/api/v1/user_labels/save_label', data=body)
        if res.status_code == 404:
            raise PermissionError(f'User label {label.id} is not one of yours.')
        if res.status_code not in (200, 201):
            raise ConnectionError(f'{res.status_code} -> {res.text}')
        self._session.reset_user_labels()
        return UserLabel.from_json(res.json())

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
        self.cell_lines_count: int | None = None
        self.device_descriptions_count: int | None = None
        self.vessels_count: int | None = None
        self.sequence_based_macromolecule_samples_count: int | None = None
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
        if type_name == 'cell_line':
            # As the UI labels a new cell line (ElementActions.generateEmptyCellLine).
            return f'{self.initials}-C{self.cell_lines_count or 0}'
        if type_name == 'sequence_based_macromolecule_sample':
            # The server labels a new SBMM sample itself; this is what it will pick.
            return f'{self.initials}-sbmmS{(self.sequence_based_macromolecule_samples_count or 0) + 1}'
        if type_name == 'device_description':
            # DeviceDescription.js in the UI.
            return f'{self.initials}-Dev{(self.device_descriptions_count or 0) + 1}'
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

    def find_users(self, name: str, types=('Person', 'Group', 'Device', 'Admin'), limit: int = 5) -> list[dict]:
        """Users whose name matches, of any kind (``GET /api/v1/admin/users/byname``):
        ``{'id', 'name', 'initials', 'type'}`` dicts."""
        if not name:
            return []
        res = self._session.get('/api/v1/admin/users/byname', params={'name': name, 'type': ','.join(types),
                                                                       'limit': limit})
        self._admin_check(res, 'finding users')
        return res.json().get('users') or []

    def default_allocated_space(self) -> int:
        """The disk space new users get, in MB (``GET /api/v1/admin/usersDefault``)."""
        res = self._session.get('/api/v1/admin/usersDefault')
        self._admin_check(res, 'reading the default user space')
        return int(res.json().get('allocated_user_space') or 0)

    def set_default_allocated_space(self, megabytes: int) -> None:
        """Set the disk space new users get, in MB (``PUT /api/v1/admin/usersDefault``)."""
        if megabytes < 0:
            raise ValueError('The space is 0 MB or more.')
        res = self._session.put('/api/v1/admin/usersDefault', data={'allocatedUserSpace': megabytes})
        self._admin_check(res, 'setting the default user space')

    def update_user(self, user, **fields) -> dict:
        """Change a user account (``PUT /api/v1/admin/users/:id``).

        :param user: a :class:`User` or its id.
        :param fields: ``email``, ``first_name``, ``last_name``, ``name_abbreviation``, ``type``,
            ``allocated_space``, ``account_active`` (bool), ``enable`` (False locks the account),
            ``confirm_user`` / ``reconfirm_user`` (bool).
        :return: the account as stored.
        """
        allowed = {'email', 'first_name', 'last_name', 'name_abbreviation', 'type', 'allocated_space',
                   'account_active', 'enable', 'confirm_user', 'reconfirm_user'}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f'Unknown user fields: {", ".join(sorted(unknown))}')
        res = self._session.put(f'/api/v1/admin/users/{_user_id(user)}', data=fields)
        self._admin_check(res, f'updating user {_user_id(user)}')
        data = res.json() or {}
        if data.get('error'):
            raise ValueError(f'User {_user_id(user)} not updated: {data["error"]}')
        return data.get('user', data)

    def delete_user(self, user, *, confirm: str) -> None:
        """Delete a user account (``DELETE /api/v1/admin/users/:id``). The account is soft-deleted:
        :meth:`restore_user` brings it back.

        :param confirm: the account's name abbreviation, to guard against deleting the wrong one.
        """
        current = self._session.get(f'/api/v1/admin/users/{_user_id(user)}')
        self._admin_check(current, f'loading user {_user_id(user)}')
        record = current.json().get('user') or current.json()
        abbreviation = record.get('initials') or record.get('name_abbreviation')
        if confirm != abbreviation:
            raise ValueError(f'To delete user {_user_id(user)}, pass confirm={abbreviation!r}.')
        res = self._session.delete(f'/api/v1/admin/users/{_user_id(user)}')
        if res.status_code == 422:
            raise ValueError(f'User {abbreviation} cannot be deleted: {res.text}')
        self._admin_check(res, f'deleting user {abbreviation}')

    def restore_user(self, name_abbreviation: str | None = None, user_id: int | None = None) -> dict:
        """Restore a deleted account (``POST /api/v1/admin/users/restoreAccount``). If another account
        now has the abbreviation, the restored one is left inactive and the answer says so.

        :return: ``{'status': 'success' | 'warning', 'message': ...}``.
        :raises LookupError: if no such deleted account exists, or several match (give ``user_id``).
        """
        if name_abbreviation is None and user_id is None:
            raise ValueError('Give the name abbreviation or the id of the deleted account.')
        body = {k: v for k, v in (('name_abbreviation', name_abbreviation), ('id', user_id)) if v is not None}
        res = self._session.post('/api/v1/admin/users/restoreAccount', data=body)
        if res.status_code in (400, 404, 500) and 'error' in res.text:
            raise LookupError(res.json().get('message') if res.text.startswith('{') else res.text)
        self._admin_check(res, 'restoring an account')
        return res.json()

    def reset_password(self, user, password: str | None = None) -> str | None:
        """Set a user's password (``PUT /api/v1/admin/users/:id/resetPassword``).

        :param password: the new password (8+ characters); ``None`` generates a random one.
        :return: the new password.
        """
        if password is not None and len(password) < 8:
            raise ValueError('A password has at least 8 characters.')
        body: dict = {'random': password is None}
        if password is not None:
            body['password'] = password
        res = self._session.put(f'/api/v1/admin/users/{_user_id(user)}/resetPassword', data=body)
        self._admin_check(res, f'resetting the password of user {_user_id(user)}')
        return res.json().get('pwd')

    def disable_two_factor(self, user) -> None:
        """Switch off a user's two-factor login (``PUT /api/v1/admin/users/:id/otp``)."""
        res = self._session.put(f'/api/v1/admin/users/{_user_id(user)}/otp', data={'enable': False})
        self._admin_check(res, f'disabling two-factor login of user {_user_id(user)}')

    def two_factor_enable_link(self, user) -> str:
        """The link with which a user switches on two-factor login (``PUT /api/v1/admin/users/:id/otp``)."""
        res = self._session.put(f'/api/v1/admin/users/{_user_id(user)}/otp', data={'enable': True})
        self._admin_check(res, f'creating a two-factor link for user {_user_id(user)}')
        return res.json()['link']

    def set_user_rights(self, user, *, templates_moderator: bool | None = None, molecule_editor: bool | None = None,
                        converter_admin: bool | None = None, text_template_editor: bool | None = None,
                        generic_elements_admin: bool | None = None, generic_segments_admin: bool | None = None,
                        generic_datasets_admin: bool | None = None) -> dict:
        """Grant or withdraw a user's special rights (``PUT /api/v1/admin/users/:id/profile``).
        Rights left at ``None`` are not changed."""
        body: dict = {k: v for k, v in (('is_templates_moderator', templates_moderator),
                                        ('molecule_editor', molecule_editor), ('converter_admin', converter_admin),
                                        ('global_text_template_editor', text_template_editor)) if v is not None}
        generic = {k: v for k, v in (('elements', generic_elements_admin), ('segments', generic_segments_admin),
                                     ('datasets', generic_datasets_admin)) if v is not None}
        if generic:
            body['auth_generic_admin'] = generic
        if not body:
            raise ValueError('Name the rights to change.')
        res = self._session.put(f'/api/v1/admin/users/{_user_id(user)}/profile', data=body)
        self._admin_check(res, f'changing the rights of user {_user_id(user)}')
        return res.json()

    def remove_users_from_group(self, group, *users) -> dict:
        """Take people out of a group (``PUT /api/v1/admin/group_device/update/:id``, ``NodeDel``)."""
        return self._group_update(group, 'NodeDel', actionType='Person', rm_users=[_user_id(u) for u in users])

    def remove_devices_from(self, owner, *devices, owner_type: str = 'Group') -> dict:
        """Detach devices from a group (``NodeDel``, ``actionType=Device``)."""
        return self._group_update(owner, 'NodeDel', rootType=owner_type, actionType='Device',
                                  rm_users=[_user_id(d) for d in devices])

    def set_group_admin(self, group, user, admin: bool = True) -> dict:
        """Make a member an administrator of the group, or not (``NodeAdm``). The last
        administrator cannot be removed."""
        return self._group_update(group, 'NodeAdm', actionType='Adm', admin_id=_user_id(user), set_admin=admin)

    def delete_group(self, group, *, confirm: str, group_type: str = 'Group') -> None:
        """Delete a group or device (``RootDel`` with ``destroy_obj``).

        :param confirm: its name abbreviation, to guard against deleting the wrong one.
        """
        abbreviation = getattr(group, 'name_abbreviation', None)
        if abbreviation is None or confirm != abbreviation:
            raise ValueError(f'To delete this {group_type.lower()}, pass a loaded one and confirm={abbreviation!r}.')
        self._group_update(group, 'RootDel', rootType=group_type, destroy_obj=True)

    def _group_update(self, group, action: str, rootType: str = 'Group', **fields) -> dict:
        group_id = _user_id(group)
        res = self._session.put(f'/api/v1/admin/group_device/update/{group_id}',
                                data={'action': action, 'rootType': rootType, 'id': group_id, **fields})
        if res.status_code == 422:
            raise ValueError(res.text)
        self._admin_check(res, f'{action} on {rootType.lower()} {group_id}')
        return res.json() if res.content else {}

    #: Device fields the admin device routes accept. The ``datacollector_*`` ones configure how the
    #: ELN collects files from the instrument (local folder or SFTP), the ``novnc_*`` ones the
    #: remote-desktop link.
    DEVICE_FIELDS = ('name', 'name_abbreviation', 'email', 'serial_number', 'verification_status', 'account_active',
                     'visibility', 'people', 'groups', 'datacollector_fields', 'datacollector_method',
                     'datacollector_dir', 'datacollector_host', 'datacollector_user', 'datacollector_authentication',
                     'datacollector_key_name', 'datacollector_user_level_selected', 'datacollector_number_of_files',
                     'novnc_target', 'novnc_token', 'novnc_password')

    def list_devices(self, name: str | None = None, limit: int = 5) -> list[dict]:
        """All devices, or those whose name matches (``GET /api/v1/admin_devices[/byname]``)."""
        if name:
            res = self._session.get('/api/v1/admin_devices/byname', params={'name': name, 'limit': limit})
        else:
            res = self._session.get('/api/v1/admin_devices')
        self._admin_check(res, 'listing devices')
        return res.json().get('devices') or []

    def get_device(self, device) -> dict:
        res = self._session.get(f'/api/v1/admin_devices/{_user_id(device)}')
        self._admin_check(res, f'loading device {_user_id(device)}')
        return res.json().get('device') or {}

    def add_device(self, name: str, name_abbreviation: str, **fields) -> dict:
        """Register an instrument as a device (``POST /api/v1/admin_devices``).

        :param fields: ``email``, ``serial_number``, ``verification_status``, ``account_active``,
            ``visibility``; configure collection afterwards with :meth:`update_device`.
        """
        allowed = {'email', 'serial_number', 'verification_status', 'account_active', 'visibility'}
        if set(fields) - allowed:
            raise ValueError(f'add_device takes {", ".join(sorted(allowed))}; set the rest with update_device.')
        res = self._session.post('/api/v1/admin_devices', data={'name': name, 'name_abbreviation': name_abbreviation} | fields)
        return self._device_answer(res, f'creating device {name_abbreviation}')

    def update_device(self, device, **fields) -> dict:
        """Change a device, its users and its data collector (``PUT /api/v1/admin_devices/:id``).

        :param fields: any of :data:`DEVICE_FIELDS`; ``people`` / ``groups`` are user ids and replace
            the current ones (an empty list removes all). ``name`` and ``name_abbreviation`` are
            required by the server and default to the device's current values.
        """
        unknown = set(fields) - set(self.DEVICE_FIELDS)
        if unknown:
            raise ValueError(f'Unknown device fields: {", ".join(sorted(unknown))}')
        current = self.get_device(device)
        body = {'id': _user_id(device), 'name': current.get('name'),
                'name_abbreviation': current.get('name_abbreviation') or current.get('initials')} | fields
        if any(k.startswith('datacollector_') for k in fields):
            body.setdefault('datacollector_fields', True)
        res = self._session.put(f'/api/v1/admin_devices/{_user_id(device)}', data=body)
        return self._device_answer(res, f'updating device {_user_id(device)}')

    def _device_answer(self, res, what: str) -> dict:
        self._admin_check(res, what)
        data = res.json() or {}
        if data.get('errors'):
            raise ValueError(f'{what}: {data["errors"]}')
        return data.get('device') or data

    def delete_device(self, device, *, confirm: str) -> None:
        """Delete a device (``DELETE /api/v1/admin_devices/:id``).

        :param confirm: its name abbreviation, to guard against deleting the wrong one.
        """
        current = self.get_device(device)
        abbreviation = current.get('name_abbreviation') or current.get('initials')
        if confirm != abbreviation:
            raise ValueError(f'To delete device {_user_id(device)}, pass confirm={abbreviation!r}.')
        res = self._session.delete(f'/api/v1/admin_devices/{_user_id(device)}')
        if res.status_code == 400:
            raise ValueError(f'Device {abbreviation} could not be deleted.')
        self._admin_check(res, f'deleting device {abbreviation}')

    def remove_device_user(self, device, user) -> None:
        """Take a user's access to a device away (``PUT /api/v1/admin_devices/delete_relation/:user_id``)."""
        res = self._session.put(f'/api/v1/admin_devices/delete_relation/{_user_id(user)}',
                                data={'id': _user_id(user), 'device_id': _user_id(device)})
        if res.status_code == 400:
            raise LookupError(f'User {_user_id(user)} has no access to device {_user_id(device)}.')
        self._admin_check(res, 'removing a device user')

    def test_sftp(self, device, host: str, user: str, authentication: str = 'password',
                  key_name: str | None = None, method: str = 'filewatchersftp') -> dict:
        """Check that the ELN can log in to a data collector's SFTP server
        (``POST /api/v1/admin_devices/test_sftp``). The ELN connects to ``host`` for this.

        :return: ``{'status': 'success' | 'error', 'message': ...}``.
        """
        body = {'id': _user_id(device), 'datacollector_method': method, 'datacollector_host': host,
                'datacollector_user': user, 'datacollector_authentication': authentication}
        if key_name is not None:
            body['datacollector_key_name'] = key_name
        res = self._session.post('/api/v1/admin_devices/test_sftp', data=body)
        self._admin_check(res, 'testing an SFTP connection')
        return res.json()

    def local_collectors(self) -> list[dict]:
        """The local data-collector folders configured on the server (``GET /api/v1/admin/listLocalCollector/all``)."""
        res = self._session.get('/api/v1/admin/listLocalCollector/all')
        self._admin_check(res, 'listing local collectors')
        return res.json().get('listLocalCollector') or []

    def device_metadata(self, device) -> dict | None:
        """A device's publication metadata, or ``None`` (``GET /api/v1/admin_device_metadata/:id``)."""
        res = self._session.get(f'/api/v1/admin_device_metadata/{_user_id(device)}')
        self._admin_check(res, f'loading the metadata of device {_user_id(device)}')
        return res.json().get('device_metadata')

    def save_device_metadata(self, device, **fields) -> dict:
        """Create or update a device's publication metadata (``POST /api/v1/admin_device_metadata``):
        ``name``, ``doi``, ``url``, ``landing_page``, ``type``, ``description``, ``publisher``,
        ``publication_year``, ``data_cite_state``, ``owners``, ``manufacturers``, ``dates``.
        Creating it also registers the device at DataCite when the ELN is configured for that."""
        allowed = {'name', 'doi', 'url', 'landing_page', 'type', 'description', 'publisher', 'publication_year',
                   'data_cite_state', 'owners', 'manufacturers', 'dates'}
        if set(fields) - allowed:
            raise ValueError(f'Unknown metadata fields: {", ".join(sorted(set(fields) - allowed))}')
        res = self._session.post('/api/v1/admin_device_metadata', data={'device_id': _user_id(device)} | fields)
        self._admin_check(res, f'saving the metadata of device {_user_id(device)}')
        data = res.json() or {}
        if data.get('error'):
            raise ValueError(data['error'])
        return data.get('device_metadata') or {}

    def sync_device_metadata(self, device) -> dict:
        """Push a device's metadata to DataCite (``PUT /api/v1/admin_device_metadata/:id/sync_to_data_cite``)."""
        res = self._session.put(f'/api/v1/admin_device_metadata/{_user_id(device)}/sync_to_data_cite')
        self._admin_check(res, f'syncing the metadata of device {_user_id(device)}')
        data = res.json() or {}
        if data.get('error'):
            raise ConnectionError(data['error'])
        return data.get('device_metadata') or {}

    #: Maintenance tasks :meth:`queue_admin_task` can start (``AdminJob``).
    ADMIN_TASKS = ('collection_restore', 'install_ketcher2', 'rerender_reactions')

    def disk_usage(self) -> dict:
        """The server's disk: ``{'percent_used', 'mb_available'}`` (``GET /api/v1/admin/disk``)."""
        res = self._session.get('/api/v1/admin/disk')
        self._admin_check(res, 'reading the disk usage')
        return res.json()

    def jobs(self) -> list[dict]:
        """The background jobs waiting or failed (``GET /api/v1/admin/jobs``): ``id``, ``queue``,
        ``run_at``, ``failed_at``, ``attempts``, ``last_error``, …"""
        res = self._session.get('/api/v1/admin/jobs')
        self._admin_check(res, 'listing background jobs')
        return res.json().get('jobs') or []

    def restart_job(self, job) -> None:
        """Run one (failed) background job again in a minute (``PUT /api/v1/admin/jobs/restart``).

        :param job: a job from :meth:`jobs`, or its id. There is deliberately no "restart all".
        """
        job_id = job['id'] if isinstance(job, dict) else job
        if not isinstance(job_id, int):
            raise ValueError('Give one job or job id.')
        res = self._session.put('/api/v1/admin/jobs/restart', data={'id': job_id})
        if res.status_code == 404 or (res.status_code == 500 and 'RecordNotFound' in res.text):
            raise LookupError(f'No background job {job_id}.')
        self._admin_check(res, f'restarting job {job_id}')

    def queue_admin_task(self, task: str) -> None:
        """Start a maintenance task in the background (``GET /api/v1/admin/jobs/queue_task``): one of
        :data:`ADMIN_TASKS`."""
        if task not in self.ADMIN_TASKS:
            raise ValueError(f'task is one of {", ".join(self.ADMIN_TASKS)}.')
        res = self._session.get('/api/v1/admin/jobs/queue_task', params={'task': task})
        self._admin_check(res, f'queuing {task}')

    def matrices(self) -> list[dict]:
        """The feature switches (``GET /api/v1/admin/matrix``): each feature's ``name``, ``label``,
        ``enabled`` and the users it is switched on (``include_ids``) or off (``exclude_ids``) for."""
        res = self._session.get('/api/v1/admin/matrix')
        self._admin_check(res, 'listing the feature switches')
        return res.json().get('matrices') or []

    def update_matrix(self, matrix, **fields) -> None:
        """Change a feature switch (``PUT /api/v1/admin/matrix``): ``label``, ``enabled``,
        ``include_ids``, ``exclude_ids``, ``configs``."""
        allowed = {'label', 'enabled', 'include_ids', 'exclude_ids', 'configs'}
        if not fields or set(fields) - allowed:
            raise ValueError(f'Change any of {", ".join(sorted(allowed))}.')
        matrix_id = matrix['id'] if isinstance(matrix, dict) else matrix
        res = self._session.put('/api/v1/admin/matrix', data={'id': matrix_id} | fields)
        self._admin_check(res, f'updating feature switch {matrix_id}')
        data = res.json() if res.content else {}
        if isinstance(data, dict) and data.get('error'):
            raise ValueError(data['error'])

    def save_spectra_data_types(self, data_types: dict) -> None:
        """Replace the ELN's mapping of spectra layouts to data types (``PUT /api/v1/admin/data_types``),
        as compared in ``instance.spectra().layouts()``."""
        res = self._session.put('/api/v1/admin/data_types', data=json.dumps(data_types),
                                headers=self._session.get_json_session_header())
        self._admin_check(res, 'saving the spectra data types')

    def info_support_links(self) -> list[dict]:
        """The *Info & support* menu links (``GET /api/v1/admin/info_support_links``)."""
        res = self._session.get('/api/v1/admin/info_support_links')
        self._admin_check(res, 'listing the support links')
        return res.json() or []

    def add_info_support_link(self, label: str, url: str, position: int = 0, enabled: bool = True) -> dict:
        res = self._session.post('/api/v1/admin/info_support_links',
                                 data={'label': label, 'url': url, 'position': position, 'enabled': enabled})
        if res.status_code == 422:
            raise ValueError(res.text)
        self._admin_check(res, f'adding the support link {label}')
        return res.json()

    def update_info_support_link(self, link, **fields) -> dict:
        """Change a support link: ``label``, ``url``, ``position``, ``enabled``."""
        link_id = link['id'] if isinstance(link, dict) else link
        res = self._session.put(f'/api/v1/admin/info_support_links/{link_id}', data=fields)
        if res.status_code == 422:
            raise ValueError(res.text)
        self._admin_check(res, f'updating support link {link_id}')
        return res.json()

    def delete_info_support_link(self, link) -> None:
        link_id = link['id'] if isinstance(link, dict) else link
        res = self._session.delete(f'/api/v1/admin/info_support_links/{link_id}')
        self._admin_check(res, f'deleting support link {link_id}')

    def import_ols_terms(self, owl_file: str) -> None:
        """Replace an ontology's terms with those of an OWL file, as *Admin > Ontologies* does
        (``POST /api/v1/admin/importOlsTerms``). The file name without extension is the ontology
        name, e.g. ``chmo.owl``.
        """
        import os
        if not os.path.splitext(owl_file)[1].lower() in ('.owl', '.xml', '.ow'):
            raise ValueError('Give an .owl or .xml file.')
        with open(owl_file, 'rb') as f:
            res = self._session.post('/api/v1/admin/importOlsTerms',
                                     files={'file': (os.path.basename(owl_file), f, 'application/rdf+xml')})
        self._admin_check(res, f'importing {owl_file}')

    def set_ols_terms_enabled(self, owl_name: str, enable=(), disable=()) -> None:
        """Show or hide ontology terms in the ELN's term pickers
        (``POST /api/v1/admin/olsEnableDisable``).

        :param owl_name: ``'chmo'``, ``'rxno'``, ``'bao'``, …
        :param enable: term ids to show, e.g. ``'CHMO:0000595'``.
        :param disable: term ids to hide (with their branches in the pickers).
        """
        if not enable and not disable:
            raise ValueError('Give term ids to enable or disable.')
        # The server rewrites the ontology's public term lists from its database. With no terms
        # imported there, that replaces the ELN's built-in lists with empty ones, so refuse.
        root = self._session.get('/api/v1/ols_terms/root', params={'name': owl_name})
        if root.status_code == 200 and not (root.json() or {}).get('ols_terms'):
            raise ValueError(f'No {owl_name} terms are imported on this ELN; import the ontology first '
                             f'(import_ols_terms). Switching terms now would empty its term lists.')
        res = self._session.post('/api/v1/admin/olsEnableDisable',
                                 data={'owl_name': owl_name, 'enableIds': list(enable), 'disableIds': list(disable)})
        self._admin_check(res, f'switching {owl_name} terms')

    @staticmethod
    def _admin_check(res, what: str) -> None:
        if res.status_code == 401:
            raise PermissionError(f'Only admins can do this ({what}).')
        if res.status_code not in (200, 201, 204):
            raise ConnectionError(f'{what}: {res.status_code} -> {res.text}')

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


def _user_id(user) -> int:
    user_id = user if isinstance(user, int) else getattr(user, 'id', None)
    if not isinstance(user_id, int):
        raise ValueError(f'Not a user or user id: {user!r}')
    return user_id
