# chemotion_api reference

Signatures of the public API (generated from the code, internal helpers omitted) plus the property keys of
each element type. Read the section you need; SKILL.md has the workflows.

## Contents

1. Instance
2. Collections
3. ElementSet (listings)
4. Common element API
5. Sample (+ property keys)
6. Reaction (+ property keys), MaterialList, Temperature
7. Variations
8. Research plan, Table, RichText
9. Wellplate
10. Generic elements
11. Segments
12. Analyses, Dataset, Attachments
13. Converter profiles
14. Search
15. Enums and units
16. Exceptions

## 1. Instance (`from chemotion_api import Instance`)

```
Instance(host_url: str | Connection, verify_ssl: bool = True)
  .test_connection() -> Instance              # ConnectionError if the server is not reachable
  .login(user, password) -> Instance          # user = name abbreviation or e-mail; PermissionError
  .login_token(jwt_token) -> Instance         # token not checked until the next request
  .token / .host_url                          # properties
  .get_user() -> Person | Admin | Group | Device
  .find_user_by_name(name) -> list[Person]    # top 3 matches
  .get_root_collection(reload=True) -> RootCollection
  .get_collection_by_id(collection_id) -> Collection
  .get_collection_of_element(element) -> Collection
  .get_sample(id) / .get_reaction(id) / .get_wellplate(id) / .get_research_plan(id)
  .get_generic_by_name(name, id) / .get_generic_by_label(label, id)   # ValueError for unknown type
  .get_json_ld_id(element.json_ld['@id']) -> element
  .get_all_types() -> list[str]               # JSON-LD types (IRIs)
  .all_element_classes                        # dict of all element types incl. generic ones
  .search_sample() -> SampleSearcher
  .search_reaction() -> ReactionSearcher
  .molecule() -> MoleculeManager              # .create_molecule_by_smiles(smiles, density=0.0)
  .get_solvent_list() -> list[str]            # names for new_solvent / SolventList.add_new_name
  .get_profile_manager() -> ProfileManager
  .generic_manager() -> GenericManager        # LabIMotion templates (admin work)
  .inbox -> Inbox                             # .sorted_boxs, .unsorted_attachments, .upload(path)
  .device_manager -> DeviceManager
```

## 2. Collections (`chemotion_api.collection`)

Paths are unix-like label paths. Absolute paths start with `/`; others are relative to the collection the
method is called on. `.` and `..` are not supported. `case_insensitive=True` ignores case.

```
AbstractCollection (RootCollection, Collection, RootSyncCollection)
  .id / .label / .children
  .name / .get_label() / .get_name()                  # read-only aliases of .label
  .get_path() -> str
  .get_root() -> RootCollection
  .find(label=None, **attrs) -> list                  # searches this collection and descendants
  .walk(include_self=False, max_depth=None) -> Generator   # all descendants, depth-first, parent before children
  .get_collection(path, case_insensitive=False)       # ModuleNotFoundError if missing
  .get_or_create_collection(path, case_insensitive=False)   # saves immediately; parents must exist
  .get_samples(per_page=10, updated_to_date=None, updated_from_date=None, product_only=False) -> ElementSet
  .get_reactions(...) / .get_research_plans(...) / .get_wellplates(...)
  .get_generics_by_name(name, ...) / .get_generics_by_label(label, ...)
  .get_elements_of_iri(element_type_iri, ...)          # iterate only, no len()/index

Collection (owned) additionally
  .new_sample() / .new_sample_smiles(smiles) / .new_solvent(name)
  .new_reaction() / .new_research_plan() / .new_wellplate()
  .new_generic(type_name) / .new_generic_by_label(label) / .new_element_by_iri(iri)
  .add_collection(name)            # local until root.save()
  .move(dest)                      # relative to the parent; local until root.save()
  .delete()                        # local until root.save()
  .share(SyncPermission, *users_or_groups)   # sent immediately; ConnectionError on failure

RootCollection
  .save()                          # sends all tree changes and reloads
  .load_collection()               # reload; drops unsaved tree changes
  .sync_root -> RootSyncCollection # collections shared with me (read-only tree)
  .all                             # info of the 'All' collection
  .move(src, dest) / .delete(src) / .add_collection(path)

SyncPermission: Read, Write, Share, Delete, ImportElements, PassOwnership
```

## 3. ElementSet (result of get_samples etc.)

A list subclass loaded page by page (`per_page`). Iterating loads all pages. `es[i]` loads the page and the
full element; `es[:5]` returns a list; negative indices raise TypeError. Elements are partial until their
data is accessed (see SKILL.md).

```
.page (get/set) / .max_page / .iter_pages() / .next_page() / .prev_page()
.iter_elements(start_page=1)
```

## 4. Common element API (`AbstractElement`)

```
.id                    # int once saved, UUID string before (.is_new is True)
.name / .short_label / .element_type / .last_update
.json_data             # raw server JSON (partial for listing elements)
.json_ld               # {'@id': ..., '@type': ...}
.properties            # main tab, dict-like
.segments              # Segment (see 11)
.analyses              # AnalysesList (see 12)
.attachments           # Attachments or None
.load()                # reload from the server, drops local changes
.save(load_after_save=False)   # Wellplate.save() takes no argument
.url(collection_id=None) -> str
.open(collection_id=None) -> str   # opens a browser tab
```

