"""Unit tests for the Pydantic v2 models (chemotion_api.models).

Pure-logic / offline: imports only the models module + pydantic. No server, no rdflib execution.
"""
import pytest

from chemotion_api.models import (
    GasType, UnitDictModel, GasPhaseModel, MoleculeModel,
    SamplePropertiesModel, ReactionPropertiesModel,
)


# --- UnitDictModel ---------------------------------------------------------------

def test_unitdict_defaults_and_to_dict():
    u = UnitDictModel()
    assert u.unit is None and u.value is None
    assert u.to_dict() == {"unit": None, "value": None}


def test_unitdict_coerces_value_to_float():
    u = UnitDictModel(unit="g", value="1.5")  # pydantic coerces numeric strings
    assert u.value == 1.5 and isinstance(u.value, float)


def test_unitdict_allows_extra_fields():
    u = UnitDictModel(unit="g", value=1.0, userText="approx")  # extra='allow'
    assert u.to_dict()["userText"] == "approx"


# --- GasType ---------------------------------------------------------------------

def test_gas_type_values():
    assert GasType.OFF.value == "off"
    assert {g.value for g in GasType} == {"off", "feedstock", "catalyst", "gas"}


# --- MoleculeModel ---------------------------------------------------------------

def test_molecule_clean_returns_expected_subset():
    m = MoleculeModel(cano_smiles="CCO", inchikey="LFQSCWFLJHTTHZ-UHFFFAOYSA-N", density=0.789,
                      molecular_weight=46.07, names=["ethanol"])
    cleaned = m.clean()
    assert set(cleaned) == {"density", "melting_point", "boiling_point",
                            "inchistring", "cano_smiles", "inchikey"}
    assert cleaned["cano_smiles"] == "CCO"
    assert "molecular_weight" not in cleaned  # clean() is a deliberate subset


def test_molecule_cas_accepts_str_or_list():
    assert MoleculeModel(cas="64-17-5").cas == "64-17-5"
    assert MoleculeModel(cas=["64-17-5", "200-578-6"]).cas == ["64-17-5", "200-578-6"]


def test_molecule_names_default_is_independent_list():
    a, b = MoleculeModel(), MoleculeModel()
    a.names.append("x")
    assert b.names == []  # default_factory, not a shared mutable default


# --- SamplePropertiesModel -------------------------------------------------------

def test_sample_properties_defaults():
    s = SamplePropertiesModel()
    assert s.gas_type == GasType.OFF
    assert isinstance(s.target_amount, UnitDictModel)
    assert s.waste is False and s.coefficient == 1.0


def test_sample_properties_allows_unknown_fields():
    s = SamplePropertiesModel(name="EtOH", some_future_field=123)
    assert s.model_dump()["some_future_field"] == 123  # extra='allow'


def test_sample_description_accepts_str_or_dict():
    assert SamplePropertiesModel(description="text").description == "text"
    assert SamplePropertiesModel(description={"ops": []}).description == {"ops": []}


# --- ReactionPropertiesModel -----------------------------------------------------

def test_reaction_yield_alias_populates_from_yield_key():
    r = ReactionPropertiesModel.model_validate({"yield": 95.0})
    assert r.yield_value == 95.0


def test_reaction_yield_alias_accepts_field_name_too():
    # populate_by_name=True -> both 'yield' and 'yield_value' work
    assert ReactionPropertiesModel(yield_value=42.0).yield_value == 42.0


def test_reaction_duration_union_accepts_str_dict_and_model():
    # a string stays a string...
    assert ReactionPropertiesModel(duration="2 h").duration == "2 h"
    # ...while a dict is coerced into the first Union member (UnitDictModel). This is exactly why
    # the load path must guard with isinstance(duration, UnitDictModel) before calling .to_dict().
    d = ReactionPropertiesModel(duration={"unit": "h", "value": 2}).duration
    assert isinstance(d, UnitDictModel) and d.unit == "h" and d.value == 2.0
    assert isinstance(ReactionPropertiesModel(duration=UnitDictModel(unit="h", value=2)).duration, UnitDictModel)


def test_reaction_temperature_default_is_unitdict():
    assert isinstance(ReactionPropertiesModel().temperature, UnitDictModel)


def test_reaction_allows_unknown_fields():
    r = ReactionPropertiesModel.model_validate({"name": "R1", "future": "x"})
    assert r.model_dump()["future"] == "x"


def test_reaction_purification_default_list():
    assert ReactionPropertiesModel().purification == []


def test_gas_phase_model_defaults():
    g = GasPhaseModel()
    assert g.time.unit == "h" and g.temperature.unit == "K"
    assert g.turnover_frequency.unit == "TON/h"
