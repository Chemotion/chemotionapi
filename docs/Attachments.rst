Attachments
================

This object handles the files attached to an element (``element.attachments``).
New files are added with :meth:`chemotion_api.elements.attachments.Attachments.add_file` and uploaded when
the element is saved. To load a new attachment, reload the element first (``element.save(load_after_save=True)``).
See also Example 3 in :doc:`Examples`.

API Classes
------------

.. autoclass:: chemotion_api.elements.attachments.Attachments
    :members:

.. autoclass:: chemotion_api.elements.attachments.Attachment
    :members: