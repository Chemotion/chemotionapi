Lab data and services
=====================

Chemical inventory and safety data sheets
-----------------------------------------

.. code-block:: python

    from chemotion_api.chemicals import Chemical

    chem = sample.save_chemical(Chemical(cas='64-17-5', data={'status': 'Available'}))
    sample.attach_safety_sheet('sds.pdf', 'Merck', 'merckProductInfo', {'productNumber': 'E7023'})
    instance.set_inventory_label('CHI', 'Chemicals', 0, collection)

.. automodule:: chemotion_api.chemicals
    :members: Chemical, find_safety_sheets, attach_safety_sheet, extract_safety_sheet

Measurements
------------

.. code-block:: python

    plan.create_measurements([{'sample': sample, 'description': 'yield', 'value': 87.5, 'unit': '%'}])
    for m in sample.measurements():
        print(m.description, m.value, m.unit)

.. automodule:: chemotion_api.measurements
    :members: Measurement, MeasurementError, create_measurements

Image annotation
----------------

.. code-block:: python

    svg = image.load_annotation()
    image.save_annotation(svg.replace('</svg>', '<rect x="1" y="1" width="20" height="10"/></svg>'))

Spectra, simulation and computation
-----------------------------------

These start work on services the ELN must have configured (ChemSpectra, nmrdb.org, the inference
and compute servers).

.. autoclass:: chemotion_api.spectra.Spectra
    :members:
.. automodule:: chemotion_api.compute
    :members: simulate_nmr, predict_products, ComputeTask, submit_compute_task

Weighing tasks
--------------

.. automodule:: chemotion_api.sample_tasks
    :members: SampleTask, create_sample_task

Text templates
--------------

.. code-block:: python

    esi = instance.text_templates().predefined('esi')
    sample.properties['description']['ops'] += esi.ops

.. autoclass:: chemotion_api.text_templates.TextTemplates
    :members:
