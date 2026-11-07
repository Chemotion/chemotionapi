"""Structure search on a live ELN (M2.4), plus the advanced sample search it sits next to."""
import uuid

import pytest

from chemotion_api.search.utils import EnumConnector, EnumMatch

pytestmark = pytest.mark.integration


@pytest.fixture()
def library(instance_with_collection):
    col = instance_with_collection['main_collection']
    tag = uuid.uuid4().hex[:6]
    samples = {}
    for smiles in ('CCO', 'CCCO', 'c1ccccc1O', 'CCCC'):
        sample = col.new_sample_smiles(smiles)
        sample.properties['name'] = f'{tag}-{smiles}'
        sample.save()
        samples[smiles] = sample
    reaction = col.new_reaction()
    reaction.properties['starting_materials'].append(samples['c1ccccc1O'])
    reaction.save()
    return instance_with_collection['instance'], col, samples, reaction, tag


def test_substructure_finds_samples_and_their_reaction(library):
    instance, col, samples, reaction, _ = library
    result = instance.search_structure().substructure('c1ccccc1O').in_collection(col.id).request()
    assert samples['c1ccccc1O'].id in {s.id for s in result.samples}
    assert samples['CCO'].id not in {s.id for s in result.samples}
    assert [r.id for r in result.reactions] == [reaction.id]


def test_substructure_matches_every_alcohol(library):
    instance, col, samples, _, _ = library
    found = {s.id for s in instance.search_structure().substructure('CO').in_collection(col.id).find_max(50)
             .request().samples}
    assert {samples[s].id for s in ('CCO', 'CCCO', 'c1ccccc1O')} <= found
    assert samples['CCCC'].id not in found


def test_similarity_and_find_max(library):
    instance, col, samples, _, _ = library
    result = instance.search_structure().similar('CCO', threshold=0.3).in_collection(col.id).find_max(1).request()
    assert len(result.samples) == 1 and result.total('sample') >= 2


def test_advanced_sample_search_returns_results(library):
    """It raised TypeError on every call before M2.4 (an ElementSet argument too many)."""
    instance, col, samples, _, tag = library
    found = instance.search_sample().add_search_condition(EnumMatch.LIKE, EnumConnector.OR, name=tag) \
        .in_collection(col.id).find_max(50).request()
    assert {s.id for s in found} >= {s.id for s in samples.values()}
