# Web UI features missing from chemotion_api

This lists what the Chemotion ELN web UI can do that this client cannot, or can only partly do.

**How it was made (2026-11-07).** The UI's own request layer, `app/javascript/src/fetchers/` (66
fetchers, ~250 endpoints), was taken from ELN `main` at `a8b47c7` (reports `v4.0.0`, labimotion
2.3.4) and compared against every `/api/v1/...` path `chemotion_api` calls, then the ambiguous
matches were checked in the client source. A feature counts as missing when the client calls none
of its endpoints; "partial" means the client covers some of it. It is an endpoint-level comparison:
a feature the UI computes in the browser without a request doesn't show up here.

Status: ❌ missing · ◐ partial · ✅ done since this list was made

## 1. Element types

The client loads and creates **samples, reactions, wellplates, research plans and LabIMotion
generic elements**. `ElementSet._get_element_class` raises `TypeError` for anything else, so the
types below can be neither read nor written.

| Status | Feature | UI fetcher → endpoints |
|---|---|---|
| ❌ | **Screens** (wellplate containers, with research-plan links) | `ScreensFetcher` → `screens` |
| ❌ | **Cell lines** (materials, samples, copy, split) | `CellLinesFetcher` → `cell_lines`, `cell_lines/material`, `cell_lines/copy`, `cell_lines/split`, `cell_lines/names/all` |
| ❌ | **Vessels** (templates, instances, bulk create, name suggestions) | `VesselsFetcher` → `vessels`, `vessels/templates*`, `vessels/instances/create`, `vessels/bulk_create`, `vessels/suggest/suggest_name` |
| ❌ | **Device descriptions** (incl. sub-devices, ontologies, device analyses) | `DeviceDescriptionFetcher` → `device_descriptions*`; `attachments/device_description_analyses` |
| ❌ | **Sequence-based macromolecules** and their samples | `SequenceBasedMacromoleculesFetcher`, `SequenceBasedMacromoleculeSamplesFetcher` → `sequence_based_macromolecules*`, `sequence_based_macromolecule_samples*` |
| ❌ | **Chemical inventory / safety data** (SDS fetch, extract, manual upload) | `ChemicalFetcher` → `chemicals*`; `InventoryFetcher` → `inventory*` |

## 2. Working with elements (all types)

| Status | Feature | UI fetcher → endpoints | Notes |
|---|---|---|---|
| ✅ | **Delete elements** | `UIFetcher` → `DELETE ui_state` | Done in M0.4: `element.delete()`, `collection.delete_elements(...)`. |
| ✅ | **Version history and revert** | `VersionsFetcher` → `versions`, `versions/revert` | Done in M1.5: `element.versions()`, `Version.revert()`, `VersionChange.revert()`. |
| ✅ | **Comments** on elements and sections | `CommentFetcher` → `comments` | Done in M1.3: `element.comments()`, `element.add_comment()`, `Comment.update/resolve/delete`. Not on generic elements (the server doesn't allow it). |
| ✅ | **Private notes** | `PrivateNoteFetcher` → `private_notes` | Done in M1.4: `element.private_note()`, `set_private_note()`, `delete_private_note()`. |
| ✅ | **User labels** | `UserLabelsFetcher` → `user_labels/bulk`, `user_labels/save_label` | Done in M1.6: `instance.save_user_label()`, `collection.update_user_labels()`, and `properties['user_labels']` on wellplates, research plans and screens too. (Saving labels was missing as well, not only bulk assignment as listed here before.) |
| ✅ | **Find by short label** | `SamplesFetcher`, `ReactionsFetcher` → `*/findByShortLabel` | Done in M1.2: `instance.find_sample_by_short_label()`, `find_reaction_by_short_label()`. |
| ❌ | **Print codes / barcodes / QR, code logs** | `CodeLogsFetcher` → `code_logs/generic`; `PrintCodeFetcher` | |
| ❌ | **Element explorer** (relation graph) | `ExplorerFetcher` → `explorer` | |

## 3. Samples and molecules

| Status | Feature | UI fetcher → endpoints | Notes |
|---|---|---|---|
| ◐ | **Molecules** | `MoleculesFetcher` → `molecules/{editor,names,save_name,delete_name,cas,svg,sf,inchikey,compute,molecular_weight,decouple}` | M2.1 added molfile input (`create_molecule_by_molfile`, `collection.new_sample_molfile`), InChIKey lookup, CAS, names (list and add), SVG render and download, and molecular weight. Still missing: the molecule-editor routes (`editor`, `save_name`, `delete_name`, which need that ELN right), `compute`, and SciFinder (`sf`, M7.7). |
| ✅ | **Split / subsamples** | `SamplesFetcher` → `samples/subsamples` | Done in M2.2: `collection.split_samples(*samples)` creates linked subsamples on the server. `Sample.split()` is the local split reactions and wellplates use; saved on its own it is an unlinked copy. |
| ✅ | **Mixtures** | `ComponentsFetcher` → `components` | Done in M2.3: `sample.components()`, `sample.save_components()`, `Component.new()`. |
| ✅ | **Import samples from a spreadsheet / SDF** | `SamplesFetcher` → `samples/import` | Done in M2.5: `collection.import_samples(path, as_chemicals=False)`, waiting for the background job's report. The UI's column-mapping step (sending validated rows as `data`) is not covered. |
| ❌ | **Batch-refresh sample SVGs** | `SamplesFetcher` → `samples/batch-refresh-svg` | |
| ❌ | **CAS lookup** | `CasLookupFetcher` → `cas_lookup/lookup` | |
| ❌ | **Sample tasks** (e.g. weighing tasks from devices) | `SampleTasksFetcher` → `sample_tasks` | |

## 4. Reactions, wellplates, research plans

| Status | Feature | UI fetcher → endpoints | Notes |
|---|---|---|---|
| ✅ | **Literature / references** | `LiteraturesFetcher` → `literatures`, `literatures/collection`, `literatures/doi/metadata` | Done in M2.6: `element.references()`, `add_reference()`, `remove_reference()`, `set_reference_type()`, `collection.references()`, `instance.doi_metadata()`. |
| ❌ | **Reaction SVG rendering** | `ReactionSvgFetcher` → `reaction_svg` | The client loads stored images only. |
| ◐ | **Wellplates** | `WellplatesFetcher` → `wellplates/import_spreadsheet`, `wellplates/bulk`, `wellplates/subwellplates`, `wellplates/by_generic_element` | Create, edit and resize are implemented. Missing: spreadsheet import, bulk create, sub-wellplates, links to generic elements. |
| ◐ | **Research plans** | `ResearchPlansFetcher` → `research_plans/linked`, `research_plans/table_schemas`, `research_plans/svg`; `research_plan_metadata` | Body editing (text, richtext, table, image) is implemented. Missing: linked elements, saved table schemas, SVG render, research-plan metadata (DataCite). |

## 5. Analyses, attachments and spectra

| Status | Feature | UI fetcher → endpoints | Notes |
|---|---|---|---|
| ◐ | **Attachments** | `AttachmentFetcher` → `attachments/{bulk_delete,thumbnail(s),image,infer,link,files,upload_dataset_attachments}` | Upload (also chunked), download, zip and dataset xlsx export are implemented. Missing: bulk delete, thumbnails, image endpoint, infer, link, dataset-level upload. |
| ❌ | **Image annotation** | `AnnotationsFetcher` → annotation routes under `attachments/` | |
| ❌ | **Spectra (ChemSpectra / NMRium)**: view, save, regenerate, combine, convert | `AttachmentFetcher` → `attachments/{save_spectrum,regenerate_spectrum,regenerate_edited_spectrum,lcms_page}`, `chemspectra/file/{convert,combine_spectra}`; `ChemSpectraFetcher` → `chemspectra/spectra_layouts` | |
| ❌ | **Containers API** (move or edit analysis containers directly) | `ContainerFetcher` → `containers`, `containers/container` | Analyses are edited only as part of saving their element. |
| ❌ | **Measurements** (bulk create from raw data) | `MeasurementsFetcher` → `measurements*` | |
| ❌ | **NMR simulation** | `NmrSimFetcher` → `simulation/nmrdb` | |
| ❌ | **Predictions / compute tasks** | `PredictionsFetcher` → `prediction`; `ComputeTaskFetcher` → `compute_tasks*` | |
| ◐ | **Inbox** | `InboxFetcher` → `inbox/samples`, `inbox/reactions`, `inbox/unlinked_attachments` | Listing and uploading are implemented. Moving inbox items onto samples or reactions, and unlinked attachments, are missing. |

## 6. Collections and sharing

| Status | Feature | UI fetcher → endpoints | Notes |
|---|---|---|---|
| ❌ | **Collection export / import** (ZIP) | `CollectionsFetcher` → `collections/export`, `collections/import` | |
| ❌ | **Collection metadata** (DataCite) | `MetadataFetcher` → `collections/metadata` | |
| ❌ | **Take ownership** of a shared collection | `CollectionSharesFetcher` → `collection_shares/take_ownership` | Sharing, unsharing, updating shares and listing collections shared with you are implemented. |

## 7. Reports and output

| Status | Feature | UI fetcher → endpoints |
|---|---|---|
| ❌ | **Reports** (docx / Excel export, archives) | `ReportsFetcher` → `reports*`, `archives*`; `UIFetcher` → `ui_state/load_report` |
| ❌ | **Report templates** | `ReportTemplateFetcher` → `report_templates` |
| ❌ | **Text templates** (predefined and personal snippets) | `TextTemplatesFetcher` → `text_templates/*` |
| ❌ | **Data publication / transmission to a repository** | `GateFetcher` → `gate/transmitting` |

## 8. Search

| Status | Feature | UI fetcher → endpoints | Notes |
|---|---|---|---|
| ◐ | **Search** | `SearchFetcher` → `search` | M2.4 added structure search (`instance.search_structure()`: substructure and similarity, results for every element type) and fixed advanced search, which raised `TypeError` on every call. Still missing: advanced (field) search for element types other than samples and reactions, and the UI's generic-element search. |
| ❌ | **Autocomplete suggestions** | `SuggestionsFetcher` → `suggestions` | |

## 9. LabIMotion (generic elements, segments, datasets)

| Status | Feature | UI fetcher → endpoints | Notes |
|---|---|---|---|
| ◐ | **Klass management** | `GenericBaseFetcher` → `generic_elements/delete_klass`, `generic_elements/delete_klass_revision` | Create, update, (de)activate, release, upload and revisions are implemented. Deleting a klass or a revision is missing. |
| ❌ | **LabIMotion Hub** (fetch / create klasses from the template repository) | `generic_*/fetch_repo`, `*/create_repo_klass`, `segments/fetch_repo_generic_template*`; `UsersFetcher` → `labimotion_hub/element_klasses_name` |
| ❌ | **Download / export klasses and elements** | `GenericKlassFetcher` → `generic_klass/download_klass`; `segments/download_klass`, `generic_elements/export` |
| ❌ | **Split generic elements** | `GenericElsFetcher` → `generic_elements/split` |
| ❌ | **Generic element variations** | `ElementVariationFetcher` → `element_variations` |
| ❌ | **MTT assay requests** | `GenericElsFetcher` → `mtt/*` |
| ❌ | **OLS term import / ontology lists** (admin) | `AdminFetcher` → `admin/importOlsTerms`, `admin/olsEnableDisable`; `UsersFetcher` → `ols_terms/list` |

## 10. Users, account and administration

| Status | Feature | UI fetcher → endpoints | Notes |
|---|---|---|---|
| ❌ | **Profile and settings** (incl. editor and Ketcher options) | `ProfilesFetcher` → `profiles`, `profiles/editors/ketcher-options` | |
| ❌ | **Two-factor auth, API auth tokens, OmniAuth** | `UsersFetcher` → `users/two_factor`, `users/auth_token`, `users/revoke_auth_token`, `users/omniauth_providers` | The client logs in with a password or a JWT. |
| ❌ | **Short-label counters** | `UsersFetcher` → `users/update_counter`, `users/reaction_short_label` | |
| ◐ | **Admin: users, groups, devices** | `AdminFetcher` → `admin/users/byname`, `admin/usersDefault`, `admin/users/restoreAccount`, `admin/group_device/delete_relation` | Listing and creating users, groups and devices, membership and device JWTs are implemented. Restore account, default settings and deleting group-device relations are missing. |
| ❌ | **Admin: device metadata, SFTP/local collectors** | `AdminDeviceFetcher` → `admin_devices*`; `AdminDeviceMetadataFetcher`; `admin/listLocalCollector/all` | |
| ❌ | **Admin: system** (disk usage, background jobs and restart, feature matrix, data types, support links) | `AdminFetcher` → `admin/disk`, `admin/jobs*`, `admin/matrix`; `ChemSpectraFetcher` → `admin/data_types`; `InfoSupportLinksFetcher` | |
| ❌ | **Instruments / device connections / noVNC** | `InstrumentsFetcher`; `DeviceFetcher` → `devices/current_connection`; `UsersFetcher` → `devices/novnc` | |
| ❌ | **SciFinder-n credentials** | `UsersFetcher` → `users/scifinder` | |

## 11. Interactive UI features (unlikely to be needed in a client)

These exist for the browser session, not for data access, and are listed only for completeness:
messages and notifications (`MessagesFetcher`), calendar (`CalendarEntryFetcher`), third-party app
launchers (`ThirdPartyAppFetcher`), editor sessions (`EditorFetcher`), UI initialisation and
per-type `ui_state` endpoints, permission status checks (`PermissionsFetcher`) and support links.

## Suggested priorities

1. **Element deletion**: a basic CRUD gap, and the client can't clean up after itself without it.
2. **Screens**: the one classic element type the client can't load at all.
3. **Structure search**, **molecule input from molfile**, and **sample splits with parent links**:
   core chemistry workflows.
4. **Collection export/import** and **reports**: bulk data out of the ELN.
5. **Cell lines, vessels, device descriptions, SBMM**: newer v4 element types. Each one is a new
   element class plus its schema.
