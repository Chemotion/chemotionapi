"""Regression tests for the bugs fixed in the 2026-06-30 bug-fix pass (see AI/BUGS.md).

All offline / no live server: each test pins one previously-broken behaviour so it cannot
silently regress.
"""
import types

import pytest


# --- Reaction duration -> valid ISO-8601 xsd:duration ----------------------------------------------



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







