"""Deleting elements on a live ELN (M0.4), through the web UI's `DELETE /api/v1/ui_state`.

v4 withdraws the selection from the user's own collections and destroys what is left in none, so
these check what actually happens to each record, not just the HTTP status.
"""
import pytest

from chemotion_api.connection import ChemotionRequestError

pytestmark = pytest.mark.integration


def _gone(load, element_id):
    with pytest.raises(ChemotionRequestError, match='404'):
        load(element_id)
    return True


def test_every_supported_kind_is_deleted_in_one_request(instance_with_collection):
    instance, col = instance_with_collection['instance'], instance_with_collection['main_collection']
    sample = col.new_sample_smiles('CCO')
    sample.save()
    reaction = col.new_reaction()
    reaction.save()
    wellplate = col.new_wellplate()
    wellplate.save()
    plan = col.new_research_plan()
    plan.save()
    generic = col.new_generic('try')
    generic.save()

    assert col.delete_elements(sample, reaction, wellplate, plan, generic) == []

    assert _gone(instance.get_sample, sample.id)
    assert _gone(instance.get_reaction, reaction.id)
    assert _gone(instance.get_wellplate, wellplate.id)
    assert _gone(instance.get_research_plan, plan.id)
    assert not [e.id for e in col.get_samples(per_page=None)]


def test_element_delete(instance_with_collection):
    instance, col = instance_with_collection['instance'], instance_with_collection['main_collection']
    sample = col.new_sample_smiles('CCC')
    sample.save()
    assert sample.delete() is True
    assert _gone(instance.get_sample, sample.id)


def test_deleting_from_the_root_collection(instance_with_collection):
    instance = instance_with_collection['instance']
    sample = instance_with_collection['main_collection'].new_sample_smiles('CCCC')
    sample.save()
    assert instance.get_root_collection().delete_elements(sample) == []
    assert _gone(instance.get_sample, sample.id)


def _reaction_with_starting_material(col):
    material = col.new_sample_smiles('CCCCC')
    material.save()
    reaction = col.new_reaction()
    reaction.properties['starting_materials'].append(material)
    reaction.save()
    return reaction, reaction.properties['starting_materials'][0]


def test_a_sample_bound_to_a_reaction_is_kept_and_reported(instance_with_collection):
    instance, col = instance_with_collection['instance'], instance_with_collection['main_collection']
    reaction, material = _reaction_with_starting_material(col)

    assert material.delete() is False
    assert col.delete_elements(material) == [material]
    assert instance.get_sample(material.id).id == material.id  # still there


def test_a_reaction_keeps_its_starting_materials_unless_asked(instance_with_collection):
    instance, col = instance_with_collection['instance'], instance_with_collection['main_collection']
    reaction, material = _reaction_with_starting_material(col)

    assert reaction.delete() is True
    assert _gone(instance.get_reaction, reaction.id)
    # Without delete_subsamples only reactants and solvents go with the reaction.
    assert instance.get_sample(material.id).id == material.id


def test_delete_subsamples_takes_the_starting_materials_too(instance_with_collection):
    instance, col = instance_with_collection['instance'], instance_with_collection['main_collection']
    reaction, material = _reaction_with_starting_material(col)

    assert reaction.delete(delete_subsamples=True) is True
    assert _gone(instance.get_reaction, reaction.id)
    assert _gone(instance.get_sample, material.id)


def test_an_unsaved_element_is_refused(instance_with_collection):
    col = instance_with_collection['main_collection']
    with pytest.raises(ValueError, match='not been saved'):
        col.delete_elements(col.new_sample_smiles('CO'))
