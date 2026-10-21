Collection
==========


Collections are the main tool given by the Chemotion system to organize elements.
In the Python API, collections are separated in different classes. The root collection
is the basic element to work with collections.

Collections are addressed by unix-like paths built from their labels, e.g. ``'/Projects/Team One'``.
The label can also be read with the aliases ``name``, ``get_label()`` and ``get_name()``.
Paths starting with ``/`` are absolute, all other paths are relative to the collection the method is called on.
Changes to the collection tree (add, move, delete) are only sent to the server when
:meth:`chemotion_api.collection.RootCollection.save` is called;
:meth:`chemotion_api.collection.Collection.get_or_create_collection` saves right away.

.. code-block:: python

    root = instance.get_root_collection()
    col = root.get_or_create_collection('/Projects/Team One')
    col.add_collection('P 124')
    col.get_collection('P 122').move('/Done Projects')
    root.save()

To iterate over the whole collection tree (or a subtree) use
:meth:`chemotion_api.collection.RootCollection.walk`. It walks depth-first and yields a parent
before its children:

.. code-block:: python

    root = instance.get_root_collection()
    for col in root.walk():                      # every owned collection
        print(col.get_path(), len(col.get_samples()))
    for col in root.sync_root.walk():            # every collection shared with you
        print(col.get_path())
    sub = root.get_collection('/Projects')
    list(sub.walk(include_self=True, max_depth=1))   # '/Projects' and its direct children


.. autoclass:: chemotion_api.collection.RootCollection
    :members:
    :inherited-members:

The root collection organizes the standard Collections:

.. autoclass:: chemotion_api.collection.Collection
    :members:
    :inherited-members:

.. autoenum:: chemotion_api.collection.SyncPermission

The RootCollection also has a property (``sync_root``) to get the RootSyncCollection. It contains all collections
shared with you.

.. autoclass:: chemotion_api.collection.RootSyncCollection