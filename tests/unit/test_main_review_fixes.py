"""Fixes for findings from a code review of `main` (2026-11-12), offline."""
import json
from types import SimpleNamespace

import pytest

from chemotion_api.collection import _col_path_join
from chemotion_api.utils import break_parent_cycles


# --- F5: an absolute segment keeps everything after it ------------------------------------

@pytest.mark.parametrize("parts, expected", [
    (('a', '/b', 'c', 'd'), '/b/c/d'),        # was '/b'   — tail dropped when i == 0
    (('a', 'x', '/b', 'c', 'd'), '/b/c/d'),   # was '/b/d' — `[-i:]` took the last i items
    (('a', 'b', 'c'), 'a/b/c'),               # no absolute segment: plain join
    (('/a', 'b'), '/a/b'),
    (('a', '/b', '/c', 'd'), '/c/d'),         # the *last* absolute segment wins
    (('a/', '/b'), '/b'),
    (('a', '', 'b'), 'a/b'),                  # duplicate slashes collapse
])
def test_col_path_join(parts, expected):
    assert _col_path_join(*parts) == expected


# --- F9: only the nodes actually on the cycle are reported --------------------------------

def test_cycle_members_only_not_the_chain_leading_in():
    """D -> C -> A <-> B: only A and B loop. D and C have real parents and must stay nested."""
    assert break_parent_cycles({'D': 'C', 'C': 'A', 'A': 'B', 'B': 'A'}) == {'A', 'B'}


def test_self_loop():
    assert break_parent_cycles({'A': 'A', 'B': 'A'}) == {'A'}


def test_proper_forest_has_no_cycles():
    assert break_parent_cycles({'A': None, 'B': 'A', 'C': 'B'}) == set()


# --- F7: the client rejects what the server rejects ---------------------------------------

@pytest.mark.parametrize("width, height", [(0, 8), (8, 0), (0, 0)])
def test_resize_refuses_zero_before_any_request(width, height):
    from chemotion_api.elements.wellplate import Wellplate

    with pytest.raises(ValueError):
        Wellplate.resize(SimpleNamespace(), width, height)


# --- F6: Molecule is a real mapping -------------------------------------------------------

def _molecule(**data):
    from chemotion_api.elements.sample import Molecule
    return Molecule(data)


def test_molecule_model_fields_and_extras_are_readable():
    m = _molecule(molecular_weight=46.07, custom_tag='x')
    assert m['molecular_weight'] == 46.07
    assert m['custom_tag'] == 'x'            # unknown keys land in model_extra


def test_molecule_missing_key_raises_so_in_and_get_work():
    """`__getitem__` used to return None for a missing key, which broke the mapping protocol:
    `MutableMapping.__contains__` and `.get()` both work by catching KeyError."""
    m = _molecule(molecular_weight=46.07)
    with pytest.raises(KeyError):
        m['no_such_key']
    assert 'no_such_key' not in m                  # was always True
    assert m.get('no_such_key', 1.0) == 1.0        # was None
    # A *declared* field that is unset is a different thing: the key exists, its value is None.
    # `density` is a MoleculeModel field, so this is correct mapping behaviour, not the bug.
    assert 'density' in m and m.get('density', 1.0) is None


# --- F4: load_sync_collection never serves a stale listing --------------------------------

class _Session:
    """Answers the two collection endpoints and counts listing fetches."""

    def __init__(self):
        self.listing_fetches = 0
        self.shared = []

    def get(self, url):
        if url == '/api/v1/collections/':
            self.listing_fetches += 1
            body = {'own': [], 'shared_with_me': list(self.shared)}
            return SimpleNamespace(status_code=200, content=json.dumps(body).encode())
        if url == '/api/v1/collections/all':
            return SimpleNamespace(status_code=200,
                                   content=json.dumps({'collection': {'id': 1, 'label': 'All'}}).encode())
        raise AssertionError(f'unexpected GET {url}')


def _root():
    from chemotion_api.collection import RootCollection
    s = _Session()
    r = RootCollection(s)
    r._element_manager = SimpleNamespace(all_classes={})
    return r, s


def test_standalone_sync_load_fetches_afresh():
    r, s = _root()
    r.load_collection()
    r.load_sync_collection()
    assert s.listing_fetches == 2


def test_paired_load_shares_one_fetch():
    r, s = _root()
    listing = r._fetch_collections()
    r.load_collection(listing)
    r.load_sync_collection(listing)
    assert s.listing_fetches == 1


def test_a_share_granted_after_save_is_visible():
    """The actual bug: `save()` -> `load_collection()` left a cached listing that a later
    standalone `load_sync_collection()` served, so a share granted in between never appeared."""
    r, s = _root()
    r.load_collection()                                  # like save(); nothing shared yet
    s.shared.append({'id': 7, 'label': 'from a colleague', 'ancestry': None})
    r.load_sync_collection()                             # the call you make to see the new share
    assert [c.id for c in r.sync_root.children] == [7]
