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
17. Collections: v4 additions (delete, split, import/export, reports, labels)
18. Element additions (comments, notes, versions, literature, analyses, chemicals, measurements)
19. More element types: Screen, CellLine, DeviceDescription, SbmmSample, vessels
20. Molecules, components and structure search
21. Inbox, attachments, annotations, spectra
22. Reports and table exports
23. LabIMotion additions (templates, hub, variations, MTT)
24. Account, profile, text templates, SciFinder-n, compute
25. Administration (`Admin`)

## 1. Instance (`from chemotion_api import Instance`)

```
Instance(host_url: str | Connection, verify_ssl: bool = True, username=None, password=None, token=None)  # username/password deprecated
  .test_connection() -> Instance              # ConnectionError if the server is not reachable
  .login(user, password) -> Instance          # DEPRECATED (FutureWarning); use login_token. PermissionError
  .login_token(jwt_token) -> Instance         # API token (chemtoken_...) or JWT; not checked until the next request
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
  .move_elements(dest, *elements)     # sent immediately; not from the root ('All') collection
  .assign_elements(dest, *elements)   # sent immediately; adds to dest too (same element, no duplicate)
  .remove_elements(*elements)         # sent immediately; element stays in 'All'
                                      # elements not in this collection are silently ignored

Collection (owned) additionally
  .new_sample() / .new_sample_smiles(smiles) / .new_solvent(name)
  .new_reaction() / .new_research_plan() / .new_wellplate()
  .new_generic(type_name) / .new_generic_by_label(label) / .new_element_by_iri(iri)
  .add_collection(name)            # local until root.save()
  .move(dest)                      # relative to the parent; local until root.save()
  .delete()                        # local until root.save()
  .share(CollectionSharePermission, *users_or_groups, detail_level=0..10)   # sent immediately
  .get_shares() / .update_share(share_id, ...) / .unshare(*users, all=False)
  .export_zip(destination) / .metadata() / .save_metadata(dict) / .take_ownership()    # see 17
  .gate_token(origin) / .register_gate(url, token) / .check_transmission(url) / .transmit(url)

RootCollection                     # no new_* methods: elements cannot be created in 'All'
  .save()                          # sends all tree changes and reloads
  .load_collection()               # reload; drops unsaved tree changes
  .sync_root -> RootSyncCollection # collections shared with me (read-only tree)
  .all                             # info of the 'All' collection
  .move(src, dest) / .delete(src) / .add_collection(path)

CollectionSharePermission: ReadElements(0), EditElements(1), AddElements(2), RemoveElements(3),
                           ManageShares(4), PassOwnership(5)   # v4 levels; use the names
```

## 3. ElementSet (result of get_samples etc.)

A list subclass loaded page by page (`per_page`). Iterating loads all pages. `es[i]` loads the page and the
full element; `es[:5]` returns a list; negative indices raise TypeError. Elements are partial until their
data is accessed (see SKILL.md). `len(es)` is the total number on the server (server max per_page: 100).
Sample listings omit samples that are only reactants or solvents of a reaction (server behavior).

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
.move_to(dest, source) / .assign_to(dest, source=root of dest) / .remove_from(collection)
```

## 5. Sample (`chemotion_api.elements.sample`)

```
.molecule -> Molecule  # dict-like: molecular_weight, exact_molecular_weight, sum_formular, cano_smiles,
                       # inchikey, inchistring, density, boiling_point, melting_point, iupac_name, ...
                       # m['molecular_weight'] or read-only m.molecular_weight
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
  .append_no_split(sample) # adds the sample itself; sets reaction, role, position, amount like append

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
properties[layer label][field label] = value   # a layer used twice: 'Nr 3.1' (suffix of its key three.1)
.label / .klass_name / .klass_version / .klass_prefix   # of the template: 'Workflow', 'wrk', '2.0', 'WRK'
.short_label                                     # set by the server on first save: '<initials>-<prefix><n>'
.layers_without_fields() -> [properties keys]    # e.g. ['Fixed'] - such layers are {} in properties
.wf_tree() / .wf_current_workflow() / .wf_next_options(flat=True)
  # option: layer_id, wf_id, wf_idx, layer_key, layer_label, source_key (+ source_layer when flat)
.wf_next(layer_id=None, wf_idx=0, wf_id=None) -> properties key   # ValueError on unknown wf / wrong layer
.wf_add_layer(layer_label, pos=None) -> properties key
.wf_workflows() -> [{'wf_id', 'wf_idx', 'layers': [{'key', 'label', 'properties_key'}]}]
.wf_layer(wf_idx | wf_id, label | key) -> the layer's fields (same object as in properties)
.field(layer, field) -> SegmentField   # template of a field: .type, .ontology, .options(), ...
```

Templates (`instance.generic_manager()`): `get_element(name=None, *, label=None, version=None, **attrs)`,
`get_segment(label=None, *, version=None, **attrs)`, `get_dataset(...)` - loaded from the server on every call;
KeyError lists the matches/available templates. The template class is `labImotion.GenericElementKlass`
(old name `labImotion.GenericElement` still works), not the element class `elements.GenericElement`.

Authoring a template (admin; `FieldType` from `labImotion.items.fields`, `SaveActionType` from `labImotion.items.options`):

```
k = gm.create_new_element(label, icon_name, description='', prefix='', name='', release=True, activate=True)
    # -> the new GenericElementKlass; release/activate make it usable right away (empty v0.1)
layer = k.properties.add_new_layer(label, key='', idx=-1)          # key generated from label; ValueError if taken
layer.add_field(FieldType.X, label, field='', idx=-1, options=None) # options=[...] only for SELECT
k.properties.add_select_option(key, values) -> key                 # shared list; link via field.option_layers = key
field.label / .required / .default                                 # stored in the template
field.ontology = 'CHMO:0000593' | term_dict | None                 # ontology term; ID looked up online (TIB TS)
layer.add_field(FieldType.TEXT, 'NMR method', ontology='CHMO:0000593')
gm.search_ontology_terms('nmr', rows=30) -> [term]                 # same search as the template designer
gm.get_ontology_term(obo_id | short_form | iri) -> term            # KeyError if unknown
    # term: {'iri', 'label', 'obo_id', 'short_form', 'ontology_prefix', 'ontology_name', 'description', 'id', 'type'}
k.klass_prefix / k.desc / k.label / k.icon_name
k.save(SaveActionType.MINOR)   # release (new elements use the latest release); DRAFT only stores
k.is_active = True / False
instance.element_manager.reload()   # drop cached types (new_generic_by_label also reloads on a miss)
```

Elements address fields by the labels of *their* template version; unknown layer/field names raise
ValueError on save. `load_all_elements()` skips invalid templates with a warning (`load_all(con, strict=True)`).

## 11. Segments (`element.segments`)

```
segments[name]             # None if the element doesn't have it
segments.available()       # labels of all generic segments for this element type
segments.get(name)         # adds it with template defaults
segments.field(seg, layer, field) -> SegmentField   # .type, .ontology, .options(), .units(), .default_unit
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
Analyses (dict: name, description, report, status, kind, content; keys readable/writable as attributes)
  .id / .type / .datasets (list attribute) / .is_new
  .add_dataset(file_path) -> Dataset   # uploaded on save
  .dataset_by_name(name) / .preview_image() -> bytes | None
Dataset (dict = metadata set {layer: {field: value}})
  .id / .name / .description / .json_data / .attachments
  .write_zip(destination='') / .write_data_set_xlsx(destination='')   # return file path
Attachments (element.attachments; iterable, indexable)
  .add_file(path) -> dict              # uploaded on save
  .load_attachment(id=None, identifier=None, filename=None) -> Attachment   # saved files only
Attachment (dict: id, identifier, filename, ...; keys readable as attributes, att.filename)
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
| chemotion_api.connection.ChemotionRequestError | subclass raised by element load/save/list; .status_code, .url, .context, .snippet |
| chemotion_api.connection.ChemotionServerError | the same for 5xx (server bug, often triggered by invalid data) |
| ModuleNotFoundError | collection path does not exist |
| ValueError | invalid segment value, unit not allowed, unknown generic type/label, unsaved element in url()/open(), SMILES the server cannot resolve ('Mg' instead of '[Mg]') |
| KeyError | sample has no reaction; unknown segment/field name |
| StopIteration | by_name/by_id/dataset_by_name found nothing |
| NotImplementedError | quantities of mixtures in variations |

## 17. Collections: v4 additions

All of these act immediately.

```
AbstractCollection
  .delete_elements(*elements, delete_subsamples=False) -> list   # the elements the server kept
  .split_samples(*samples) -> list[Sample]                       # linked subsamples <label>-<n>
  .split_wellplates(*plates) / .create_wellplates(*names)
  .split_device_descriptions(*devs) / .split_sbmm_samples(*s) / .split_generic_elements(*els)
  .import_samples(path, as_chemicals=False, wait=True, timeout=300) -> ImportResult   # .sdf .mol .csv .xlsx
  .export_elements(path, *elements, file_format='xlsx'|'sdf', columns=None) -> path | None
  .export_reaction_smiles(path, *reactions, notation='SM>R>P') -> path | None
  .references() -> {'collection'|'sample'|'reaction'|'research_plan': [Reference]}
  .get_screens() / .get_cell_lines() / .get_device_descriptions() / .get_sbmm_samples()   # ElementSet
  .get_vessels() / .new_vessel(template, **fields) / .new_vessels(template, count, base_name=None)
  .inventory_label() -> InventoryLabel | None
Collection
  .export_zip(destination, timeout=900) -> path   # the ELN's native ZIP, via a background job
  .metadata() -> dict | None / .save_metadata(dict)              # DataCite fields
  .take_ownership() -> dict                 # accept a PassOwnership share
  .gate_token(origin) / .register_gate(destination, token)
  .check_transmission(target) / .transmit(target, wait=True)     # target required (server default = public repo)
Instance
  .import_zip(path) -> list[Collection]
```

## 18. Element additions (`AbstractElement`)

```
.delete(delete_subsamples=False) -> bool    # True when the record is really gone
.comments() / .add_comment(content, section=None)
.private_note() / .set_private_note(text) / .delete_private_note()
.versions() -> list[Version]                # Version.changes, Version.revert(fields=None)
.references() / .add_reference(doi=, url=, title=, isbn=, bibtex=, litype='citedOwn')
.remove_reference(ref) / .set_reference_type(ref, litype)
.save_analyses()                            # only the analyses (PUT /containers/container)
.delete_analysis(analysis)                  # immediate, files gone
.linked_research_plans() -> [{'id', 'name'}]      # samples and reactions
Sample.get_chemical() -> Chemical                                   # .exists / .save(); .cas, .data
Sample.attach_safety_sheet(pdf, vendor_name, vendor_product, vendor_info=None, cas=None) -> Chemical
Sample.save_vendor_safety_sheet(chemical, vendor_product) -> Chemical
.measurements(hierarchy=True, source=None) -> list[Measurement]      # samples
.create_measurements([{'sample', 'description', 'value', 'unit', 'metadata'?}])   # on the source element
Sample:   .svg_path / .components() / .save_components([Component])
Reaction: .render_scheme_svg(products_only=False) / .report_docx(path) / .export_samples_excel(path)
Wellplate: .export_samples_excel(path) / .download_template(path) / .import_spreadsheet(path)
ResearchPlan: .metadata() / .save_metadata(**fields) / .upload_svg(svg, is_chemdraw=False)
```
`chemotion_api.elements.sample.Chemical`: `data` is `chemical_data[0]`; `.safety_sheets` paths.

## 19. More element types

```
Screen        col.new_screen(); .add_wellplate(p) / .remove_wellplate(p) / .add_research_plan(rp)
              .new_research_plan(collection); properties: name, collaborator, requirements,
              conditions, result, description, wellplates, research_plans
CellLine      col.new_cell_line(material_name, source); .material is the shared cell line material
              (edits check who owns it); see docs/CellLineDetails.rst
DeviceDescription  col.new_device_description(); a rejected create raises ValueError
SbmmSample    col.new_sbmm_sample(uniprot_accession); .macromolecule is read-only
vessels       VesselTemplate(name, vessel_type, material_type, volume_amount, ...).save()/.delete()/.vessels()
              Vessel(name, short_label, weight_amount, ...).save()/.delete(); UUID ids
```

## 20. Molecules, components, structure search

```
instance.molecule() -> MoleculeManager
  .create_molecule_by_molfile(molfile, decoupled=False)   # ValueError for the server's DUMMY molecule
  .get_molecule_by_inchikey(k) / .load_cas(inchikey) / .lookup_cas(cas)
  .get_names(mol_id) -> [MoleculeName] / .add_name(mol_id, name) -> MoleculeName
  .render_svg(molfile) / .load_svg(mol)
  .molecular_weight(sum_formula)
col.new_sample_molfile(molfile)
sample.components() / sample.save_components([Component.new(molecule, amount_mol=...)])
instance.search_structure().substructure(smiles_or_molfile) | .similar(s, threshold=0.7)
  .in_collection(id).find_max(n).request() -> StructureSearchResult(.samples, .reactions, .total(type))
instance.suggestions(query, element_type='all') / instance.doi_metadata(doi)
instance.find_sample_by_short_label(l) / find_reaction_by_short_label(l)
```

## 21. Inbox, attachments, annotations, spectra

```
instance.inbox.unlinked_attachments() / .search_samples(q) / .search_reactions(q)
instance.inbox.assign(attachment, sample_or_reaction, variation=None) -> dataset container
Attachment.load_image() / .load_thumbnail() / .delete() / .unlink()
Attachment.load_annotation() -> svg / .save_annotation(svg)
attachments.delete_attachments(con, atts) / load_thumbnails(con, atts) / load_files(con, atts)
instance.spectra(): .save(att, **params) / .infer(att) / .regenerate(orig, generated) /
  .regenerate_edited(edited, molfile) / .lcms_page(att, rt) / .convert(path, mass) /
  .combine(atts, front_index) / .layouts() / .nmrium_url()          # need the ChemSpectra service
```

## 22. Reports and table exports (`chemotion_api.reports`)

```
instance.report_templates() -> [ReportTemplate]
instance.create_report(*samples_and_reactions, template='standard', file_name=, description=,
    sample_settings={}, reaction_settings={}, si_reaction_settings={}, page_break=True,
    all_chemicals_in_schemes=True, image_format='png', molecule_serials={}, wait=True) -> Archive
instance.report_archives() -> [Archive]; Archive.download(path) / .refresh() / .delete()
REPORT_TYPES: standard, spectrum, supporting_information, supporting_information_std_rxn,
              rxn_list_xlsx, rxn_list_csv, rxn_list_html
```

## 23. LabIMotion additions

```
klass (GenericElementKlass / GenericSegment / GenericDataset)
  .delete(confirm=<label>) / .revisions(limit=10) / .delete_revision(rev) / .download(path)
gm = instance.generic_manager()
  .hub_templates(kind) / .import_hub_template(identifier, kind) / .submit_to_hub(...)
  .published_templates(kind) / .active_element_names(generic_only=False)
GenericElement
  .export_docx(path) / .variations() / .save_variations(rows, layout=None)
  .export_variations(path) / .import_variations(path) -> warnings
  .create_mtt_request(*wellplates) -> app link / .mtt_requests() -> [MttRequest(.update/.revoke/.delete)]
generic_element.variation_key(layer, field)   # property-cell key
instance.ols_terms(name='chmo'|'rxno'|'bao', edited=True)
```

## 24. Account, profile, templates, SciFinder-n, compute

```
instance.profile() -> Profile(.data, display flags, .structure_templates, .save(),
    .add_structure_template(content), .delete_structure_template(t))
instance.ketcher_options() / .save_ketcher_options(dict)
instance.two_factor_enabled() / .request_two_factor_change()
instance.api_tokens() / .create_api_token(otp, name=None, expires_in_days=30) / .revoke_api_token(t, otp)
instance.set_short_label_counter(type, value) / .set_reaction_short_label(prefix, count)
instance.text_templates(): .predefined_names() / .predefined(name) / .personal() /
    .create_personal(name, ops) / .update_personal(t) / .delete_personal(t) / .toolbar(type) / .set_toolbar(type, groups)
instance.scifinder_credential() / .scifinder_search(structure, search_for, structure_type)
instance.simulate_nmr(mol) / .predict_products(smiles) / .predict_reactants(smiles)
instance.compute_tasks() / .submit_compute_task(sample); ComputeTask.check() / .revoke() / .delete()
instance.sample_tasks(status) / .create_sample_task(sample, description, n); SampleTask.add_scan_result(...)
instance.set_inventory_label(prefix, name, counter, *cols) / .inventory_collections()
instance.find_safety_sheets(name, molecule=None, vendor='All') / .download_safety_sheet / .extract_safety_sheet
instance.research_plan_table_schemas() / .save_research_plan_table_schema(name, table) / .delete_...(id)
instance.instruments(kind='all')
```

## 25. Administration (`Admin`, from `instance.get_user()` of an admin account)

```
users    .find_users(name) / .update_user(u, **fields) / .delete_user(u, confirm=abbr) / .restore_user(abbr)
         .reset_password(u, password=None) / .two_factor_enable_link(u) / .disable_two_factor(u)
         .set_user_rights(u, molecule_editor=, converter_admin=, generic_elements_admin=, ...)
         .default_allocated_space() / .set_default_allocated_space(mb)
groups   .remove_users_from_group(g, *users) / .set_group_admin(g, u, admin=True) / .delete_group(g, confirm=abbr)
devices  .list_devices(name=None) / .get_device(d) / .add_device(name, abbr) / .update_device(d, **fields)
         .delete_device(d, confirm=abbr) / .remove_device_user(d, u) / .test_sftp(d, host, user)
         .local_collectors() / .device_metadata(d) / .save_device_metadata(d, **f) / .sync_device_metadata(d)
system   .disk_usage() / .jobs() / .restart_job(job) / .queue_admin_task(task) / .matrices() / .update_matrix(m, **f)
         .save_spectra_data_types(d) / .info_support_links() / .add_/update_/delete_info_support_link(...)
ontology .import_ols_terms(owl) / .set_ols_terms_enabled(owl_name, enable=(), disable=())
```

