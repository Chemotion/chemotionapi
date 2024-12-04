from chemotion_api.labImotion.items.fields.abstract_fields import SystemDefined, Select
from chemotion_api.labImotion.items.fields.sub_fields import SubBaseField
from chemotion_api.labImotion.items.options import SubTableFieldType
from chemotion_api.labImotion.structure import StructureRegistry

class TableSubBaseField(SubBaseField):
    _default_required_fields = ["id", "col_name", "field_type", "value"]
    required_fields = []

    def __init__(self, sr: StructureRegistry, layer_key: str, json_data: dict):
        super().__init__(sr, layer_key, json_data)
        self._col_name = json_data.get("col_name", "")

    @property
    def col_name(self) -> str:
        return self._col_name
    
    @col_name.setter
    def col_name(self, value: str):
        if not isinstance(value, str):
            raise TypeError(f"col_name {type(value)} not supported")
        self._col_name = value


class TSDragMolecule(TableSubBaseField):
    field_type = SubTableFieldType.DRAG_MOLECULE

    @property
    def value(self) -> str:
        if self._value is None or self._value == '':
            self._value = ';'
        return self._value

    @value.setter
    def value(self, value: str):
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
    field_type = SubTableFieldType.DRAG_SAMPLE

    @property
    def value(self) -> str:
        if self._value is None or self._value == '':
            self._value = ';'
        return self._value

    @value.setter
    def value(self, value: str):
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
        self._value = ''.join(value)

    def set_sample_display(self, name: bool, external_label: bool, molecular_weight: bool):
        text_display = []
        if name:
            text_display.append("name;")
        if external_label:
            text_display.append("external_label;")
        if molecular_weight:
            text_display.append("molecular_weight;")
        self.value = ''.join(text_display)



class TSSelect(TableSubBaseField, Select):
    field_type = SubTableFieldType.SELECT
    required_fields = ['option_layers']

    def __init__(self, sr: StructureRegistry,  layer_key: str, json_data: dict):
        super().__init__(sr, layer_key, json_data)
        Select.__init__(self, sr, json_data)


class TSSystemDefined(TableSubBaseField, SystemDefined):
    field_type = SubTableFieldType.SYSTEM_DEFINED
    required_fields = ['option_layers', 'value_system']

    def __init__(self, sr: StructureRegistry,  layer_key: str, json_data: dict):
        super().__init__(sr, layer_key, json_data)
        SystemDefined.__init__(self, json_data)


class TSText(TableSubBaseField):
    field_type = SubTableFieldType.TEXT
