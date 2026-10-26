from types import SimpleNamespace

import pytest

from chemotion_api.elements.reaction import SampleVariation
from chemotion_api.elements.sample import SampleVariationType
from chemotion_api.elements.utils import QuantityUnit
from chemotion_api.generic_segments import GenericSegments


def _sample(mw=100.0, purity=0.5, molarity=0.0, density=0.0):
    return SimpleNamespace(
        properties={'coefficient': 1, 'purity': purity, 'reference': False,
                    'molarity': {'value': molarity}, 'density': density,
                    'gas_type': SimpleNamespace(value='off'),
                    'amount': {'value': 0, 'unit': 'mol'}},
        molecule={'molecular_weight': mw, 'sum_formular': 'X'},
        get_amount=lambda: {'value': 0, 'unit': 'mol'},
        is_mixture=False,
    )


def _variation(sample_type=SampleVariationType.REACTANT, ref_amount=2.0, **kwargs):
    return SampleVariation(_sample(**kwargs), sample_type, None, get_ref_amount=lambda: ref_amount)


def test_mass_round_trip():
    sv = _variation(mw=100.0, purity=0.5)
    sv.set_quantity(10, QuantityUnit.Gram)
    assert sv.get_amount() == pytest.approx(0.05)
    assert sv.get_mass() == pytest.approx(10)


def test_volume_from_molarity():
    sv = _variation(molarity=2.0)
    sv.set_quantity(0.5, 'l')
    assert sv.get_amount() == pytest.approx(1.0)
    sv._values['volume']['value'] = 0
    assert sv.get_volume() == pytest.approx(0.5)


def test_equivalent():
    sv = _variation(ref_amount=2.0)
    sv.set_equivalent(1.5)
    assert sv.get_amount() == pytest.approx(3.0)
    assert sv.clean()['equivalent']['value'] == pytest.approx(1.5)


def test_yield_in_percent():
    sv = _variation(SampleVariationType.PRODUCT, ref_amount=2.0)
    sv.set_quantity(85, QuantityUnit.Yield)
    assert sv.get_amount() == pytest.approx(1.7)
    values = sv.clean()
    assert values['yield']['value'] == pytest.approx(85)
    assert 'yield' not in values['amount']


def test_new_segment_does_not_share_template():
    template = {'id': 1, 'properties_release': {'layers': {'l': {'fields': [{'value': ''}]}}}}
    seg = GenericSegments.new_session(template)
    seg['properties']['layers']['l']['fields'][0]['value'] = 'changed'
    assert template['properties_release']['layers']['l']['fields'][0]['value'] == ''
    assert seg['properties_release']['layers']['l']['fields'][0]['value'] == ''


def test_mixture_quantity_not_supported():
    sv = _variation()
    sv._sample.is_mixture = True
    with pytest.raises(NotImplementedError):
        sv.set_quantity(1, QuantityUnit.Mole)


def test_a_solvent_volume_does_not_need_an_amount():
    """A solvent variation carries only a volume -- there is no `amount` key to derive one from.

    `_update_equivalent()` recomputes `volume` whenever the key exists, which it always does for
    a solvent, so falling through to the molarity/density branches raised KeyError('amount')
    for any solvent whose sample had a density or a molarity.
    """
    sv = _variation(SampleVariationType.SOLVENTS, density=0.8)
    assert sv.get_volume() == 0
    sv.clean()   # must not raise


def test_a_solvent_with_molarity_also_survives_clean():
    sv = _variation(SampleVariationType.SOLVENTS, molarity=2.0)
    sv.set_quantity(1.5, QuantityUnit.Liter)
    assert sv.get_volume() == pytest.approx(1.5)
    assert sv.clean()['volume']['value'] == pytest.approx(1.5)



def test_litres_accepted_for_a_sample_with_density_but_no_molarity():
    """`Sample._allowed_quantity_units()` offers litres when density OR molarity is set, and
    `_set_quantity_from_sample()` passes the sample's own unit straight through -- so litres can
    reach `set_quantity()` with molarity 0. `get_volume()` already handles that case; this is the
    inverse of it.
    """
    sv = _variation(mw=100.0, purity=0.5, density=0.8)
    sv.set_quantity(2, QuantityUnit.Liter)
    # 2 l * 0.8 g/ml * 1000 ml/l = 1600 g;  amount = 1600 / 100 * 0.5 = 8 mol
    assert sv.get_amount() == pytest.approx(8.0)
    # and it round-trips back through the density branch of get_volume()
    assert sv.get_volume() == pytest.approx(2.0)


def _gas_product(gas_phase_data=None):
    sample = _sample()
    sample.properties['gas_type'] = SimpleNamespace(value='gas')
    sample.properties['reference'] = None
    if gas_phase_data is not None:
        sample.properties['gas_phase_data'] = SimpleNamespace(to_dict=lambda: gas_phase_data)
    return sample


GAS_ENTRIES = ['duration', 'temperature', 'concentration', 'turnoverNumber', 'turnoverFrequency']


def test_a_gas_product_gets_the_gas_entries_of_the_frontend():
    """The variations tab reads every gas product entry as {'value', 'unit'} and crashes on null."""
    sv = SampleVariation(_gas_product({'time': {'value': 2, 'unit': 'h'},
                                       'temperature': {'value': 300, 'unit': 'K'},
                                       'part_per_million': 5, 'turnover_number': 3,
                                       'turnover_frequency': {'value': 1.5, 'unit': 'TON/h'}}),
                         SampleVariationType.PRODUCT, None)
    values = sv.clean()
    assert all(isinstance(values[entry], dict) for entry in GAS_ENTRIES)
    assert values['duration'] == {'value': 7200, 'unit': 'Second(s)'}
    assert values['temperature']['value'] == pytest.approx(26.85)
    assert values['temperature']['unit'] == '°C'
    assert values['concentration'] == {'value': 5, 'unit': 'ppm'}
    assert values['turnoverNumber']['value'] == 3
    assert values['turnoverFrequency']['value'] == 1.5
    assert values['aux']['isReference'] is False


def test_null_gas_entries_of_a_loaded_variation_are_repaired():
    loaded = {'aux': {'gasType': 'gas'}, 'amount': {'value': 1e-5, 'unit': 'mol'},
              'mass': {'value': 0, 'unit': 'g'}, 'volume': {'value': 0, 'unit': 'l'},
              'yield': {'value': 0, 'unit': None}} | {entry: None for entry in GAS_ENTRIES}
    values = SampleVariation(_gas_product(), SampleVariationType.PRODUCT, 20, loaded).clean()
    assert all(isinstance(values[entry], dict) for entry in GAS_ENTRIES)
    assert values['duration']['unit'] == 'Second(s)'
    assert values['amount']['value'] == 1e-5


def test_a_non_gas_product_has_no_gas_entries():
    values = _variation(SampleVariationType.PRODUCT).clean()
    assert not any(entry in values for entry in GAS_ENTRIES)
