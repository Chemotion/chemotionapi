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