## 5. Sample (`chemotion_api.elements.sample`)

```
.molecule -> Molecule  # dict-like: molecular_weight, exact_molecular_weight, sum_formular, cano_smiles,
                       # inchikey, inchistring, density, boiling_point, melting_point, iupac_name, ...
.set_amount(value, unit=None)          # unit: QuantityUnit or 'g'/'mol'/'l'/'Equivalent'
.get_amount() -> {'value', 'unit'}     # real_amount for products, else target_amount
.allowed_quantity_units() -> list[QuantityUnit]
.gram / .mol / .liter                  # converted amount
.equivalent / .reference / .is_mixture
.reaction / .role_in_reaction          # 'starting_materials' | 'reactants' | 'products' | 'solvents' |
                                       # 'purification_solvents' | None
.gas_type / .set_gas_type(GasType) / .allowed_gas_types()   # gas-phase reactions only
.split() / .copy()                     # save self, return unsaved new Sample
.toggle_decoupled()
.load_image() -> Response              # SVG of the structure in .content
```

Property keys (`sample.properties[...]`):

| key | type | notes |
|---|---|---|
| name, short_label | str | read-only |
| external_label, description, location, reaction_description | str | |
| target_amount, real_amount | {'value': float, 'unit': 'g'/'l'/'mol'} | prefer set_amount |
| molarity | {'value': float, 'unit': 'M'} | |
| purity | float | 0 < purity <= 1 |
| density | float | g/ml |
| boiling_point_lowerbound/upperbound, melting_point_lowerbound/upperbound | int | |
| stereo | {'abs': ..., 'rel': ...} | |
| solvent | SolventList | .add_new_name(name), .add_new_smiles(smiles); entries {label, smiles, inchikey, ratio} |
| is_top_secret, is_restricted, decoupled, waste, inventory_sample, show_label | bool | |
| reference | bool | reference material of its reaction |
| equivalent | float | setting it sets the amount from the reference |
| coefficient | int | > 0 |
| user_labels | list | |
| metrics, sum_formula | str | |
| molecular_mass | float | |
| gas_type | GasType | |
| gas_phase_data | GasPhaseObj | gas products only: time, temperature, turnover_number, part_per_million, turnover_frequency |
| position | int | position in the reaction material list |

## 6. Reaction (`chemotion_api.elements.reaction`)

```
.starting_materials / .reactants / .products / .solvents / .purification_solvents -> MaterialList
.reference_sample (get/set)       # default: first starting material or reactant
.variations -> Variations
.gas_schema (get/set bool)        # gas-phase reaction
.get_feedstock() / .get_catalyst()
.update_equivalent() / .update_amount()
.load_image() -> Response

MaterialList (list of Sample)
  .append(sample)          # starting_materials/reactants: split; products: copy; solvents: as is
  .append_no_split(sample)

Temperature (properties['temperature'], a dict)
  .add_time_point(hour, minute, second, temperature)
  keys: data [{'time': 'hh:mm:ss', 'value': '80'}], userText, valueUnit ('°C' | '°F' | 'K')
```

Property keys (`reaction.properties[...]`):

| key | type | notes |
|---|---|---|
| starting_materials, reactants, products, solvents, purification_solvents | MaterialList | |
| name, conditions, duration | str | |
| description, observation | str or Quill delta {'ops': [...]} | plain strings are converted |
| status | str | '', Planned, Running, Done, Analyses Pending, Successful, Not Successful |
| purification | list[str] | Flash-Chromatography, TLC, HPLC, Extraction, Distillation, Dialysis, Filtration, Sublimation, Crystallisation, Recrystallisation, Precipitation |
| temperature | Temperature | |
| timestamp_start, timestamp_stop | datetime | duration is computed on save |
| vessel_size | {'amount': float, 'unit': 'l'/'ml'} | |
| dangerous_products | list | |
| gaseous | bool | same as gas_schema |
| rxno, rinchi_long_key, rinchi_short_key, rinchi_web_key | str | read-only |

## 7. Variations

```
Variations (reaction.variations, list-like, sorted by id)
  .add_new() -> Variation       # amounts from the reaction materials
  .remove(variation) -> bool

Variation
  .properties   # {'temperature': {'value', 'unit': '°C'}, 'duration': {'value', 'unit': 'Second(s)'}}
  .notes        # str
  .starting_materials / .reactants / .products / .solvents -> list[SampleVariation]
  .segments     # {segment: {layer: {field: value}}}; text, integer, select, system-defined fields only
  .link_analyses(analyses) / .get_analyses()

SampleVariation
  .sample / .is_ref / .potential_units()
  .set_quantity(value, unit)    # solvents: always liter; liter needs molarity; Yield in percent
  .set_equivalent(value)        # starting materials/reactants, not the reference
  .set_yield(percent)           # products
  .get_amount() (mol) / .get_mass() (g) / .get_volume() (l) / .get_equivalent_or_yield() (fraction)
```

Variation segment values: select = option key or label; system-defined = {'value', 'unit'} or a number in
the default unit (a field without default unit cannot get a value); every variation gets the same segments.

## 8. Research plan (`chemotion_api.elements.research_plan`)

```
.body -> list            # entries with id/type/value; RichText and Table objects for text/tables
.add_richtext(text=None, at_idx=None) -> RichText
.add_table(at_idx=None) -> Table
.add_image(image_path, at_idx=None) -> dict   # png/jpg/jpeg/tiff/bmp/gif; uploaded on save

RichText.add_text(text, bold=None, underline=None, italic=None, list=None ('bullet'|'ordered'),
                  header=None (RichText.HeaderType.H1/H2/H3)) -> RichText   # lists/headers: end with '\n'
Table.add_columns(*labels) -> list[col_id]    # ids are letters 'a'..'z'
Table.add_row(*values, **{col_id: value}) -> Table
Table.set_entry(row, col_id, value) / .get_column(col_id) / .column_id_by_label(label) / len(table)
```

## 9. Wellplate

`wp.wells` is a list of 12 columns (0-11), each a mapping 'A'-'H' -> Sample | None; assigning a sample stores
a split. `wp.properties`: name, description. `wp.save()` saves and reloads.

## 10. Generic elements

```
properties[layer label][field label] = value
.wf_tree() / .wf_current_workflow() / .wf_next_options(flat=True)
.wf_next(layer_id=None, wf_idx=0, wf_id=None)   # options from wf_next_options give layer_id/wf_id
.wf_add_layer(layer_label, pos=None)
```

## 11. Segments (`element.segments`)

```
segments[name]             # None if the element doesn't have it
segments.get(name)         # adds it with template defaults
segments.field(seg, layer, field) -> SegmentField   # .type, .options(), .units(), .default_unit
segments.field_type(seg, layer, field) / .options(...) / .units(...)
```

Field values: select = option key (label accepted), system-defined = {'value', 'unit'} (bare number gets the
default unit), integer = whole number, text/others as is. Changed values are validated on save
(ValueError naming the field); unchanged server values are never rejected.

## 12. Analyses, Dataset, Attachments

```
AnalysesList (element.analyses)
  .by_name(name) / .by_id(id)          # StopIteration if missing
  .add_analyses(name='New') -> Analyses
Analyses (dict: name, description, report, status, kind, content)
  .id / .type / .datasets (list attribute) / .is_new
  .add_dataset(file_path) -> Dataset   # uploaded on save
  .dataset_by_name(name) / .preview_image() -> bytes | None
Dataset (dict = metadata set {layer: {field: value}})
  .id / .name / .description / .json_data / .attachments
  .write_zip(destination='') / .write_data_set_xlsx(destination='')   # return file path
Attachments (element.attachments; iterable, indexable)
  .add_file(path) -> dict              # uploaded on save
  .load_attachment(id=None, identifier=None, filename=None) -> Attachment   # saved files only
Attachment (dict: id, identifier, filename, ...)
  .load_file() -> bytes / .save_file(directory='.') -> path
```

## 13. Converter profiles

```
pm = instance.get_profile_manager()
pm.profiles                      # property, list[Profile], cached
pm.get_profile(id) -> Profile | None
pm.new_profile_from_file(path) -> Profile | None   # new id if it already exists; not saved
Profile: id, title, description, identifiers, tables, data, matchTables, ols
  .save() (create or update) / .delete() / .to_dict() / .to_json()
```

## 14. Search

```
instance.search_sample().add_search_condition(match, connector, name=, short_label=, external_label=,
    inventory_label=, cas=, private_note=)
instance.search_reaction().add_search_condition(match, connector, name=, short_label=, status=,
    conditions=, reaction_type=, temperature_in_c=, duration_in_sec=, private_note=)
  .in_collection(collection_id) / .find_max(n)   # default 15 results
  .request() -> ElementSet
EnumMatch: LIKE, NOT_LIKE (case insensitive), LESS_THAN, BIGGER_THAN, EXACT
EnumConnector: AND, OR   # links a condition to the ones before it
```

## 15. Enums and units (`chemotion_api.elements.utils`)

```
QuantityUnit: Liter 'l', Mole 'mol', Gram 'g', Equivalent 'Equivalent', Yield 'Yield'
GasType: OFF, GAS, CATALYST, FEEDSTOCK
```

## 16. Exceptions

| exception | typical cause |
|---|---|
| ConnectionError | server unreachable, collection/profile request failed, share failed |
| PermissionError | login failed |
| requests.exceptions.RequestException | element load/save failed; 401 = not visible to this user |
| ModuleNotFoundError | collection path does not exist |
| ValueError | invalid segment value, unit not allowed, unknown generic type/label, unsaved element in url()/open() |
| KeyError | sample has no reaction; unknown segment/field name |
| StopIteration | by_name/by_id/dataset_by_name found nothing |
| NotImplementedError | quantities of mixtures in variations |
