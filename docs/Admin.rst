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
