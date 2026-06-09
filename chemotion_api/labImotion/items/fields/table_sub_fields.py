"""Column (sub-field) types used inside LabIMotion table fields."""
from chemotion_api.labImotion.items.fields.abstract_fields import SystemDefined, Select
from chemotion_api.labImotion.items.fields.sub_fields import SubBaseField
from chemotion_api.labImotion.items.options import SubTableFieldType
from chemotion_api.labImotion.structure import StructureRegistry

class TableSubBaseField(SubBaseField):
    """Common base for table columns, adding a ``col_name`` on top of :class:`SubBaseField`."""

    _default_required_fields = ["id", "col_name", "field_type", "value"]
    required_fields: list = []

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        """Build the table column and read its column name from the raw JSON data.

        :param sr: Structure registry providing access to the surrounding element schema.
        :param layer_key: Key of the layer the parent table field belongs to.
        :param json_data: Raw JSON dictionary describing the column.
        """
        super().__init__(sr, layer_key, json_data)
        self._col_name = json_data.get("col_name", "")

    @property
    def col_name(self) -> str:
        """The display name of the table column."""
        return self._col_name
    
    @col_name.setter
    def col_name(self, value: str):
        """Set the column name.

        :raises TypeError: If ``value`` is not a string.
        """
        if not isinstance(value, str):
            raise TypeError(f"col_name {type(value)} not supported")
        self._col_name = value


class TSDragMolecule(TableSubBaseField):
    """A table column referencing a molecule, configurable in which molecule fields it displays."""

    field_type = SubTableFieldType.DRAG_MOLECULE

    @property
    def value(self) -> str:
        """The semicolon-separated list of displayed molecule attributes (defaults to ``';'``)."""
        if self._value is None or self._value == '':
            self._value = ';'
        return self._value

    @value.setter
    def value(self, value: str):
        """Set the displayed molecule attributes from a semicolon-separated string.

        Only ``inchikey``, ``smiles``, ``iupac`` and ``molecular_weight`` tokens are retained.

        :raises TypeError: If ``value`` is not a string.
        """
        if not isinstance(value, str):
            raise TypeError(f"value {type(value)} not supported")
        text_display = []
        value_split = value.split(';')
        if 'inchikey' in value_split:
            text_display.append("inchikey;")
        if 'smiles' in value_split:
            text_display.append("smiles;")
        if 'iupac' in value_split:
            text_display.append("iupac;")
        if 'molecular_weight' in value_split:
            text_display.append("molecular_weight;")
        self._value = ''.join(text_display)

    def set_sample_display(self, inchikey: bool, smiles: bool, iupac: bool, molecular_weight: bool):
        """Select which molecule attributes are displayed in the column.

        :param inchikey: Whether to display the InChIKey.
        :param smiles: Whether to display the SMILES string.
        :param iupac: Whether to display the IUPAC name.
        :param molecular_weight: Whether to display the molecular weight.
        """
        text_display = []
        if inchikey:
            text_display.append("inchikey;")
        if smiles:
            text_display.append("smiles;")
        if iupac:
            text_display.append("iupac;")
        if molecular_weight:
            text_display.append("molecular_weight;")
        self.value = ''.join(text_display)


class TSDragSample(TableSubBaseField):
    """A table column referencing a sample, configurable in which sample fields it displays."""

    field_type = SubTableFieldType.DRAG_SAMPLE

    @property
    def value(self) -> str:
        """The semicolon-separated list of displayed sample attributes (defaults to ``';'``)."""
        if self._value is None or self._value == '':
            self._value = ';'
        return self._value

    @value.setter
    def value(self, value: str):
        """Set the displayed sample attributes from a semicolon-separated string.

        Recognised tokens are ``name``, ``external_label`` and ``molecular_weight``.

        :raises TypeError: If ``value`` is not a string.
        """
        if not isinstance(value, str):
            raise TypeError(f"value {type(value)} not supported")
        text_display = []
        value_split = value.split(';')
        if 'name' in value_split:
            text_display.append("name;")
        if 'external_label' in value_split:
            text_display.append("external_label;")
        if 'molecular_weight' in value_split:
            text_display.append("molecular_weight;")
        self._value = ''.join(text_display)

    def set_sample_display(self, name: bool, external_label: bool, molecular_weight: bool):
        """Select which sample attributes are displayed in the column.

        :param name: Whether to display the sample name.
        :param external_label: Whether to display the external label.
        :param molecular_weight: Whether to display the molecular weight.
        """
        text_display = []
        if name:
            text_display.append("name;")
        if external_label:
            text_display.append("external_label;")
        if molecular_weight:
            text_display.append("molecular_weight;")
        self.value = ''.join(text_display)



class TSSelect(TableSubBaseField, Select):
    """A table column offering a choice from a predefined set of select options."""

    field_type = SubTableFieldType.SELECT
    required_fields = ['option_layers']

    def __init__(self, sr: StructureRegistry,  layer_key: str, json_data: dict):
        """Build the column and initialise its select-option support from JSON.

        :param sr: Structure registry providing access to the surrounding element schema.
        :param layer_key: Key of the layer the parent table field belongs to.
        :param json_data: Raw JSON dictionary describing the column.
        """
        super().__init__(sr, layer_key, json_data)
        Select.__init__(self, sr, json_data)


class TSSystemDefined(TableSubBaseField, SystemDefined):
    """A table column whose value/unit is constrained by a system-defined option set."""

    field_type = SubTableFieldType.SYSTEM_DEFINED
    required_fields = ['option_layers', 'value_system']

    def __init__(self, sr: StructureRegistry,  layer_key: str, json_data: dict):
        """Build the column and initialise its system-defined support from JSON.

        :param sr: Structure registry providing access to the surrounding element schema.
        :param layer_key: Key of the layer the parent table field belongs to.
        :param json_data: Raw JSON dictionary describing the column.
        """
        super().__init__(sr, layer_key, json_data)
        SystemDefined.__init__(self, json_data)


class TSText(TableSubBaseField):
    """A free-text table column."""

    field_type = SubTableFieldType.TEXT
