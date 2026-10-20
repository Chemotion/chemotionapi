Analyses
==========
The Analyses object represents the Analyses tab in the Chemotion user interface.
It contains all measurement data and metadata associated with the elements.

Each element has an :class:`chemotion_api.elements.abstract_element.AnalysesList` (``element.analyses``).
An analysis contains datasets; a dataset contains the measurement files and a metadata set, which Chemotion fills
automatically if a converter profile (:meth:`chemotion_api.Instance.get_profile_manager`) matches the uploaded file.
New analyses and datasets are created and uploaded when the element is saved.

.. code-block:: python

    sample = instance.get_sample(1)
    analysis = sample.analyses.add_analyses('NMR')
    analysis['description'] = '1H NMR in CDCl3'
    analysis.add_dataset('./nmr_data.zip')
    sample.save()

API Classes
------------

.. autoclass:: chemotion_api.elements.abstract_element.AnalysesList
    :members:

.. autoclass:: chemotion_api.elements.abstract_element.Analyses
    :members:

.. autoclass:: chemotion_api.elements.abstract_element.Dataset
    :members: