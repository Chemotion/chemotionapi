import json
import os
from types import SimpleNamespace

import pytest

import chemotion_api.elements.empty_elements as empty_elements
from chemotion_api.elements.reaction import Reaction
from chemotion_api.elements.sample import Molecule, Sample
from chemotion_api.elements.utils import QuantityUnit

SESSION = SimpleNamespace(_host_url='http://localhost',
                          schema_manager=SimpleNamespace(generate_model_type=lambda *args: 'chemotion:type'))
SEGMENTS = SimpleNamespace(all_classes=[])


def _sample_json(sample_id, mw=100.0, **kwargs):
    with open(os.path.join(os.path.dirname(empty_elements.__file__), 'sample.json')) as f:
        data = json.load(f)
    data |= {'id': sample_id, 'short_label': f'S-{sample_id}', 'real_amount_unit': 'g',
             'molecule': {'id': 1, 'molecular_weight': mw}} | kwargs
    return data


def _sample(sample_id=1, **kwargs):
    return Sample(SEGMENTS, SESSION, json_data=_sample_json(sample_id, **kwargs))


def _reaction(starting_materials, reactants=()):
    """A reaction built offline; materials are added without splitting (which would need a server)."""
    reaction = Reaction(SEGMENTS, SESSION, json_data={
        'id': 1, 'type': 'reaction', 'name': '', 'starting_materials': [], 'reactants': [], 'products': [],
        'solvents': [], 'purification_solvents': []})
    for role, samples in (('starting_materials', starting_materials), ('reactants', reactants)):
        for sample in samples:
            reaction.properties[role].append_no_split(sample)
    return reaction


def test_standalone_sample_properties():
    sample = _sample()
    sample.properties['purity'] = 0.5
    sample.properties['coefficient'] = 2
    sample.properties['reference'] = True
    sample.properties['real_amount']['value'] = 3.7
    assert (sample.properties['purity'], sample.properties['coefficient']) == (0.5, 2)
    assert sample.properties['reference'] is True
    # A standalone sample keeps target and real amount independent
    assert sample.properties['real_amount']['value'] == 3.7
    assert sample.properties['target_amount']['value'] == 0
    with pytest.raises(ValueError):
        sample.properties['purity'] = 0


def test_amount_assignment_replaces_dict():
    sample = _sample()
    sample.properties['target_amount'] = {'value': 2, 'unit': 'mol'}
    assert sample.properties['target_amount'].to_dict() == {'value': 2, 'unit': 'mol'}


def test_amount_in_reaction_updates_equivalent():
    ref, reactant = _sample(1, reference=True), _sample(2)
    reaction = _reaction([ref], [reactant])
    ref.properties['target_amount']['value'] = 1.0  # 0.01 mol
    reactant.properties['target_amount']['value'] = 2.0  # 0.02 mol
    assert reaction.reference_sample is ref
    assert reactant.properties['equivalent'] == pytest.approx(2.0)
    reactant.set_amount(0.5, QuantityUnit.Equivalent)
    assert reactant.mol == pytest.approx(0.005)


def test_no_reference_is_invented_when_none_is_flagged():
    """Reading `reference_sample` must not pick one, and must not mutate.

    The ELN does not invent a reference either: `Reaction.referenceMaterial` is
    `allReactionMaterials.find(s => s.reference)`, undefined when nothing is flagged.

    This previously returned the *first* material here — not by design but by accident of
    ordering: the getter flagged `candidates[-1]`, and `update_equivalent()` called it during the
    first append, when the first material was the only candidate. A server-loaded reaction with
    two unflagged materials got the *last* instead, so the same code gave two different answers
    depending on how the reaction was built.
    """
    first, second = _sample(1), _sample(2)
    reaction = _reaction([first, second])
    assert reaction.reference_sample is None
    assert first.properties['reference'] is False
    assert second.properties['reference'] is False


def test_an_explicitly_flagged_reference_is_returned():
    first, second = _sample(1), _sample(2)
    reaction = _reaction([first, second])
    second.properties['reference'] = True
    assert reaction.reference_sample is second


def test_reference_without_materials():
    assert _reaction([]).reference_sample is None


def test_unit_from_string():
    assert QuantityUnit.from_string('G') is QuantityUnit.Gram
    assert QuantityUnit.from_string(None) is None


def test_set_amount_without_stored_unit():
    # Issue: samples without a persisted amount crashed with AttributeError
    sample = _sample(target_amount_unit=None, target_amount_value=None)
    sample.set_amount(None)
    assert sample.properties['target_amount'].to_dict() == {'value': 0.0, 'unit': 'g'}


def test_append_material_without_amount():
    ref = _sample(1, reference=True)
    product = _sample(2, real_amount_unit=None, real_amount_value=None)
    reaction = _reaction([ref])
    product.reaction = reaction
    product.role_in_reaction = 'products'
    reaction.properties['products'].after_append(product)
    assert product.properties['real_amount']['unit'] == 'g'


def test_a_nested_amount_write_keeps_the_coerced_value():
    """PropertyDict.__setitem__ re-assigns the *caller's* object, so a handler that returns True
    discards whatever pydantic coerced. The amount branch must apply the change itself."""
    sample = _sample()
    sample.properties['real_amount']['value'] = "3.7"
    stored = sample.properties['real_amount']['value']
    assert stored == 3.7 and isinstance(stored, float), f'stored {stored!r} ({type(stored).__name__})'
    # and the validation that produced the coercion is still enforced
    with pytest.raises(Exception):
        sample.properties['real_amount']['value'] = "not-a-number"


def test_unknown_unit_message():
    with pytest.raises(ValueError, match='Allowed units'):
        _sample().set_amount(1, QuantityUnit.Equivalent)


def test_temperature_profile_of_new_reaction():
    reaction = _reaction([])
    reaction.properties['temperature'].add_time_point(1, 2, 3, 100)
    assert reaction.properties['temperature']['data'] == [{'time': '01:02:03', 'value': '100'}]


def test_partial_element_loads_before_access(monkeypatch):
    # Issue: listing elements were saved with their incomplete listing data
    listing = _sample_json(3, description=None, target_amount_unit=None, target_amount_value=None)
    full = _sample_json(3, description='Stored cold', target_amount_value=2.0)
    sample = Sample(SEGMENTS, SESSION, json_data=listing)
    sample.mark_partial()
    loads = []
    monkeypatch.setattr(sample, '_load_data_from_server', lambda: loads.append(1) or (None, full))
    assert sample.short_label == 'S-3' and loads == []
    sample.set_amount(1.5, QuantityUnit.Gram)
    assert loads == [1]
    assert sample.properties['description'] == 'Stored cold'
    assert sample.properties['target_amount']['value'] == 1.5
    sample.properties['description'] = 'x'
    assert loads == [1]


def test_molecule_density_is_copied_to_sample_without_density_or_molarity():
    sample = _sample()
    sample.molecule = Molecule({'id': 2, 'molecular_weight': 46.07, 'density': 0.789})
    assert sample.properties['density'] == 0.789
    assert QuantityUnit.Liter in sample.allowed_quantity_units()


def test_molecule_molarity_is_copied_to_sample():
    sample = _sample()
    sample.molecule = Molecule({'id': 2, 'molecular_weight': 46.07, 'density': 0, 'molarity': 2.5})
    assert (sample.properties['density'], sample.properties['molarity'].to_dict()) == (0, {'value': 2.5, 'unit': 'M'})
    sample = _sample()
    sample.molecule = Molecule({'id': 2, 'molecular_weight': 46.07, 'molarity': {'value': 0.1, 'unit': 'mM'}})
    assert sample.properties['molarity'].to_dict() == {'value': 0.1, 'unit': 'mM'}


def test_molecule_does_not_overwrite_sample_density_or_molarity():
    sample = _sample(density=1.2)
    sample.molecule = Molecule({'id': 2, 'molecular_weight': 46.07, 'density': 0.789, 'molarity': 2.5})
    assert (sample.properties['density'], sample.properties['molarity']['value']) == (1.2, 0)
    sample = _sample(molarity_value=0.5)
    sample.molecule = Molecule({'id': 2, 'molecular_weight': 46.07, 'density': 0.789})
    assert (sample.properties['density'], sample.properties['molarity']['value']) == (0, 0.5)


def test_molecule_without_density_or_molarity_changes_nothing():
    sample = _sample()
    sample.molecule = Molecule({'id': 2, 'molecular_weight': 46.07, 'density': 0.0})
    assert (sample.properties['density'], sample.properties['molarity']['value']) == (0, 0)


def test_append_no_split_assigns_reaction_role_and_position():
    first, second = _sample(1), _sample(2, target_amount_unit=None, target_amount_value=None)
    reaction = _reaction([first, second])
    assert reaction.starting_materials[1] is second
    assert (second.reaction, second.role_in_reaction, second.properties['position']) == (
        reaction, 'starting_materials', 1)
    assert second.properties['target_amount'].to_dict() == {'value': 0.0, 'unit': 'g'}


def test_direct_build_computes_equivalents_and_yield():
    # Issue: materials added with append_no_split got no equivalents and products no yield
    ref, reactant, product = _sample(1), _sample(2), _sample(3)
    for sample, role, value, unit in ((ref, 'starting_materials', 0.002, QuantityUnit.Mole),
                                      (reactant, 'reactants', 0.003, QuantityUnit.Mole),
                                      (product, 'products', 0.1, QuantityUnit.Gram)):
        sample.role_in_reaction = role
        sample.set_amount(value, unit)
    reaction = _reaction([ref], [reactant])
    reaction.products.append_no_split(product)
    reaction.reference_sample = ref
    assert [m.properties['equivalent'] for m in (ref, reactant, product)] == pytest.approx([1, 1.5, 0.5])


def test_equivalent_without_reference_amount_is_unknown():
    ref, reactant = _sample(1, target_amount_value=0), _sample(2)
    _reaction([ref], [reactant])
    assert reactant.properties['equivalent'] is None


def test_product_amount_in_mol():
    product = _sample(2)
    reaction = _reaction([_sample(1)])
    reaction.products.append_no_split(product)
    product.set_amount(0.002, QuantityUnit.Mole)
    assert product.properties['real_amount'].to_dict() == {'value': 0.002, 'unit': 'mol'}
    assert product.gram == pytest.approx(0.2)


def test_molecule_attribute_access():
    molecule = Molecule({'id': 2, 'molecular_weight': 46.07})
    assert molecule.molecular_weight == molecule['molecular_weight'] == 46.07
    assert molecule.sum_formular is None
    with pytest.raises(AttributeError):
        _ = molecule.unknown_key


def test_an_unknown_unit_names_the_valid_ones():
    with pytest.raises(ValueError, match=r'Valid units: l, mol, g, Equivalent\..*gas_phase_data.*ppm'):
        _sample().set_amount(1, 'ppm')


def test_variation_edits_are_serialised_not_the_stale_property():
    """A reaction that already has variations must serialise the live Variations object.

    `properties['variations']` is parsed from the server payload and never written back, so
    `get_prop_or_json('variations') or self._clean_variations()` short-circuited on the stale
    (truthy) value and silently dropped every edit made through `reaction.variations`. Only
    reactions with no existing variations — where the value is falsy — reached the serialiser.
    """
    reaction = _reaction([_sample(1)])
    reaction._properties['description'] = {'ops': []}
    reaction._properties['observation'] = {'ops': []}
    reaction.json_data['variations'] = [{'id': 'stale-from-server'}]
    reaction._properties['variations'] = [{'id': 'stale-from-server'}]

    # Stand in for a materialised Variations object: the bug is in which source is chosen,
    # not in what clean() produces.
    reaction._variations = SimpleNamespace(clean=lambda: [{'id': 'edited-in-memory'}])

    assert reaction._clean_properties_data()['variations'] == [{'id': 'edited-in-memory'}]


def test_untouched_variations_fall_back_to_the_stored_value():
    """If `reaction.variations` was never materialised there is nothing to serialise from."""
    reaction = _reaction([_sample(1)])
    reaction._properties['description'] = {'ops': []}
    reaction._properties['observation'] = {'ops': []}
    reaction.json_data['variations'] = [{'id': 'stored'}]
    reaction._properties['variations'] = [{'id': 'stored'}]
    assert reaction._variations is None
    assert reaction._clean_properties_data()['variations'] == [{'id': 'stored'}]


def _reaction_with_product(product_equivalent):
    reaction = _reaction([_sample(1)])
    reaction._properties['description'] = {'ops': []}
    reaction._properties['observation'] = {'ops': []}
    # target_amount_unit must be one a product allows: appending initialises the amount, and a
    # stored 'Equivalent' is rejected for products.
    product = _sample(2, target_amount_unit='g', target_amount_value=1.0)
    reaction.properties['products'].append_no_split(product)
    # Written underneath the change handler on purpose: assigning properties['equivalent'] on a
    # product routes through set_amount(Equivalent), which products reject. This stands in for
    # what update_equivalent() computes during save().
    product._properties['equivalent'] = product_equivalent
    return reaction, product


def test_a_recomputed_yield_is_not_overwritten_by_the_load_time_value():
    """`save()` recomputes equivalents, then serialisation must not undo that.

    `_clean_properties_data` wrote `_current_yield() / 100` onto products[0]['equivalent'].
    `_current_yield()` reads `properties['yield_value']`, captured when the reaction was parsed,
    so raising a product amount and saving sent the old yield back and discarded the recompute.
    """
    reaction, product = _reaction_with_product(0.80)
    reaction._properties['yield_value'] = 50.0   # as parsed from the server at load time
    assert reaction._yield_value_cache is None   # the user never assigned a yield

    data = reaction._clean_properties_data()
    assert data['materials']['products'][0]['equivalent'] == pytest.approx(0.80)
    assert data['yield'] == pytest.approx(80.0)


def test_an_explicitly_set_yield_still_wins():
    reaction, product = _reaction_with_product(0.80)
    reaction.properties['yield'] = 25.0

    data = reaction._clean_properties_data()
    assert data['materials']['products'][0]['equivalent'] == pytest.approx(0.25)
    assert data['yield'] == pytest.approx(25.0)


def test_save_refuses_when_the_full_record_never_loaded():
    """A failed lazy load must not become a silent overwrite.

    `_ensure_loaded()` swallows the error, leaves `_data_loaded` False and still hands out an
    editable `properties` built from the list payload. `save()` then refetched and re-parsed,
    throwing those edits away while the PUT reported success.
    """
    sample = _sample(1)
    sample._data_loaded = False
    sample._load_failed = True

    with pytest.raises(ConnectionError, match=r'could not be loaded.*would discard data'):
        sample.save()


def _vessel_reaction():
    reaction = _reaction([_sample(1)])
    reaction._properties['description'] = {'ops': []}
    reaction._properties['observation'] = {'ops': []}
    reaction._properties['vessel_size'] = {'amount': 2.0, 'unit': 'l'}
    return reaction


def test_vessel_size_unit_can_be_changed_in_place():
    """`vessel_size` is `{amount, unit}` on the server and in the client.

    The model used to type it as a float, so this write raised "stored as a single value" — and
    the error told the caller to assign the whole field instead, which failed too.
    """
    reaction = _vessel_reaction()
    reaction.properties['vessel_size']['unit'] = 'ml'
    assert reaction._properties['vessel_size'] == {'amount': 2.0, 'unit': 'ml'}


def test_vessel_size_whole_field_assignment_keeps_the_mapping():
    reaction = _vessel_reaction()
    reaction.properties['vessel_size'] = {'amount': 5.0, 'unit': 'ml'}
    assert reaction._properties['vessel_size'] == {'amount': 5.0, 'unit': 'ml'}
    assert isinstance(reaction._properties['vessel_size'], dict)  # never a bare float


def test_vessel_size_bad_amount_is_still_rejected():
    reaction = _vessel_reaction()
    with pytest.raises(Exception):
        reaction.properties['vessel_size'] = {'amount': 'not a number', 'unit': 'ml'}


# --- F2: building an element from a listing row must not fetch it ------------------------

def test_constructing_from_a_listing_row_issues_no_load(monkeypatch):
    """`_set_json_data` read `self.properties`, whose getter calls `_ensure_loaded()` — and
    during construction `id` is set while `_data_loaded` is not, so every element built from a
    listing row issued a full `load()`: a 50-row page cost 51 requests. A failed fetch then left
    `_load_failed` set on an element that had merely been listed."""
    loads = []
    monkeypatch.setattr(Sample, 'load', lambda self: loads.append(self.id))
    sample = _sample(42)
    assert loads == [], f'construction fetched {loads}'
    assert sample._load_failed is False


def test_first_property_read_still_loads(monkeypatch):
    """Loading stays lazy, not removed: the first real read fetches, exactly once."""
    loads = []

    def _load(self):                     # as the real one does: mark loaded, then fetch
        self._data_loaded = True
        loads.append(self.id)

    monkeypatch.setattr(Sample, 'load', _load)
    sample = _sample(42)
    sample.properties
    sample.properties
    assert loads == [42]


# --- F3: vessel_size end to end ----------------------------------------------------------

def _reaction_json(**extra):
    return {'id': 1, 'type': 'reaction', 'name': '', 'starting_materials': [], 'reactants': [],
            'products': [], 'solvents': [], 'purification_solvents': []} | extra


def test_a_reaction_with_a_vessel_size_loads():
    """The parse path flattened `vessel_size` to its amount before validating, so once the model
    typed it as `{amount, unit}`, every reaction loaded with a vessel size failed to parse. The
    seeded test reactions have none, which is why the integration suite did not notice."""
    reaction = Reaction(SEGMENTS, SESSION, json_data=_reaction_json(vessel_size={'amount': 2.0, 'unit': 'l'}))
    assert reaction._properties['vessel_size'] == {'amount': 2.0, 'unit': 'l'}


def test_a_bare_number_sets_the_amount_and_keeps_the_unit():
    """`properties['vessel_size'] = 200` is natural usage. It used to store the bare float,
    which then went to the server where `{amount, unit}` is expected."""
    reaction = _vessel_reaction()                 # {'amount': 2.0, 'unit': 'l'}
    reaction.properties['vessel_size'] = 5
    assert reaction._properties['vessel_size'] == {'amount': 5.0, 'unit': 'l'}


def test_sample_vessel_size_is_a_volume_in_ml():
    """The gas maths divides by it; it used to receive the `{amount, unit}` mapping."""
    reaction = _vessel_reaction()                 # 2 l
    sample = reaction.properties['starting_materials'][0]
    assert sample.vessel_size == 2000.0
    reaction.properties['vessel_size'] = {'amount': 150, 'unit': 'ml'}
    assert sample.vessel_size == 150.0


@pytest.mark.parametrize("given, ml", [
    (None, None), ({'amount': None, 'unit': 'ml'}, None),
    ({'amount': 10, 'unit': 'ml'}, 10.0), ({'amount': 2, 'unit': 'l'}, 2000.0), (200, 200.0),
])
def test_vessel_volume_ml(given, ml):
    from chemotion_api.elements.utils import vessel_volume_ml
    assert vessel_volume_ml(given) == ml


# --- F8: a property write validates one field, not the whole property set ----------------

def test_validate_field_passes_unknown_names_through_and_caches():
    from chemotion_api.models import SamplePropertiesModel, _field_adapter, validate_field
    assert validate_field(SamplePropertiesModel, 'not_a_model_field', {'x': 1}) == {'x': 1}
    assert _field_adapter(SamplePropertiesModel, 'purity') is _field_adapter(SamplePropertiesModel, 'purity')


def test_an_invalid_value_still_fails_at_assignment():
    """Validation moved scope, not place: a bad write is still refused where it happens."""
    sample = _sample(1)
    sample._data_loaded = True
    with pytest.raises(Exception):
        sample.properties['purity'] = 'not a number'


def test_a_whole_field_write_copies_nothing(monkeypatch):
    """It used to deep-copy the entire property set on every write."""
    import chemotion_api.elements.sample as sample_mod
    sample = _sample(1)
    sample._data_loaded = True
    copies = []
    real = sample_mod.copy.deepcopy
    monkeypatch.setattr(sample_mod.copy, 'deepcopy', lambda *a, **k: copies.append(1) or real(*a, **k))
    sample.properties['purity'] = 0.9
    assert copies == []


def test_an_unrelated_bad_field_no_longer_blocks_a_write():
    """The one deliberate behaviour change: whole-model validation re-checked every field, so a
    bad value already sitting in one field made writes to any *other* field fail."""
    sample = _sample(1)
    sample._data_loaded = True
    sample._properties['coefficient'] = 'garbage already stored'
    sample.properties['purity'] = 0.9
    assert sample._properties['purity'] == 0.9
