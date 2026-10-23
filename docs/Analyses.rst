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

Note that the datasets of an analysis are an attribute (``analysis.datasets``), not a dict key, and that a
dataset's dict holds only its metadata set; its name is ``dataset.name``.

.. code-block:: python

    for analysis in sample.analyses:
        print(analysis['name'], analysis['kind'] if 'kind' in analysis else '')
        for dataset in analysis.datasets:
            print('  ', dataset.name, dataset.id, [a['filename'] for a in dataset.attachments or []])

Converter profiles
------------------

The metadata set of a dataset is only filled automatically if a converter profile matches the uploaded file.
Profiles are managed with the :class:`chemotion_api.converter.ProfileManager`:

.. code-block:: python

    pm = instance.get_profile_manager()
    for profile in pm.profiles:          # a property, not a method
        print(profile.id, profile.title)
    profile = pm.new_profile_from_file('./my_profile.json')
    profile.save()

API Classes
------------

.. autoclass:: chemotion_api.elements.abstract_element.AnalysesList
    :members:

.. autoclass:: chemotion_api.elements.abstract_element.Analyses
    :members:

.. autoclass:: chemotion_api.elements.abstract_element.Dataset
    :members:

.. autoclass:: chemotion_api.converter.ProfileManager
    :members:

.. autoclass:: chemotion_api.converter.Profile
    :members: