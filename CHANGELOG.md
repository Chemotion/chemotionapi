# Changelog

The version scheme tracks the server: `401.x.y` ↔ ELN 4.0.1, `312.x.y` ↔ ELN 3.1.2,
`211.x.y` ↔ ELN 2.1.1.

## 🚨 401.0.0 — Chemotion ELN v4 only, verified against a released server

**Breaking: this release supports ELN v4 exclusively.** ELN 3.x and older are not supported and
cannot be, in any meaningful sense — v4 rewrote collections and sharing from the ground up.
**Stay on the `312.x` line for an ELN 3.1.x server.**

This is the **first release of the 4xx line**; no `400.x` was ever tagged.

**It is also the first release verified against a published ELN v4 image rather than a release
candidate.** Until 2026-11-10 the only v4 container was a rolling `next-release` tag, so earlier
work could only claim alignment "by source inspection". ComPlat now publishes immutable
per-release images, and this client is tested against `complat/chemotion:eln-4.0.1`
(digest-pinned; `/about` reports `v4.0.1-0-g84f58f4`): **81 passed, 1 skipped, 0 failed**.

**`.eln` / RO-Crate export is not in this release.**

### Removed: three device methods that never worked

Each posted to a route no Chemotion release serves, so every call raised `ConnectionError` on a
404:

| Removed | Called |
|---|---|
| `DeviceManager.get_jwt_for_device()` | `GET /api/v1/devices/remote/jwt/:id` |
| `DeviceManager.create_new_device()` | `POST /api/v1/devices/remote/create` |
| `Device.get_jwt()` | (via `get_jwt_for_device`) |

Checked against ELN 3.1.1, 3.1.2, 3.1.3, 4.0.0 and 4.0.1: the `devices/remote` namespace exists in
none of them, and appears in no version of the server's own Swagger document.

Neither could be repaired in place. There is no device-JWT route in any release. And
`POST /api/v1/devices` describes an *instrument* — `title`, `code`, `types`, `samples` — not the
device-*user* these methods took, so pointing them at it would have changed what they mean.

**Use `Admin.create_device()`** — but note its signature changed in this release, because it was
broken too:

```python
admin = instance.get_user()                         # an Admin, when logged in as one
device = admin.create_device("Device Name", "ABC")  # was (first_name, last_name, abbreviation)
```

It posted to `/api/v1/admin/group_device/create` with `rootType: 'Device'`, supplying
`first_name`/`last_name`. But `Device` has `validates :name, presence: true` — since at least ELN
3.1.2 — and that endpoint declares no `name` parameter, so Grape's `declared` dropped any attempt
to pass one. **Every call failed** with `Validation failed: Name Please enter a name`. It now
posts to `/api/v1/admin_devices`, which takes `name` and `name_abbreviation` (plus optional
`email` and `serial_number`).

`Admin.create_group()` is unaffected and still uses the group endpoint: groups carry no such
validation.

It also raises on a rejected create. The device endpoint answers a duplicate `name_abbreviation`
with **`201` and an `errors` body** — plural, where the group endpoint uses `error` — so checking
the status code, or only the singular key, reads a failure as a success.

There is no replacement for `get_jwt_for_device()` / `Device.get_jwt()`, because the server offers
none.

`DeviceManager` itself remains: `add_users_to_group()` and `add_users_to_group_by_id()` use
`PUT /api/v1/admin/group_device/update/:id`, which is real and unaffected.

`docs/Admin.rst` showed device creation and listing on `DeviceManager`; both are on `Admin`, and
the page is corrected.

### Fixed: `get_generic_by_name()` could return an element of the wrong type ([#14])

Asking for one generic type and passing the id of another returned the other element, silently:

```python
instance.get_generic_by_name("elyte", 2).klass_name   # -> "ecell"
```

The name was only checked against the list of types the server knows; it never constrained the
lookup. The server resolves a generic element **by id alone**, so the id decided what came back
and the caller got an object of the wrong type with nothing to indicate it. Both methods now
verify the element's `klass_name` and raise `ValueError` naming both types.

`get_generic_by_label()` delegated to the same path and had the same bug, as the report suspected.

Reported by **@SebaWitt** against 312.0 / ELN 3.1.2, and confirmed still present on ELN v4.0.1.

