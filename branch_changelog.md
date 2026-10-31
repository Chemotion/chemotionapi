# Branch changelog — `expansion-improvement`

Developer-facing log of this branch (diverged from `main` at *"Version for Chemotion v211"*).
One entry per commit (or small group of related commits), newest first. Dates are commit dates.

Scope of the branch: modernize the client (uv/just, Python 3.14, Pydantic v2, typing),
add FAIR export (`chem-dcat-ap` mapping + RO-Crate 1.1 `.eln`), offline ingestion of
Chemotion export ZIPs, a `.eln` importer, and a self-contained seeded test environment.

---

## 2026-10-23 (later) — the rest of the port, the dependency bump, and the history rewrite

**Remaining version-3 element fixes ported.** `append_no_split` bound nothing — the sample arrived
with no reaction, role, position or amount and was saved that way. Products gained mol. Equivalents
stopped raising out of a getter on a missing reference amount, and `set_amount`'s bare `pass`
became a warning.

**One fix could not be taken.** version-3 recomputes equivalents inside
`_clean_properties_data`. The bug is real — save an amount change and the server stores it beside
the *previous* equivalents — but the fix mutates the in-memory model during serialisation, which
this branch deliberately forbids; `test_zero_yield_round_trips_to_product_equivalent` fails on it
and is right to. The design that satisfies both (write into the serialised payload, as `yield`
already does) is in `AI/DEFERRED.md` §2.6. Not attempted, because a wrong equivalent is
indistinguishable from a right one once stored.

**collections/elements, retargeted rather than ported.** Martin's feature calls
`/api/v1/collections/elements`; all three verbs are removed at v4. Shape adopted, transport
rewritten onto `collection_elements`, with the three v4 behaviours that matter: no move endpoint
(so a move is two requests and not atomic), DELETE answering **200 with `locked_sample_ids`** as a
non-success 2xx, and `checkedAll` never sent because the server applies it over the whole element
class rather than the collection.

**chem-dcat-ap 0.1.0rc3 → rc4.** Not cosmetic: every crate records it in `softwareRequirements`, so
it is the vocabulary version our metadata claims. Confirmed the mapping did not shift — same 91
nodes, **identical type multiset**, only the version string and counter numbering differ.

**History rewritten locally, not pushed.** `tests/data/test.sql` now carries the re-salted hashes
in every commit that contains it: 79 commits, 0 sharing a hash with `main`'s committed dump,
including the commit that introduces the file. The tree is byte-identical to the pre-rewrite tip.
Backups kept at `backup/pre-rewrite` and tag `backup/pre-rewrite-20261023`; stack rebuilt as
`local/pr5-v4-core`, `local/pr6-fair-export`, `local/pr7-offline-ingest`. Two corrections the plan
needed are recorded in `AI/DEFERRED.md` §0.6 — `97ca9c6` was not a no-op and had to be reworded
rather than dropped, and `35ea166` was pruned as empty, which loses a genuine step from the history
and must be said in the PR.

Verification: 465 offline tests, `just conformance` 16 PASS, TheELNFileFormat's own suite 18
passed / 27 subtests on the regenerated example, docs clean. The live suite remains **not**
evidence for any of the v4 work: it runs the rc image.

## 2026-10-23 — ELN v4.0.0 API parity, and the first ports from version-3

Our client was verified against `v4.0.0-rc-260818`; the released v4.0.0 moved 55 API files
(+1475/-835). The integration suite cannot see any of it — it runs the rc image, and no v4.0.0
image is published — so the whole delta was worked from **source at the tag**, with
`AI/check_api_drift.py` doing the comparing.

**Broken against the release, now fixed.** Both group calls. `POST /groups/create` is gone and
`PUT /groups/upd/:id` with it; group endpoints moved into a new `group_api.rb` with flat params
and REST sub-resources. We also gained what we never wrapped: `DELETE /groups/:id`, member
removal, and admin promote/demote.

**Silently broken, which is worse.** Assigning `width`/`height` to a wellplate and calling
`save()` has been a no-op on v4: the ordinary PUT no longer declares them, so Grape drops them.
Upstream did that deliberately. `Wellplate.resize()` wraps the dedicated route and surfaces the
422 that names wells still holding data, rather than clearing them to force the shrink through.

**A field that was not merely additive.** `concentration_mode` replaces `use_reaction_volume`, and
the boolean maps to only two of its three values — `combined` was unreachable from this client.
Also adopted `can_update` and `previewable` as read-only server hints, returning `None` for "the
server did not say", which is not `False`.

**Sharing** gained `include_new_subcollections`, which mints shares on sub-collections that were
not shared before — it grants access rather than adjusting it. Exposed through a new
`update_share()`, refused without `apply_to_subcollections` (the server would ignore it silently),
and logged when used. `share()` now also documents that v4 mails the recipients.

**Declined:** `GET /explorer` — feature-flagged off by default, bespoke shape, data already
reachable.

**Ported from Martin's version-3 (PR #6), reviewed against v3.1.2 first.** The review earns its
keep immediately: his `move/assign/remove elements` feature calls `/api/v1/collections/elements`,
all three verbs of which are **removed** at v4. Its shape is worth adopting; its transport must be
rewritten. Ported so far: solvent suggestions, the Mg SMILES guard, molecule attribute access and
the request-error classes — two of which needed adapting to our internals rather than copying, and
one of which turned up a bug of ours (`density` clobbered with `0.0`) sitting beside his fix.

**Security:** `tests/unit/test_seed_credentials.py` pins the seed's password hashes. The seed once
carried five hashes identical to a real instance dump, and the fix was written four branches above
the branch that introduced it, so everything in between shipped it. Nothing noticed because
nothing checked.

Verification: 443 offline tests (376 at the start of the day), `just conformance` 16 PASS, docs
clean. The live suite is **not** evidence here, for the reason in the first paragraph.

## 2026-10-23 — RO-Crate 1.2 / `.eln` 1.2+20260923

Prompted by reviewing TheELNFileFormat PR #168: the consortium moved to RO-Crate 1.2 and
`eln-spec/1.2+20260923`, rebuilt its checker (`tests/checks/`, `tests/run_checks.py`) and shipped a
migration guide. Verifying that PR showed **our own example failing their current checks**, so this
is a correction, not an upgrade for its own sake.

- `@context` is now generated rather than fixed. The old list declared only `sha256`; every
  chem-dcat-ap predicate used as a key stayed a bare IRI, which 1.2 rejects. `_declare_unmapped_terms`
  walks the finished document and emits an explicit definition per undefined key.
- **Prefixes alone were not enough, and finding that out needed both validator versions.**
  `roc-validator` 0.13.0 accepts a compact IRI whose prefix is declared; **0.11.3, which their CI
  pins, does not** — it requires the key itself to be in the `@context`. A fix verified only
  against 0.13.0 passed here and failed there. `just conformance` now runs both.
- RO-Crate 1.2 context vendored (2899 terms). Root `conformsTo` carries both profiles; both exist
  as `Profile` entities. `additionalType`/eln-spec-1.1 removed.
- `ro-crate-1.2_18.1`: an element with no attachments had no ZIP member, so its Dataset existed
  only in metadata. Directory entries are now written explicitly. This surfaced only on the
  two-collection fixture, whose shared sample carries no files — the single-collection fixture
  would not have caught it.
- `ro-crate-1.2_32.2/32.3`: `SoftwareApplication` MUST have `url` and `version`. Producer node
  gained a `url`; the source-ELN node drops to `CreativeWork` when the version is unknown, which
  keeps the "never invent what the source did not record" rule intact.
- Molecule `cas`/`names` → `identifier`/`alternateName`.

### Clearing the RECOMMENDED rules too

RO-Crate's RECOMMENDED rules do not fail the consortium's CI (it validates REQUIRED only), but
they are what make a crate readable by a person rather than merely valid. **128 issues → 2.**

- Every contextual entity now has a `name` and a schema.org `@type`. Names come from the data the
  chem-dcat-ap mapping already carries (`dct:title` → "Amount [mmol]", "Yield [%]"), not filler.
- Every IRI the crate references is now described. This needed two realisations: an entity's
  `@type` is an RDF reference (that was 15 of them), and so is an object-valued **predicate** such
  as `qudt:unit` (6 more). Counting only `{"@id": …}` objects found neither.
- Organizations carry `url` and a `ContactPoint`; Persons with an email get one too.
- Data entities carry a `description`.
- Nothing is stranded: anything otherwise unreferenced is added to the root's `mentions`.

**A latent bug surfaced while doing this.** The id-rewriting pass rebuilds every node as a *new
dict*, so `root_node`, `graph_nodes` and any other reference held across it point at discarded
copies — mutations through them vanish silently. The polish pass now re-resolves the root from the
live graph. Every other holder of those references is still exposed; see `AI/DEFERRED.md`.

**Two issues remain, both genuinely blocked:**

- `53.0` (root identifier SHOULD be a PropertyValue) **contradicts the consortium's own schema**,
  which requires `identifier` to be a string. Their migration guide says to ignore it.
- `66.1` (local Datasets SHOULD list contents via `hasPart`) fires on an element with no
  describable files. In the example that is a fixture artifact: `mini_export.json`'s attachment
  carries no bytes, so its File node is withdrawn and the element has nothing to list.

Verification: 376 offline tests; `just conformance` 16 PASS (4 checks × 2 fixtures × 2 validator
versions); TheELNFileFormat's own suite **18 passed, 27 subtests** with our regenerated example in
place, in *their* pinned environment; docs build clean.

## 2026-09-21 — Element↔collection membership: `isPartOf`, not a folder

The last crate-modelling defect on the "known defects" list, decided the multi-parent way.

`build_element_index` derived an element's crate path from the collection it was reached through
and kept one collection per `(kind, id)` key, so an element in collections A *and* B was visited
twice under the same key and the second traversal overwrote the first. `elem_to_col` — the field
that should have carried membership — was populated and read **nowhere**.

- `elem_to_col` → `elem_to_cols` (a list), and it is now actually consumed. Paths are set on first
  sight only; a repeat sighting neither re-`load()`s the element nor re-paths it, which also drops
  one fetch per extra membership.
- Collections became contextual `Collection` entities. This was decided empirically, not assumed:
  four crate shapes were probed against both gates, and contextual entities typed `Dataset` with a
  `#fragment` id fail two REQUIRED rules — `ro-crate-1.1_13.1` (a Dataset needs an inverse
  `hasPart`) and `ro-crate-1.1_15.1` (a Data Entity Directory URI must end with `/`). `Collection`
  and `CreativeWork` both pass; the vendored `ro-crate-context.jsonld` already maps all four terms,
  so no `@context` extension was needed.
- Collection fragments are derived from a stable token, never `id(col)` — `col.id or id(col)` was
  fine as a dict key but its fallback is a Python object address, and writing that into the crate
  would make two exports of identical data differ.
- The root's `hasPart` filter was deliberately **left alone**. Tightening it to path-shaped ids
  looked like the safe direction and is the dangerous one: the loose "any Dataset" filter is what
  satisfies 13.1 for every Dataset in the graph. Collections drop out of it on their own now that
  they are not Datasets. Verified against the generated crate first.
- Reader: `ElnCrate.collections`, `ElnCollection`, `ElnDataset.collections`. The round-trip test
  failed today for *two* reasons — the export dropped a membership and the reader could not report
  one either.
- The conformance gate was vacuous for exactly this change (a single-collection fixture makes every
  membership shape trivially consistent), so `just conformance` now also exports and validates a
  two-collection crate with a genuinely shared standalone sample.

Verification: 374 offline tests (12 new; 7 of them confirmed failing against the old code),
`just conformance` green on both fixtures, TheELNFileFormat suite 19 passed on the regenerated
example, docs build clean, live integration 77 passed / 4 skipped / 0 failed (unchanged from the
pre-change baseline).

**Multi-membership itself is offline-tested only.** The integration collections are disjoint, so
the live run exercises the single-membership path through `build_element_index` and nothing more.
It is one code path either way, but the live suite does not prove the multi-collection case.

## 2026-09-21 — The "known defects" list, mostly retired

Seven defects had been carried as *deliberately not fixed*. The label came from review passes whose
standing instruction was "record, don't fix"; that had expired, and five were a few lines each.

- Crate file `@id`s were keyed on Python object identity (`id(att)`), which held only while every
  accessor returned the same wrapper object. A miss fell through to recomputing the name **without**
  the collision-disambiguation suffix — an `@id` pointing at a ZIP entry that does not exist,
  latently reintroducing the very failure the suffix prevents. Now keyed on the record's own
  identifier, matching `_CrateFileNamer`.
- `_check_member_size` guarded itself with a bare `assert`, which `python -O` strips.
- The upload gate accepted only 200/201, so a legitimate `204 No Content` raised *after* a
  successful upload — and the retry uploaded everything again.
- A strict-mode export discarded that run's OLS lookups: `_ols_cache.save()` sat after the
  `try/finally` and a strict failure raised past it.
- `Connection(timeout=...)` makes the near-unbounded 500 s read timeout configurable.

Two remained, with reasons rather than silence: element↔collection key collisions (a crate-modelling
decision — duplicate per collection, or multi-parent `isPartOf`?) and `pytest-logging` (2015) as a
transitive runtime dependency of `linkml-runtime`, which is upstream's to fix. The first was decided
and fixed the same day; see the entry above.

## 2026-09-21 — Pre-release review: five rounds, and the seed we ship

Three independent agents re-reviewed the whole `main..HEAD` range (correctness/data loss,
untrusted input, API contract/docs). Findings fixed in `6f63cbf`, `dbf2294`, `4cf39ce`, `7509cee`,
`118eff1`; the credential audit in `97ca9c6`. Every fix carries a test confirmed to fail first.

- **Two missed twins of the iterate-then-save fix.** `save()` refreshed `json_data` without
  re-parsing it *and* set `_data_loaded = True`, so the accessor-level fix could never fire: a bare
  `for s in col.get_samples(): s.save()` wrote list-derived nulls over description, location,
  solvent and both amounts. The `name` setter reached the same path. Separately, a failed load left
  the element permanently marked "loaded", reproducing the same loss after one transient 500.
- **Archive guards that only covered one caller.** A nested `attachments/` decoy could shadow a
  real payload (and the swapped bytes then got a correct sha256, so the crate certified the swap);
  `iter_attachment` — the path `export_eln` actually uses — had no size or ratio cap;
  `ontology_patch` was a third, unguarded ZIP reader; `export.json` had no shallowest-wins
  tiebreak; the extracted-directory branch had no cap and `rglob` followed symlinks out of the crate.
- **Metadata that never reached the crate.** Four of the nine `_ELN_EXTRA_FIELDS` never resolved,
  so melting point, boiling point, role and `tlc_description` were absent from every export and
  `normalise_range_value` was dead code.
- **Duplicates and drops.** `MutableAttachments.save()` never cleared its queue (N saves = N
  uploads); export dropped attachments sharing an original filename; a retried save duplicated a
  new analysis; offline export dropped samples whose only reaction was in another collection.
- **Silence removed.** Six bare `except: pass` in `Sample.to_dcat_ap` exported samples with no
  quantity and no log line — which immediately surfaced a real one: offline samples had been
  losing their volume all along.
- **Packaging.** `README.md` carried a stray merge-conflict marker and would have rendered it on
  PyPI. Coverage was documented, configured and uninstallable; measured properly it is 62.6%.
  `Collection` was discarding eleven fields the server sends, including `shared`.
