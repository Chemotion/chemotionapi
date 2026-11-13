Screen
==========

A screen groups wellplates and research plans, for example the plates of one assay campaign.
Create one with :meth:`chemotion_api.collection.Collection.new_screen`, fetch one with
:meth:`chemotion_api.Instance.get_screen`, and list them with
:meth:`chemotion_api.collection.Collection.get_screens`.

``properties`` holds ``name``, ``collaborator``, ``requirements``, ``conditions``, ``result`` and
``description``. The description is rich text: assign a plain string or a Quill delta (see
:doc:`Elements`, *Rich text*).

The linked wellplates and research plans are id lists, ``wellplate_ids`` and
``research_plan_ids``. A save sends these lists as the new links, so they always hold the current
state, and an empty list removes every link. ``wellplates`` and ``research_plans`` load the
linked elements.

.. code-block:: python

    plate = col.new_wellplate()
    plate.save()

    screen = col.new_screen()
    screen.properties['name'] = 'Kinase panel'
    screen.properties['conditions'] = '37 °C, 24 h'
    screen.wellplate_ids.append(plate.id)
    screen.save()

    screen = instance.get_screen(screen.id)
    print([w.properties['name'] for w in screen.wellplates])

.. autoclass:: chemotion_api.elements.screen.Screen
    :members:
