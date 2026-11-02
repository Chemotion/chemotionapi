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

Elements are moved between collections with
:meth:`chemotion_api.collection.AbstractCollection.move_elements`,
:meth:`chemotion_api.collection.AbstractCollection.assign_elements` and
:meth:`chemotion_api.collection.AbstractCollection.remove_elements`
(or the element methods ``move_to``, ``assign_to`` and ``remove_from``). These requests are sent right away.
Assigning adds the same element to a second collection, it does not duplicate it.
Elements cannot be moved or removed from the root ('All') collection:

.. code-block:: python

    src = root.get_collection('/Projects/Team One')
    dest = root.get_collection('/Done Projects')
    sample = src.get_samples()[0]
    src.move_elements(dest, sample)       # or sample.move_to(dest, src)
    root.assign_elements(src, sample)     # or sample.assign_to(src)
    src.remove_elements(sample)           # or sample.remove_from(src)


.. autoclass:: chemotion_api.collection.RootCollection
    :members:
    :inherited-members:

The root collection organizes the standard Collections:

.. autoclass:: chemotion_api.collection.Collection
    :members:
    :inherited-members:

.. autoenum:: chemotion_api.collection.CollectionSharePermission

Collections shared **with** you are reached through :attr:`RootCollection.sync_root`. The
"sync" naming predates ELN v4, which removed the ``/syncCollections`` namespace: shared
collections now arrive in the ``shared_with_me`` list of the ordinary collection listing, and no
extra request is made. The names are kept for compatibility.

.. autoclass:: chemotion_api.collection.RootSyncCollection
    :members:
    :inherited-members:
