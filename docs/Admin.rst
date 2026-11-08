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

Administration through the admin account
----------------------------------------

Logging in with an admin account makes :meth:`chemotion_api.Instance.get_user` return an
:class:`chemotion_api.user.Admin`, which manages users, groups, devices and the system. Deleting a
user, group or device needs its abbreviation passed back as ``confirm=``; a deleted user can be
restored. ``restart_job`` takes one job at a time.

.. code-block:: python

    admin = Instance(url).login('ADM', password).get_user()
    (user,) = admin.find_users('Smith')
    admin.update_user(user['id'], account_active=False)
    admin.set_user_rights(user['id'], generic_elements_admin=True)
    device = admin.add_device('NMR 400', 'NMR1')
    admin.update_device(device['id'], people=[user['id']])
    print(admin.disk_usage(), len(admin.jobs()))

.. autoclass:: chemotion_api.user.Admin
    :members:
