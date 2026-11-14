Elements
==========

The API can handle different kinds of elements from Chemotion.
It can read and write samples, reactions, wellplates, research plans, screens, cell lines,
SBMM samples and device descriptions, as well as LabIMotion generic elements.

How to load Elements
******************************

Single elements can be fetched directly from the instance,
whereas lists of elements must be fetched by a collection.
The documentation for these methods can be found in the corresponding sections
(:mod:`chemotion_api.collection.Collection` & :mod:`chemotion_api.Instance`).

Let's construct an example based on Samples.
To load a single sample you can use :meth:`chemotion_api.Instance.get_sample`.
However, to do so you need to know the exact Database Id of the Sample.

.. code-block:: python

    try:
        sample = instance.get_sample(3)
    except requests.exceptions.RequestException as e:
        pass

To load all elements within a list use :meth:`chemotion_api.collection.Collection.get_samples`.
This method returns an Object of class ElementSet

.. autoclass:: chemotion_api.elements.ElementSet
    :members: page, iter_pages, next_page, prev_page, load_element

.. code-block:: python

    try:
        for sample in instance.get_root_collection().get_collection('Main Test').get_samples():
            pass # DO something
    except requests.exceptions.RequestException as e:
        pass

The elements are loaded lazily, page by page, with 10 elements per page by default.
You can change the page size with the *per_page* argument of the get methods
(e.g. ``col.get_samples(per_page=50)``). All get methods also accept *updated_from_date* and
*updated_to_date* to fetch only elements updated in a time range.

Alternatively, elements can be loaded using their JSON-LD *@id*.
Use the method :meth:`chemotion_api.Instance.get_json_ld_id`.
This id contains its origin host, type and DB id.
The following nonsense code snippet introduces the workflow:

.. code-block:: python

    try:
        sample_A = instance.get_sample(3)
        sample_B = instance.get_json_ld_id(sample_A.json_ld['@id'])
        assert sample_A == sample_B
    except requests.exceptions.RequestException as e:
        pass


The JSON-LD alternative for loading lists of elements uses
the JSON-LD property *@type*: :meth:`chemotion_api.collection.Collection.get_elements_of_iri`.
This type contains the version and the element type. All types known by the server are listed by
:meth:`chemotion_api.Instance.get_all_types`.
The following nonsensical code snippet introduces the workflow:

.. code-block:: python

    try:
        sample_A = instance.get_sample(3)
        col = instance.get_root_collection().get_collection('Main Test')
        for sample in col.get_elements_of_iri(sample_A.json_ld['@type']):
            pass # DO something
    except requests.exceptions.RequestException as e:
        pass

Elements can also be found with the advanced search, see :doc:`Search`.

Elements in a list are only partially loaded. An element is loaded completely (one request per element) the first time its properties, segments, analyses or attachments are read or changed, so neither reading nor saving uses incomplete data. ``id``, ``name``, ``short_label`` and ``json_data`` are available without loading.
Elements accessed by index (``col.get_samples()[3]``) are loaded completely.

How to create Elements
******************************

To make a new entry in the ELN, you must first select the collection in which the element is to be created. Collection objects have the appropriate methods for creating objects.

The following methods can be used to create the standard objects. They create an empty object of their type; cell lines and SBMM samples need a little information up front.

The created object is not saved and must be saved explicitly so that the entry is transferred to the ELN.

* :meth:`chemotion_api.collection.Collection.new_sample`
* :meth:`chemotion_api.collection.Collection.new_reaction`
* :meth:`chemotion_api.collection.Collection.new_research_plan`
* :meth:`chemotion_api.collection.Collection.new_wellplate`
* :meth:`chemotion_api.collection.Collection.new_screen`
* :meth:`chemotion_api.collection.Collection.new_device_description`
* :meth:`chemotion_api.collection.Collection.new_cell_line` (material name and source)
* :meth:`chemotion_api.collection.Collection.new_sbmm_sample` (UniProt accession)

To create a generic element, the type must be specified as a parameter. Either by the human-readable label or by the system-internal name:

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
        sample = col.new_sample_smiles('CCO')
        sample.properties['external_label'] = 'Ethanol'
        sample.save()
    except requests.exceptions.RequestException as e:
        pass

How to work with Elements
********************************

All Objects have a set of common properties and methods:

* ``properties``: the data of the main tab of the element. The available keys are listed in the
  sections of the element types.
* ``segments``: the generic segments (tabs) of the element, see :doc:`Segments`.
* ``analyses``: the analyses tab, see :doc:`Analyses`.
* ``attachments``: the attached files, see :doc:`Attachments`.
* ``save()`` / ``load()``: writes the element to / reads it from the server.
* ``open()``: opens the saved element in a new tab of your web browser; ``url()`` returns its URL.

.. code-block:: python

    sample = instance.get_sample(3)
    sample.properties['description'] = 'Stored in the fridge'
    sample.save()
    # Check the result in the Chemotion web client (you need to be logged in in the browser)
    sample.open()

Restricted elements
-------------------

An element in a collection shared with you below the full detail level (10) comes with some fields
withheld by the server. :attr:`~chemotion_api.elements.abstract_element.AbstractElement.is_restricted`
tells you; withheld properties read as :data:`chemotion_api.utils.withheld.WITHHELD`, and
``save()`` refuses such an element with ``PermissionError`` (it would write placeholders over the
real values).

``WITHHELD`` is neither ``None`` nor a number. Test for it by identity, ``value is WITHHELD``.
Using it as a number — ``float()``, arithmetic, comparisons — raises ``WithheldValueError`` (a
``PermissionError``). It is also a ``str`` whose text is ``'***'``, the server's own mask, so the
element's raw ``json_data`` still serialises exactly as the server sent it. As a consequence,
``WITHHELD == '***'`` is true and ``isinstance(WITHHELD, str)`` too: compare by identity, not by
equality or type.

.. code-block:: python

    from chemotion_api.utils.withheld import WITHHELD

    for sample in shared_collection.get_samples():
        if sample.is_restricted and sample.properties['description'] is WITHHELD:
            print(sample.id, 'description withheld')

.. autodata:: chemotion_api.utils.withheld.WITHHELD
    :no-value:

.. autoexception:: chemotion_api.utils.withheld.WithheldValueError

Rich text
---------

Some properties are rich text in the ELN — a reaction's ``description`` and ``observation``, and the
``description`` of a wellplate or a screen. They are stored as `Quill deltas
<https://quilljs.com/docs/delta>`_, the ELN editor's format, and read as one;
:func:`~chemotion_api.quill_to_text` flattens it to text. Write a plain string — it is stored via
:func:`~chemotion_api.text_to_quill`, as a delta of the shape the ELN creates itself — or a
well-formed delta, so content read from the ELN (formatting included) can be written back. Anything
that is neither raises ``ValueError``.

.. code-block:: python

    from chemotion_api import quill_to_text

    reaction.properties['observation'] = 'Turned yellow after 5 min.
    reaction.save()
    print(quill_to_text(reaction.properties['description']))

.. autofunction:: chemotion_api.text_to_quill

.. autofunction:: chemotion_api.quill_to_text

.. autoclass:: chemotion_api.elements.abstract_element.AbstractElement
    :members: