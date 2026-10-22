Generic Elements
======================

Generic elements are element types defined by the administration of a Chemotion instance with LabIMotion.
They are loaded with :meth:`chemotion_api.Instance.get_generic_by_name` or
:meth:`chemotion_api.Instance.get_generic_by_label`, listed with
:meth:`chemotion_api.collection.Collection.get_generics_by_name` or
:meth:`chemotion_api.collection.Collection.get_generics_by_label`, and created with
:meth:`chemotion_api.collection.Collection.new_generic` or
:meth:`chemotion_api.collection.Collection.new_generic_by_label`.

Their templates can be loaded and edited with the :class:`chemotion_api.labImotion.GenericManager`
(:meth:`chemotion_api.Instance.generic_manager`). A template is a
:class:`chemotion_api.labImotion.GenericElementKlass` (formerly ``labImotion.GenericElement``); the element
exposes the label, name and version of its template as :attr:`~GenericElement.label`,
:attr:`~GenericElement.klass_name` and :attr:`~GenericElement.klass_version`.

The server sets the short label of a new element on its first save: the creator's initials, the template's
``klass_prefix`` and a counter of the user's elements of this type, e.g. ``API-WRK10``.

Layers and workflows
--------------------

Layers without fields appear in ``properties`` as empty dicts; :meth:`~GenericElement.layers_without_fields`
lists them. The generic segments of the element type are listed by ``elem.segments.available()``.

``properties`` holds the layers by their label: ``properties['Nr 1']['name_one']``. A layer that is used more
than once (e.g. in two workflows) gets a suffix taken from its layer key: the layer ``three.1`` is
``properties['Nr 3.1']``. The suffix belongs to the layer, so the names stay the same when the element is
saved and loaded again. Layers are ordered by position and workflow step.

The next steps of the workflows are listed by :meth:`~GenericElement.wf_next_options`; each option names its
workflow (``wf_idx``, ``wf_id``) and template layer (``layer_key``, ``layer_label``) and can be passed to
:meth:`~GenericElement.wf_next`, which returns the key of the new layer in ``properties``::

    option = next(o for o in elem.wf_next_options() if o['wf_idx'] == 1 and o['layer_label'] == 'Nr 4')
    key = elem.wf_next(**option)
    elem.properties[key]['name_four'] = 'done'

:meth:`~GenericElement.wf_workflows` lists the layers of each workflow with their ``properties`` key, and
:meth:`~GenericElement.wf_layer` returns a layer by workflow and label or key: ``elem.wf_layer(1, 'Nr 3')``.

Creating a template
-------------------

:meth:`~chemotion_api.labImotion.GenericManager.create_new_element` creates a template and returns it. By
default it releases an empty version 0.1 and activates the template; only released and active templates can
be used for new elements. Layers and fields are added to ``klass.properties``, and a new release makes them
available::

    from chemotion_api.labImotion.items.fields import FieldType
    from chemotion_api.labImotion.items.options import SaveActionType

    gm = instance.generic_manager()
    klass = gm.create_new_element('Micro Biology', 'bug', description='...', prefix='MB')
    general = klass.properties.add_new_layer('General')
    general.add_field(FieldType.TEXT, 'Strain')
    general.add_field(FieldType.SELECT, 'Growth medium', options=['LB', 'TB'])
    klass.properties.add_new_layer('Cultivation').add_field(FieldType.INTEGER, 'Temperature (°C)')
    klass.save(SaveActionType.MINOR)   # release; SaveActionType.DRAFT only stores the template

    elem = collection.new_generic_by_label('Micro Biology')
    elem.properties['General']['Strain'] = 'E. coli K12'
    elem.save()

Notes:

* Layer and field keys are generated from the labels (``'Temperature (°C)'`` -> ``temperature_c``) unless
  given with ``key=`` / ``field=``. Keys must be unique.
* A SELECT field uses a select option list of the template. ``options=[...]`` creates one for the field;
  shared lists are created with ``klass.properties.add_select_option(key, values)`` and linked by
  ``field.option_layers = key``.
* ``field.required`` and ``field.default`` are stored in the template.
* Elements address their fields by the labels of the template version they were created with. After a
  label change, existing elements keep the old names; unknown names raise a ``ValueError`` on save.
* The ``description`` is stored as ``desc``; the short label prefix is ``klass.klass_prefix``.
* ``load_all_elements()`` skips templates that do not validate (with a warning); pass ``strict=True`` to
  :meth:`GenericElementKlass.load_all` to get the error instead.
* Element types are cached by the instance. :meth:`~chemotion_api.collection.Collection.new_generic_by_label`
  reloads them if a label is unknown; ``instance.element_manager.reload()`` does it explicitly.

.. autoclass:: chemotion_api.labImotion.GenericManager
    :members: get_element, get_segment, get_dataset, load_all_elements, load_all_segments, load_all_datasets,
        create_new_element

.. autoclass:: chemotion_api.elements.generic_element.GenericElement
    :members:
