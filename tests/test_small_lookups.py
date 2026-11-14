"""Small lookups on a live ELN (M2.7). CAS lookup needs PubChem and is skipped offline."""
import pytest

pytestmark = pytest.mark.integration


def test_cas_lookup(logged_in_instance):
    try:
        result = logged_in_instance.molecule().lookup_cas('64-17-5')
    except Exception as e:  # noqa: BLE001 - PubChem unreachable from this stack
        pytest.skip(f'PubChem not reachable: {e}')
    assert result['smiles'] == 'CCO'


def test_suggestions_find_a_short_label(instance_with_collection):
    sample = instance_with_collection['main_collection'].new_sample_smiles('CCO')
    sample.save()
    names = [s['name'] for s in instance_with_collection['instance'].suggestions(sample.short_label, 'samples')]
    assert sample.short_label in names


def test_render_a_reaction_scheme(instance_with_collection):
    col = instance_with_collection['main_collection']
    reaction = col.new_reaction()
    reaction.properties['starting_materials'].append(col.new_sample_smiles('CCO'))
    reaction.properties['products'].append(col.new_sample_smiles('CC=O'))
    reaction.save()
    reaction = instance_with_collection['instance'].get_reaction(reaction.id)
    assert all(m.svg_path for m in reaction.properties['starting_materials'])
    assert reaction.render_scheme_svg().startswith('<svg')
    assert reaction.render_scheme_svg(products_only=True).startswith('<svg')
