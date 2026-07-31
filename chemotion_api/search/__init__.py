"""Advanced (field-based) search over Chemotion elements.

Builds the payload for the ``/api/v1/search/advanced`` endpoint via per-element-type
searchers (:class:`~chemotion_api.search.sample.SampleSearcher`,
:class:`~chemotion_api.search.reaction.ReactionSearcher`) layered on the shared
:class:`~chemotion_api.search.search_helper.SearchHelperBase`. Match operators and
condition connectors are :class:`~chemotion_api.search.utils.EnumMatch` and
:class:`~chemotion_api.search.utils.EnumConnector`.
"""
