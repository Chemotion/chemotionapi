from chemotion_api.connection import Connection


class AdminMenu:
    """Administrator-only endpoints.

    ``create_device`` and its misspelling ``greate_device`` were removed in 401.0. Both posted to
    ``/api/v1/admin/group_device/create`` with ``rootType: 'Device'``, which cannot create a
    device on any Chemotion release: ``Device`` has ``validates :name, presence: true`` and that
    endpoint declares no ``name`` parameter, so Grape's ``declared`` dropped any attempt to supply
    one and every call failed with ``Validation failed: Name Please enter a name``. They also
    returned the server's error hash as if it were a created device, so the failure was silent.

    Use :meth:`chemotion_api.user.Admin.create_device`, which posts to ``/api/v1/admin_devices``,
    returns a typed :class:`~chemotion_api.user.Device`, and raises on a rejected create.
    """

    def __init__(self, session: Connection):
        self._session = session
