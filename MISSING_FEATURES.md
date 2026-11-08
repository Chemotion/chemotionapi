# Web UI features missing from chemotion_api

This lists what the Chemotion ELN web UI can do that this client cannot, or can only partly do.

**How it was made (2026-11-07).** The UI's own request layer, `app/javascript/src/fetchers/` (66
fetchers, ~250 endpoints), was taken from ELN `main` at `a8b47c7` (reports `v4.0.0`, labimotion
2.3.4) and compared against every `/api/v1/...` path `chemotion_api` calls, then the ambiguous
matches were checked in the client source. A feature counts as missing when the client calls none
of its endpoints; "partial" means the client covers some of it. It is an endpoint-level comparison:
a feature the UI computes in the browser without a request doesn't show up here.

Status: ❌ missing · ◐ partial · ✅ done since this list was made · — left out on purpose

## 1. Element types

The client loads and creates **samples, reactions, wellplates, research plans, screens and
LabIMotion generic elements**. `ElementSet._get_element_class` raises `TypeError` for anything else, so the
types below can be neither read nor written.

| Status | Feature | UI fetcher → endpoints |
|---|---|---|
| ✅ | **Screens** (wellplate containers, with research-plan links). Done in M1.1: `Screen`, `instance.get_screen()`, `collection.new_screen()` / `get_screens()` | `ScreensFetcher` → `screens` |
| ✅ | **Cell lines** (materials, samples, copy, split) | `CellLinesFetcher` → `cell_lines`, `cell_lines/material`, `cell_lines/copy`, `cell_lines/split`, `cell_lines/names/all` Done in M4.1: `CellLine` (sample and material fields in one `properties`), `collection.new_cell_line()` / `get_cell_lines()`, `instance.get_cell_line()` / `cell_line_materials()`, `copy()` / `split()`, analyses, moving between collections and deletion. |
| ✅ | **Vessels** (templates, instances, bulk create, name suggestions) | `VesselsFetcher` → `vessels`, `vessels/templates*`, `vessels/instances/create`, `vessels/bulk_create`, `vessels/suggest/suggest_name` Done in M4.2: `chemotion_api.vessels`; `instance.vessel_templates()` / `new_vessel_template()` / `get_vessel_template()` / `get_vessel()`, `collection.get_vessels()` / `new_vessel()` / `new_vessels(template, count)`, saving and deleting both. `vessels/suggest/suggest_name` does not exist on ELN main. |
| ✅ | **Device descriptions** (incl. sub-devices, ontologies, device analyses) | `DeviceDescriptionFetcher` → `device_descriptions*`; `attachments/device_description_analyses` Done in M4.3: `DeviceDescription` (all fields in `properties`), `collection.new_device_description()` / `get_device_descriptions()` / `split_device_descriptions()`, `instance.get_device_description()` / `device_ontologies()`, `download_analyses()`; analyses, segments, moving and deletion as for other elements. |
| ✅ | **Sequence-based macromolecules** and their samples | `SequenceBasedMacromoleculesFetcher`, `SequenceBasedMacromoleculeSamplesFetcher` → `sequence_based_macromolecules*`, `sequence_based_macromolecule_samples*` Done in M4.4: `SbmmSample` with its `macromolecule` dict (saved along with the sample), `use_uniprot(accession)`, `collection.new_sbmm_sample()` / `get_sbmm_samples()` / `split_sbmm_samples()`, `instance.get_sbmm_sample()` / `search_macromolecules()` / `get_macromolecule()`, `request_change()`; a macromolecule used elsewhere raises `SbmmUpdateNotAllowed`. |
| ✅ | **Chemical inventory / safety data** (SDS fetch, extract, manual upload) | `ChemicalFetcher` → `chemicals*`; `InventoryFetcher` → `inventory*` Done in M4.5: `chemotion_api.chemicals`; `sample.chemical()` / `save_chemical()` (also SBMM samples), `attach_safety_sheet()` (manual upload) and `save_vendor_safety_sheet()`, `instance.find_safety_sheets()` / `download_safety_sheet()` / `extract_safety_sheet()`, inventory labels via `instance.set_inventory_label()` / `inventory_collections()` and `collection.inventory_label()`. Vendor lookups need the server's internet access and are not integration-tested. |

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
| — | **Batch-refresh sample SVGs** | `SamplesFetcher` → `samples/batch-refresh-svg` | Left out on purpose (M2.7): a repair step of the UI's reaction editor that writes a rendered SVG into the server's `public/images/samples` under a file name the caller chooses. |
| ✅ | **CAS lookup** | `CasLookupFetcher` → `cas_lookup/lookup` | Done in M2.7: `instance.molecule().lookup_cas()`. |
| ✅ | **Sample tasks** (e.g. weighing tasks from devices) | `SampleTasksFetcher` → `sample_tasks` | Done in M5.5: `instance.sample_tasks(status)` / `create_sample_task()`, `task.update()` / `add_scan_result()` / `delete()`. The stack runs with `weighing_tasks` off, so the flow is unit-tested and the integration test checks the "not enabled" error. |

## 4. Reactions, wellplates, research plans

| Status | Feature | UI fetcher → endpoints | Notes |
|---|---|---|---|
| ✅ | **Literature / references** | `LiteraturesFetcher` → `literatures`, `literatures/collection`, `literatures/doi/metadata` | Done in M2.6: `element.references()`, `add_reference()`, `remove_reference()`, `set_reference_type()`, `collection.references()`, `instance.doi_metadata()`. |
| ✅ | **Reaction SVG rendering** | `ReactionSvgFetcher` → `reaction_svg` | Done in M2.7: `reaction.render_scheme_svg()`, plus `sample.svg_path`. |
| ✅ | **Wellplates** | `WellplatesFetcher` → `wellplates/import_spreadsheet`, `wellplates/bulk`, `wellplates/subwellplates`, `wellplates/by_generic_element` | Done in M3.7: `wellplate.download_template()` / `import_spreadsheet(path)`, `collection.create_wellplates(*names)`, `collection.split_wellplates(*plates)`. `by_generic_element` does not exist on ELN main. |
| ✅ | **Research plans** | `ResearchPlansFetcher` → `research_plans/linked`, `research_plans/table_schemas`, `research_plans/svg`; `research_plan_metadata` | Done in M3.6 (`plan.metadata()` / `save_metadata(**fields)`) and M3.7 (`sample.linked_research_plans()`, `instance.research_plan_table_schemas()` / `save_…` / `delete_…`, `plan.upload_svg()`). |

## 5. Analyses, attachments and spectra

| Status | Feature | UI fetcher → endpoints | Notes |
|---|---|---|---|
| ✅ | **Attachments** | `AttachmentFetcher` → `attachments/{bulk_delete,thumbnail(s),image,infer,link,files,upload_dataset_attachments}` | Done in M3.4: `attachment.load_image()`, `load_thumbnail()`, `delete()`, `unlink()`, and `delete_attachments()`, `load_thumbnails()`, `load_files()` for several at once. `infer` moves to M5.1 (spectra); `upload_dataset_attachments` is left out on purpose (marked unused and due for removal server-side). |
| ✅ | **Image annotation** | `AnnotationsFetcher` → annotation routes under `attachments/` | Done in M5.3: `attachment.load_annotation()` / `save_annotation(svg)`; the server sanitises the SVG and renders the annotated image. |
| ✅ | **Spectra (ChemSpectra / NMRium)**: view, save, regenerate, combine, convert | `AttachmentFetcher` → `attachments/{save_spectrum,regenerate_spectrum,regenerate_edited_spectrum,lcms_page}`, `chemspectra/file/{convert,combine_spectra}`; `ChemSpectraFetcher` → `chemspectra/spectra_layouts` | Done in M5.1: `instance.spectra()` → `save()`, `infer()`, `regenerate()`, `regenerate_edited()`, `lcms_page()`, `convert()`, `combine()`, `layouts()`, `nmrium_url()` (also `chemotion_api.spectra` functions). The stack runs no ChemSpectra service, so only the routes that need none are integration-tested; the rest are unit-tested. Viewing (the browser editor) is out of scope. |
| ✅ | **Containers API** (move or edit analysis containers directly) | `ContainerFetcher` → `containers`, `containers/container` | Done in M3.5: `element.save_analyses()` and `element.delete_analysis(analysis)`, both through `containers/container`. `DELETE /containers/:id` and `PUT /containers/:id` refuse element owners on ELN main (a neighbouring route's inbox check guards them too), so they are not used; the inbox `PATCH` is for device inbox boxes and left out. |
| ✅ | **Measurements** (bulk create from raw data) | `MeasurementsFetcher` → `measurements*` | Done in M5.2: `source.create_measurements(rows)` (e.g. from a research plan; `MeasurementError` lists refused rows), `sample.measurements(hierarchy, source)`, `Measurement.delete()`. |
| ✅ | **NMR simulation** | `NmrSimFetcher` → `simulation/nmrdb` | Done in M5.4: `instance.simulate_nmr(molecule)` (the server asks nmrdb.org; unit-tested only). |
| ✅ | **Predictions / compute tasks** | `PredictionsFetcher` → `prediction`; `ComputeTaskFetcher` → `compute_tasks*` | Done in M5.4: `instance.predict_products()` / `predict_reactants()`, `instance.compute_tasks()` with `check()` / `revoke()` / `delete()`, `instance.submit_compute_task(sample)` (`molecules/compute`). The prediction routes fail with a 500 on ELN main (`return` in a Grape `before` block raises `LocalJumpError`). |
| ✅ | **Inbox** | `InboxFetcher` → `inbox/samples`, `inbox/reactions`, `inbox/unlinked_attachments` | Done in M3.3: `inbox.assign(attachment, sample_or_reaction, variation=None)`, `inbox.search_samples()` / `search_reactions()`, `inbox.unlinked_attachments()`; listing and uploading were already there. |

## 6. Collections and sharing

| Status | Feature | UI fetcher → endpoints | Notes |
|---|---|---|---|
| ✅ | **Collection export / import** (ZIP) | `CollectionsFetcher` → `collections/export`, `collections/import` | Done in M3.1: `collection.export(path)`, `root.export_collections(*cols, file_path=...)` (waits for the job's notification, downloads the archive) and `root.import_collections(path)` (returns the new top-level collections). |
| ✅ | **Collection metadata** (DataCite) | `MetadataFetcher` → `collections/metadata` | Done in M3.6: `collection.metadata()` / `save_metadata(dict)`. |
| ✅ | **Take ownership** of a shared collection | `CollectionSharesFetcher` → `collection_shares/take_ownership` | Done in M3.6: `shared_collection.take_ownership()`, after the owner shares it at `CollectionSharePermission.PassOwnership`. |

## 7. Reports and output

| Status | Feature | UI fetcher → endpoints |
|---|---|---|
| ✅ | **Reports** (docx / Excel export, archives) | `ReportsFetcher` → `reports*`, `archives*`; `UIFetcher` → `ui_state/load_report` — Done in M3.2: `instance.create_report()` (waits for the job) and `report_archives()` with `Archive.download()` / `delete()`; `collection.export_elements()` (XLSX/SDF) and `export_reaction_smiles()`; `reaction.report_docx()`, `reaction.export_samples_excel()` and `wellplate.export_samples_excel()`. Not covered: the spectrum report's choice of product attachments (`prdAtts`). `ui_state/load_report` does not exist on ELN main. |
| ◐ | **Report templates** | `ReportTemplateFetcher` → `report_templates` — Done in M3.2: listing (`instance.report_templates()`). Editing templates is admin-only and not covered. |
| ✅ | **Text templates** (predefined and personal snippets) | `TextTemplatesFetcher` → `text_templates/*` — Done in M3.8: `instance.text_templates()` reads predefined templates, edits personal ones and your per-type editor toolbars; admins and global editors can create, update and delete predefined ones. `TextTemplate.ops` is a Quill delta to append to rich-text fields. |
| ✅ | **Data publication / transmission to a repository** | `GateFetcher` → `gate/transmitting` — Done in M3.9: `collection.register_gate(destination, token)`, `check_transmission(target)`, `transmit(target)` (waits for the *Gate Transfer Completed* notification) and, on the receiving side, `collection.gate_token(origin)`. `target` has no default because the server's default is the public Chemotion Repository. Only the check is integration-tested: the transfer posts to `gate/received` / `gate/receiving_chunk`, which only a Chemotion Repository has, so the stack's ELN cannot receive it. |

## 8. Search

| Status | Feature | UI fetcher → endpoints | Notes |
|---|---|---|---|
| ◐ | **Search** | `SearchFetcher` → `search` | M2.4 added structure search (`instance.search_structure()`: substructure and similarity, results for every element type) and fixed advanced search, which raised `TypeError` on every call. Still missing: advanced (field) search for element types other than samples and reactions, and the UI's generic-element search. |
| ✅ | **Autocomplete suggestions** | `SuggestionsFetcher` → `suggestions` | Done in M2.7: `instance.suggestions()`. |

## 9. LabIMotion (generic elements, segments, datasets)

| Status | Feature | UI fetcher → endpoints | Notes |
|---|---|---|---|
| ✅ | **Klass management** | `GenericBaseFetcher` → `generic_elements/delete_klass`, `generic_elements/delete_klass_revision` | Done in M6.1: `klass.delete(confirm=<label>)`, `klass.revisions()` and `klass.delete_revision()` (the active one is refused), for element, segment and dataset templates. Create, update, (de)activate, release and upload were already there. |
| ✅ | **LabIMotion Hub** (fetch / create klasses from the template repository) | `generic_*/fetch_repo`, `*/create_repo_klass`, `segments/fetch_repo_generic_template*`; `UsersFetcher` → `labimotion_hub/element_klasses_name` Done in M6.3: `generic_manager.hub_templates(kind)`, `import_hub_template(identifier, kind)`, `submit_to_hub(...)`, and for this ELN as a hub `published_templates()` / `active_element_names()`. `segments/fetch_repo_generic_template*` are older variants of the same lookup. |
| ✅ | **Download / export klasses and elements** | `GenericKlassFetcher` → `generic_klass/download_klass`; `segments/download_klass`, `generic_elements/export` Done in M6.2: `klass.download(path)` (template JSON, re-uploadable with `upload()`), `generic_element.export_docx(path)`. `segments/download_klass` is the older route for the same file. |
| ✅ | **Split generic elements** | `GenericElsFetcher` → `generic_elements/split` — Done in M6.4: `collection.split_generic_elements(*elements)`. |
| ✅ | **Generic element variations** | `ElementVariationFetcher` → `element_variations` — Done in M6.4: `generic_element.variations()` / `save_variations()` / `export_variations()` / `import_variations()`, `variation_key(layer, field)`. |
| ✅ | **MTT assay requests** | `GenericElsFetcher` → `mtt/*` — Done in M6.5: `generic_element.create_mtt_request(*wellplates)` (returns the app link), `mtt_requests()`, `MttRequest.update()` / `revoke()` / `delete()`, `mtt.delete_outputs()` / `delete_output_result()`. The token routes the external app calls (`public/mtt_apps`) are for that app and left out. |
| ✅ | **OLS term import / ontology lists** (admin) | `AdminFetcher` → `admin/importOlsTerms`, `admin/olsEnableDisable`; `UsersFetcher` → `ols_terms/list` — Done in M6.6: `instance.ols_terms(name, edited)`; admins: `import_ols_terms(owl_file)` and `set_ols_terms_enabled(owl_name, enable, disable)`, which refuses when no terms are imported (the server would otherwise overwrite the built-in term lists with empty ones). |

## 10. Users, account and administration

| Status | Feature | UI fetcher → endpoints | Notes |
|---|---|---|---|
| ✅ | **Profile and settings** (incl. editor and Ketcher options) | `ProfilesFetcher` → `profiles`, `profiles/editors/ketcher-options` | Done in M7.1: `instance.profile()` with `save()`, `add_structure_template()` / `delete_structure_template()` (only for templates the profile lists: the server route deletes any path it is given), `instance.ketcher_options()` / `save_ketcher_options()`. |
| ✅ | **Two-factor auth, API auth tokens, OmniAuth** | `UsersFetcher` → `users/two_factor`, `users/auth_token`, `users/revoke_auth_token`, `users/omniauth_providers` | Done in M7.2: `instance.two_factor_enabled()` / `request_two_factor_change()` (the ELN emails a confirmation link), `api_tokens()`, `create_api_token(otp, name, expires_in_days)`, `revoke_api_token(token, otp)`; log in with a token through `login_token()`. A login with a 2FA code has no API route: `public/token` issues a JWT on the password alone, also for 2FA accounts. OmniAuth is a browser flow and left out. |
| ✅ | **Short-label counters** | `UsersFetcher` → `users/update_counter`, `users/reaction_short_label` | Done in M7.3: `instance.set_short_label_counter(type, value)`, `set_reaction_short_label(prefix, count)`. |
| ✅ | **Admin: users, groups, devices** | `AdminFetcher` → `admin/users/byname`, `admin/usersDefault`, `admin/users/restoreAccount`, `admin/group_device/delete_relation` | Done in M7.4 (on `Admin`): `find_users()`, `default_allocated_space()` / `set_default_allocated_space()`, `update_user()`, `delete_user(user, confirm=<abbreviation>)`, `restore_user()`, `reset_password()`, `two_factor_enable_link()` / `disable_two_factor()`, `set_user_rights()`, `remove_users_from_group()` / `remove_devices_from()` / `set_group_admin()` / `delete_group(confirm=...)`. Listing and creating were already there. |
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