- **Credentials.** Audited on the rule that history stays as-is but nothing *we* add may be
  guilty. Clean, except that the shipped seed carried five bcrypt hashes byte-identical to a real
  instance's dump; all five re-salted, so the seed shares zero bytes with it. The credentials that
  remain in git history are rotated outside this repo by decision — the list is in
  `AI/DEFERRED.md` §1.

## 2026-09-18 → 2026-09-19 — Fix plan: nine slices

Worked by shared root cause rather than by file, because several findings were the same bug
written correctly once and wrongly elsewhere. Standing rule: the test must fail before the fix.

- `642ee67` **slices 1, 3, 4** — reading a shared collection returned *everything the caller owns*
  (4 samples became 193) because `sync_collection_id` does not exist in v4 and Grape ignored it;
  one cycle guard for four tree walkers, where a cycle had silently discarded every element with a
  success exit; one `safe_join` for six path sites, plus size and compression-ratio caps.
- `f35ab7b` **slice 2** — iterating a collection then saving destroyed the fields v4 gates behind
  `unless: :displayed_in_list`. Fixed at the `properties` accessor so iteration and indexing agree.
- `54d0595` **slice 7** — `RootCollection.save()` poisoned its own delete queue on any failure.
- `73cdfbd`, `7f8a68a` **slice 5** — ORCID and ROR are validated, including ISO 7064 MOD 11-2 and
  MOD 97-10 check digits, on the write path *and* the read path (which had been a substring test,
  so a foreign crate could launder an attacker-chosen URI into the next export).
- `2037075` **slice 6** — eight parsing sites that a routine Rails dump or a foreign crate could
  crash. Note `source_id`: the plan prescribed `isdecimal()`, but that and `\d` are Unicode-aware,
  so `"٩"` still parsed to a *wrong* id of 9; only `[0-9]+` closes it.
- `d7dc283` **slice 8** — wellplates are not all 12×8 (v4 allows 1..100). Two further bugs found in
  the same file: reading a wellplate **wrote to the server** (the parse path went through
  `Sample.split()`, which saves), and `wells` was eager, so a plate from a listing had an empty
  grid and saving wiped it.
- `7b72f8e`, `9f6cb38` **slice 9** — destructive-operation guards (`DROP DATABASE`, `restore()`,
  `.part` clobber), serialising no longer mutates the element, query strings use `params=`. Two
  owner decisions: the EBI ontology lookup stays on by default but is now documented prominently
  (it is independent of `disclose_host`), and `share()` **requires** `detail_level` — with
  `unshare()`/`get_shares()` added and the always-`None` attributes removed.

## 2026-09-15 → 2026-09-17 — FAIR export: say more, and say it honestly

- `9dc99f7`, `97cfb56` — crates carry the metadata they were dropping, and record which ELN
  produced them and at what version (`isBasedOn`), with `disclose_host=False` substituting
  `https://offline.chemotion.invalid` while still recording the version.
- `1152854` — `declare_skipped=True` states inside the crate what the export left out.
- `6e348ab`, `6c5a40d`, `f5eb7c9` — stop writing a `PropertyDict` memory address into the crate;
  stop describing content the crate does not have; three reviews' worth of data-loss fixes.
- `cab0228`, `71303be` — user labels are read and resolved (helpdesk #501526), and the documented
  `User.get_affiliations()` — which had always raised `AttributeError` — actually exists.
- `70e740b`, `268cd92`, `153bc24` — LabIMotion 2.3: the unit table was 25 of 65 types behind and
  raised on load; klasses the client does not fully understand now survive instead of failing.

## 2026-08-20 → 2026-08-25 — ELN v4 port and the 400.0.0 line

- `cc48022` — the client detects the server version from `/about` and **refuses anything but v4**,
  before credentials are sent.
- `324e71f`, `49f6ed6` — collection loading/saving and sharing ported: `roots.json` is gone, the
  tree is rebuilt from `ancestry`, `PATCH /collections` split into per-collection calls, the whole
  `/syncCollections` namespace removed, sharing moved to `/collection_shares` with renumbered
  permission levels.
- `8f591af`, `ff96cda`, `6f80483`, `a483edb` — exported crates are RO-Crate 1.1 conformant, gated
  in CI.
- `4fdfb66` — version scheme tracks the server: `400.x.y` ↔ ELN 4.0.
- `12778de`, `c216a1d`, `35ea166`, `7ca0d17`, `3de961c` — self-contained seeded integration stack,
  pinned by digest, with the generated DB dumps untracked.

## 2026-07-02 — Collection trees for native-ZIP import + producer marker

- `import_export_zip` now rebuilds the exported **collection tree** (bundles supported): one `OfflineCollection` per collection, elements scoped via the `CollectionsSample`/`CollectionsReaction` join tables; several top-level collections group under a synthetic root. Import only — writing the native format stays with the ELN GUI.
- Every exported crate embeds a producer marker: a `SoftwareApplication` node named `chemotion-api` (with version) referenced by the descriptor's `sdPublisher`. Grep: `"name": "chemotion-api"` in `ro-crate-metadata.json`.
- `import_eln` accepts only our own crates by default (foreign `.eln` import is deferred); `allow_foreign=True` opens them best-effort. `ElnCrate.producer` / `.is_chemotion_api` expose the marker.
- Fix: `_OfflineResponse` lacked `close()`, so archived attachment payloads were skipped during offline export.

## 2026-07-02 — `.eln` importer

- `Instance.import_eln(path)` / `chemotion_api.offline.import_eln` opens a `.eln` (ZIP or extracted crate dir) and exposes it as navigable objects: `ElnCrate` (root, datasets, files, authors, `read_file`) / `ElnDataset` (kind, files, sub-datasets) / `ElnFile` (`read()`/`extract()`).
- Zip-slip-safe payload access; metadata-only File nodes raise `FileNotFoundError` on `read()` instead of failing silently.
- ORCID/ROR authors round-trip back into `Author`/`AuthorAffiliation` objects.
- Round-trip tested against our own exporter output.

## 2026-07-01 — Gated coverage reporting and offline-suite expansion

- Coverage gate via `fail_under` in `pyproject.toml` (54% then; since raised to 55%); CI posts the coverage summary and uploads `coverage.xml` as an artifact.
- New unit tests: `tests/unit/test_pure_helpers.py` and `tests/unit/test_research_plan_body.py`.

## 2026-07-01 — GitHub Actions — offline gate and nightly integration

- New `.github/workflows/ci.yml`: ruff lint, mypy, offline test suite and docs build on pushes to main and PRs.
- New `.github/workflows/integration.yml`: nightly integration run against the seeded docker stack.

## 2026-06-30 — Docs: Sphinx site, user-facing README and CHANGELOG

- `docs/` site: Sphinx build with cross-references and autodoc for main entry points (theme: `sphinx_rtd_theme`).
- User-facing `README.md` and `CHANGELOG.md` (newest-first, dates, summaries).

## 2026-06-30 — Self-contained seeded integration environment

- `tests/test_config/compose.yml` boots a live ELN + Postgres on port 3579.
- Pre-seeded DB (`tests/data/test.sql`): API/ADM/MM users plus sample data.
- `conftest.py` runs `tests/data/setup_chemotion_db.sh` when `NO_SETUP=0`: boots the stack, resets the DB from the seed, waits for the `**SUCCESS**` marker.
- Replaces the old root `test_config/` (manual `.env`, no committed seed), which is deleted.

## 2026-06-02 — Migrate to uv + just, target Python 3.14

- `pyproject.toml`: uv-managed deps, Python ≥ 3.14.
- `justfile`: reproducible dev tasks (build, test, lint, coverage).
- Removed the `requirements.txt` files.

## 2026-06-01 — Remove build artifacts, generated dumps and stale configs

- Housekeeping: deleted `.gitlab-ci.yml`, `.readthedocs.yaml`, `.tool-versions`, `chemotionapi.iml`, `config.json.sample` and the `dist/` wheels.
