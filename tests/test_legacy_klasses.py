"""Klasses authored by older chem-generic-ui versions must still load.

These five fixtures are real klasses captured from a live v4 instance
(`next-release.chemotion.ibcs.kit.edu`, 2026-09-15). Every one of them made the client raise:

* `demo`      — uses field type ``select-multi``, which the server emits but the LabIMotion gem
                deliberately does not declare in ``field_type.rb``
* `dev_mass`, `GCMS`, `GC`, single-crystal XRD
              — select fields pointing at an option set the klass no longer defines (for two of
                them ``select_options`` is empty entirely)

The damage was not limited to these klasses: every accessor goes through ``load_all()``, so one
of them made ``get_element``/``get_segment``/``get_dataset`` fail for *all* klasses. The local
seeded stack cannot catch this — its klasses are too clean — which is why the integration suite
stayed green over a dead API.
"""
import collections
import json
import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from chemotion_api.labImotion import GenericDataset, GenericElement, GenericSegment
from chemotion_api.labImotion.items.options import FieldType

FIXTURES = Path(__file__).parent / 'fixtures' / 'legacy_klasses'

CASES = [
    ('demo.json', GenericElement, 'select-multi field type'),
    ('dev_mass.json', GenericSegment, 'select option set not defined by the klass'),
    ('gas_chromatography_mass_spectrometry__gcms.json', GenericDataset, 'empty select_options'),
    ('gas_chromatography__gc.json', GenericDataset, 'empty select_options'),
    ('single_crystal_x_ray_diffraction__single_crystal.json', GenericDataset,
     'select option set not defined by the klass'),
]


def _payload(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


def _field_classes(klass) -> collections.Counter:
    """Histogram of the Field subclass used for each field, across every layer."""
    seen: collections.Counter = collections.Counter()
    for layer in klass.properties.layers:
        for field in layer.fields:
            seen[type(field).__name__] += 1
    return seen


@pytest.mark.parametrize(('fixture', 'cls', 'why'), CASES)
def test_legacy_klass_parses(fixture, cls, why):
    """Each of these used to raise; all must now construct — and be *understood*, not shrugged at.

    Asserting only "does not raise" is not enough: `OpaqueField` exists precisely so an unknown
    field type cannot break a klass, so a regression that routed *every* field to it would parse
    everything and understand nothing. Verified: mutating the factory to return OpaqueField for
    all types leaves a bare no-exception test green.
    """
    klass = cls(_payload(fixture), MagicMock())
    classes = _field_classes(klass)
    assert classes, f"{fixture} produced no fields at all"
    real = {name: n for name, n in classes.items() if name != "OpaqueField"}
    assert real, f"{fixture} parsed but every field fell back to OpaqueField: {dict(classes)}"


def test_the_select_multi_klass_is_understood_field_by_field():
    """`demo` is the klass that motivated all of this; pin what it actually parses to.

    An exact histogram, so silent degradation to OpaqueField — or a field type quietly changing
    class — fails here rather than passing as "no exception".
    """
    klass = GenericElement(_payload('demo.json'), MagicMock())
    classes = _field_classes(klass)

    assert classes["SelectMultiField"] == 1, "the select-multi field must use its own class"
    assert classes["OpaqueField"] == 0, "nothing in this klass should need the escape hatch"
    assert sum(classes.values()) == 9, f"expected 9 fields, got {dict(classes)}"


def test_select_multi_is_a_known_field_type():
    """The gem does not declare it (by design) but the server emits it, so we must."""
    assert FieldType('select-multi') is FieldType.SELECT_MULTI


@pytest.mark.parametrize('value', ['date', 'wf-next', 'sys-reaction', 'drag', 'drag_reaction'])
def test_gem_declared_field_types_are_known(value):
    """Declared in the gem's field_type.rb; previously missing from this client."""
    assert FieldType(value).value == value


def test_unknown_field_type_is_kept_opaque_not_fatal():
    """A type LabIMotion adds after this client was built must degrade, not break the klass."""
    from chemotion_api.labImotion.items.fields import field_factory
    from chemotion_api.labImotion.items.fields.fields import OpaqueField

    sr = MagicMock()
    sr.get_select_options_list.return_value = []
    field = field_factory(sr, 'layer', {'type': 'a-type-from-the-future', 'field': 'f',
                                        'label': 'L', 'position': 1})
    assert isinstance(field, OpaqueField)


def test_load_all_skips_an_unparseable_klass_instead_of_aborting(caplog):
    """One bad klass must not take the whole generic API down with it."""
    good = _payload('demo.json')
    broken = {'name': 'broken-beyond-repair', 'properties_template': None, 'id': 99}

    con = MagicMock()
    con.get.return_value = MagicMock(status_code=200,
                                     json=lambda: {'klass': [broken, good, broken]})
    with caplog.at_level(logging.WARNING):
        loaded = GenericElement.load_all(con)
    assert [k.name for k in loaded] == ['demo'], 'the parseable klass must survive its neighbours'
    # Skipping silently would mean a klass — and every element using it — disappearing from a
    # real instance with nothing to explain why.
    assert 'broken-beyond-repair' in caplog.text, 'the skipped klass must be named in a warning'
