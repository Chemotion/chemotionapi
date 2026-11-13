from chemotion_api.connection import Connection


class AdminMenu:
    """Administrator-only endpoints.

    ``greate_device`` was removed in 312.1. It posted to ``/api/v1/admin/group_device/create``
    with ``rootType: 'Device'``, which cannot create a device on ELN 3.1.x: ``Device`` has
    ``validates :name, presence: true`` and that endpoint declares no ``name`` parameter, so every
    call failed with ``Validation failed: Name Please enter a name``. It also returned the server's
    error hash as if it were a created device, so the failure was silent.

    Use :meth:`chemotion_api.user.Admin.create_device`, which posts to ``/api/v1/admin_devices``,
    returns a typed :class:`~chemotion_api.user.Device`, and raises on a rejected create.
    """

    def __init__(self, session: Connection):
        self._session = session
