Administration
==============

Some operations require administrator (or device) privileges; the server returns ``401`` otherwise.

Device management
-----------------

Devices are managed through the instance's device manager, obtained via
:attr:`chemotion_api.Instance.device_manager`.

.. code-block:: python

    dm = instance.device_manager
    device = dm.create_new_device("First", "Last", "FL")   # admin/super-device only
    devices = dm.fetchDevices()

.. autoclass:: chemotion_api.user.DeviceManager
    :members:

Admin-only endpoints
--------------------

:class:`chemotion_api.admin.AdminMenu` wraps administrator-only API endpoints. Construct it with an
authenticated connection.

.. note::
   ``AdminMenu.create_device`` was previously misspelled ``greate_device``; the old name remains as a
   deprecated alias (emits a ``DeprecationWarning``) and will be removed in a future release.

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
