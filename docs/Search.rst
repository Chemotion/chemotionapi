Search
==========

The advanced search of Chemotion is available for samples (:meth:`chemotion_api.Instance.search_sample`)
and reactions (:meth:`chemotion_api.Instance.search_reaction`). Conditions are added with
``add_search_condition``; each condition has a match type and a connector that links it with the
conditions before it. :meth:`chemotion_api.search.search_helper.SearchHelperBase.request` runs the search
and returns an :class:`chemotion_api.elements.ElementSet`.

.. code-block:: python

    from chemotion_api.search.utils import EnumMatch, EnumConnector

    samples = (instance.search_sample()
               .add_search_condition(EnumMatch.LIKE, EnumConnector.OR, name='Ethanol')
               .add_search_condition(EnumMatch.EXACT, EnumConnector.AND, cas='64-17-5')
               .find_max(5)
               .request())
    for sample in samples:
        print(sample.short_label)

    reactions = (instance.search_reaction()
                 .add_search_condition(EnumMatch.BIGGER_THAN, EnumConnector.AND, temperature_in_c=30)
                 .request())

Conditions are combined with the connector (``AND`` / ``OR``); the connector is applied only
*between* conditions (the first condition's connector is ignored). Restrict the search to one
collection with ``in_collection(...)`` and cap the number of results with ``find_max(...)``.

API Classes
------------

.. autoclass:: chemotion_api.search.sample.SampleSearcher
    :members:
    :inherited-members:

.. autoclass:: chemotion_api.search.reaction.ReactionSearcher
    :members:
    :inherited-members:

.. autoclass:: chemotion_api.search.search_helper.SearchHelperBase
    :members: in_collection, find_max, request

Match and connector options
---------------------------

.. autoenum:: chemotion_api.search.utils.EnumMatch

.. autoenum:: chemotion_api.search.utils.EnumConnector
