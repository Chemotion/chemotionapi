---
name: chemotion-api
description: How to read and write data in a Chemotion ELN (electronic lab notebook) with the chemotion_api Python package - samples, reactions, research plans, wellplates, generic (LabIMotion) elements, collections, segments, analyses/datasets, attachments, reaction variations and search. Use this skill whenever code imports chemotion_api, whenever a task involves a Chemotion instance (creating or editing samples or reactions, setting amounts or equivalents, uploading measurement files, filling segment fields, sharing collections), or when the user mentions Chemotion, ChemAssistent or an ELN at KIT - even if they don't name the package.
---

# chemotion_api cheat sheet

`chemotion_api` wraps the REST API of a Chemotion ELN. Objects are edited locally and only reach the
server on `save()`. Everything you change through it is changed in a real lab notebook used by real
people, so read before you write, change only what the task asks for, and confirm with the user before
bulk edits or deletions. If a test instance exists, try risky operations there first.

For full method signatures and all property keys, read `references/api.md`.

## Connect

```python
from chemotion_api import Instance

instance = Instance('https://eln.example.org').test_connection().login('ABC', 'password')
# test_connection() raises ConnectionError, login() raises PermissionError
# instance.token is the JWT; Instance(url).login_token(jwt) reuses it
```

## Find things

```python
root = instance.get_root_collection()            # the 'All' collection tree
col = root.get_collection('/Projects/Team One')  # raises ModuleNotFoundError if missing
col = root.get_or_create_collection('/Projects/Team One/P 123')  # creates + saves the last level only
sub = col.get_collection('P 123')                # relative to col; './' and '..' do NOT work
for c in root.walk():                            # every collection in the tree, parent before children
    print(c.label, c.get_path())                 # root.sync_root.walk() for shared ones; max_depth=1 = children only
# c.name, c.get_name() and c.get_label() are read-only aliases of c.label

sample = instance.get_sample(12)                 # also get_reaction / get_wellplate / get_research_plan
elem = instance.get_generic_by_label('Device', 3)   # generic element by label (or get_generic_by_name)

for s in col.get_samples(per_page=50):           # get_reactions, get_wellplates, get_research_plans,
    print(s.id, s.short_label, s.name)           # get_generics_by_label(label), get_generics_by_name(name)
```

Listing and search results are partial. `id`, `name`, `short_label` and `json_data` come from the
listing; the first access to `properties`, `segments`, `analyses`, `attachments` (or `molecule`, `wells`,
`workflow`) loads the full element - one request each. So iterate cheaply over labels, and expect a
request per element once you touch data.

Search (samples and reactions):

```python
from chemotion_api.search.utils import EnumMatch, EnumConnector
hits = (instance.search_sample()
        .add_search_condition(EnumMatch.LIKE, EnumConnector.OR, name='Ethanol', cas='64-17-5')
        .find_max(20).request())
# search_reaction() fields: name, short_label, status, conditions, reaction_type, temperature_in_c,
# duration_in_sec, private_note
```

## Create things

All `new_*` methods return an unsaved object; nothing exists on the server until `save()`.
Elements cannot be created in the root collection ('All'): `root` has no `new_*` methods
(AttributeError). Create them in a real collection, e.g. `root.get_or_create_collection('My data')`.

```python
s = col.new_sample_smiles('CCO')         # molecule from SMILES (server-side lookup)
solv = col.new_solvent('CDCl3')          # name from instance.get_solvent_list()
r = col.new_reaction(); rp = col.new_research_plan(); wp = col.new_wellplate()
g = col.new_generic_by_label('Device')   # or new_generic(type_name)
s.save()                                 # s.id is an int afterwards (a UUID string before)
```

Setting a molecule (`new_sample_smiles`, `s.molecule = ...`) copies its density (or a `molarity` set on the
`Molecule`) to the sample if the sample has neither a density nor a molarity yet.

## Edit and save

`element.properties` is the main tab. Assign keys; then `save()`. `save(load_after_save=True)` reloads
from the server, which you need before reading back attachments or ids of new sub-objects.

### Samples

```python
from chemotion_api.elements.utils import QuantityUnit

s.properties['external_label'] = 'EtOH batch 3'
s.properties['description'] = 'Stored at 4 °C'
s.properties['purity'] = 0.98            # fraction, 0 < purity <= 1 (not percent)
s.properties['density'] = 0.789          # g/ml; molarity is properties['molarity']['value']
s.set_amount(2.5, QuantityUnit.Gram)     # preferred way to set an amount
print(s.gram, s.mol, s.liter)            # converted amount (needs molecular weight / density / molarity)
s.save()
```

