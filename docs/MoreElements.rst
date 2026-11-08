More element types and element tools
====================================

Vessels, deletion, splitting, comments, private notes, versions, literature, labels, molecules and
mixtures: tools that work across element types.

Screens, cell lines, device descriptions and SBMM samples each have their own page
(:doc:`ScreenDetails`, :doc:`CellLineDetails`, :doc:`DeviceDescriptionDetails`,
:doc:`SbmmSampleDetails`). Device descriptions and SBMM samples can also be split on the server:

.. code-block:: python

    (sub,) = collection.split_device_descriptions(dev)
    (part,) = collection.split_sbmm_samples(sbmm)

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
    sample.properties['user_labels'] = [label.id]; sample.save()

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
