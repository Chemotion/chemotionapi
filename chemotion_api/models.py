"""Pydantic v2 data models used to validate and normalize element properties on read and write."""
from functools import cache

from pydantic import BaseModel, Field, ConfigDict, TypeAdapter, field_validator
from typing import Annotated, Literal, Any
from enum import Enum

from chemotion_api.utils.withheld import WITHHELD

class GasType(str, Enum):  # noqa: UP042 — StrEnum would change str()/format() output ('GasType.OFF' -> 'off')
    """Enumeration of the gas roles a sample can play in a gas-phase reaction.

    Members are ``OFF`` (not a gas), ``FEEDSTOCK``, ``CATALYST`` and ``GAS``.
    """
    OFF = 'off'
    FEEDSTOCK = 'feedstock'
    CATALYST = 'catalyst'
    GAS = 'gas'

class _PropertiesBase(BaseModel):
    """Base for every properties model: lets :data:`~chemotion_api.utils.withheld.WITHHELD` through.

    A field the server withheld (shared below full detail) carries the sentinel instead of a value
    of the field's type. It must survive validation untouched rather than fail it, or a restricted
    element could not be loaded at all.
    """

    @field_validator('*', mode='wrap')
    @classmethod
    def _keep_withheld(cls, value, handler):
        return value if value is WITHHELD else handler(value)


class VesselSizeModel(_PropertiesBase):
    """A reaction's vessel size, as the server stores it: ``{'amount': 10, 'unit': 'ml'}``.

    Note ``amount``, not ``value`` — this is why it is not a :class:`UnitDictModel`. Until 401.0
    the reaction model typed this as ``float | None``, which did not match what the server sends
    or what the rest of the client reads (``vessel_size.get('amount')``), so the field could not
    be assigned through ``properties`` at all. Extra keys are preserved (``extra='allow'``).

    :ivar amount: the volume.
    :ivar unit: its unit, e.g. ``"ml"`` or ``"l"``.
    """
    model_config = ConfigDict(extra='allow')
    amount: float | None = None
    unit: str | None = None


class UnitDictModel(_PropertiesBase):
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

class GasPhaseModel(_PropertiesBase):
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

class MoleculeModel(_PropertiesBase):
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

class SamplePropertiesModel(_PropertiesBase):
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

class ReactionPropertiesModel(_PropertiesBase):
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
    vessel_size: VesselSizeModel | None = None
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


@cache
def _field_adapter(model: type[BaseModel], field: str) -> TypeAdapter:
    info = model.model_fields[field]
    # Keep the field's constraints (`Field(ge=...)` etc. live in `metadata`, not the annotation).
    annotation: Any = Annotated[(info.annotation, *info.metadata)] if info.metadata else info.annotation
    return TypeAdapter(annotation)


def validate_field(model: type[BaseModel], field: str, value: Any) -> Any:
    """Validate and coerce one field of ``model`` — the cost of a single property write.

    Property writes used to rebuild the *whole* property set, deep-copy it, and run
    ``model.model_validate`` on all of it, so adding N materials to a reaction ran N full-model
    validations (review finding F8, 2026-11-12). Validating only the written field is
    equivalent for these models — they carry no cross-field validators and no field constraints
    beyond the annotation — with one deliberate difference: an unrelated field already holding a
    bad value no longer makes this write fail.

    A name that is not a model field is returned unchanged, exactly as ``extra='allow'`` passed it
    through under whole-model validation. Adapters are built once per ``(model, field)``.
    """
    if field not in model.model_fields:
        return value
    return _field_adapter(model, field).validate_python(value)


class WellplatePropertiesModel(_PropertiesBase):
    """Validates the writable properties of a wellplate.

    ``description`` is Quill delta (the server declares it a ``Hash``). Wells and their samples are
    edited through :attr:`Wellplate.wells`, not through properties.
    """
    model_config = ConfigDict(extra='allow')
    name: str | None = None
    description: dict[str, Any] | None = None


class ResearchPlanPropertiesModel(_PropertiesBase):
    """Validates the properties of a research plan.

    Its only property is ``body``: the plan's blocks (text, tables, images, samples, reactions),
    each a typed object with its own API. The model checks it is a list; the blocks validate
    themselves.
    """
    model_config = ConfigDict(extra='allow')
    body: list[Any] = Field(default_factory=list)


class ScreenPropertiesModel(_PropertiesBase):
    """Validates the writable properties of a screen (types as the server's update route declares)."""
    model_config = ConfigDict(extra='allow')
    name: str | None = None
    collaborator: str | None = None
    requirements: str | None = None
    conditions: str | None = None
    result: str | None = None
    description: dict[str, Any] | str | None = None   # Quill delta; a plain string is wrapped on save
    component_graph_data: dict[str, Any] | None = None
    user_labels: list[int] = Field(default_factory=list)


class DeviceDescriptionPropertiesModel(_PropertiesBase):
    """Validates the modelled fields of a device description (types as the server's API declares)."""
    model_config = ConfigDict(extra='allow')
    name: str | None = None
    short_label: str | None = None
    description: str | None = None
    device_type_name: str | None = None
    device_type_id: str | None = None
    device_type_id_type: str | None = None
    device_class: str | None = None
    device_class_detail: str | None = None
    operation_mode: str | None = None
    vendor_device_name: str | None = None
    vendor_device_id: str | None = None
    vendor_company_name: str | None = None
    serial_number: str | None = None
    version_number: str | None = None
    version_doi: str | None = None
    version_doi_url: str | None = None
    version_characterization: str | None = None
    version_installation_start_date: str | None = None   # ISO date-time
    version_installation_end_date: str | None = None
    owner_institution: str | None = None
    university_campus: str | None = None
    institute: str | None = None
    building: str | None = None
    room: str | None = None
    application_name: str | None = None
    application_version: str | None = None
    vendor_url: str | None = None
    general_tags: list[Any] | None = None
    operators: list[Any] | None = None


class _QuantityModel(_PropertiesBase):
    """A value with its unit, as an SBMM sample's quantities are held in ``properties``."""
    model_config = ConfigDict(extra='forbid')
    value: float | None = None
    unit: str | None = None


class SbmmSamplePropertiesModel(_PropertiesBase):
    """Validates an SBMM sample's own properties (types and units as the server's API declares)."""
    model_config = ConfigDict(extra='allow')
    name: str | None = None
    external_label: str | None = None
    function_or_application: str | None = None
    inventory_sample: bool | None = None
    obtained_by: Literal['purchased', 'self_produced', ''] | None = None
    supplier: str | None = None
    formulation: Literal['dissolved', 'solid', ''] | None = None
    purity: float | None = None
    purity_detection: str | None = None
    purification_method: str | None = None
    concentration: _QuantityModel | None = None
    concentration_rt: _QuantityModel | None = None
    molarity: _QuantityModel | None = None
    activity_per_volume: _QuantityModel | None = None
    activity_per_mass: _QuantityModel | None = None
    volume_as_used: _QuantityModel | None = None
    amount_as_used_mol: _QuantityModel | None = None
    amount_as_used_mass: _QuantityModel | None = None
    activity: _QuantityModel | None = None


class CellLinePropertiesModel(_PropertiesBase):
    """Validates a cell-line sample's own properties (types as the server's API declares)."""
    model_config = ConfigDict(extra='allow')
    name: str | None = None
    description: str | None = None
    amount: int | None = None
    unit: str | None = None
    passage: int | None = None
    contamination: str | None = None


class CellLineMaterialModel(_PropertiesBase):
    """Validates a cell line's shared material — the cell line *concept* (types as the server declares)."""
    model_config = ConfigDict(extra='allow')
    name: str | None = None
    source: str | None = None
    organism: str | None = None
    tissue: str | None = None
    disease: str | None = None
    cell_type: str | None = None
    biosafety_level: str | None = None
    growth_medium: str | None = None
    variant: str | None = None
    mutation: str | None = None
    optimal_growth_temp: float | None = None
    cryo_pres_medium: str | None = None
    gender: str | None = None
    description: str | None = None