- A sample has `target_amount` (planned/used) and `real_amount` (obtained). `set_amount` writes
  `real_amount` for reaction products and `target_amount` otherwise, and clears the other one.
- Units: `QuantityUnit.Gram` ('g'), `Mole` ('mol'), `Liter` ('l'), `Equivalent` (relative to the reaction's
  reference material; starting materials and reactants only). `s.allowed_quantity_units()` lists what is
  valid for this sample. With no unit given and none stored, the first allowed unit is used.
- `s.molecule` is a dict-like `Molecule` (`molecular_weight`, `sum_formular`, `cano_smiles`, `inchikey`, ...).
- `s.split()` and `s.copy()` save the original first, then return an unsaved new sample.

### Reactions

```python
r = instance.get_reaction(5)
r.starting_materials.append(instance.get_sample(12))   # appends a SPLIT (saves the original first)
r.reactants.append(instance.get_sample(13))            # split, short label 'reactant'
r.products.append(instance.get_sample(14))             # appends a COPY
r.solvents.append(col.new_solvent('Toluene'))          # solvents are added as they are
# r.starting_materials.append_no_split(sample) avoids splitting and pre-saving

r.reference_sample = r.starting_materials[0]   # equivalents and yields are relative to it
r.reactants[0].set_amount(1.5, QuantityUnit.Equivalent)
r.properties['temperature'].add_time_point(0, 30, 0, 80)   # h, min, s, value in valueUnit (°C)
r.properties['status'] = 'Running'      # '', Planned, Running, Done, Analyses Pending, Successful, Not Successful
r.properties['purification'] = ['TLC', 'Filtration']   # unknown values are dropped silently
r.properties['description'] = 'Plain text is converted to Quill.js'
r.properties['vessel_size'] = {'amount': 50, 'unit': 'ml'}
r.save()
```

The material lists are also `r.properties['starting_materials']` etc. Unknown status values are ignored
on save, so check spelling.

### Reaction variations (Chemotion >= 3.1)

```python
v = r.variations.add_new()                         # starts with the reaction's current amounts
v.properties['temperature']['value'] = 60          # {'value', 'unit': '°C'}; duration unit 'Second(s)'
v.notes = 'run 2'
v.starting_materials[0].set_quantity(2, QuantityUnit.Gram)
v.reactants[0].set_equivalent(1.5)                 # not for the reference material
v.products[0].set_yield(85)                        # percent
v.solvents[0].set_quantity(0.01, QuantityUnit.Liter)
v.segments['Electrochemistry']['Cell']['Electrode type'] = 'disk'
v.link_analyses(r.analyses.by_name('HPLC 2'))      # analysis must already be saved
r.save()
r.variations.remove(r.variations[-1]); r.save()
```

Mixtures (`sample.is_mixture`) cannot be quantified in variations (NotImplementedError).

### Research plans

```python
rp.add_richtext('Plain text')
rt = rp.add_richtext(); rt.add_text('Title\n', header=rt.HeaderType.H1).add_text('bold', bold=True)
t = rp.add_table(); a, b = t.add_columns('Name', 'Yield'); t.add_row('Run 1', **{b: 85})
rp.add_image('./setup.png')        # uploaded on save
rp.save()
# rp.body: list of entries; RichText / Table objects, sample/reaction entries hold Sample/Reaction objects
```

### Wellplates

`wp.wells[col][row]` with col 0-11 and row 'A'-'H'; assigning a sample stores a split of it.
Caution: parsing a wellplate currently splits (and saves) every well sample, so avoid loading and
re-saving wellplates in bulk until that is fixed.

### Generic elements (LabIMotion)

```python
g = instance.get_generic_by_label('Device', 3)
g.properties['General']['Serial number'] = 'X-12'   # properties[layer label][field label]
g.label, g.klass_name, g.klass_version          # 'Device', 'dev', '1.0' (the template)
opt = next(o for o in g.wf_next_options() if o['wf_idx'] == 0 and o['layer_label'] == 'Calibration')
key = g.wf_next(**opt)                          # returns the new layer's key in g.properties
g.properties[key]['Result'] = 'ok'
g.wf_layer(0, 'Calibration')['Result'] = 'ok'   # same layer, addressed by workflow and label/key
g.wf_add_layer('Calibration')  # add a template layer directly (returns its properties key)
g.save()
```

A layer used twice gets a suffix from its layer key (`three.1` -> `properties['Nr 3.1']`), stable across
reloads; `g.wf_workflows()` lists each workflow's layers with `key`, `label` and `properties_key`.
Templates: `instance.generic_manager().get_element('dev', version='1.0')` (also `label=`; reloads every call).
New type: `gm.create_new_element('Micro Biology', 'bug', prefix='MB')` returns a released, active klass; add
`k.properties.add_new_layer(...).add_field(FieldType.TEXT, 'Strain')`, then `k.save(SaveActionType.MINOR)` (see api.md §10).

## Segments (extra tabs, all element types)

`element.segments[segment][layer][field]` using the labels shown in Chemotion (duplicates get `.1`, `.2`).
`element.segments.available()` lists the generic segments of the element type.

```python
cell = s.segments.get('Electrochemistry')['Cell']   # .get() ADDS a missing segment;
                                                     # s.segments['X'] is None if not added yet
s.segments.field_type('Electrochemistry', 'Cell', 'Electrode type')   # 'select'
s.segments.options('Electrochemistry', 'Cell', 'Electrode type')      # [{'key', 'label'}]
s.segments.units('Electrochemistry', 'Cell', 'Temperature')           # ['C', 'F', 'K']
cell['Electrode type'] = 'disk'                    # select: key or label (stored as key)
cell['Temperature'] = {'value': 25, 'unit': 'C'}   # system-defined; a bare number gets the default unit
cell['Cycles'] = 3                                 # integer
s.save()                                           # invalid changed values raise ValueError here
```

`segments['Properties']` and `segments['Analyses']` are the same objects as `properties` / `analyses`.

## Analyses, datasets, attachments

```python
ana = s.analyses.add_analyses('NMR')            # name; dict keys: name, description, kind, status, ...
ana['description'] = '1H NMR in CDCl3'
ds = ana.add_dataset('./nmr.zip')               # uploaded on save; metadata filled by a converter profile
s.save()

for ana in s.analyses:
    for ds in ana.datasets:                     # ATTRIBUTE, not ana['datasets']
        print(ds.name, ds.id)                   # dataset dict = metadata only; name/id are attributes
# Analyses and Attachment keys work as attributes too: ana.name == ana['name'], att.filename
        for att in ds.attachments or []:
            att.save_file('./out')

s.attachments.add_file('./report.pdf')          # element attachments
s.save(load_after_save=True)                    # reload, otherwise the new file can't be found
s.attachments.load_attachment(filename='report.pdf').save_file('./out')   # basename, not path
```

`s.attachments` can be None for elements that have no attachment container (e.g. some generic ones).
Converter profiles: `pm = instance.get_profile_manager(); pm.profiles` (property), `pm.get_profile(id)`,
`pm.new_profile_from_file(path).save()`, `profile.delete()`.

## Collections and sharing

Collection tree changes (`add_collection`, `move`, `delete`) are local until `root.save()`
(`get_or_create_collection` saves itself). Shared-with-me collections are under `root.sync_root` and
cannot be moved, deleted or extended.

```python
from chemotion_api.collection import SyncPermission
users = instance.find_user_by_name('Smith')        # top 3 matches
col.share(SyncPermission.Read, *users)              # sent immediately
```

Moving elements between collections is sent immediately (no `root.save()`):

```python
src.move_elements(dest, sample, reaction)   # not from root ('All'): use assign_elements there
root.assign_elements(dest, sample)          # sample is now in both; same element, not a copy
dest.remove_elements(sample)                # stays in 'All'; nothing is deleted
```

## Show the user

`element.open()` opens the saved element in the browser (the user must be logged in there);
`element.url()` returns the link - put it in your answer so the user can check the result.

## Pitfalls checklist

- Nothing is persisted without `save()`; check `element.id` is an int afterwards.
- Purity is a fraction (0-1), yields in variations are percent, equivalents are plain factors.
- Appending to starting materials/reactants/products saves the source sample and creates a new sample.
  Use `append_no_split` if you must not create splits.
- Segment and property names are the human-readable labels, case-sensitive.
- `ElementSet` (listings) cannot be indexed negatively; with an IRI filter it can only be iterated.
- `ValueError` from `save()` usually means a segment value does not fit its field; the message names the field.
- `requests.exceptions.RequestException` with `401` means the element is not visible to this user.
