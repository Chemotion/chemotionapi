"""Search must at least run. It could not, on the whole v4 line, until 2026-11-12.

`SearchHelperBase.request()` kept passing `collection_is_sync` positionally after the v4 port
removed it from `ElementSet.__init__`, so every `search_sample()` / `search_reaction()` raised
TypeError before sending a request — and three consecutive green integration runs never noticed,
because nothing here called search. These tests exist so that cannot happen again.
"""
from chemotion_api.elements import ElementSet
from chemotion_api.search.utils import EnumConnector, EnumMatch


def test_search_sample_runs(instance_with_collection):
    searcher = instance_with_collection['instance'].search_sample()
    searcher.add_search_condition(EnumMatch.LIKE, EnumConnector.AND, name='%')
    result = searcher.request()
    assert isinstance(result, ElementSet)
    list(result)    # iterating the (possibly empty) result must not raise either


def test_search_reaction_runs(instance_with_collection):
    searcher = instance_with_collection['instance'].search_reaction()
    searcher.add_search_condition(EnumMatch.LIKE, EnumConnector.AND, name='%')
    result = searcher.request()
    assert isinstance(result, ElementSet)
    list(result)
