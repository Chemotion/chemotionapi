Reaction
==========

A reaction has five material lists: starting materials, reactants, products, solvents and purification solvents
(:class:`chemotion_api.elements.reaction.MaterialList`). Adding a sample to the starting materials or reactants
adds a split of it, adding it to the products adds a copy.
:meth:`chemotion_api.elements.reaction.MaterialList.append_no_split` adds the sample itself. In both cases the
reaction, role and position of the sample are set and its amount is initialized. Saving the reaction recomputes the
equivalents (and the yields of the products) from the amounts and the reference material.

.. autoclass:: chemotion_api.elements.reaction.Reaction
    :members:

.. autoclass:: chemotion_api.elements.reaction.MaterialList
    :members:

.. autoclass:: chemotion_api.elements.reaction.Temperature
    :members:

Variations
----------

The variations tab of a reaction is accessible through :attr:`chemotion_api.elements.reaction.Reaction.variations`.
Each variation has a temperature, a duration, notes, the quantities of all materials and the values of the reaction
segments. Variations are saved with the reaction.

.. code-block:: python

    from chemotion_api.elements.utils import QuantityUnit

    reaction = instance.get_reaction(1)
    variation = reaction.variations.add_new()
    variation.properties['temperature']['value'] = 80
    variation.notes = 'Second run'

    # Quantities of the materials
    variation.starting_materials[0].set_quantity(2, QuantityUnit.Gram)
    variation.reactants[0].set_equivalent(1.5)
    variation.products[0].set_yield(85)  # in percent

    # Link an (already saved) analysis of the reaction
    variation.link_analyses(reaction.analyses.by_name('HPLC run 2'))

    # Segment values ({segment: {layer: {field: value}}})
    variation.segments['Electrochemistry']['Cell']['Electrode type'] = 'disk'
    variation.segments['Electrochemistry']['Cell']['Temperature'] = {'value': 25, 'unit': 'C'}
    reaction.save()

Only text, integer, select and system-defined segment fields can be varied. Select fields take the option key
or label, system-defined fields take ``{'value': ..., 'unit': ...}`` or a number in the field's default unit.
On save, every variation gets the same segments, as the Chemotion frontend builds the columns from them.
A system-defined field without a default unit in the segment template cannot be given a value in a
variation, since the frontend cannot show it.

Quantities of mixtures (:attr:`chemotion_api.elements.sample.Sample.is_mixture`) are not supported in
variations yet.

.. autoclass:: chemotion_api.elements.reaction.Variations
    :members: add_new, remove

.. autoclass:: chemotion_api.elements.reaction.Variation
    :members: properties, segments, starting_materials, reactants, products, solvents, link_analyses, get_analyses

.. autoclass:: chemotion_api.elements.reaction.SampleVariation
    :members: sample, is_ref, potential_units, set_quantity, set_equivalent, set_yield, get_amount, get_mass, get_volume, get_equivalent_or_yield

.. autoclass:: chemotion_api.elements.reaction.VariationSegments
