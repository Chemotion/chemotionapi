"""Pydantic v2 data models used to validate and normalize element properties on read and write."""
from pydantic import BaseModel, Field, ConfigDict
from typing import Literal, Any
from enum import Enum

class GasType(str, Enum):  # noqa: UP042 — StrEnum would change str()/format() output ('GasType.OFF' -> 'off')
    """Enumeration of the gas roles a sample can play in a gas-phase reaction.

    Members are ``OFF`` (not a gas), ``FEEDSTOCK``, ``CATALYST`` and ``GAS``.
    """
    OFF = 'off'
    FEEDSTOCK = 'feedstock'
    CATALYST = 'catalyst'
    GAS = 'gas'

class UnitDictModel(BaseModel):
    """A scalar value together with its unit.

    Used throughout the API for quantities such as amounts, temperatures and durations.
    Extra keys are preserved (``extra='allow'``).

    :ivar unit: the unit symbol (e.g. ``"K"``, ``"h"``).
    :ivar value: the numeric value in that unit.
    """
    model_config = ConfigDict(extra='allow', populate_by_name=True)
    unit: str | None = None
    value: float | None = None

    def to_dict(self) -> dict:
        """Return this model as a plain ``dict``.

        :return: the model serialized via Pydantic's ``model_dump``.
        """
        return self.model_dump()

class GasPhaseModel(BaseModel):
    """Gas-phase kinetic data attached to a sample taking part in a gas-phase reaction.

    :ivar time: reaction time (default unit ``"h"``).
    :ivar temperature: reaction temperature (default unit ``"K"``).
    :ivar turnover_number: catalytic turnover number (TON).
    :ivar part_per_million: concentration in parts per million.
    :ivar turnover_frequency: catalytic turnover frequency (default unit ``"TON/h"``).
    """
    model_config = ConfigDict(extra='allow', populate_by_name=True)
    time: UnitDictModel = Field(default_factory=lambda: UnitDictModel(unit="h"))
    temperature: UnitDictModel = Field(default_factory=lambda: UnitDictModel(unit="K"))
    turnover_number: float | None = None
    part_per_million: float | None = None
    turnover_frequency: UnitDictModel = Field(default_factory=lambda: UnitDictModel(unit="TON/h"))

    def to_dict(self) -> dict:
        """Return this model as a plain ``dict``.

        :return: the model serialized via Pydantic's ``model_dump``.
        """
        return self.model_dump()

class MoleculeModel(BaseModel):
    """Physico-chemical and identity properties of the molecule behind a sample.

    Holds structural identifiers (SMILES, InChI, InChIKey, molfile, sum formula, CAS, names) and
    physical constants (density, melting/boiling point, molecular weights). Extra keys are
    preserved (``extra='allow'``).
    """
    model_config = ConfigDict(extra='allow', populate_by_name=True)
    id: int | None = None
    cano_smiles: str | None = None
    density: float | None = None
    inchikey: str | None = None
    inchistring: str | None = None
    melting_point: float | None = None
    boiling_point: float | None = None
    molecular_weight: float | None = None
    exact_molecular_weight: float | None = None
    sum_formular: str | None = None
    molfile: str | None = None
    cas: str | list[str] | None = None
    names: list[str] | None = Field(default_factory=list)

    def clean(self) -> dict:
        """Return the subset of molecule properties that may be sent back on update.

        :return: a ``dict`` with density, melting/boiling point and the structural identifiers
            (``inchistring``, ``cano_smiles``, ``inchikey``).
        """
        return {
            "density": self.density,
            "melting_point": self.melting_point,
            "boiling_point": self.boiling_point,
            "inchistring": self.inchistring,
            "cano_smiles": self.cano_smiles,
            "inchikey": self.inchikey
        }

class SamplePropertiesModel(BaseModel):
    """Editable properties of a Chemotion *sample* element.

    Covers identity (name, labels), amounts (target/real amount, molarity, purity, density,
    equivalent, coefficient), structure (sum formula, stereo), physical bounds (melting/boiling
    point ranges), flags (top-secret, restricted, decoupled, waste, reference, dry solvent) and
    gas-phase data (``gas_type`` / ``gas_phase_data``). Extra keys are preserved
    (``extra='allow'``).
    """
    model_config = ConfigDict(extra='allow', populate_by_name=True)
    name: str | None = None
    short_label: str | None = None
    solvent: list[Any] | None = Field(default_factory=list)
    description: str | dict[str, Any] | None = None
    external_label: str | None = None
    boiling_point_lowerbound: int | float | None = None
    boiling_point_upperbound: int | float | None = None
    melting_point_lowerbound: int | float | None = None
    melting_point_upperbound: int | float | None = None
    target_amount: UnitDictModel | None = Field(default_factory=lambda: UnitDictModel())
    real_amount: UnitDictModel | None = Field(default_factory=lambda: UnitDictModel())
    stereo: dict[str, Any] | None = Field(default_factory=dict)
    location: str | None = None
    is_top_secret: bool | None = None
    is_restricted: bool | None = None
    purity: float | None = None
    density: float | None = None
    user_labels: list[Any] | None = Field(default_factory=list)
    decoupled: bool | None = None
    waste: bool | None = False
    reference: bool | None = False
    metrics: str | None = None
    sum_formula: str | None = None
    equivalent: float | None = None
    coefficient: float | None = 1.0
    reaction_description: str | dict[str, Any] | None = None
    molarity: UnitDictModel | None = Field(default_factory=lambda: UnitDictModel())
    molecular_mass: float | None = None
    inventory_sample: bool | None = None
    position: int | None = None
    show_label: bool | None = None
    gas_type: GasType = GasType.OFF
    gas_phase_data: GasPhaseModel | None = None
    dry_solvent: bool | None = False
    impurities: str | None = None
    xref: dict[str, Any] | None = Field(default_factory=dict)

class ReactionPropertiesModel(BaseModel):
    """Editable properties of a Chemotion *reaction* element.

    Covers identity (name, labels, status), conditions (temperature, duration, vessel, vessel
    size, volume), outcome (yield, observation, RInChI strings), descriptions, TLC data, the
    reaction type (``rxno``), gas-phase flag and the reaction ``variations``. The ``yield`` field
    is exposed as ``yield_value`` (aliased to ``yield``). Extra keys are preserved
    (``extra='allow'``).
    """
    model_config = ConfigDict(extra='allow', populate_by_name=True)
    name: str | None = None
    short_label: str | None = None
    status: str | None = None
    duration: UnitDictModel | str | dict[str, Any] | None = Field(default_factory=lambda: UnitDictModel())
    temperature: UnitDictModel | None = Field(default_factory=lambda: UnitDictModel())
    vessel_size: float | None = None
    yield_value: float | None = Field(default=None, alias='yield')
    tlc_description: str | None = None
    dangerous_products: str | list[Any] | None = None
    description: str | dict[str, Any] | None = None
    reaction_description: str | dict[str, Any] | None = None
    observation: str | dict[str, Any] | None = None
    user_labels: list[Any] | None = Field(default_factory=list)
    vessel: str | None = None
    gas_schema: bool | None = False
    position: int | None = None
    show_label: bool | None = None
    rxno: str | None = None
    conditions: str | None = None
    purification: str | list[str] | None = Field(default_factory=list)
    tlc_solvents: str | None = None
    rf_value: str | float | None = None
    volume: float | None = None
    use_reaction_volume: bool | None = False
    #: ELN v4.0.0 replaced the `use_reaction_volume` boolean with a three-valued mode. The
    #: server still accepts the boolean and maps it (True -> 'reaction_volume',
    #: False -> 'solvents_only'), which is why the legacy field stays — but the boolean
    #: cannot express 'combined' at all.
    concentration_mode: Literal['solvents_only', 'combined', 'reaction_volume'] | None = None
    weight_percentage: bool | None = False
    rinchi_string: str | None = None
    rinchi_web_key: str | None = None
    variations: dict[str, Any] | list[Any] | None = Field(default_factory=dict)
