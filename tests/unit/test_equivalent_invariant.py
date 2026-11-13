"""Equivalents must always equal what a full recompute gives, whatever path changed them.

Pins behaviour while the incremental recompute (2026-11-13) replaces the full pass that every
amount change used to trigger.
"""
import math
import random
import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from test_sample_properties import _reaction, _sample  # noqa: E402

from chemotion_api.elements.utils import QuantityUnit  # noqa: E402


def _equivalents(reaction):
    return [m.properties['equivalent'] for m in [*reaction.starting_materials, *reaction.reactants,
                                                  *reaction.products]]


def _same(a, b):
    return all((x is None and y is None) or (x is not None and y is not None and math.isclose(x, y))
               for x, y in zip(a, b, strict=True))


@pytest.mark.parametrize("seed", range(5))
def test_incremental_equivalents_match_a_full_recompute(seed):
    rng = random.Random(seed)
    reaction = _reaction([_sample(i, mw=50 + 10 * i) for i in range(1, 5)],
                         reactants=[_sample(i, mw=30 + 7 * i) for i in range(5, 9)])
    mats = [*reaction.starting_materials, *reaction.reactants]
    reaction.reference_sample = mats[0]
    for _ in range(60):
        target = rng.choice(mats)
        op = rng.randrange(5)
        if op == 0:
            target.set_amount(rng.uniform(0.1, 5), rng.choice([QuantityUnit.Gram, QuantityUnit.Mole]))
        elif op == 1:
            target.properties['purity'] = rng.choice([0.5, 0.8, 1.0])
        elif op == 2:
            target.properties['coefficient'] = rng.choice([1, 2, 3])
        elif op == 3:
            reaction.reference_sample = rng.choice(mats)
        else:
            new = _sample(100 + rng.randrange(1000), mw=rng.uniform(20, 200))
            reaction.properties['reactants'].append_no_split(new)
            mats.append(new)
        seen = _equivalents(reaction)
        reaction.update_equivalent()
        assert _same(seen, _equivalents(reaction)), f'after op {op} on seed {seed}'


def test_save_sends_equivalents_that_match_the_amounts(monkeypatch):
    """Reaction.save() recomputes before serialising (serialising itself stays side-effect free),
    so an amount changed behind the client's back still goes out with a matching equivalent."""
    from chemotion_api.elements.abstract_element import AbstractElement
    from chemotion_api.utils import UnitDict
    reaction = _reaction([_sample(1, mw=100.0)], reactants=[_sample(2, mw=100.0)])
    ref, other = reaction.starting_materials[0], reaction.reactants[0]
    reaction.reference_sample = ref
    ref.set_amount(1.0, QuantityUnit.Mole)
    other.set_amount(1.0, QuantityUnit.Mole)
    assert other.properties['equivalent'] == pytest.approx(1.0)
    other._properties['target_amount'] = UnitDict(unit='mol', value=3.0)    # no recompute triggered
    assert other.properties['equivalent'] == pytest.approx(1.0)              # stale

    sent = {}
    monkeypatch.setattr(AbstractElement, 'save', lambda self, load_after_save=False: sent.update(
        equivalent=self.reactants[0].properties['equivalent']))
    reaction.save()
    assert sent['equivalent'] == pytest.approx(3.0)
