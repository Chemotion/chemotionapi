"""Offline tests for PropertyDict ergonomics (attribute discoverability + helpful errors)."""
import pytest

from chemotion_api.utils import PropertyDict


def _pd(**kw):
    return PropertyDict(lambda d, n, v: True, dict(**kw))


def test_dir_exposes_keys_for_autocomplete():
    pd = _pd(purity=0.99, name="Ethanol")
    d = dir(pd)
    assert "purity" in d and "name" in d
    # still includes normal attributes
    assert "to_dict" in d


def test_attribute_access_roundtrip():
    pd = _pd(purity=0.99)
    assert pd.purity == 0.99
    pd.purity = 0.5
    assert pd["purity"] == 0.5


def test_helpful_attribute_error_suggests_close_match():
    pd = _pd(purity=0.99, density=1.0)
    with pytest.raises(AttributeError) as exc:
        _ = pd.purty  # typo
    assert "purity" in str(exc.value)  # "Did you mean: purity?"
