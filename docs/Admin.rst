Administration
==============

Some operations require administrator (or device) privileges; the server returns ``401`` otherwise.

Device management
-----------------

Devices are created and listed through :class:`chemotion_api.user.Admin`, which
:meth:`chemotion_api.Instance.get_user` returns when the logged-in user is an administrator.

.. code-block:: python

    admin = instance.get_user()                             # an Admin, when logged in as one
    device = admin.create_device("Device Name", "ABC")      # admin only
    device.delete()

:meth:`~chemotion_api.user.Admin.create_device` returns a typed :class:`~chemotion_api.user.Device`
and raises when the server reports an error — note that a rejected ``name_abbreviation`` comes back
as ``201`` with an ``errors`` body rather than as a failure status.

.. warning::
   **A device you create does not appear in** :meth:`~chemotion_api.user.Admin.fetchDevices`.
   The two read different things on the server: creation writes a row to the ``devices`` table,
   while ``fetchDevices()`` lists *users* whose type is ``Device`` — a separate, older concept
   that happens to share the name. This is a server-side inconsistency, not something this client
   can paper over; a created device is visible through ``GET /api/v1/admin_devices``.

:class:`chemotion_api.user.DeviceManager` covers group membership only
(:meth:`~chemotion_api.user.DeviceManager.add_users_to_group`); it does not create devices.

.. autoclass:: chemotion_api.user.DeviceManager
    :members:

Admin-only endpoints
--------------------

:class:`chemotion_api.admin.AdminMenu` wraps administrator-only API endpoints. Construct it with an
authenticated connection.

.. autoclass:: chemotion_api.admin.AdminMenu
    :members:
