Cell line
==========

A cell-line sample is a quantity of cells: amount, unit, passage, contamination. It belongs to a
cell-line **material**, the cell line itself, which every sample of it shares: name, source,
organism, tissue, growth medium and so on. The client keeps the two apart. ``properties`` holds
the sample's own fields and :attr:`~chemotion_api.elements.cell_line.CellLine.material` the
shared ones.

Create one with :meth:`chemotion_api.collection.Collection.new_cell_line`, naming the material
and its source. An existing material with that name and source is reused; otherwise saving
creates one. ``amount``, ``unit`` and ``passage`` must be set before saving. Fetch one with
:meth:`chemotion_api.Instance.get_cell_line` and list them with
:meth:`chemotion_api.collection.Collection.get_cell_lines`.

.. code-block:: python

    line = col.new_cell_line('HeLa', source='ATCC')
    line.properties['amount'] = 1_000_000
    line.properties['unit'] = 'cells'
    line.properties['passage'] = 3
    line.material['organism'] = 'Homo sapiens'
    line.save()

How the material behaves on save:

* Changing the material's ``name`` or ``source`` links the sample to another material, which is
  created if none matches.
* Every save sends the full material, so a save that only changed the sample never re-links it.
* The ELN applies changes to the material's other fields only when you created that material. For
  a material someone else created, it ignores the change while reporting success. The client
  checks this first and raises ``PermissionError`` instead.
* A change to the material shows on every sample of that cell line.

.. autoclass:: chemotion_api.elements.cell_line.CellLine
    :members:
