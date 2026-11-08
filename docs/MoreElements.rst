More element types and element tools
====================================

Screens, cell lines, device descriptions and SBMM samples are elements like samples: create them in a
collection, change ``properties`` and call ``save()``. Listing works through the collection
(``get_screens()``, ``get_cell_lines()``, ``get_device_descriptions()``, ``get_sbmm_samples()``) and
single elements through the instance (``get_screen(id)``, …).

Screens
-------

.. code-block:: python

    screen = collection.new_screen()
    screen.properties['name'] = 'Kinase panel'
    plate = collection.new_wellplate(); plate.save()
    screen.add_wellplate(plate)
    screen.save()
    plan = screen.new_research_plan(collection)   # created and linked by the server

.. autoclass:: chemotion_api.elements.screen.Screen
    :members:

Cell lines
----------

A cell line *sample* belongs to a cell line *material*, which the server finds or creates by
``material_names`` and ``source``.

.. code-block:: python

    cells = collection.new_cell_line()
    cells.properties.update(material_names='HeLa', source='ATCC', amount=1_000_000,
                            unit='cell count', passage=12, organism='Homo sapiens')
    cells.save()
    part = cells.split(collection)       # created right away, labelled <short label>-1

.. autoclass:: chemotion_api.elements.cell_line.CellLine
    :members: copy, split, material_id

Device descriptions
-------------------

.. code-block:: python

    dev = collection.new_device_description()
    dev.properties.update(name='NMR 400', vendor_company_name='Bruker', room='1.23')
    dev.save()
    (sub,) = collection.split_device_descriptions(dev)
    dev.download_analyses('analyses.zip')

.. autoclass:: chemotion_api.elements.device_description.DeviceDescription
    :members: ancestor_ids, download_analyses

Sequence-based macromolecule samples
------------------------------------

.. code-block:: python

    s = collection.new_sbmm_sample()
    s.properties['name'] = 'Lysozyme batch 1'
    s.use_uniprot('P61626')               # or fill s.macromolecule (short_name, sequence, ...)
    s.save()
    instance.search_macromolecules('lysozyme', 'protein_name')

.. autoclass:: chemotion_api.elements.sbmm.SbmmSample
    :members: macromolecule, use_uniprot

.. autoexception:: chemotion_api.elements.sbmm.SbmmUpdateNotAllowed

Vessels
-------

Vessel templates describe a kind of vessel and are shared by everyone; vessels are physical items of
a template. Both are saved immediately and have UUID ids.

.. code-block:: python

    flask = instance.new_vessel_template('Flask 250 ml', vessel_type='round bottom flask',
                                         material_type='glass', volume_amount=250, volume_unit='ml').save()
    v = collection.new_vessel(flask, weight_amount=120.5, weight_unit='g')
    rack = collection.new_vessels(flask, 10, base_name='rack')

.. automodule:: chemotion_api.vessels
    :members: VesselTemplate, Vessel

Deleting elements
-----------------

``element.delete()`` and ``collection.delete_elements(*elements)`` delete the way the web UI does:
ELN v4 withdraws the elements from every collection you own and destroys only records left in no
collection. ``delete()`` returns whether the record is really gone. Ask before deleting.

Splitting
---------

``collection.split_samples(*samples)`` creates *linked* subsamples on the server (``<label>-<n>``).
``Sample.split()`` only builds an unsaved copy, which is linked to its parent only when it is saved
as part of a reaction or wellplate. Wellplates, device descriptions, SBMM samples and generic
elements have matching ``split_*`` methods on the collection.

Comments, private notes, versions, literature and labels
--------------------------------------------------------

.. code-block:: python

    sample.add_comment('Check the purity', section='properties')
    sample.set_private_note('only visible to me')
    for version in sample.versions():
        print(version.time, version.user, version.changes)
    sample.add_reference(doi='10.1021/acs.jchemed.0c00101')
    collection.update_user_labels(sample, reaction, add=[label])

.. automethod:: chemotion_api.elements.abstract_element.AbstractElement.versions
    :no-index:
.. autoclass:: chemotion_api.elements.versions.Version
    :members: revert
.. autoclass:: chemotion_api.elements.literature.Reference

Molecules and mixtures
----------------------

.. code-block:: python

    mm = instance.molecule()
    mol = mm.create_molecule_by_molfile(molfile)     # ValueError for unreadable molfiles
    sample = collection.new_sample_molfile(molfile)
    mm.load_cas(mol['inchikey']); mm.lookup_cas('64-17-5')
    parts = sample.components()                       # mixture components

.. autoclass:: chemotion_api.elements.components.Component
    :members: new
