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

User labels
-----------

A sample's user labels are exposed as bare ids in ``properties['user_labels']``. Use
``sample.user_labels_resolved`` to get :class:`~chemotion_api.user.UserLabel` objects with their
titles — see :doc:`Instance` for details and the caching behaviour.
