Elements
==========

The API can handle different kinds of elements from Chemotion.
It can read and write Samples, Reactions, Wellplates, and Research Plans
as well as Generic Elements.

1) **How to load Elements**

Single elements can be fetched directly from the instance,
whereas lists of elements must be fetched by a collection.
The documentation for these methods can be found in the corresponding sections
(:mod:`chemotion_api.collection.Collection` & :mod:`chemotion_api.Instance`).

Lets construct an example base on Samples.
To load a single sample you can use :meth:`chemotion_api.Instance.get_sample`
However, to do so you need to know the exact Database Id of the Sample.

.. code-block:: python

    try:
        sample = instance.get_sample(3)
    except requests.exceptions.RequestException as e:
        pass

To load all elements within a list use :meth:`chemotion_api.collection.Collection.get_samples`.
This method returns an Object of class ElementSet

.. autoclass:: chemotion_api.elements.ElementSet

.. code-block:: python

    try:
        for sample in instance.get_root_collection().get_collection('Main Test').get_samples():
            pass # DO something
    except requests.exceptions.RequestException as e:
        pass

The elements are loaded lazily and always in bundles of size 10.
You can increase the bundle size with the second argument of the Load method.

Alternative elements can be loaded using there JSON LD *@id*.
Use the methode :meth:`chemotion_api.Instance.get_json_ld_id`
This id contains its origen host, type and DB id.
The following nonsense code snippet introduces the workflow:

.. code-block:: python

    try:
        sample_A = instance.get_sample(3)
        sample_B = instance.get_json_ld_id(sample.json_ld['@id'])
        assert sample_A == sample_B
    except requests.exceptions.RequestException as e:
        pass

The JSON LD alternative for loading lists of elements uses the
the JSON LD property *@type* :meth:`chemotion_api.collection.Collection.get_elements_of_iri`
This type contains teh version and the type Element.
The following nonsense code snippet introduces the workflow:

.. code-block:: python

    try:
        sample_A = instance.get_sample(3)
        col = instance.get_root_collection().get_collection('Main Test')
        sample_list = col.get_elements_of_iri(sample.json_ld['@type'])
    except requests.exceptions.RequestException as e:
        pass

2) **How to create Elements**


3) **How to work with Elements**
