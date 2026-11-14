"""A molecule assigned to a sample obtained from a listing is kept (ported from the 401 line).

A listed sample loads its full record on first use. The molecule setter stored the new molecule
and then read the properties, whose load re-parsed the server's molecule over it.
"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(__file__))
from test_sample_properties import SEGMENTS, SESSION, _sample_json  # noqa: E402

from chemotion_api.elements.sample import Molecule, Sample  # noqa: E402


def test_a_molecule_assigned_to_a_listed_sample_is_kept():
    full = _sample_json(2) | {'molecule': {'id': 1, 'molecular_weight': 100.0}}
    listing = {k: full[k] for k in ('id', 'type', 'name', 'short_label', 'molecule')}
    session = SimpleNamespace(**vars(SESSION), get=lambda url, **kw: SimpleNamespace(
        status_code=200, headers={}, json=lambda: {'sample': full, 'attachments': []}))
    sample = Sample(SEGMENTS, session, json_data=listing)
    sample.mark_partial()
    sample.molecule = Molecule({'id': 7, 'molecular_weight': 46.07, 'density': 0.789})
    assert sample.molecule['id'] == 7
