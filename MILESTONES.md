# Milestones and work packages: closing the web UI feature gap

This plans the features listed in [`MISSING_FEATURES.md`](MISSING_FEATURES.md). Section numbers
there are given as **(MF §n)**. The plan targets the 400.x line (ELN v4). Each milestone is meant
to ship as one minor release (400.1.0, 400.2.0, …) and leaves the client releasable when it's done.

**Sizes** are relative, not dates: **S** a few days, **M** about a week, **L** two weeks or more,
for one developer with the test stack running.

## Conventions every work package follows

These come from how the client is built now, so new code looks like the existing code.

- **API shape.** Element types get a class under `chemotion_api/elements/`, an empty-element
  template in `elements/empty_elements/<type>.json`, `Instance.get_<type>(id)` and
  `Collection.new_<type>()` / `get_<type>s()`. Non-element features hang off `Instance`, a
  manager object (like `generic_manager()`, `inbox`) or the element they belong to.
- **Captured payloads, not hand-written ones.** Unit tests validate against JSON captured from a
  real server (see `tests/unit/data/segment_klass_labimotion_2_3_4.json`). Strict schemas
  (`additionalProperties: False`) need these, or the next server release breaks validation again.
- **Integration tests on the seeded stack.** Every WP adds `@pytest.mark.integration` tests. If a
  WP needs data the seed lacks (e.g. a screen, a cell line), it extends `tests/data/test.sql` with
  fictional data and re-dumps it at the pinned stack version.
- **Version gating.** Features that exist only on newer servers (ELN `main` after v4.0.0) check the
  server version through `SchemaManager` and raise a clear error on older servers instead of an
  HTTP 404/500.
- **Test against both servers.** Run the pinned v4 image from `images.env` and a p2d build of ELN
  `main` (`CHEMOTION_ELN_IMAGE=chemotion-eln-p2d:<ref> CHEMOTION_STACK_SUFFIX=p2d`), so a change
  that only works on one of them is caught before release.
- **Definition of done.** Offline and integration suites green on both servers. Public methods
  carry docstrings. The feature's row in `MISSING_FEATURES.md` is updated or removed.

---

## M0: Foundations (S–M)

Groundwork that makes the later milestones cheaper. No user-visible features except deletion.

| WP | Title | Scope | Size | Depends on |
|---|---|---|---|---|
| **M0.1** | Element-type registry | Replace the `if/elif` chain in `ElementSet._get_element_class` (and the matching ones for URLs and response keys) with a registry, so a new element type is one class plus one registration. Unknown types raise a typed error naming the type. | S | – |
| **M0.2** | Payload capture tooling | A small script (`tests/tools/capture_payload.py`) that logs into the test stack and stores an endpoint's JSON as a unit-test fixture, scrubbed of timestamps and ids where needed. | S | – |
| **M0.3** | p2d test stack as a recipe | `just stack-p2d <ref>`: shallow clone, build `Dockerfile.p2d`, run the suite with `COMPOSE_PROJECT_NAME`/`CHEMOTION_STACK_SUFFIX=p2d`. Document the ~45 min first build and the ports it shares with the default stack. | S | compose project-name fix (`bbfccbb`) merged |
| **M0.4** | Element deletion (MF §2) | `AbstractElement.delete()` and `Collection.delete_elements(*elements)`, via `DELETE /api/v1/ui_state` (the UI's route) or the per-type `DELETE` routes, whichever v4 supports for all types. Deletion is irreversible, so it takes the element objects explicitly and never "everything in a collection". | M | M0.1 |

**Exit:** new element types need one class and one registration; tests can delete what they create.

## M1: Core element gaps (M–L)

The basic per-element features the UI has on every detail page.

| WP | Title | Endpoints | Size | Depends on |
|---|---|---|---|---|
| **M1.1** | Screens (MF §1) | `screens` (CRUD), wellplate membership, research-plan links | M | M0.1 |
| **M1.2** | Find by short label (MF §2) | `samples/findByShortLabel`, `reactions/findByShortLabel` → `Instance.find_sample(short_label)` etc. | S | – |
| **M1.3** | Comments (MF §2) | `comments` (list / add / resolve / delete) on elements and their sections | M | – |
| **M1.4** | Private notes (MF §2) | `private_notes`: read and write the current user's note on an element | S | – |
| **M1.5** | Version history and revert (MF §2) | `versions` (list changes per element), `versions/revert` | M | – |
| **M1.6** | User labels, complete (MF §2) | `user_labels/bulk`; map `user_labels` into `properties` for wellplates, research plans, screens | S | M1.1 |

**Exit:** every classic element type (sample, reaction, wellplate, screen, research plan) can be
created, read, updated, deleted, commented, versioned and labelled.

## M2: Chemistry workflows (L)

What chemists actually do in the UI beyond typing in a SMILES.

| WP | Title | Endpoints | Size | Depends on |
|---|---|---|---|---|
| **M2.1** | Molecules, complete (MF §3) | `molecules/{editor,names,save_name,delete_name,cas,svg,sf,inchikey,compute,molecular_weight,decouple}`. Create a molecule from a molfile, manage names, CAS, render SVG. | M | – |
| **M2.2** | Sample splits (MF §3) | `samples/subsamples`: `Sample.split(n)` creating server-side children linked to the parent. Keep `copy()` as it is, documented as an unlinked copy. | M | – |
| **M2.3** | Mixtures and components (MF §3) | `components`: read and edit mixture components; lift the "partially supported" note on `Sample.is_mixture` | M | – |
| **M2.4** | Structure search (MF §8) | `search` with structure (substructure / similarity, by SMILES or molfile), plus search across all element types | L | M1.1 |
| **M2.5** | Sample import (MF §3) | `samples/import` (spreadsheet / SDF), returning the created samples | M | – |
| **M2.6** | Literature (MF §4) | `literatures`, `literatures/collection`, `literatures/doi/metadata`: add / remove references with DOI lookup on samples, reactions, research plans | M | – |
| **M2.7** | Small lookups (MF §3, §4, §8) | `cas_lookup/lookup`, `reaction_svg`, `samples/batch-refresh-svg`, `suggestions` | S | M2.1 |

**Exit:** a reaction can be set up from molfiles, its samples split and referenced, and found
again by structure.

## M3: Data in and out (L)

Bulk movement of data, the main reason people script against the ELN.

| WP | Title | Endpoints | Size | Depends on |
|---|---|---|---|---|
| **M3.1** | Collection export / import (MF §6) | `collections/export`, `collections/import`: start the job, poll, download / upload the ZIP | M | – |
| **M3.2** | Reports and archives (MF §7) | `reports*`, `archives*`, `ui_state/load_report`, `report_templates` | L | – |
| **M3.3** | Inbox assignment (MF §5) | `inbox/samples`, `inbox/reactions`, `inbox/unlinked_attachments`: move inbox items onto an element's analyses | M | – |
| **M3.4** | Attachments, complete (MF §5) | `attachments/{bulk_delete,thumbnail(s),image,infer,link,files,upload_dataset_attachments}` | M | – |
| **M3.5** | Containers (MF §5) | `containers`, `containers/container`: edit analysis containers without saving the whole element | S | – |
| **M3.6** | Collection metadata and ownership (MF §6) | `collections/metadata` (DataCite), `collection_shares/take_ownership`, `research_plan_metadata` | S | – |
| **M3.7** | Wellplates and research plans, complete (MF §4) | `wellplates/{import_spreadsheet,bulk,subwellplates,by_generic_element}`, `research_plans/{linked,table_schemas,svg}` | M | – |
| **M3.8** | Text templates (MF §7) | `text_templates/*`: read and use predefined / personal templates | S | – |
| **M3.9** | Repository transmission (MF §7) | `gate/transmitting`. Needs a target repository in the test stack or a mocked one; check feasibility first. | M | M3.1 |

**Exit:** a collection can be exported, re-imported, reported on, and filled from the inbox
without the UI.

## M4: New v4 element types (L)

Each is a new element class on the M0.1 registry, with its own schema, template, seed data and tests.

| WP | Title | Endpoints | Size | Depends on |
|---|---|---|---|---|
| **M4.1** | Cell lines (MF §1) | `cell_lines*` (materials vs samples, copy, split, name list) | L | M0.1 |
| **M4.2** | Vessels (MF §1) | `vessels*` (templates, instances, bulk create, name suggestions) | M | M0.1 |
| **M4.3** | Device descriptions (MF §1) | `device_descriptions*`, sub-devices, ontologies, `attachments/device_description_analyses` | L | M0.1, M3.4 |
| **M4.4** | Sequence-based macromolecules (MF §1) | `sequence_based_macromolecules*`, `sequence_based_macromolecule_samples*`, change requests | L | M0.1 |
| **M4.5** | Chemicals and inventory (MF §1) | `chemicals*` (safety data sheets: fetch, extract, save), `inventory*` | M | – |

**Exit:** every element type the v4 UI shows can be read and written; collection shares cover all
the types in `SHARE_DETAIL_LEVEL_TYPES`.

## M5: Analyses and spectra (M–L)

Mostly server-side processing the client starts and collects.

| WP | Title | Endpoints | Size | Depends on |
|---|---|---|---|---|
| **M5.1** | Spectra (MF §5) | `attachments/{save_spectrum,regenerate_spectrum,regenerate_edited_spectrum,lcms_page}`, `chemspectra/file/{convert,combine_spectra}`, `chemspectra/spectra_layouts`. Needs the spectra service in the test stack (not in `compose.yml` today). | L | M3.4 |
| **M5.2** | Measurements (MF §5) | `measurements*`, `measurements/bulk_create_from_raw_data` | M | – |
| **M5.3** | Image annotation (MF §5) | annotation routes under `attachments/` | S | M3.4 |
| **M5.4** | NMR simulation, predictions, compute tasks (MF §5) | `simulation/nmrdb`, `prediction`, `compute_tasks*`. External services: implement against recorded responses, and integration-test only where the stack can run the service. | M | – |
| **M5.5** | Sample tasks (MF §3) | `sample_tasks` | S | – |

**Exit:** a dataset's spectra can be processed and its measurements extracted from a script.

## M6: LabIMotion completeness (M)

| WP | Title | Endpoints | Size | Depends on |
|---|---|---|---|---|
| **M6.1** | Delete klasses and revisions (MF §9) | `generic_elements/delete_klass`, `generic_elements/delete_klass_revision` | S | – |
| **M6.2** | Download / export (MF §9) | `generic_klass/download_klass`, `segments/download_klass`, `generic_elements/export` | S | – |
| **M6.3** | LabIMotion Hub (MF §9) | `generic_*/fetch_repo`, `*/create_repo_klass`, `segments/fetch_repo_generic_template*`, `labimotion_hub/element_klasses_name`. Needs Hub access from the test stack, or recorded responses. | M | – |
| **M6.4** | Split generic elements, element variations (MF §9) | `generic_elements/split`, `element_variations` | M | M2.2 (same split semantics) |
| **M6.5** | MTT requests (MF §9) | `mtt/*` | S | – |
| **M6.6** | OLS terms (MF §9) | `ols_terms/list`; admin `admin/importOlsTerms`, `admin/olsEnableDisable` | S | M7.4 |

**Exit:** a LabIMotion template's whole lifecycle (hub → klass → elements → export → delete) is
scriptable.

## M7: Account and administration (M)

| WP | Title | Endpoints | Size | Depends on |
|---|---|---|---|---|
| **M7.1** | Profile and settings (MF §10) | `profiles`, `profiles/editors/ketcher-options` | S | – |
| **M7.2** | API tokens and 2FA (MF §10) | `users/auth_token`, `users/revoke_auth_token`, `users/two_factor`; login with a 2FA code | M | – |
| **M7.3** | Short-label counters (MF §10) | `users/update_counter`, `users/reaction_short_label` | S | – |
| **M7.4** | Admin: users, complete (MF §10) | `admin/users/byname`, `admin/usersDefault`, `admin/users/restoreAccount`, `admin/group_device/delete_relation` | S | – |
| **M7.5** | Admin: devices and collectors (MF §10) | `admin_devices*` (incl. SFTP test), `admin_device_metadata`, `admin/listLocalCollector/all`, `instruments`, `devices/current_connection` | M | – |
| **M7.6** | Admin: system (MF §10) | `admin/disk`, `admin/jobs*` (incl. restart), `admin/matrix`, `admin/data_types`, `admin/info_support_links` | S | – |
| **M7.7** | SciFinder-n credentials (MF §10) | `users/scifinder` | S | – |

**Exit:** an ELN instance can be provisioned and administered from a script.

## Out of scope

Interactive browser features from MF §11: messages and notifications, calendar, third-party app
launchers, editor sessions, `ui_state` initialisation, permission-status checks and noVNC. They
serve a browser session, not data access. Reconsider only if someone asks for one.

## Order and dependencies

```
M0 ─┬─> M1 ──> M2 ──> M3
    └─> M4 (parallel to M1–M3 once M0.1 is in)
M3.4 ──> M4.3, M5.1, M5.3
M7.4 ──> M6.6
M5, M6, M7 are independent of each other and can run in any order after M0.
```

The order follows the priorities in `MISSING_FEATURES.md`: deletion and screens first, then the
chemistry workflows, then bulk data, then the newer element types. M4 can run alongside M1–M3 if a
second person is available, because it only depends on the registry from M0.1.

## Risks

- **Moving server.** The client already had to adapt to labimotion 2.3.4. Each milestone should
  start by running the suite against a fresh p2d build of ELN `main` (M0.3), so drift shows up at
  the start of the work rather than at release.
- **Services missing from the test stack.** Spectra, NMR simulation, predictions, the LabIMotion
  Hub and repository transmission need services `compose.yml` doesn't run. Decide per WP whether
  to add the service or test against recorded responses; that decision is part of the WP.
- **Seed growth.** M1, M4 and M5 extend `tests/data/test.sql`. Re-dump it at the pinned version,
  and keep all data fictional (see `test_seed_credentials.py`).
- **Irreversible operations.** Deletion (M0.4), klass deletion (M6.1), ownership transfer (M3.6)
  and job restarts (M7.6) need explicit arguments and no "delete everything" default, in line
  with the existing `unshare()` change that refuses an empty user list.