[#14]: https://github.com/Chemotion/chemotionapi/issues/14

### Transport: reads are retried, writes are not, credentials stay on your server

Prompted by a downstream consumer that had to subclass `Connection` and override a private method
to get both of these.

- **Reads are retried on a transport failure** — `GET`, `HEAD` and `OPTIONS`, three attempts by
  default with a 1s/2s backoff. Configurable per connection with
  `Connection(..., retries=n)`; `retries=1` switches it off.
- **Writes are never retried.** A `POST` or `PUT` that fails after the server received it would be
  applied twice on a second attempt, so the caller is told plainly that the write's fate is
  unknown instead of risking a duplicate. This holds whatever `retries` is set to.
- Only *transport* failures are retried — a dropped connection, or a timeout on a read. An HTTP
  error status is a considered answer from the server and is returned to the caller untouched.
  Certificate and proxy errors are not retried either: they are configuration, and fail the same
  way every time.
- A read that times out on every attempt still raises `requests.Timeout`, as before.
- **An expired login token is refused before it is sent**, with `TokenExpiredError` (a
  `PermissionError`) saying when it expired and how to log in again. The check reads the JWT's own
  `exp` claim; Chemotion tokens last six months. A `401` from the server is deliberately *not*
  treated as "log in again": the server answers `401` for ordinary permission denials too. Public
  routes are exempt, so logging in again with an expired token still set works.
- **A request whose URL is not on this connection's host is now refused.** Every request carries
  the bearer token, so a URL pointing elsewhere would hand over the session. Relative paths —
  which is everything this client issues itself — are unaffected; this guards a caller that
  passes an absolute URL, such as one the server supplied for a download or thumbnail. Host case
  and default ports are not significant: `https://ELN.example.org:443` is the same origin as
  `https://eln.example.org`.

### `Sample.gas_type` no longer makes a request or changes anything

Reading it used to load the sample's linked reaction and, when there was none, write
`GasType.OFF` back. So reading one property issued a request *and* mutated the sample — and it
raised whenever the linked reaction held a field this client could not parse, an error with no
relation to the value being read.

It still reads as `GasType.OFF` for a sample that belongs to no reaction, but decides that from
the sample's own data — a reaction object attached to it, or a reaction id in its tag — and
leaves the stored value alone. To change the stored value, use `set_gas_type()`.

### Changed: `Sample.vessel_size` is a volume in ml

It returned the reaction's stored `{'amount': 10, 'unit': 'ml'}` mapping. Both of its consumers —
the gas amount conversions and the gas-product equivalent — do arithmetic with it, so a gas
calculation on a reaction loaded from the server divided a mapping by a molecular weight. It now
returns a float in millilitres (a `'l'` unit is scaled), or `None` when there is no vessel size.
`reaction.properties['vessel_size']` is unchanged: still the `{amount, unit}` mapping.

### Aligned with ELN v4.0.1

- **LabIMotion 2.3.4** (ELN v4.0.1 ships it; v4.0.0 shipped 2.3.2). Its klass payloads carry a new
  `metadata_release` field — the metadata a release was cut with, kept apart from the klass's own
  `metadata`, which follows every save including drafts. The bundled schemas declare it.
  It is **declared, not tolerated**: the schemas keep `additionalProperties: False`, which is what
  turns an unannounced server field into a visible failure instead of silence.
- The unit and field-type tables are confirmed in sync: `units.rb` is byte-identical between gem
  2.3.0 and 2.3.4, so the hand-maintained mirror needed no change (65 unit types).
- Routes removed in v4.0.1 — `device_api.rb`, `devices_analysis_api.rb`, `icon_nmr_api.rb` and five
  `chemspectra` endpoints — are **not called by this client**, verified rather than assumed.
- Server fields added in v4.0.1 (`attachment.root_id`, `reaction_sbmm_material.parent_id`) are read
  leniently and need no change here.

### Version gate

- `Instance.test_connection()` now refuses any server whose major version is not 4, raising
  `UnsupportedServerVersion` and naming both the detected version and the release line to use
  instead. The check reads `/about`, which is unauthenticated, so it fires **before** credentials
  are sent.
- `login()` and `login_token()` apply the same check, so `Instance(url).login(...)` refuses an
  unsupported server before sending the password. The result is cached per connection; after
  `test_connection()` it costs no further request.
- Version parsing no longer degrades silently. It previously fell back to the literal string
  `'TEST'`, which then appeared in every built-in element's JSON-LD `@type` IRI with no error.
- Built-in `@type` IRIs now carry `major.minor` (`chemotion:type/sample/4.0`). Deployments track
  dated release candidates, so a patch-level segment made an unchanged element's semantic type
  churn on every server rebuild.

### Collections and sharing (the bulk of the v4 delta)

- **Elements shared with you below the full detail level now load.** The server sends them with
  `is_restricted: true` and the string `'***'` in place of each withheld field — numbers and
  booleans included — and the client used to fail parsing them, so a recipient could not even list
  the collection's samples. Withheld fields now read as `chemotion_api.utils.withheld.WITHHELD`, a
  sentinel that is neither `None` nor a number: test for it with `value is WITHHELD`; using it as a
  number (or adding, multiplying, comparing it) raises `WithheldValueError`, a `PermissionError`.
  It is a `str` whose text is `'***'`, the server's own mask, so `json_data` still serialises
  exactly as the server sent it (`json.dumps`, `str()`, f-strings). Consequently
  `WITHHELD == '***'` is true and `isinstance(WITHHELD, str)` too — check identity, not equality. `element.is_restricted` says whether this applies, and `save()` on such an
  element raises `PermissionError`, since it would write placeholders over the real values.

- `GET /collections/roots.json` is gone — it now answers **400 `id is invalid`**, because v4 routes
  it to `/collections/:id` whose id pattern rejects `"roots.json"`. Replaced by
  `GET /api/v1/collections/`, which returns `{own, shared_with_me}` as flat lists; the tree is
  rebuilt from each entry's `ancestry` materialized path.
- `PATCH /collections` (whole tree + `deleted_ids`, now 405) is split into per-collection
  `POST`/`DELETE` plus `PUT /collections/bulk_update_own_collections`.
- The entire `/syncCollections` namespace is removed (a genuine 404). Collections shared with you
  arrive in `shared_with_me` from the same listing, so no extra request is made.
- Sharing moves to `/api/v1/collection_shares`. `user_ids` is now a flat list of integers (it was a
  list of `{value: …}` hashes), and the create endpoint's per-type detail levels grew from five to
  nine. Only one of the nine is a *rename* — `research_plan_detail_level` → `researchplan_detail_level`;
  `celllinesample` and `sequencebasedmacromoleculesample` are newly exposed (they already carried
  those spellings in the old `sync_collections_users` table).
- **`SyncPermission` is replaced by `CollectionSharePermission`, and the same integer now grants a
  different permission.** The ladder still runs 0-5 — nothing was renumbered — but the capabilities
  were **reassigned to different levels**: share administration moved from 2 to 4
  (`ManageShares`), and adding/importing elements moved from 4 to 2 (`AddElements`). Level 3 stayed
  put (`Delete` → `RemoveElements`). Port call sites **by name, not by number**.
- `PUT /collections/elements` (the single-call "move elements between collections" verb) was removed
  server-side. The replacement is the `POST` / `DELETE /api/v1/collection_elements` pair — i.e.
  add-then-remove, as two calls. **This client does not wrap either yet**: it has no
  move-elements API at all, so use the endpoints directly.

### LabIMotion 2.3

- The bundled validation schemas accept LabIMotion 2.3 klass payloads: all 49 generic klasses on the
  reference instance validate, where previously none did. New optional keys (`metadata`,
  `placeholder`, `ontology`, `hasOwnRow`, `condition`, `desc`, `released_at`, `_checksum`, `is_new`),
  `eln.current_revision` corrected from `number` to a string, and `cols: 1` accepted.
- Layer-key and option-set-name regexes were dropped: real templates use names they rejected
  (trailing digits, spaces). Requirements were relaxed only where the server genuinely omits a
  field — audited against every klass rather than loosened wholesale.

### LabIMotion: surviving klasses the client does not fully understand

- **One unparseable klass no longer takes the whole generic API down.** `load_all()` skips it with a
  warning naming it; before, every accessor (`get_element`/`get_segment`/`get_dataset`) routed
  through it and raised — so a single legacy klass made `generic_manager()` return nothing usable,
  including for klasses that parse perfectly. On a real instance this was 5 of 29 klasses failing
  and taking the other 24 with them.
- **Parsing a server payload no longer inherits user-assignment strictness.** `BaseField._parse_json`
  assigns through the property setters, which validate — right for user code, wrong for parsing, and
  it made values the server is perfectly happy with unreadable here. A rejected value is now kept
  verbatim and reported once. This is also what makes the unit-table leniency below actually work on
  the real parse path.
- `FieldType` gains `select-multi` (which the server emits but the gem deliberately does not declare)
  plus `date`, `wf-next`, `sys-reaction`, `drag`, `drag_reaction`. Unmodelled types are kept opaque
  and round-trippable rather than fatal.
- The unit table is re-synced with the gem: it was 25 of 65 unit types behind, so a klass using
  `kg`, `kWh`, `mpa`, or a `mass_flow` field raised on load. `scripts/sync_labimotion_units.py`
  regenerates or checks it from rubygems; a `.gem` is a plain tar, so this needs no Ruby toolchain.
- Five real failing klasses are committed as fixtures, because the seeded test stack's klasses are
  too clean to reproduce any of this — the integration suite stayed green over a dead feature area.

### User labels (helpdesk #501526)

- `Instance.get_user_labels()` returns the id-to-title map that reading `user_labels` off an element
  never provided, and `AbstractElement.user_labels_resolved` turns an element's bare ids into
  titles. The label list is fetched **once per connection**, so resolving across 500 samples is one
  request; the cache is dropped on every bearer-token change, since serving one user's private
  labels to another after a re-login would be a cross-user leak rather than mere staleness.
- A label owned by another user resolves to a placeholder carrying only the id — never an error.
- Write support (`save_label`, `bulk`) is deliberately absent: `save_label` has no ownership check
  server-side, so wrapping it would ship a method capable of hijacking another user's label.

### Caught up with ELN v4.0.0

Two things were **broken against the released server** and are fixed:

- **Groups.** `POST /groups/create` and `PUT /groups/upd/:id` no longer exist; the endpoints moved
  into a new `group_api.rb` with flat params and REST sub-resources. `Person.create_group()` and
  `Group.add_users()` are retargeted, and the previously unwrapped operations are now available:
  `Group.remove_users()`, `promote_admin()`, `demote_admin()`, `delete()`, and
  `Person.get_groups()`. Failures map to `PermissionError` (401) and `ValueError` (404/422)
  instead of a blanket `ConnectionError`.
- **Wellplate dimensions.** v4 removed `width`/`height` from the ordinary wellplate `PUT`, so
  assigning them and calling `save()` was a **silent no-op**. Use the new
  `Wellplate.resize(width, height)`. Growing always works; shrinking is refused when a well that
  would fall outside the new grid still holds data, and the server names the blocking positions.

New surface:

- **Every built-in element type validates its properties.** Wellplates, research plans, screens and
  device descriptions now have pydantic models, as samples and reactions did: payloads are
  validated on load, and each `properties[...] = …` write is validated for that field alone.
- **Rich-text helpers.** Reaction `description`/`observation` and wellplate/screen `description`
  are Quill deltas, the ELN editor's format. New public `chemotion_api.quill_to_text()` flattens
  one to text and `chemotion_api.text_to_quill()` builds one from text (the shape the ELN creates
  itself). Writing these properties accepts a plain string (stored via `text_to_quill`) or a
  well-formed delta, formatting included; anything else now raises `ValueError` at assignment
  rather than at save.

- **Screens.** `Collection.get_screens()` / `new_screen()`, `Instance.get_screen()`. The linked
  wellplates and research plans are id lists (`wellplate_ids`, `research_plan_ids`) that a save
  sends as the new links; `wellplates` / `research_plans` load them.
- **Cell lines.** `Collection.get_cell_lines()` / `new_cell_line(material_name, source)`,
  `Instance.get_cell_line()`. The sample's own fields are in `properties`; the cell line itself —
  organism, tissue, growth medium and the rest, shared by every sample of it — is `material`.
  Every save sends the full material, so a sample-only edit never re-links it. The server ignores
  changes to a material someone else created while reporting success; the client checks and
  raises `PermissionError` instead.
- **Moving elements between collections** now covers wellplates, screens, device descriptions,
  cell lines, SBMM samples and generic elements, each verified against ELN v4.0.1.
- Saving an element no longer sends an empty attachment-upload request when no file is queued.
- **Loading a reaction and saving it no longer clears its reference material.** Each material
  fetched its own sample record, which lacks the fields of its link to the reaction (reference,
  equivalent, coefficient, position), and the save wrote those back as empty. Materials of a loaded
  reaction now keep the reaction's complete data.
- **A variation created through the client is fully editable in the ELN.** Starting materials and
  reactants get the `concentration` entry ELN v4 expects; without it the web UI showed that
  concentration as not editable.
- **SBMM samples** (sequence-based macromolecules). `Collection.get_sbmm_samples()` /
  `new_sbmm_sample(uniprot='P69905')`, `Instance.get_sbmm_sample()`. Quantities are
  `{'value', 'unit'}` pairs in `properties`; the protein is readable as `macromolecule`.
  Limitations: a new sample's protein is chosen by UniProt accession only, and a sample's protein
  is read-only. If these affect you, please open an issue.
- **Device descriptions.** `Collection.get_device_descriptions()` lists the v4
  `device_description` element; a `DeviceDescription` reads and saves its fields through
  `properties` (fields it does not model survive a save) and exposes its ontology annotations as
  `ontology_terms()`. Previously the type fell through to the generic-element endpoint and listed
  as empty. The built-in types still not modelled (`cell_line`, `screen`,
  `sequence_based_macromolecule_sample`) raise a `TypeError` naming the type.

- **`Collection.assign_elements()` / `remove_elements()` / `move_elements()`** — put an element in
  another collection, take it out, or both. `move_elements()` is **not atomic**: v4 has no move
  endpoint, so it adds and then removes, and returns the ids of anything left in both. A sample
  belonging to a reaction or wellplate still in the collection cannot be removed alone — v4
  reports that as **200 with `locked_sample_ids`**, a 2xx that is not success. Scoped to samples,
  reactions and research plans.
- **`Collection.update_share()`** — edit one share, and the only route accepting
  `include_new_subcollections`, which cascades into sub-collections *not previously shared*. That
  grants access rather than adjusting it, so it is off by default and refused without
  `apply_to_subcollections`. Note `share()` now **sends mail**: v4 added a share notifier.
- **`element.can_update`** and **`attachment.previewable`** — read-only server hints. `None` means
  the server did not say, which is not `False`.
- **`reaction.properties['concentration_mode']`** — replaces the `use_reaction_volume` boolean,
  whose two values could not express `combined`.
- **`sample.molecule.molecular_weight`** — molecule fields are readable as attributes.

Fixes to existing behaviour:

- `create_molecule_by_smiles()` no longer defaults `density` to `0.0` and write it back, which
  silently replaced the server's real density for every caller that omitted one. An unresolvable
  SMILES now raises instead of producing an empty molecule that fails later with a 500.
- Products can be expressed in **mol** (gas products excepted — their amount is derived).
- `append_no_split()` now binds the sample to the reaction (role, position, amount) as the
  splitting path does; it previously added a detached sample and saved it that way.
- A missing reference amount yields `equivalent = None` instead of raising out of a getter, and a
  failed equivalent update is logged rather than silently swallowed.
- Unknown solvent names suggest near matches.
- `reaction.properties['vessel_size'] = 200` (or `'200'`) sets the amount and keeps the unit. It
  used to store the bare number, which the server does not accept in place of `{amount, unit}`.
- Joining collection paths no longer drops the segments after an absolute one:
  `'a', '/b', 'c', 'd'` now gives `/b/c/d`.
- Richer request errors (`ChemotionRequestError`, `ChemotionServerError`) carry the status, method,
  URL and a readable snippet instead of an entire HTML error page. They also subclass the builtin
  `ConnectionError`, so existing `except ConnectionError` handlers keep working.

This release depends only on `requests`, `python-dateutil`, `python-magic`, `click`, `jinja2`,
`pyyaml`, `jsonschema` and `pydantic`. It does not pull in an RDF stack.

