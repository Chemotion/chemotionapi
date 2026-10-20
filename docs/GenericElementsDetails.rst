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
(:meth:`chemotion_api.Instance.generic_manager`).

.. autoclass:: chemotion_api.elements.generic_element.GenericElement
    :members:
