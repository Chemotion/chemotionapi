Sample
==========

A sample is created in a collection, usually from a SMILES code
(:meth:`chemotion_api.collection.Collection.new_sample_smiles`), or as solvent from the predefined
solvent list (:meth:`chemotion_api.collection.Collection.new_solvent`).

The amount of a sample is set with :meth:`chemotion_api.elements.sample.Sample.set_amount`, in gram, liter or mol
(see :meth:`chemotion_api.elements.sample.Sample.allowed_quantity_units`). If the sample is part of a reaction,
this updates the equivalents of all reaction materials. The converted amount is available as
:attr:`chemotion_api.elements.sample.Sample.gram`, :attr:`chemotion_api.elements.sample.Sample.mol` and
:attr:`chemotion_api.elements.sample.Sample.liter`.

.. code-block:: python

    from chemotion_api.elements.utils import QuantityUnit

    sample = col.new_sample_smiles('CCO')
    sample.properties['external_label'] = 'Ethanol'
    sample.set_amount(2.5, QuantityUnit.Gram)
    sample.save()

    # Set the amount of a starting material via its equivalent
    reaction = instance.get_reaction(1)
    reaction.reactants[0].set_amount(1.5, QuantityUnit.Equivalent)
    reaction.save()

.. autoclass:: chemotion_api.elements.sample.Sample
    :members:


.. autoclass:: chemotion_api.elements.sample.Molecule
    :members:

.. autoclass:: chemotion_api.elements.sample.MoleculeManager
    :members:

.. autoclass:: chemotion_api.elements.sample.SolventList
    :members:

.. autoclass:: chemotion_api.elements.sample.GasPhaseObj
    :members: ppm, time_in_h, temperature_in_k

.. autoenum:: chemotion_api.elements.utils.QuantityUnit

.. autoenum:: chemotion_api.elements.utils.GasType

Chemical inventory and safety data
----------------------------------

The ELN's *Chemicals* tab, with vendor, amounts, storage location and safety data, is a separate
record. :meth:`~chemotion_api.elements.sample.Sample.get_chemical` returns it as a
:class:`~chemotion_api.elements.sample.Chemical`. When the sample has none yet, ``exists`` is
``False`` and ``save()`` creates it.

.. code-block:: python

    chemical = sample.get_chemical()
    chemical.cas = '64-17-5'
    chemical.data['location'] = 'Cabinet 3'
    chemical.save()

.. autoclass:: chemotion_api.elements.sample.Chemical
    :members:

Molecule names
--------------

A molecule is known by several names: IUPAC name, sum formula, and names users added. A sample
shows one of them. :meth:`~chemotion_api.elements.sample.MoleculeManager.get_names` lists them,
:meth:`~chemotion_api.elements.sample.MoleculeManager.add_name` adds one, and
:attr:`~chemotion_api.elements.sample.Sample.molecule_name_id` chooses the one the sample shows.

.. code-block:: python

    molecules = instance.molecule()
    name = molecules.add_name(sample.molecule['id'], 'Spirit')
    sample.molecule_name_id = name.id
    sample.save()

.. autoclass:: chemotion_api.elements.sample.MoleculeName
    :members:

User labels
-----------

A sample's user labels are exposed as bare ids in ``properties['user_labels']``. Use
``sample.user_labels_resolved`` to get :class:`~chemotion_api.user.UserLabel` objects with their
titles — see :doc:`Instance` for details and the caching behaviour.
