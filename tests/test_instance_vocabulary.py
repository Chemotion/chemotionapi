"""Live check that the instance's own ontology terms are actually readable.

This exists because the unit tests could not catch the bug it guards. They were written from
the ELN's entity source, which exposes `term_id` as an attribute; the published tree is built
from string-keyed hashes, so `term_id` serialises as null on every node and the id survives
only inside `value`. Indexing on `term_id` passed every unit test and resolved **zero** terms
against a real server — a silent downgrade to the EBI fallback, with no error anywhere.

So the assertion that matters here is a floor on the count, against a real instance.
"""
import pytest

from chemotion_api.ontology import InstanceVocabulary


@pytest.fixture()
def vocabulary(logged_in_instance):
    vocab = InstanceVocabulary.from_session(logged_in_instance._con)
    assert vocab is not None, "a live instance must yield a vocabulary"
    return vocab


def test_instance_publishes_a_usable_chmo_vocabulary(vocabulary):
    """A real instance ships thousands of CHMO names; anything near zero means a parse failure."""
    index = vocabulary._index("chmo")
    assert len(index) > 500, (
        f"only {len(index)} CHMO names parsed from the instance — the published tree's shape "
        f"has changed and resolution has silently fallen back to EBI")
    assert all(term.iri.startswith("http://purl.obolibrary.org/obo/") for term in index.values())


def test_a_known_synonym_resolves_to_the_instance_label(vocabulary):
    """`13C NMR` is a synonym; the crate should record the term the ELN displays for it."""
    term = vocabulary.lookup("13C NMR")
    assert term is not None, "a stock CHMO synonym did not resolve against the instance"
    assert term.iri == "http://purl.obolibrary.org/obo/CHMO_0000595"
    # The full label, not the synonym that was searched for.
    assert "nuclear magnetic resonance" in term.label.lower()


def test_an_unpublished_ontology_is_not_an_error(vocabulary):
    """The stack publishes no `bao` file: `{"ols_terms": null}` must read as empty, not raise."""
    assert vocabulary._index("bao") == {}
    assert vocabulary.lookup("anything at all", ontology="bao") is None


def test_nonsense_does_not_resolve(vocabulary):
    assert vocabulary.lookup("not a real technique name at all") is None
