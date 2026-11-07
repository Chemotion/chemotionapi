"""The built-in element-type registry (M0.1) that replaced the if/elif dispatch chains."""
import pytest

from chemotion_api.elements import ElementSet
from chemotion_api.elements.abstract_element import AbstractElement
from chemotion_api.elements.generic_element import GenericElement
from chemotion_api.elements.reaction import Reaction
from chemotion_api.elements.registry import (
    UnknownElementType,
    element_class,
    register_element_type,
    registered_element_types,
)
from chemotion_api.elements.research_plan import ResearchPlan
from chemotion_api.elements.sample import Sample
from chemotion_api.elements.wellplate import Wellplate
from chemotion_api.elements.screen import Screen
from chemotion_api.elements.device_description import DeviceDescription
from chemotion_api.elements.sbmm_sample import SbmmSample
from chemotion_api.elements.cell_line import CellLine

# What the removed if/elif chains returned, so the registry is a drop-in replacement.
BUILT_INS = {
    'sample': (Sample, '/api/v1/samples', 'sample'),
    'reaction': (Reaction, '/api/v1/reactions', 'reaction'),
    'wellplate': (Wellplate, '/api/v1/wellplates', 'wellplate'),
    'research_plan': (ResearchPlan, '/api/v1/research_plans', 'research_plan'),
    'screen': (Screen, '/api/v1/screens', 'screen'),
    'device_description': (DeviceDescription, '/api/v1/device_descriptions', 'device_description'),
    'sequence_based_macromolecule_sample': (SbmmSample, '/api/v1/sequence_based_macromolecule_samples',
                                            'sequence_based_macromolecule_sample'),
    'cell_line': (CellLine, '/api/v1/cell_lines', 'cell_line'),
}


def test_exactly_the_built_in_types_are_registered():
    assert registered_element_types() == sorted(BUILT_INS)


@pytest.mark.parametrize('name', sorted(BUILT_INS))
def test_built_in_types_resolve_as_before(name):
    cls, url, key = BUILT_INS[name]
    assert element_class(name) is cls
    assert AbstractElement.get_url(name) == url
    assert AbstractElement.get_response_key(name) == key


def test_unregistered_names_fall_back_to_the_generic_routes():
    assert AbstractElement.get_url('my_generic_klass') == '/api/v1/generic_elements'
    assert AbstractElement.get_response_key('my_generic_klass') == 'element'


def test_an_unknown_non_generic_type_names_itself_and_is_still_a_type_error():
    with pytest.raises(UnknownElementType, match='"no_such_type"') as err:
        element_class('no_such_type')
    assert isinstance(err.value, TypeError)
    assert err.value.name == 'no_such_type'


def _element_set(name, is_generic):
    es = ElementSet.__new__(ElementSet)  # dispatch only reads _element_type
    es._element_type = {'name': name, 'is_generic': is_generic}
    return es


def test_element_set_dispatches_through_the_registry():
    assert _element_set('reaction', False)._get_element_class() is Reaction
    assert _element_set('anything', True)._get_element_class() is GenericElement
    with pytest.raises(UnknownElementType):
        _element_set('no_such_type', False)._get_element_class()


def test_a_name_cannot_be_registered_to_two_classes():
    with pytest.raises(ValueError, match='already registered'):
        register_element_type('sample', url='/api/v1/other')(type('Other', (), {}))


def test_re_registering_the_same_class_is_harmless():
    register_element_type('sample', url='/api/v1/samples')(Sample)
    assert element_class('sample') is Sample
