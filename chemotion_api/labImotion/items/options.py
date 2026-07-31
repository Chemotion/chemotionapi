"""Enumerations and unit tables describing LabIMotion field, layer and element options."""

from enum import Enum

class ListableEnum(Enum):
    """Enum mixin exposing the member values as a plain list."""

    @classmethod
    def list(cls):
        """Return the values of all enum members as a list.

        :return: List of the ``.value`` of every member of this enum.
        """
        return list(map(lambda c: c.value, cls))

class SaveActionType(Enum):
    """Release level used when saving a generic template (draft, minor or major)."""
    DRAFT = "draft"
    MINOR = "minor"
    MAJOR = "major"

class ElementType(ListableEnum):
    """The kind of generic klass: segment, element or dataset."""
    SEGMENT = 'SegmentKlass'
    ELEMENT = 'ElementKlass'
    DATASET = 'DatasetKlass'

class SubFieldType(ListableEnum):
    """Allowed types for sub-fields of an input-group field."""
    NUMBER = 'number'
    LABEL = 'label'
    TEXT = 'text'
    SYSTEM_DEFINED = 'system-defined'


class SubTableFieldType(ListableEnum):
    """Allowed column types for the columns of a table field."""
    DRAG_MOLECULE = "drag_molecule"
    DRAG_SAMPLE = "drag_sample"
    SELECT = "select"
    SYSTEM_DEFINED = 'system-defined'
    TEXT = 'text'


class FieldType(ListableEnum):
    """The type of a generic field within a layer."""
    DUMMY = 'dummy'
    CHECKBOX = "checkbox"
    DATETIME = "datetime"
    DATETIME_RANGE = "datetime-range"
    DRAG_ELEMENT = "drag_element"
    DRAG_MOLECULE = "drag_molecule"
    DRAG_SAMPLE = "drag_sample"
    FORMULA_FIELD = "formula-field"
    INPUT_GROUP = "input-group"
    INTEGER = "integer"
    SELECT = "select"
    SYSTEM_DEFINED = "system-defined"
    TABLE = "table"
    TEXT_FORMULA = 'text-formula'
    TEXT = 'text'
    TEXTAREA = 'textarea'
    UPLOAD = 'upload'


class ConditionOperator(ListableEnum):
    """How multiple conditions combine: match all, any (one) or none."""
    MATCH_ALL = 9
    MATCH_ONE = 1
    MATCH_NONE = 0


class FieldUnit(ListableEnum):
    """Physical-quantity categories for which selectable units are defined."""
    ACCELERATION = "acceleration"
    AGITATION = "agitation"
    AMOUNT_ENZYME = "amount_enzyme"
    AMOUNT_SUBSTANCE = "amount_substance"
    MOLARITY = "molarity"
    CHEM_DISTANCES = "chem_distances"
    CONCENTRATION = "concentration"
    CONDUCTIVITY = "conductivity"
    CURRENT = "current"
    DEGREE = "degree"
    DENSITY = "density"
    DURATION = "duration"
    ELASTIC_MODULUS = "elastic_modulus"
    ELECTRIC_CHARGE_C = "electric_charge_c"
    ELECTRIC_CHARGE_MOL = "electric_charge_mol"
    ELECTRIC_FIELD = "electric_field"
    ENERGY = "energy"
    ENZYME_ACTIVITY = "enzyme_activity"
    FARADAY = "faraday"
    FLOW_RATE = "flow_rate"
    FREQUENCY = "frequency"
    HEATING_RATE = "heating_rate"
    LENGTH = "length"
    MAGNETIC_FLUX_DENSITY = "magnetic_flux_density"
    MASS = "mass"
    MASS_MOLECULE = "mass_molecule"
    MOLECULAR_WEIGHT = "molecular_weight"
    PERCENTAGE = "percentage"
    PRESSURE = "pressure"
    REACTION_RATE = "reaction_rate"
    SPECIFIC_VOLUME = "specific_volume"
    SPEED = "speed"
    SUBATOMIC_LENGTH = "subatomic_length"
    SURFACE = "surface"
    TEMPERATURE = "temperature"
    TURNOVER_NUMBER = "turnover_number"
    VISCOSITY = "viscosity"
    KINEMATIC_VISCOSITY = "kinematic_viscosity"
    VOLTAGE = "voltage"
    VOLUMES = "volumes"


class LayerColor(ListableEnum):
    """Bootstrap-style colour theme applied to a layer panel."""
    NONE = "none"
    BLUE = "primary"
    BLUE_LIGHT = "info"
    GREEN = "success"
    GREY = "default"
    RED = "danger"
    ORANGE = "warning"

UNITS = {
    FieldUnit.ACCELERATION: ["mm_s2"],
    FieldUnit.AGITATION: ["rpm"],
    FieldUnit.AMOUNT_ENZYME: ["u", "mu", "kat", "mkat", "µkat", "nkat"],
    FieldUnit.AMOUNT_SUBSTANCE:  ["mol", "mmol", "umol", "nmol", "pmol"],
    FieldUnit.MOLARITY: ["mol_l", "mmol_l", "umol_l", "nmol_l", "pmol_l"],
    FieldUnit.CHEM_DISTANCES: ["angstrom"],
    FieldUnit.CONCENTRATION: ["ng_l", "mg_l", "g_l"],
    FieldUnit.CONDUCTIVITY: ["s_m"],
    FieldUnit.CURRENT: ["A", "mA", "uA", "nA"],
    FieldUnit.DEGREE: ["degree"],
    FieldUnit.DENSITY: ["g_cm3", "kg_l"],
    FieldUnit.DURATION: ["d", "h", "min", "s"],
    FieldUnit.ELASTIC_MODULUS: ["m_pa", "k_pa", "pa"],
    FieldUnit.ELECTRIC_CHARGE_C: ["ec_c"],
    FieldUnit.ELECTRIC_CHARGE_MOL: ["ec_mol"],
    FieldUnit.ELECTRIC_FIELD: ["v_m"],
    FieldUnit.ENERGY: ["eV", "keV", "j", "k_j"],
    FieldUnit.ENZYME_ACTIVITY: ["u_l", "u_ml"],
    FieldUnit.FARADAY: ["faraday"],
    FieldUnit.FLOW_RATE: ["ul_min", "ml_min", "l_m"],
    FieldUnit.FREQUENCY: ["mhz", "hz", "khz"],
    FieldUnit.HEATING_RATE: ["k_min"],
    FieldUnit.LENGTH: ["mm", "cm", "m"],
    FieldUnit.MAGNETIC_FLUX_DENSITY: ["T"],
    FieldUnit.MASS: ["g", "mg", "ug"],
    FieldUnit.MASS_MOLECULE: ["dalton", "kilo_dalton"],
    FieldUnit.MOLECULAR_WEIGHT: ["g_mol"],
    FieldUnit.PERCENTAGE: ["p"],
    FieldUnit.PRESSURE: ["atm", "pa", "torr"],
    FieldUnit.REACTION_RATE: ["mol_lmin", "mol_lsec"],
    FieldUnit.SPECIFIC_VOLUME: ["cm3_g"],
    FieldUnit.SPEED: ["cm_s", "mm_s", "um_m", "nm_m", "cm_h", "mm_h"],
    FieldUnit.SUBATOMIC_LENGTH: ["um", "nm", "pm"],
    FieldUnit.SURFACE: ["a_2", "um_2", "mm_2", "cm_2"],
    FieldUnit.TEMPERATURE: ["C", "F", "K"],
    FieldUnit.TURNOVER_NUMBER: ["1_s", "1_m"],
    FieldUnit.VISCOSITY: ["pas", "mpas"],
    FieldUnit.KINEMATIC_VISCOSITY: ["m2_s"],
    FieldUnit.VOLTAGE: ["mv", "v"],
    FieldUnit.VOLUMES: ["l", "ml", "ul", "nl"],
}

def get_unit(field_unit: FieldUnit) -> list[str]:
    """Return the list of allowed unit codes for a physical-quantity category.

    :param field_unit: The :class:`FieldUnit` whose units are requested.
    :return: The ordered list of unit-code strings for that category.
    """
    return UNITS[field_unit]
