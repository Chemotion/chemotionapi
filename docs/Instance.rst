Chemotion Instance
==================

The chemotion instance is the foundation of the
the python chemtion client. It includes all methods to work with this tool.

.. autoclass:: chemotion_api.Instance
    :members:

User labels
***********

Chemotion shows coloured *user labels* on samples and reactions. On the wire an element carries
only the label **ids**, so reading ``properties['user_labels']`` gives you something like
``[3, 5]`` and nothing about what those mean.

To get the id-to-title map for the logged-in user:

.. code-block:: python

    for label in instance.get_user_labels():
        print(label.id, label.title, 'shared' if label.is_shared else 'private')

You see your own private labels plus every shared one, in the order the ELN itself displays them.

To resolve the labels *of a particular element*, use its ``user_labels_resolved`` property rather
than matching ids by hand:

.. code-block:: python

    sample = instance.get_sample(3)
    print(', '.join(label.display_title for label in sample.user_labels_resolved))

The label list is fetched **once per connection**, so resolving labels across hundreds of
elements costs a single request. The raw id list in ``properties['user_labels']`` is left
untouched, so an element can be resolved and saved without changing what goes back to the server.

An element may carry a label owned by another user, which the server will not return to you. That
is not an error: the id resolves to a placeholder :class:`~chemotion_api.user.UserLabel` with
``title`` ``None``, ``is_resolved`` ``False`` and ``display_title`` ``"#<id>"``. Prefer
``display_title`` over ``title`` when building strings, so an unresolvable label cannot break a
``join``.

To create a label, or change one of your own, use :meth:`~chemotion_api.Instance.save_user_label`.
The ELN overwrites every field a request leaves out, so the whole label is always sent; set every
field you want to keep. ``access_level`` is ``0`` for a private label and ``1`` or ``2`` for a
shared one. Put labels on an element through ``properties['user_labels']`` and save it.

.. code-block:: python

    from chemotion_api.user import UserLabel

    label = instance.save_user_label(UserLabel(title='Needs review', color='#d9534f', access_level=0))
    sample.properties['user_labels'] = list(sample.properties['user_labels'] or []) + [label.id]
    sample.save()

.. autoclass:: chemotion_api.user.UserLabel
    :members:

Affiliations
************

.. autoclass:: chemotion_api.user.Affiliation
    :members:

Errors
******

Requests the server refuses raise one of these. Each is also a ``ConnectionError``, so a broad
``except ConnectionError`` still catches them.

* :class:`~chemotion_api.connection.ChemotionRequestError`: the server answered with an error
  status (4xx). The message carries the status, the request and a short form of the reply.
* :class:`~chemotion_api.connection.ChemotionServerError`: a 5xx, usually the server failing on
  data it did not accept.
* :class:`~chemotion_api.connection.ChemotionRejectedError`: the server answered with a success
  status but said in the body that it did not do it (``{"errors": …}``, ``{"error": …}``,
  ``{"success": false}``). It is also a ``ValueError``; the decoded reply is in ``body``.

Before a request is sent:

* :class:`~chemotion_api.schema_manager.UnsupportedServerVersion`: the server is not an ELN v4.
* :class:`~chemotion_api.connection.TokenExpiredError` (a ``PermissionError``): the login token
  has expired; log in again.

Reading a field the server withheld from you, as a number, raises
:class:`~chemotion_api.utils.withheld.WithheldValueError` (a ``PermissionError``); see
:doc:`Elements`.

.. code-block:: python

    from chemotion_api.connection import ChemotionRejectedError

    admin = instance.get_user()            # logged in as an administrator

    try:
        device = admin.create_device('NMR 400', 'NMR')
    except ChemotionRejectedError as e:
        print('refused:', e.body)

.. autoclass:: chemotion_api.connection.ChemotionRejectedError
    :members:
