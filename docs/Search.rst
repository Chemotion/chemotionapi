Search
======

Advanced searches for samples and reactions are built with a small fluent API. Obtain a searcher from
the instance with :meth:`chemotion_api.Instance.search_sample` or
:meth:`chemotion_api.Instance.search_reaction`, add one or more conditions, then run it.

.. code-block:: python

    from chemotion_api.search.utils import EnumMatch, EnumConnector

    # Find samples whose name matches "Ethanol"
    result = (instance.search_sample()
              .add_search_condition(EnumMatch.EQUAL, EnumConnector.AND, name="Ethanol")
              .request())
    for sample in result:
        pass  # do something

Conditions are combined with the connector (``AND`` / ``OR``); the connector is applied only *between*
conditions (the first condition has none). Restrict the collection with ``in_collection(...)`` and cap
the number of results with ``find_max(...)``.

Searchers
---------

.. autoclass:: chemotion_api.search.sample.SampleSearcher
    :members:
    :inherited-members:

.. autoclass:: chemotion_api.search.reaction.ReactionSearcher
    :members:
    :inherited-members:

Match and connector options
---------------------------

.. autoenum:: chemotion_api.search.utils.EnumMatch

.. autoenum:: chemotion_api.search.utils.EnumConnector
