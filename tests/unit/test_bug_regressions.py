"""Regression tests for the bugs fixed in the 2026-06-30 bug-fix pass (see AI/BUGS.md).

All offline / no live server: each test pins one previously-broken behaviour so it cannot
silently regress.
"""
import types

import pytest


# --- Reaction duration -> valid ISO-8601 xsd:duration ----------------------------------------------

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


# --- O1: search no longer writes a stray test.json -------------------------------------------------

def test_search_send_request_does_not_write_test_json(tmp_path, monkeypatch):
    from chemotion_api.search.search_helper import SearchHelperBase

    class _Helper(SearchHelperBase):
        element_type = "sample"
        element_type_res = "samples"

        def new_field(self, match, connector, field_name, field_value):
            return {}

    fake_res = types.SimpleNamespace(
        status_code=201,
        json=lambda: {"samples": {"elements": []}},
    )
    connection = types.SimpleNamespace(post=lambda *a, **k: fake_res)

    helper = _Helper(connection, element_manager=None, root_collection_id=1)

    # Run with the temp dir as CWD so a leaked test.json would land somewhere observable.
    monkeypatch.chdir(tmp_path)
    assert helper._send_request() == []
    assert not (tmp_path / "test.json").exists()


# --- O2: MaterialList.after_append catches KeyError, not just ValueError ----------------------------

def test_material_list_after_append_falls_back_on_key_error():
    from chemotion_api.elements.reaction import MaterialList

    ml = MaterialList(reaction=None, mat_type="products")

    calls = []

    class _Element:
        def get_amount(self):
            raise KeyError("missing amount")

        def allowed_quantity_units(self):
            return ["g"]

        def set_amount(self, *args, **kwargs):
            calls.append((args, kwargs))

    # Before the fix `except ValueError or KeyError` only caught ValueError, so this KeyError
    # would propagate instead of triggering the zero-amount fallback.
    ml.after_append(_Element())
    assert calls == [((0, "g"), {})]


# --- O3: greate_device is a deprecated alias of create_device --------------------------------------

def test_greate_device_alias_warns_and_delegates():
    from chemotion_api.admin import AdminMenu

    fake_res = types.SimpleNamespace(status_code=201, json=lambda: {"id": 7})
    posts = []

    def _post(url, **kwargs):
        posts.append((url, kwargs))
        return fake_res

    session = types.SimpleNamespace(
        post=_post,
        get_default_session_header=lambda: {},
    )
    admin = AdminMenu(session)

    with pytest.warns(DeprecationWarning):
        result = admin.greate_device("Bench", "Top", "BT")

    assert result == {"id": 7}
    assert posts and posts[0][0] == "/api/v1/admin/group_device/create"


# --- O5: SubBaseField.id setter uses its value argument (not the builtin id) ------------------------

def test_sub_field_id_setter_stores_value():
    from chemotion_api.labImotion.items.fields.sub_fields import TextField

    field = TextField(sr=None, layer_key="", json_data={})
    field.id = "my-id"
    assert field.id == "my-id"

    with pytest.raises(TypeError):
        field.id = 123


# --- O6: TSDragSample.value setter stores the filtered display tokens, not the raw input ------------

def test_ts_drag_sample_value_setter_keeps_display_tokens():
    from chemotion_api.labImotion.items.fields.table_sub_fields import TSDragSample

    field = TSDragSample(sr=None, layer_key="", json_data={})
    field.value = "name;bogus;molecular_weight"
    # Only recognised tokens are retained, each terminated with ';'; the unknown token is dropped.
    assert field.value == "name;molecular_weight;"


# --- Yield cache: 0.0 must round-trip; zero-product loses yield loudly, not silently ---------------

def _offline_reaction():
    import os
    from chemotion_api.offline import import_export_zip
    fixtures = os.path.join(os.path.dirname(__file__), "..", "fixtures")
    return import_export_zip(os.path.join(fixtures, "mini_export.json")).get_reactions()[0]


def test_zero_yield_round_trips_to_product_equivalent():
    rxn = _offline_reaction()
    rxn.properties['yield_value'] = 0.0
    serialized = rxn._clean_properties_data()
    # 0.0 is a legitimate yield (failed reaction); an or-chain would have dropped it
    assert serialized['yield'] == 0.0
    assert rxn.properties['products'][0]._properties['equivalent'] == 0.0


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
    with caplog.at_level(logging.WARNING, logger="chemotion_api.elements.reaction"):
        rxn._clean_properties_data()
    assert any("stored only on the first product" in r.message for r in caplog.records)
    assert rxn.properties['products'][0]._properties['equivalent'] == 0.5
