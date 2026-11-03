"""Two ways data went missing or got duplicated without any error being raised."""
import pytest

from chemotion_api.offline.export_reader import ExportAdapter


def _two_collection_dump():
    """Sample s1 belongs to collection X; its only reaction R belongs to collection Y."""
    return {
        "Collection": {"X": {"label": "X"}, "Y": {"label": "Y"}},
        "Sample": {"s1": {"name": "Shared material"}, "s2": {"name": "Plain"}},
        "Reaction": {"R": {"name": "R"}},
        "ReactionsStartingMaterialSample": {"j1": {"reaction_id": "R", "sample_id": "s1"}},
        "CollectionsSample": {"c1": {"collection_id": "X", "sample_id": "s1"},
                              "c2": {"collection_id": "X", "sample_id": "s2"}},
        "CollectionsReaction": {"c3": {"collection_id": "Y", "reaction_id": "R"}},
    }


def test_a_sample_whose_reaction_is_in_another_collection_is_not_lost():
    """`_samples_in_reactions` was computed over the whole dump, before scoping — so s1 was in
    neither list: not a reaction material (R is out of scope) and not standalone (it is in some
    reaction somewhere). It vanished from the crate with no warning and a success exit."""
    ad = ExportAdapter(_two_collection_dump())
    assert ad.reaction_uuids("X") == []                 # the premise: R is not in X
    assert set(ad.standalone_sample_uuids("X")) == {"s1", "s2"}


def test_a_sample_covered_by_an_in_scope_reaction_is_still_not_duplicated():
    """It must not appear standalone *and* as the reaction's material."""
    dump = _two_collection_dump()
    dump["CollectionsReaction"]["c3"]["collection_id"] = "X"
    dump["CollectionsSample"]["c4"] = {"collection_id": "X", "sample_id": "s1"}
    ad = ExportAdapter(dump)
    assert ad.reaction_uuids("X") == ["R"]
    assert ad.standalone_sample_uuids("X") == ["s2"]


def test_unscoped_export_behaviour_is_unchanged():
    ad = ExportAdapter(_two_collection_dump())
    assert ad.standalone_sample_uuids() == ["s2"]       # s1 is covered by R


# --- analyses are not duplicated when a save is retried --------------------

def test_retrying_a_failed_save_does_not_duplicate_a_new_analysis():
    """`res_list` was `container['children'][0]['children']` itself, and `res_list +=` mutated it
    in place. `is_new` clears only after a successful PUT, so the retry appended a second copy."""
    from chemotion_api.elements.abstract_element import AbstractElement

    class _Analysis:
        def __init__(self, id_, is_new):
            self.id, self.is_new = id_, is_new

        def to_json(self):
            return {"id": self.id, "name": "NMR"}

    class _Elem:
        _clean_analyses_data = AbstractElement._clean_analyses_data

        def __init__(self):
            self.json_data = {"container": {"children": [{"children": []}]}}
            self.analyses = [_Analysis("new-1", True)]

    el = _Elem()
    first = el._clean_analyses_data()
    assert len(first["container"]["children"][0]["children"]) == 1
    # the PUT failed: is_new is still True, json_data must be untouched
    assert el.json_data["container"]["children"][0]["children"] == []
    second = el._clean_analyses_data()
    assert len(second["container"]["children"][0]["children"]) == 1, "retry must not duplicate"
