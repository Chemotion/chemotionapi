"""Regressions that only surface through the exporter or offline ingestion."""
import types
import pytest


def test_reaction_duration_to_iso8601_is_valid_xsd_duration():
    from chemotion_api.elements.reaction import _chemotion_duration_to_iso8601
    from rdflib import Literal, XSD

    # Chemotion display strings must become ISO-8601 (a raw "4 Hour(s)" is an invalid xsd:duration).
    assert _chemotion_duration_to_iso8601("4 Hour(s)") == "PT4H"
    assert _chemotion_duration_to_iso8601("3 Day(s)") == "P3D"
    assert _chemotion_duration_to_iso8601("3.5 Hour(s)") == "PT3H30M"
    assert _chemotion_duration_to_iso8601("90 Minute(s)") == "PT1H30M"
    # Unparseable / empty -> None so the field is omitted rather than emitted invalid.
    for bad in ("garbage", "", None):
        assert _chemotion_duration_to_iso8601(bad) is None
    # Every produced value must round-trip through rdflib's xsd:duration parser without error.
    for s in ("4 Hour(s)", "3 Day(s)", "3.5 Hour(s)", "1 Hour(s)", "24 Hour(s)"):
        Literal(_chemotion_duration_to_iso8601(s), datatype=XSD.duration).toPython()


def _offline_reaction():
    import os
    from chemotion_api.offline import import_export_zip
    fixtures = os.path.join(os.path.dirname(__file__), "..", "fixtures")
    return import_export_zip(os.path.join(fixtures, "mini_export.json")).get_reactions()[0]


def test_zero_yield_round_trips_to_product_equivalent():
    rxn = _offline_reaction()
    rxn.properties['yield_value'] = 0.0
    before = rxn.properties['products'][0]._properties.get('equivalent')
    serialized = rxn._clean_properties_data()
    # 0.0 is a legitimate yield (failed reaction); an or-chain would have dropped it
    assert serialized['yield'] == 0.0
    # Asserted on the serialised payload, which is what reaches the server. It used to be asserted
    # on `products[0]._properties` — but writing there meant *serialising* a reaction mutated the
    # in-memory model, so merely inspecting or exporting one silently altered it.
    assert serialized['materials']['products'][0]['equivalent'] == 0.0
    assert rxn.properties['products'][0]._properties.get('equivalent') == before


def test_yield_without_products_warns_instead_of_silent_loss(caplog):
    import logging
    rxn = _offline_reaction()
    rxn.properties['yield_value'] = 42.0
    rxn.properties['products'] = []
    with caplog.at_level(logging.WARNING, logger="chemotion_api.elements.reaction"):
        rxn._clean_properties_data()
    assert any("cannot be persisted" in r.message for r in caplog.records)


def test_multi_product_yield_warns_and_writes_first_product(caplog):
    import logging
    rxn = _offline_reaction()
    rxn.properties['yield_value'] = 50.0
    rxn.properties['products'] = rxn.properties['products'] * 2
    before = rxn.properties['products'][0]._properties.get('equivalent')
    with caplog.at_level(logging.WARNING, logger="chemotion_api.elements.reaction"):
        serialized = rxn._clean_properties_data()
    assert any("stored only on the first product" in r.message for r in caplog.records)
    assert serialized['materials']['products'][0]['equivalent'] == 0.5
    assert rxn.properties['products'][0]._properties.get('equivalent') == before
