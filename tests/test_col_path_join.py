"""`_col_path_join` dropped segments after an absolute one (found by a 2026-11-12 review of main;
the same bug is on this line, returning '/b/' for the first case)."""
import pytest

from chemotion_api.collection import _col_path_join


@pytest.mark.parametrize("parts, expected", [
    (('a', '/b', 'c', 'd'), '/b/c/d'),
    (('a', 'x', '/b', 'c', 'd'), '/b/c/d'),
    (('a', 'b', 'c'), 'a/b/c'),
    (('/a', 'b'), '/a/b'),
    (('a', '/b', '/c', 'd'), '/c/d'),
    (('a', '', 'b'), 'a/b'),
])
def test_col_path_join(parts, expected):
    assert _col_path_join(*parts) == expected
