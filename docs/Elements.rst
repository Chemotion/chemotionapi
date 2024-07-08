Elements
==========

The API can handle different kinds of elements from Chemotion.
It can read and write Samples, Reactions, Wellplates, and Research Plans
as well as Generic Elements.

How to load Elements
******************************

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

How to create Elements
******************************

To make a new entry in the ELN, you must first select the collection in which the element is to be created. Collection objects have the appropriate methods for creating objects.

The following methods can be used to create the standard objects. All of them have no parameters and create an empty object corresponding to its type.

The created object is not saved and must be saved explicitly so that the entry is transferred to the ELN.

* :meth:`chemotion_api.collection.Collection.new_samples`
* :meth:`chemotion_api.collection.Collection.new_reaction`
* :meth:`chemotion_api.collection.Collection.new_research_plan`
* :meth:`chemotion_api.collection.Collection.new_wellplate`

To create a generic element, the type must be specified as a parameter. Either by the human readable lable or by the system internal name:

* :meth:`chemotion_api.collection.Collection.new_generic`
* :meth:`chemotion_api.collection.Collection.new_generic_by_label`

Since a sample cannot be created without a molecule (not by default at least), there is also the shortcut using the following methods

* :meth:`chemotion_api.collection.Collection.new_sample_smiles`
* :meth:`chemotion_api.collection.Collection.new_solvent`

And finally, all objects can be created using the IRI-based method:

* :meth:`chemotion_api.collection.Collection.new_element_by_iri`


.. code-block:: python

    try:
        col = instance.get_root_collection().get_collection('Main Test')
        sample = col.new_sample_smiles('XXX')
        sample.save()
    except requests.exceptions.RequestException as e:
        pass


How to work with Elements
********************************

