Chemotion Instance
==================

The chemotion instance is the foundation of the
the python chemtion client. It includes all methods to work with this tool.

.. autoclass:: chemotion_api.Instance
    :members:

Errors
******

Requests the server refuses raise one of these.

* :class:`~chemotion_api.connection.ChemotionRequestError`: the server answered with an error
  status (4xx). The message carries the status, the request and a short form of the reply.
* :class:`~chemotion_api.connection.ChemotionServerError`: a 5xx, usually the server failing on
  data it did not accept.
* :class:`~chemotion_api.connection.ChemotionRejectedError`: the server answered with a success
  status but said in the body that it did not do it (``{"errors": …}``, ``{"error": …}``,
  ``{"success": false}``). It is also a ``ConnectionError`` and a ``ValueError``; the decoded
  reply is in ``body``.

.. code-block:: python

    from chemotion_api.connection import ChemotionRejectedError

    admin = instance.get_user()            # logged in as an administrator

    try:
        device = admin.create_device('NMR 400', 'NMR')
    except ChemotionRejectedError as e:
        print('refused:', e.body)

.. autoclass:: chemotion_api.connection.ChemotionRejectedError
    :members:
