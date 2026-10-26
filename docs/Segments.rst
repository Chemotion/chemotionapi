Segments
==========

Segments are additional tabs of an element, defined with LabIMotion. All elements, including samples
and reactions, can have segments. A segment consists of layers, and each layer of fields. The values are
accessible through the ``segments`` property of an element: ``element.segments[segment][layer][field]``.
The segment, layer and field names are the labels shown in Chemotion; duplicate names get the suffix
``.1``, ``.2``, ...

``element.segments`` also contains the keys ``'Properties'`` and ``'Analyses'``, which are the same objects
as ``element.properties`` and ``element.analyses``.

A segment the element does not have yet is ``None``. Use ``segments.get(name)`` to add it with the default
values of the template.

.. code-block:: python

    sample = instance.get_sample(1)
    cell = sample.segments.get('Electrochemistry')['Cell']

    # Look up what a field accepts
    sample.segments.field_type('Electrochemistry', 'Cell', 'Electrode type')  # 'select'
    sample.segments.options('Electrochemistry', 'Cell', 'Electrode type')
    # [{'key': 'traditional', 'label': 'disk'}, {'key': 'mesh', 'label': 'mesh'}]
    sample.segments.units('Electrochemistry', 'Cell', 'Temperature')  # ['C', 'F', 'K']

    cell['Electrode type'] = 'disk'                      # key or label; stored as key
    cell['Temperature'] = {'value': 25, 'unit': 'C'}
    cell['Cycles'] = 3
    sample.save()

Values by field type
--------------------

* **select**: the option key. The option label is accepted as well and stored as key.
* **system-defined**: ``{'value': ..., 'unit': ...}``. A bare number gets the default unit of the field.
* **integer**: a whole number.
* **text** and other fields: stored as they are.

Changed select, system-defined and integer values are checked against the template when the element is saved;
an invalid value raises a ``ValueError``. Values loaded from the server are never rejected, even if they
do not fit the template anymore.

For segment values in reaction variations, see :doc:`ReactionDetails`.

API Classes
------------

.. autoclass:: chemotion_api.elements.abstract_element.Segment
    :members: get, field, field_type, options, units

.. autoclass:: chemotion_api.utils.segment_fields.SegmentField
    :members:
